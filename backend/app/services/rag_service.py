import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from openai import OpenAI
from app.core.config import settings
from app.services.vector_store import VectorDatabase

logger = logging.getLogger("xo.rag")

class RAGService:
    """
    Strict PRD Architecture RAG Pipeline:
    Knowledge Documents → Embeddings → Vector Database → Retriever → Reranker → Relevant Context → LLM
    
    Zero BM25, zero hybrid keyword math, pure vector similarity search:
    - Embedding Model: OpenAI text-embedding-3-small (1536 dimensions)
    - Vector Database: VectorDatabase with cosine similarity dot product
    - Retriever: Vector search retrieving top candidates
    - Reranker: Scope boundary filter, confidence evaluator, statutory disclaimer appender
    - Relevant Context: Clean grounded payload for LLM context injection
    """
    _openai_client: Optional[OpenAI] = None
    _kb_data: Optional[Dict[str, Any]] = None

    @classmethod
    def _get_client(cls) -> OpenAI:
        if cls._openai_client is None:
            cls._openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return cls._openai_client

    @classmethod
    def load_kb(cls, force_reload: bool = False) -> None:
        """
        Loads the master Knowledge Base metadata and loads the Vector Database index.
        """
        if cls._kb_data is not None and not force_reload:
            return

        kb_path = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base", "xobia_kb_master.json")
        if not os.path.exists(kb_path):
            kb_path = os.path.join(os.getcwd(), "backend", "app", "data", "knowledge_base", "xobia_kb_master.json")
        
        if os.path.exists(kb_path):
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    cls._kb_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading master KB JSON: {e}")
                cls._kb_data = {"articles": [], "glossary": [], "metadata": {}}
        else:
            cls._kb_data = {"articles": [], "glossary": [], "metadata": {}}

        VectorDatabase.load(force_reload=force_reload)

    @classmethod
    def _sanitize_query(cls, query: str) -> str:
        """
        Input sanitization and prompt injection defense (PRD Sec 7 / RAG-PINJ).
        Strips adversarial role-play or system override injection tokens.
        """
        if not query:
            return ""
        sanitized = re.sub(
            r'(?i)(ignore previous instructions|system prompt|disregard prior|you are now|override security|jailbreak)',
            '',
            query
        )
        return sanitized.strip()

    @classmethod
    def _generate_query_embedding(cls, text: str, session_id: Optional[str] = None) -> np.ndarray:
        """
        PRD Step: Embeddings
        Generates 1536-dimensional unit-normalized embedding using text-embedding-3-small.
        """
        client = cls._get_client()
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text
        )
        if session_id and hasattr(response, "usage") and response.usage:
            try:
                from app.core.usage_tracker import UsageTracker
                toks = getattr(response.usage, "prompt_tokens", 0) or getattr(response.usage, "total_tokens", 0) or 0
                UsageTracker.record_embedding(
                    session_id=session_id,
                    model=settings.EMBEDDING_MODEL,
                    prompt_tokens=toks
                )
            except Exception as e_track:
                logger.debug(f"Could not record embedding usage: {e_track}")

        vec = np.array(response.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    @classmethod
    def retrieve_candidates(cls, query: str, top_k: int = 8, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        PRD Step: Retriever
        Embeds the query and queries the Vector Database for top candidates.
        Excluded documents (Articles 25-28) are suppressed at the Vector Database layer.
        """
        cls.load_kb()
        clean_query = cls._sanitize_query(query)
        if not clean_query:
            return []

        query_vector = cls._generate_query_embedding(clean_query, session_id=session_id)
        candidates = VectorDatabase.search(
            query_vector=query_vector,
            top_k=top_k,
            exclude_status=["EXCLUDED"]
        )
        return candidates

    @classmethod
    def rerank_and_filter(
        cls,
        candidates: List[Dict[str, Any]],
        query: str,
        confidence_threshold: float = 0.40
    ) -> Dict[str, Any]:
        """
        PRD Step: Reranker
        Evaluates retrieved candidates against:
        1. Low confidence threshold (Domain 11.4 fallback)
        2. Scope boundary constraints (Articles 9-12 conventional mortgage calculation block)
        3. Statutory disclaimer requirements
        4. Glossary prioritization for definition questions
        """
        # Domain 11.4 Low-Confidence Fallback
        if not candidates or candidates[0]["similarity"] < confidence_threshold:
            sim = candidates[0]["similarity"] if candidates else 0.0
            logger.info(f"RAG low-confidence query: '{query}' (best similarity: {sim:.3f})")
            return {
                "status": "fallback",
                "article_number": None,
                "intent_name": "fallback_unrecognised_intent",
                "domain": "Conversational Error Handling",
                "title": "Unrecognised Intent Fallback",
                "confidence": round(sim, 3),
                "message": "That question falls outside of my knowledge base regarding UAE real estate, mortgages, and platform guidance.",
                "short_answer": "I don't have enough verified information about that specific topic.",
                "detail": (
                    "To assist you best, here are available options:\n"
                    "1. Search live property inventory across Dubai.\n"
                    "2. Calculate UAE mortgage affordability and monthly EMI.\n"
                    "3. Connect directly with a licensed human property specialist."
                ),
                "text": "That question falls outside of my knowledge base. Would you like me to connect you with a licensed property specialist, or help you search properties?",
                "handoff_offered": True,
                "disclaimer": "",
                "suggested_follow_ups": [
                    "Speak to a property specialist",
                    "Search apartments in Dubai",
                    "Calculate mortgage affordability"
                ]
            }

        top_match = candidates[0]
        top_doc = top_match["document"]
        similarity = top_match["similarity"]

        # Scope restriction enforcement for Articles 9-12 (Mortgages)
        art_num = top_doc.get("article_number")
        is_mortgage_art = art_num is not None and (9 <= art_num <= 12)
        q_lower = query.lower()

        calc_triggers = ["calculate", "my emi", "my affordability", "how much can i borrow", "apply for mortgage", "start my loan application", "conventional interest rate"]
        if is_mortgage_art and any(t in q_lower for t in calc_triggers):
            return {
                "status": "scope_restricted",
                "article_number": art_num,
                "intent_name": top_doc.get("intent_name", ""),
                "domain": top_doc.get("domain", ""),
                "title": top_doc.get("title", ""),
                "confidence": round(similarity, 3),
                "is_educational_only": True,
                "message": (
                    "Detailed calculation or underwriting is outside our current conversational scope. "
                    "I can provide educational mortgage guidance, or you can use our deterministic mortgage calculator for exact figures."
                ),
                "short_answer": top_doc.get("short_answer", ""),
                "detail": (
                    f"Guidance from Article {art_num} ({top_doc.get('title')}): {top_doc.get('short_answer')}\n\n"
                    "For accurate monthly payment and affordability numbers according to UAE Central Bank regulations, please provide your monthly income and down payment."
                ),
                "text": (
                    f"{top_doc.get('short_answer')}\n\n"
                    "Would you like me to calculate your exact monthly EMI or borrowing capacity using our mortgage calculator?"
                ),
                "disclaimer": "estimate only, subject to lender approval",
                "suggested_follow_ups": [
                    "Calculate monthly EMI",
                    "Check mortgage affordability",
                    "What are the down payment requirements in the UAE?"
                ]
            }

        # Statutory disclaimer
        disclaimer = ""
        if top_doc.get("disclaimer_flag") == "YES":
            disclaimer = (
                "Statutory Notice: Real estate regulations, fees, and visa criteria in the UAE are subject to regulatory updates. "
                "Please consult a licensed property professional for your specific emirate. "
                "Always verify official figures with the Dubai Land Department (DLD) or licensed legal advisors."
            )

        # Glossary term payload
        if top_doc.get("type") == "glossary":
            return {
                "status": "success",
                "article_number": None,
                "intent_name": top_doc.get("intent_name", ""),
                "domain": "Glossary",
                "title": top_doc.get("title", ""),
                "term": top_doc.get("title", ""),
                "definition": top_doc.get("short_answer", ""),
                "confidence": round(similarity, 3),
                "short_answer": top_doc.get("short_answer", ""),
                "detail": top_doc.get("detail", ""),
                "text": f"**{top_doc.get('title')}**: {top_doc.get('short_answer')}",
                "disclaimer": "",
                "suggested_follow_ups": []
            }

        full_text = f"{top_doc.get('short_answer', '')}\n\n{top_doc.get('detail', '')}".strip()

        return {
            "status": "success",
            "article_number": top_doc.get("article_number"),
            "intent_name": top_doc.get("intent_name", ""),
            "domain": top_doc.get("domain", ""),
            "title": top_doc.get("title", ""),
            "confidence": round(similarity, 3),
            "short_answer": top_doc.get("short_answer", ""),
            "detail": top_doc.get("detail", ""),
            "text": full_text,
            "disclaimer": disclaimer,
            "suggested_follow_ups": top_doc.get("follow_up_prompts", [])
        }

    @classmethod
    def retrieve_kb(cls, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        PRD Architecture Function: retrieve_kb(query)
        Executes full RAG pipeline:
        Embeddings → Vector Database → Retriever → Reranker → Relevant Context
        """
        if not query or not query.strip():
            return {
                "status": "empty_query",
                "confidence": 0.0,
                "message": "Query cannot be empty."
            }

        candidates = cls.retrieve_candidates(query, top_k=8, session_id=session_id)
        result = cls.rerank_and_filter(candidates, query)
        return result
