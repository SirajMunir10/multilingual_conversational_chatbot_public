"""Knowledge base in the admin module (PRD FR-24, with FR-18 sources and the FR-26 corrected-answer drafts).

Content editors and up (kb.edit). Every change adds a version and is live from the next question; every change is
in the activity log. Changing which websites may be added is an Admin task (integrations.manage)."""
import base64
import binascii
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.admin import permissions as P
from app.admin.activity import ActivityLog
from app.admin.auth import Actor, require
from app.admin.knowledge import REVIEW_EVERY_DAYS, KnowledgeError, KnowledgeStore, normalize, plus_days
from app.admin.knowledge_text import IngestError, extract_file
from app.admin.knowledge_web import ALLOWED_KEY, WebSources, allowed_domains, clean_domain
from app.admin.reviews import ReviewError, ReviewStore
from app.admin.settings_store import SettingsStore
from app.core.config import settings
from app.services.vector_store import VectorDatabase

router = APIRouter(prefix="/api/admin/kb", tags=["Admin knowledge base"])
editor = require(P.KB_EDIT)


def _kb_error(exc: KnowledgeError) -> HTTPException:
    codes = {"not_found": 404, "version_not_found": 404, "stale": 409, "invalid": 422, "index_failed": 502, "already_retired": 409}
    return HTTPException(status_code=codes.get(exc.code, 400), detail={"code": exc.code, "errors": exc.errors})


def _ingest_error(exc: IngestError) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": exc.code, "errors": [exc.message]})


def _summary(article_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    d = entry["data"]
    return {"id": article_id, "type": d["type"], "title": d["title"], "short_answer": d["short_answer"][:220],
            "status": d["status"], "tags": d.get("tags", []), "domain": d.get("domain"), "version": entry["version"],
            "source": d.get("source", {}).get("kind", "manual"), "published_by": entry.get("published_by"),
            "published_at": entry["published_at"].isoformat() if hasattr(entry.get("published_at"), "isoformat") else entry.get("published_at"),
            "review_by": d.get("review_by"), "due": KnowledgeStore.due_for_review(entry),
            "overdue": bool(d.get("review_by") and d["status"] != "RETIRED" and d["review_by"] < date.today().isoformat())}


@router.get("/articles")
async def list_articles(q: Optional[str] = Query(None, max_length=200), type: Optional[str] = None,
                        status: Optional[str] = None, tag: Optional[str] = None, actor: Actor = Depends(editor)):
    entries = await KnowledgeStore.entries()
    items = [_summary(k, e) for k, e in entries.items()]
    if q:
        words = q.lower().split()
        items = [i for i in items if all(w in f"{i['title']} {i['short_answer']} {' '.join(i['tags'])}".lower() for w in words)]
    if type:
        items = [i for i in items if i["type"] == type]
    if status == "live":
        items = [i for i in items if i["status"] != "RETIRED"]
    elif status == "retired":
        items = [i for i in items if i["status"] == "RETIRED"]
    elif status == "due":
        items = [i for i in items if i["due"]]
    if tag:
        items = [i for i in items if tag in i["tags"]]
    items.sort(key=lambda i: (i["status"] == "RETIRED", -(i["version"] > 0), i["title"].lower()))
    all_items = [_summary(k, e) for k, e in entries.items()]
    return {"items": items, "counts": {
        "live": sum(i["status"] != "RETIRED" for i in all_items), "retired": sum(i["status"] == "RETIRED" for i in all_items),
        "due": sum(i["due"] for i in all_items), "overdue": sum(i["overdue"] for i in all_items),
        "indexed": VectorDatabase.get_document_count()},
        "tags": sorted({t for i in all_items for t in i["tags"]})}


@router.get("/articles/{article_id}")
async def get_article(article_id: str, actor: Actor = Depends(editor)):
    try:
        entry = await KnowledgeStore.get(article_id)
        return {**_summary(article_id, entry), "data": entry["data"], "versions": await KnowledgeStore.versions(article_id)}
    except KnowledgeError as exc:
        raise _kb_error(exc)


@router.get("/articles/{article_id}/versions/{number}")
async def get_version(article_id: str, number: int, actor: Actor = Depends(editor)):
    try:
        row = await KnowledgeStore.version(article_id, number)
        return {k: v for k, v in row.items() if k != "embedding"}
    except KnowledgeError as exc:
        raise _kb_error(exc)


class ArticleBody(BaseModel):
    data: Dict[str, Any]
    note: str = Field("", max_length=500)
    base_version: Optional[int] = Field(None, ge=0)
    draft_id: Optional[int] = None


@router.post("/articles")
async def create_article(body: ArticleBody, actor: Actor = Depends(editor)):
    data = {**body.data, "source": {"kind": "review", "draft_id": body.draft_id} if body.draft_id else {"kind": "manual"}}
    if not data.get("review_by"):
        data["last_reviewed"] = date.today().isoformat()
    data = normalize(data)
    if not data["review_by"]:
        data["review_by"] = plus_days(data["last_reviewed"], REVIEW_EVERY_DAYS)
    if body.draft_id and not await ReviewStore.draft(body.draft_id):
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "errors": ["That draft was already used or dismissed."]})
    try:
        article_id = await KnowledgeStore.new_id(data)
        saved = await KnowledgeStore.save(article_id, data, actor, body.note or "New entry")
    except KnowledgeError as exc:
        raise _kb_error(exc)
    if body.draft_id:
        await ReviewStore.set_draft_status(body.draft_id, "published")
    await ActivityLog.record(actor, "kb_published", article_id, {"title": data["title"], "version": saved["version"], "new": True,
                                                                  "from_draft": body.draft_id})
    return saved


