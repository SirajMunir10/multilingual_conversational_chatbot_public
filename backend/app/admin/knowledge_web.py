"""Web pages in the knowledge base (PRD FR-18, FR-24): approved sites only, refreshed weekly and on request.

Every address is checked before each request, including redirects: HTTPS only, a host on the approved list, and a
public IP address (never the server's own network). Pages are size- and time-limited and screened like uploads."""
import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from app.admin.knowledge import KnowledgeError, KnowledgeStore
from app.admin.knowledge_text import IngestError, page_entries
from app.admin.settings_store import SettingsStore
from app.db.database import Database

logger = logging.getLogger("xo.knowledge.web")

ALLOWED_KEY = "kb_allowed_domains"
DEFAULT_ALLOWED = ["xoto.ae"]
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
REFRESH_AFTER = timedelta(days=7)
_SYSTEM = {"email": "system", "role": "admin"}


async def allowed_domains() -> List[str]:
    return list(await SettingsStore.get(ALLOWED_KEY, DEFAULT_ALLOWED) or [])


def clean_domain(value: str) -> Optional[str]:
    """'https://www.xoto.ae/x' or 'XOTO.ae' → 'xoto.ae'; None when it is not a plain public domain name."""
    value = (value or "").strip().lower()
    host = urlsplit(value if "//" in value else f"//{value}").hostname or ""
    host = host[4:] if host.startswith("www.") else host
    try:
        ipaddress.ip_address(host)
        return None  # addresses are not allowed, only names
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) < 2 or not all(l and len(l) <= 63 and all(c.isalnum() or c == "-" for c in l) for l in labels):
        return None
    return host


