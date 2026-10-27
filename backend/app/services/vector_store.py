import os
import json
import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger("xo.vector_store")

class VectorDatabase:
    """
    PRD Architecture Component: Vector Database
    In-memory, matrix-backed vector database holding precomputed,
    unit-normalized document embeddings (1536-dim text-embedding-3-small).
    """
    _instance: Optional["VectorDatabase"] = None
    _vectors: Optional[np.ndarray] = None
    _docs: List[Dict[str, Any]] = []
    _metadata: Dict[str, Any] = {}
    _loaded: bool = False

    @classmethod
    def _get_store_path(cls) -> str:
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base", "vector_store.json"),
            os.path.join(os.getcwd(), "backend", "app", "data", "knowledge_base", "vector_store.json"),
            os.path.join(os.getcwd(), "data", "knowledge_base", "vector_store.json")
        ]
        for p in candidates:
            if os.path.exists(p):
                return os.path.abspath(p)
        return candidates[0]

    @classmethod
    def load(cls, force_reload: bool = False) -> None:
        if cls._loaded and not force_reload:
            return

        store_path = cls._get_store_path()
        if not os.path.exists(store_path):
            logger.warning(f"Vector store file not found at {store_path}. Initializing empty store.")
            cls._vectors = np.zeros((0, 1536), dtype=np.float32)
            cls._docs = []
            cls._metadata = {}
            cls._loaded = True
            return

        try:
            with open(store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            cls._metadata = data.get("metadata", {})
            raw_docs = data.get("documents", [])
            
            vec_list = []
            doc_list = []
            for doc in raw_docs:
                vec = doc.get("embedding", [])
                if vec:
                    vec_np = np.array(vec, dtype=np.float32)
                    # Ensure unit normalization for cosine similarity dot product
                    norm = np.linalg.norm(vec_np)
                    if norm > 0:
                        vec_np = vec_np / norm
                    vec_list.append(vec_np)
                    doc_copy = dict(doc)
                    # Don't keep raw embedding in memory twice
                    del doc_copy["embedding"]
                    doc_list.append(doc_copy)

            cls._vectors = np.vstack(vec_list) if vec_list else np.zeros((0, 1536), dtype=np.float32)
            cls._docs = doc_list
            cls._loaded = True
            logger.info(f"Loaded Vector Database from {store_path}: {len(doc_list)} documents, {cls._vectors.shape[1] if len(doc_list) else 0}-dim vectors.")
        except Exception as e:
            logger.error(f"Failed to load Vector Database: {e}")
            cls._vectors = np.zeros((0, 1536), dtype=np.float32)
            cls._docs = []
            cls._loaded = True

    @classmethod
    def search(
        cls,
        query_vector: np.ndarray,
        top_k: int = 10,
        exclude_status: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes vector dot product (cosine similarity) search across the index.
        Filters out excluded status documents (e.g. Articles 25-28) at the DB level.
        """
        cls.load()
        if cls._vectors is None or len(cls._docs) == 0:
            return []

        if exclude_status is None:
            # Articles 25-28 are strictly EXCLUDED per Phase 5 scope boundary
            exclude_status = ["EXCLUDED"]

        # Ensure query vector is unit normalized
        q_norm = np.linalg.norm(query_vector)
        if q_norm > 0:
            q_vec = query_vector / q_norm
        else:
            q_vec = query_vector

        # Fast vectorized matrix-vector dot product (cosine similarities)
        similarities = np.dot(cls._vectors, q_vec)

        # Build candidate matches with status filtering
        results = []
        for idx, sim in enumerate(similarities):
            doc = cls._docs[idx]
            if doc.get("status") in exclude_status:
                continue
            
            results.append({
                "document": doc,
                "similarity": float(sim)
            })

        # Sort descending by similarity
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    @classmethod
    def replace(cls, docs: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        """Swaps in a new index at once (knowledge-base publish); searches in flight keep the old one."""
        rows = []
        for vec in vectors:
            v = np.array(vec, dtype=np.float32)
            norm = np.linalg.norm(v)
            rows.append(v / norm if norm > 0 else v)
        cls._vectors, cls._docs = (np.vstack(rows) if rows else np.zeros((0, 1536), dtype=np.float32)), list(docs)
        cls._loaded = True

    @classmethod
    def get_document_count(cls) -> int:
        cls.load()
        return len(cls._docs)