@router.put("/articles/{article_id}")
async def update_article(article_id: str, body: ArticleBody, actor: Actor = Depends(editor)):
    try:
        entry = await KnowledgeStore.get(article_id)
        if entry["data"]["status"] == "RETIRED":
            raise KnowledgeError("invalid", ["This entry is removed. Restore a version first."])
        data = {**body.data, "source": entry["data"].get("source", {"kind": "manual"})}
        saved = await KnowledgeStore.save(article_id, data, actor, body.note, base_version=body.base_version)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_published", article_id, {"title": saved["data"]["title"], "version": saved["version"], "note": body.note})
    return saved


class NoteBody(BaseModel):
    note: str = Field("", max_length=500)


@router.post("/articles/{article_id}/retire")
async def retire_article(article_id: str, body: NoteBody, actor: Actor = Depends(editor)):
    try:
        saved = await KnowledgeStore.retire(article_id, actor, body.note)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_retired", article_id, {"title": saved["data"]["title"], "version": saved["version"]})
    return saved


class RestoreBody(BaseModel):
    version: int = Field(..., ge=0)
    note: str = Field("", max_length=500)


@router.post("/articles/{article_id}/restore")
async def restore_article(article_id: str, body: RestoreBody, actor: Actor = Depends(editor)):
    try:
        saved = await KnowledgeStore.restore(article_id, body.version, actor, body.note)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_restored", article_id, {"title": saved["data"]["title"], "from_version": body.version,
                                                                 "version": saved["version"]})
    return saved


@router.post("/articles/{article_id}/reviewed")
async def mark_reviewed(article_id: str, actor: Actor = Depends(editor)):
    try:
        saved = await KnowledgeStore.mark_reviewed(article_id, actor)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_reviewed", article_id, {"title": saved["data"]["title"], "review_by": saved["data"]["review_by"]})
    return saved


# ---- Uploads ----

class UploadBody(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    content_base64: str = Field(..., max_length=12 * 1024 * 1024)


@router.post("/upload")
async def read_upload(body: UploadBody, actor: Actor = Depends(editor)):
    """Reads a PDF, DOCX or CSV into proposed entries. Nothing is saved until the editor publishes them."""
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail={"code": "bad_file", "errors": ["The file could not be read."]})
    try:
        result = extract_file(body.filename, raw)
    except IngestError as exc:
        raise _ingest_error(exc)
    return {"filename": body.filename, **result}


class BulkBody(BaseModel):
    entries: List[Dict[str, Any]] = Field(..., min_length=1, max_length=200)
    note: str = Field("", max_length=500)
    filename: str = Field("", max_length=200)


