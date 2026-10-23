"""Knowledge base management (PRD FR-24): articles and glossary terms, versions and rollback, and the live index.

The built-in knowledge base (xobia_kb_master.json with its precomputed embeddings in vector_store.json) is version 0
of each entry. Every edit, retirement or restore adds a version; the latest version of each entry is live. Publishing
re-embeds only when the searchable text changed, then swaps the in-memory index at once. Other instances pick the
change up within 30 seconds."""
import asyncio
import copy
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.admin.knowledge_text import find_injection
from app.core.config import settings
from app.core.usage_tracker import UsageTracker
from app.db.database import Database
from app.services.vector_store import VectorDatabase

logger = logging.getLogger("xo.knowledge")

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base")
TYPES = ("article", "glossary")
STATUSES = ("ACTIVE", "PARTIALLY_ACTIVE", "RETIRED")
REVIEW_EVERY_DAYS = 182
REFRESH_SECONDS = 30


class KnowledgeError(Exception):
    def __init__(self, code: str, errors: Optional[List[str]] = None):
        super().__init__(code)
        self.code, self.errors = code, errors or []


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:60] or "entry"


def _date(value: Any) -> Optional[str]:
    """ISO date from '23/03/2026', '2026-03-23' or a date; None when absent or unreadable."""
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def plus_days(iso: Optional[str], days: int) -> Optional[str]:
    return (datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d") if iso else None


def normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fills defaults and trims, so stored entries always have the same shape."""
    d = dict(data or {})
    clean = lambda v: " ".join(str(v or "").split())  # noqa: E731
    out = {
        "type": d.get("type") if d.get("type") in TYPES else "article",
        "title": clean(d.get("title")),
        "short_answer": str(d.get("short_answer") or "").strip(),
        "detail": str(d.get("detail") or "").strip(),
        "domain": clean(d.get("domain")) or ("Glossary" if d.get("type") == "glossary" else "General"),
        "status": d.get("status") if d.get("status") in STATUSES else "ACTIVE",
        "disclaimer_flag": "YES" if d.get("disclaimer_flag") in ("YES", True) else "NO",
        "tags": [clean(t)[:40] for t in (d.get("tags") or []) if clean(t)],
        "utterances": [clean(u) for u in (d.get("utterances") or []) if clean(u)],
        "follow_up_prompts": [clean(u) for u in (d.get("follow_up_prompts") or []) if clean(u)],
        "owner": clean(d.get("owner")) or "XOTO Knowledge Team",
        "last_reviewed": _date(d.get("last_reviewed")),
        "review_by": _date(d.get("review_by")),
        "source": d.get("source") if isinstance(d.get("source"), dict) else {"kind": "manual"},
    }
    out["intent_name"] = _slug(d.get("intent_name") or out["title"])
    out["scope"] = "EDUCATIONAL_ONLY" if out["status"] == "PARTIALLY_ACTIVE" else "FULL"
    if out["type"] == "glossary" and not out["detail"]:
        out["detail"] = out["short_answer"]
    return out


def validate(data: Dict[str, Any]) -> List[str]:
    errors = []
    if len(data["title"]) < 2 or len(data["title"]) > 200:
        errors.append("The title needs 2 to 200 characters.")
    if not data["short_answer"]:
        errors.append("Add a short answer.")
    elif len(data["short_answer"]) > 1500:
        errors.append("Keep the short answer under 1,500 characters; put the rest in the detail.")
    if len(data["detail"]) > 12000:
        errors.append("The detail is longer than 12,000 characters. Split it into several entries.")
    if len(data["tags"]) > 12:
        errors.append("Use at most 12 tags.")
    # Generous limits: some built-in entries hold long example lists, and editing them must not be blocked.
    if len(data["utterances"]) > 40 or any(len(u) > 1000 for u in data["utterances"]):
        errors.append("Use at most 40 example questions of up to 1,000 characters.")
    if len(data["follow_up_prompts"]) > 8:
        errors.append("Use at most 8 follow-up suggestions.")
    for field, label in (("title", "title"), ("short_answer", "short answer"), ("detail", "detail")):
        hit = find_injection(data[field])
        if hit:
            errors.append(f"The {label} contains “{hit}”, which reads like an instruction to the AI. Reword or remove it.")
    return errors


def embed_text(data: Dict[str, Any]) -> str:
    """The text that is embedded for search; the same layout as scripts/generate_vector_store.py."""
    if data["type"] == "glossary":
        return f"Term: {data['title']}\nDefinition: {data['short_answer']}\nDomain: UAE Real Estate & Mortgage Glossary"
    parts = [f"Title: {data['title']}", f"Domain: {data['domain']}", f"Topic: {data['intent_name'].replace('_', ' ')}",
             f"Summary: {data['short_answer']}", f"Detail: {data['detail']}"]
    if data["utterances"]:
        parts.append("Sample user questions: " + " | ".join(data["utterances"]))
    return "\n".join(parts)


def index_document(article_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """The document the retrieval service reads (same fields as the built-in vector store)."""
    return {"doc_id": article_id, "type": data["type"], "title": data["title"], "intent_name": data["intent_name"],
            "domain": data["domain"], "status": data["status"], "scope": data["scope"],
            "disclaimer_flag": data["disclaimer_flag"], "short_answer": data["short_answer"], "detail": data["detail"],
            "follow_up_prompts": data["follow_up_prompts"]}


@lru_cache(maxsize=1)
def _builtin() -> Dict[str, Dict[str, Any]]:
    """Version 0 of every built-in entry, with its precomputed embedding. Excluded articles stay out, as before."""
    with open(os.path.join(_DATA, "xobia_kb_master.json"), encoding="utf-8") as f:
        master = json.load(f)
    vectors: Dict[str, List[float]] = {}
    try:
        with open(VectorDatabase._get_store_path(), encoding="utf-8") as f:
            vectors = {d["doc_id"]: d["embedding"] for d in json.load(f).get("documents", []) if d.get("embedding")}
    except (OSError, ValueError) as exc:
        logger.error("Built-in embeddings unavailable: %s", exc)
    entries: Dict[str, Dict[str, Any]] = {}
    for a in master.get("articles", []):
        if a.get("status") == "EXCLUDED":
            continue
        reviewed = _date(a.get("last_reviewed"))
        tags = [t.strip() for t in re.split(r"[,;]", a.get("metadata_tags") or "") if t.strip()]
        data = normalize({**a, "type": "article", "tags": tags, "owner": a.get("content_owner"), "last_reviewed": reviewed,
                          "review_by": plus_days(reviewed, REVIEW_EVERY_DAYS), "source": {"kind": "builtin"}})
        data["intent_name"] = a.get("intent_name") or data["intent_name"]
        entries[f"art_{a['article_number']}"] = {"data": data}
    for g in master.get("glossary", []):
        data = normalize({"type": "glossary", "title": g.get("term"), "short_answer": g.get("definition"),
                          "detail": g.get("definition"), "domain": "Glossary", "status": g.get("status"),
                          "intent_name": g.get("intent_name"), "source": {"kind": "builtin"}})
        data["intent_name"] = g.get("intent_name") or data["intent_name"]
        entries[f"gloss_{g.get('intent_name', '')}"] = {"data": data}
    for article_id, entry in entries.items():
        entry.update(article_id=article_id, version=0, embedding=vectors.get(article_id), action="builtin",
                     note="Built-in knowledge base", published_by="XOTO", published_at=None)
    return entries


def _public(row: Dict[str, Any], with_embedding: bool = False) -> Dict[str, Any]:
    out = {k: v for k, v in row.items() if with_embedding or k != "embedding"}
    if isinstance(out.get("published_at"), datetime):
        out["published_at"] = out["published_at"].isoformat()
    return out


class KnowledgeStore:
    _memory: Dict[str, List[Dict[str, Any]]] = {}
    _signature: Any = None

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory = {}
        cls._signature = None

    # ---- Reading ----

    @classmethod
    async def _latest_rows(cls) -> Dict[str, Dict[str, Any]]:
        if Database.pool:
            rows = await Database.pool.fetch(
                "SELECT DISTINCT ON (article_id) * FROM kb_versions ORDER BY article_id, version DESC")
            return {r["article_id"]: cls._row(r) for r in rows}
        return {k: v[-1] for k, v in cls._memory.items() if v}

    @staticmethod
    def _row(r: Any) -> Dict[str, Any]:
        row = dict(r)
        for key in ("data", "embedding"):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        return row

    @classmethod
    async def entries(cls) -> Dict[str, Dict[str, Any]]:
        """Every entry at its latest version (retired ones included), keyed by id."""
        merged = {k: dict(v) for k, v in _builtin().items()}
        merged.update(await cls._latest_rows())
        return merged

    @classmethod
    async def get(cls, article_id: str) -> Dict[str, Any]:
        entry = (await cls.entries()).get(article_id)
        if not entry:
            raise KnowledgeError("not_found")
        return entry

    @classmethod
    async def versions(cls, article_id: str) -> List[Dict[str, Any]]:
        if Database.pool:
            rows = [cls._row(r) for r in await Database.pool.fetch(
                "SELECT article_id, version, data, action, note, published_by, published_at FROM kb_versions "
                "WHERE article_id = $1 ORDER BY version DESC", article_id)]
        else:
            rows = list(reversed(cls._memory.get(article_id, [])))
        if article_id in _builtin():
            rows.append(_builtin()[article_id])
        if not rows:
            raise KnowledgeError("not_found")
        return [_public(r) for r in rows]

    @classmethod
    async def version(cls, article_id: str, number: int) -> Dict[str, Any]:
        if number == 0 and article_id in _builtin():
            return _builtin()[article_id]
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM kb_versions WHERE article_id = $1 AND version = $2",
                                               article_id, number)
            row = cls._row(row) if row else None
        else:
            row = next((r for r in cls._memory.get(article_id, []) if r["version"] == number), None)
        if not row:
            raise KnowledgeError("version_not_found")
        return row

    @classmethod
    def due_for_review(cls, entry: Dict[str, Any], within_days: int = 30) -> bool:
        review_by = entry["data"].get("review_by")
        return bool(review_by and entry["data"]["status"] != "RETIRED"
                    and review_by <= (date.today() + timedelta(days=within_days)).isoformat())

    # ---- Writing ----

    @classmethod
    async def _embed(cls, texts: List[str]) -> List[List[float]]:
        """One embedding per text, in order. Tests replace this."""
        from app.llm.client import LLMService
        response = await LLMService.client().embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
        if getattr(response, "usage", None):
            UsageTracker.record_embedding(None, settings.EMBEDDING_MODEL, getattr(response.usage, "prompt_tokens", 0))
        return [list(item.embedding) for item in response.data]

    @classmethod
    async def save_many(cls, changes: List[Tuple[str, Dict[str, Any], Optional[int]]], actor: Dict[str, Any], note: str,
                        action: str = "published") -> List[Dict[str, Any]]:
        """Adds a version for each (id, data, base_version). All are checked first; nothing is saved if one fails."""
        note = " ".join((note or "").split())[:500]
        current = await cls.entries()
        prepared, problems = [], []
        for article_id, raw, base_version in changes:
            data = normalize(raw)
            errors = validate(data)
            if errors:
                problems.extend(f"{data['title'] or article_id}: {e}" if len(changes) > 1 else e for e in errors)
                continue
            existing = current.get(article_id)
            if base_version is not None and existing and existing["version"] != base_version:
                raise KnowledgeError("stale", [f"“{existing['data']['title']}” was changed by someone else. Reload it and redo your edit."])
            reuse = existing and existing.get("embedding") and embed_text(normalize(existing["data"])) == embed_text(data)
            prepared.append({"article_id": article_id, "data": data, "embedding": existing["embedding"] if reuse else None})
        if problems:
            raise KnowledgeError("invalid", problems)
        missing = [p for p in prepared if p["embedding"] is None and p["data"]["status"] != "RETIRED"]
        if missing:
            try:
                vectors = []
                for i in range(0, len(missing), 64):
                    vectors += await cls._embed([embed_text(p["data"]) for p in missing[i:i + 64]])
            except Exception as exc:  # the model provider is down or the key is wrong
                logger.error("Knowledge-base embedding failed: %s", exc)
                raise KnowledgeError("index_failed", ["XO could not index this text right now. Nothing was published; try again in a minute."])
            for p, vec in zip(missing, vectors):
                p["embedding"] = vec
        saved = [await cls._add_version(p["article_id"], p["data"], p["embedding"], action, note, actor["email"]) for p in prepared]
        await cls.rebuild_index()
        return saved

    @classmethod
    async def save(cls, article_id: str, data: Dict[str, Any], actor: Dict[str, Any], note: str,
                   base_version: Optional[int] = None, action: str = "published") -> Dict[str, Any]:
        return (await cls.save_many([(article_id, data, base_version)], actor, note, action))[0]

    @classmethod
    async def _add_version(cls, article_id: str, data: Dict[str, Any], embedding: Optional[List[float]], action: str,
                           note: str, author: str) -> Dict[str, Any]:
        if Database.pool:
            async with Database.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('kb:' || $1))", article_id)
                    latest = await conn.fetchval("SELECT MAX(version) FROM kb_versions WHERE article_id = $1", article_id)
                    row = await conn.fetchrow(
                        """INSERT INTO kb_versions (article_id, version, data, embedding, action, note, published_by)
                           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
                        article_id, (latest or 0) + 1, json.dumps(data), json.dumps(embedding) if embedding else None,
                        action, note, author)
            return _public(cls._row(row))
        # No await in between, so concurrent requests in this process cannot interleave here.
        history = cls._memory.setdefault(article_id, [])
        row = {"article_id": article_id, "version": (history[-1]["version"] if history else 0) + 1,
               "data": copy.deepcopy(data), "embedding": embedding, "action": action, "note": note,
               "published_by": author, "published_at": datetime.now(timezone.utc)}
        history.append(row)
        return _public(row)

    @classmethod
    async def new_id(cls, data: Dict[str, Any]) -> str:
        existing = await cls.entries()
        base = ("gloss_" if data.get("type") == "glossary" else "kb_") + _slug(data.get("title", ""))
        article_id, n = base, 2
        while article_id in existing:
            article_id, n = f"{base}_{n}", n + 1
        return article_id

    @classmethod
    async def retire(cls, article_id: str, actor: Dict[str, Any], note: str) -> Dict[str, Any]:
        entry = await cls.get(article_id)
        if entry["data"]["status"] == "RETIRED":
            raise KnowledgeError("already_retired")
        return await cls.save(article_id, {**entry["data"], "status": "RETIRED"}, actor, note or "Removed from XO", action="retired")

    @classmethod
    async def restore(cls, article_id: str, number: int, actor: Dict[str, Any], note: str) -> Dict[str, Any]:
        old = await cls.version(article_id, number)
        data = dict(old["data"])
        if data["status"] == "RETIRED":
            raise KnowledgeError("invalid", ["That version was a removal. Pick a version with content."])
        return await cls.save(article_id, data, actor, note or f"Restored version {number}", action="restored")

    @classmethod
    async def mark_reviewed(cls, article_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
        entry = await cls.get(article_id)
        today = date.today().isoformat()
        return await cls.save(article_id, {**entry["data"], "last_reviewed": today, "review_by": plus_days(today, REVIEW_EVERY_DAYS)},
                              actor, "Reviewed: still correct", action="reviewed")

    # ---- Live index ----

    @classmethod
    async def rebuild_index(cls) -> int:
        entries = await cls.entries()
        live = [(k, e) for k, e in entries.items() if e["data"]["status"] != "RETIRED" and e.get("embedding")]
        VectorDatabase.replace([index_document(k, normalize(e["data"])) for k, e in live], [e["embedding"] for _, e in live])
        from app.services.rag_service import RAGService
        RAGService.clear_cache()
        cls._signature = await cls._current_signature()
        return len(live)

    @classmethod
    async def _current_signature(cls) -> Any:
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT COUNT(*) AS n, MAX(published_at) AS last FROM kb_versions")
            return (row["n"], row["last"])
        return sum(len(v) for v in cls._memory.values())

    @classmethod
    async def refresh(cls) -> bool:
        """Rebuilds the index when another instance published; cheap when nothing changed."""
        if await cls._current_signature() != cls._signature:
            await cls.rebuild_index()
            return True
        return False

    @classmethod
    async def refresh_forever(cls) -> None:
        from app.admin.knowledge_web import WebSources
        ticks = 0
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            ticks += 1
            try:
                await cls.refresh()
                if ticks % 120 == 0:  # about hourly: refresh web pages older than a week
                    await WebSources.refresh_due()
            except Exception as exc:
                logger.error("Knowledge-base refresh failed: %s", exc)