async def _public_address(host: str) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise IngestError("not_found", "This address could not be found.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise IngestError("not_public", "This address points to a private network and cannot be used.")


async def check_url(url: str) -> str:
    """The cleaned URL, or IngestError explaining why it cannot be fetched."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https":
        raise IngestError("https_only", "Use a full https:// address.")
    if parts.username or parts.password or (parts.port not in (None, 443)):
        raise IngestError("bad_address", "Addresses with a user name, password or port are not allowed.")
    host = (parts.hostname or "").lower()
    allowed = await allowed_domains()
    if not any(host == d or host.endswith(f".{d}") for d in allowed):
        raise IngestError("not_approved", f"{host or 'This site'} is not an approved website. Approved: {', '.join(allowed) or 'none'}.")
    await _public_address(host)
    return parts._replace(fragment="").geturl()


async def fetch(url: str) -> str:
    """The page's HTML. Redirects are followed by hand so every hop is checked again."""
    async with httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(10.0),
                                 headers={"User-Agent": "XO-knowledge-bot/1.0 (+https://xoto.ae)"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            url = await check_url(url)
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        url = urljoin(url, response.headers["location"])
                        continue
                    stream = response.extensions.get("network_stream")
                    peer = stream.get_extra_info("server_addr") if stream else None
                    if peer and not ipaddress.ip_address(peer[0]).is_global:  # DNS changed between the check and the request
                        raise IngestError("not_public", "This address points to a private network and cannot be used.")
                    if response.status_code != 200:
                        raise IngestError("http_error", f"The site answered {response.status_code}.")
                    kind = response.headers.get("content-type", "").lower()
                    if "html" not in kind and "text/plain" not in kind:
                        raise IngestError("not_html", "This address is not a web page. Upload files on the Upload tab.")
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_PAGE_BYTES:
                            raise IngestError("too_large", "This page is larger than 2 MB.")
                    return body.decode(response.encoding or "utf-8", errors="replace")
            except httpx.HTTPError:
                raise IngestError("unreachable", "The site could not be reached. Try again later.")
    raise IngestError("redirects", "This address redirects too many times.")


def _iso(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k in ("added_at", "last_fetched_at"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].isoformat()
    if isinstance(out.get("article_ids"), str):
        out["article_ids"] = json.loads(out["article_ids"])
    return out


class WebSources:
    _memory: Dict[int, Dict[str, Any]] = {}
    _next_id = 1

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory, cls._next_id = {}, 1

    @classmethod
    async def list(cls) -> List[Dict[str, Any]]:
        if Database.pool:
            return [_iso(dict(r)) for r in await Database.pool.fetch("SELECT * FROM kb_sources ORDER BY id")]
        return [_iso(r) for r in cls._memory.values()]

    @classmethod
    async def get(cls, source_id: int) -> Dict[str, Any]:
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM kb_sources WHERE id = $1", source_id)
            row = dict(row) if row else None
        else:
            row = cls._memory.get(source_id)
        if not row:
            raise KnowledgeError("not_found")
        return _iso(row)

    @classmethod
    async def _update(cls, source_id: int, **fields: Any) -> None:
        if Database.pool:
            if "article_ids" in fields:
                fields["article_ids"] = json.dumps(fields["article_ids"])
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
            await Database.pool.execute(f"UPDATE kb_sources SET {sets} WHERE id = $1", source_id, *fields.values())
        else:
            cls._memory[source_id].update(fields)

    @classmethod
    async def add(cls, url: str, actor: Dict[str, Any]) -> Dict[str, Any]:
        url = await check_url(url)
        if any(s["url"] == url for s in await cls.list()):
            raise IngestError("duplicate", "This page is already in the knowledge base.")
        page = page_entries(await fetch(url), url)  # fetch before saving, so a bad page leaves nothing behind
        if Database.pool:
            row = await Database.pool.fetchrow("INSERT INTO kb_sources (url, title, added_by) VALUES ($1, $2, $3) RETURNING id",
                                               url, page["title"], actor["email"])
            source_id = row["id"]
        else:
            source_id, cls._next_id = cls._next_id, cls._next_id + 1
            cls._memory[source_id] = {"id": source_id, "url": url, "title": page["title"], "added_by": actor["email"],
                                      "added_at": datetime.now(timezone.utc), "last_fetched_at": None, "last_status": "new",
                                      "last_error": "", "content_hash": "", "article_ids": []}
        try:
            await cls._apply(source_id, page, actor, f"Added from {url}")
        except KnowledgeError:
            await cls._delete_row(source_id)
            raise
        return {**await cls.get(source_id), "removed": page["removed"]}

    @classmethod
    async def _apply(cls, source_id: int, page: Dict[str, Any], actor: Dict[str, Any], note: str) -> None:
        digest = hashlib.sha256(json.dumps(page["entries"], sort_keys=True).encode()).hexdigest()
        source = await cls.get(source_id)
        now = datetime.now(timezone.utc)
        if digest == source["content_hash"]:
            await cls._update(source_id, last_fetched_at=now, last_status="unchanged", last_error="")
            return
        ids = [f"web_{source_id}_{i + 1}" for i in range(len(page["entries"]))]
        current = await KnowledgeStore.entries()
        changes = [(article_id, {**entry, "tags": (current.get(article_id, {}).get("data", {}).get("tags") or ["web"])}, None)
                   for article_id, entry in zip(ids, page["entries"])]
        await KnowledgeStore.save_many(changes, actor, note)
        for old in source["article_ids"]:
            if old not in ids and old in current and current[old]["data"]["status"] != "RETIRED":
                await KnowledgeStore.retire(old, actor, "No longer on the page")
        await cls._update(source_id, title=page["title"], last_fetched_at=now, last_status="updated", last_error="",
                          content_hash=digest, article_ids=ids)

    @classmethod
    async def refresh(cls, source_id: int, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        source = await cls.get(source_id)
        try:
            page = page_entries(await fetch(source["url"]), source["url"])
            await cls._apply(source_id, page, actor or _SYSTEM, "Refreshed from the website")
        except (IngestError, KnowledgeError) as exc:
            message = exc.message if isinstance(exc, IngestError) else "; ".join(exc.errors) or exc.code
            # The last good version stays live; the page shows the problem.
            await cls._update(source_id, last_fetched_at=datetime.now(timezone.utc), last_status="failed", last_error=message[:500])
        return await cls.get(source_id)

    @classmethod
    async def refresh_due(cls) -> int:
        due = [s for s in await cls.list()
               if not s["last_fetched_at"] or datetime.fromisoformat(s["last_fetched_at"]) < datetime.now(timezone.utc) - REFRESH_AFTER]
        for source in due:
            await cls.refresh(source["id"])
        return len(due)

    @classmethod
    async def _delete_row(cls, source_id: int) -> None:
        if Database.pool:
            await Database.pool.execute("DELETE FROM kb_sources WHERE id = $1", source_id)
        else:
            cls._memory.pop(source_id, None)

    @classmethod
    async def remove(cls, source_id: int, actor: Dict[str, Any]) -> Dict[str, Any]:
        source = await cls.get(source_id)
        current = await KnowledgeStore.entries()
        for article_id in source["article_ids"]:
            if article_id in current and current[article_id]["data"]["status"] != "RETIRED":
                await KnowledgeStore.retire(article_id, actor, f"Web page removed: {source['url']}")
        await cls._delete_row(source_id)
        return source
