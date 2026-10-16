"""Knowledge-base retrieval (PRD FR-17–FR-20): embeddings → vector search → scoped passages → LLM synthesis."""
import logging
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.config import settings
from app.core.usage_tracker import UsageTracker
from app.llm.client import LLMService
from app.services.vector_store import VectorDatabase

logger = logging.getLogger("xo.rag")

_INJECTION = re.compile(r"(?i)(ignore (all )?previous instructions|disregard prior|system prompt|you are now|override security|jailbreak)")


class RAGService:
    _cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    @classmethod
    def _sanitize(cls, query: str) -> str:
        return _INJECTION.sub(" ", query or "").strip()[:500]

    @classmethod
    async def _embed(cls, text: str, session_id: Optional[str]) -> np.ndarray:
        client = LLMService.client()
        response = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=text)
        if getattr(response, "usage", None):
            UsageTracker.record_embedding(session_id, settings.EMBEDDING_MODEL, getattr(response.usage, "prompt_tokens", 0))
        vec = np.array(response.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    @classmethod
    def _passage(cls, doc: Dict[str, Any], similarity: float) -> Dict[str, Any]:
        passage = {
            "title": doc.get("title"),
            "type": doc.get("type"),
            "similarity": round(similarity, 3),
            "answer": doc.get("short_answer", ""),
            "detail": doc.get("detail", ""),
        }
        if doc.get("status") == "PARTIALLY_ACTIVE":
            passage["scope"] = "Educational only. For personal figures, use the calculator tools."
        if doc.get("disclaimer_flag") == "YES":
            passage["requires_disclaimer"] = True
        return passage

    @classmethod
    async def retrieve(cls, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        clean = cls._sanitize(query)
        if not clean:
            return {"status": "empty_query"}
        key = clean.lower()
        if key in cls._cache:
            cls._cache.move_to_end(key)
            return cls._cache[key]

        vector = await cls._embed(clean, session_id)
        candidates = VectorDatabase.search(vector, top_k=settings.RAG_TOP_K, exclude_status=["EXCLUDED"])
        relevant = [c for c in candidates if c["similarity"] >= settings.RAG_MIN_SIMILARITY]
        if not relevant:
            result: Dict[str, Any] = {
                "status": "not_found",
                "best_similarity": round(candidates[0]["similarity"], 3) if candidates else 0.0,
                "instruction": "The knowledge base has no reliable answer. Say you don't know and offer to connect the user with an advisor.",
            }
        else:
            passages = [cls._passage(c["document"], c["similarity"]) for c in relevant]
            result = {"status": "success", "passages": passages}
            if any(p.get("requires_disclaimer") for p in passages):
                result["disclaimer_note"] = "End with one short clause that this is general guidance, not legal or financial advice."
        cls._cache[key] = result
        while len(cls._cache) > settings.RAG_CACHE_SIZE:
            cls._cache.popitem(last=False)
        return result

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