@router.post("/articles/bulk")
async def publish_bulk(body: BulkBody, actor: Actor = Depends(editor)):
    today = date.today().isoformat()
    changes, taken = [], set((await KnowledgeStore.entries()).keys())
    for raw in body.entries:
        data = normalize({**raw, "source": {"kind": "upload", "file": body.filename} if body.filename else {"kind": "manual"},
                          "last_reviewed": today, "review_by": raw.get("review_by") or plus_days(today, REVIEW_EVERY_DAYS)})
        article_id = await KnowledgeStore.new_id(data)
        n = 2
        while article_id in taken:
            article_id, n = f"{article_id}_{n}", n + 1
        taken.add(article_id)
        changes.append((article_id, data, None))
    try:
        saved = await KnowledgeStore.save_many(changes, actor, body.note or (f"Imported from {body.filename}" if body.filename else "Imported"))
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_uploaded", body.filename or "bulk", {"entries": len(saved)})
    return {"saved": len(saved), "ids": [s["article_id"] for s in saved]}


# ---- Web pages ----

@router.get("/sources")
async def list_sources(actor: Actor = Depends(editor)):
    return {"sources": await WebSources.list(), "allowed_domains": await allowed_domains(),
            "can_edit_domains": P.INTEGRATIONS_MANAGE in actor["permissions"]}


class SourceBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)


@router.post("/sources")
async def add_source(body: SourceBody, actor: Actor = Depends(editor)):
    try:
        source = await WebSources.add(body.url, actor)
    except IngestError as exc:
        raise _ingest_error(exc)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_source_added", source["url"], {"entries": len(source["article_ids"]), "removed": source["removed"]})
    return source


@router.post("/sources/{source_id}/refresh")
async def refresh_source(source_id: int, actor: Actor = Depends(editor)):
    try:
        source = await WebSources.refresh(source_id, actor)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_source_refreshed", source["url"], {"status": source["last_status"]})
    return source


@router.delete("/sources/{source_id}")
async def remove_source(source_id: int, actor: Actor = Depends(editor)):
    try:
        source = await WebSources.remove(source_id, actor)
    except KnowledgeError as exc:
        raise _kb_error(exc)
    await ActivityLog.record(actor, "kb_source_removed", source["url"], {"entries": len(source["article_ids"])})
    return {"removed": source_id}


class DomainsBody(BaseModel):
    domains: List[str] = Field(..., max_length=50)


@router.put("/sources/domains")
async def set_domains(body: DomainsBody, actor: Actor = Depends(require(P.INTEGRATIONS_MANAGE))):
    cleaned, bad = [], []
    for d in body.domains:
        c = clean_domain(d)
        (cleaned.append(c) if c else bad.append(d))
    if bad:
        raise HTTPException(status_code=422, detail={"code": "invalid", "errors": [f"“{b}” is not a website name like xoto.ae." for b in bad]})
    cleaned = sorted(set(cleaned))
    await SettingsStore.set(ALLOWED_KEY, cleaned, actor["email"])
    await ActivityLog.record(actor, "kb_domains_updated", "approved websites", {"domains": cleaned})
    return {"allowed_domains": cleaned}


# ---- Corrected answers from conversation review (FR-26 → FR-24) ----

@router.get("/drafts")
async def list_drafts(actor: Actor = Depends(editor)):
    return await ReviewStore.drafts()


@router.post("/drafts/{draft_id}/dismiss")
async def dismiss_draft(draft_id: int, actor: Actor = Depends(editor)):
    try:
        draft = await ReviewStore.set_draft_status(draft_id, "dismissed")
    except ReviewError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "errors": ["That draft was already used or dismissed."]})
    await ActivityLog.record(actor, "kb_draft_dismissed", str(draft_id), {"title": draft["title"]})
    return draft


# ---- Try a question against the live knowledge base ----

class QuestionBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


@router.post("/test-question")
async def test_question(body: QuestionBody, actor: Actor = Depends(editor)):
    """The entries XO would find for this question, with their match score. One embedding call; nothing is saved."""
    from app.services.rag_service import RAGService
    try:
        vector = await RAGService._embed(RAGService._sanitize(body.question), None)
    except Exception:
        raise HTTPException(status_code=502, detail={"code": "index_failed", "errors": ["The search could not run right now. Try again in a minute."]})
    results = VectorDatabase.search(vector, top_k=5)
    threshold = settings.RAG_MIN_SIMILARITY
    used = 0
    matches = []
    for r in results:
        doc = r["document"]
        is_used = r["similarity"] >= threshold and used < settings.RAG_TOP_K
        used += is_used
        matches.append({"id": doc["doc_id"], "title": doc["title"], "type": doc["type"], "score": round(r["similarity"], 3), "used": is_used})
    return {"threshold": threshold, "matches": matches, "answered": any(m["used"] for m in matches)}
