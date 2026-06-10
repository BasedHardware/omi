"""
Club Knowledge Retrieval — Supabase backend

Fixes vs original:
  • Uses lazy get_club_vector_store() instead of the module-level singleton
    so a missing env var doesn't crash on import.
  • Lazy singleton pattern applied to ClubKnowledgeRetriever itself.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

from knowledge_engine.club.config import club_config
from knowledge_engine.club.vector_store import get_club_vector_store

logger = logging.getLogger(__name__)

try:
    from knowledge_engine.embedding_service import EmbeddingService
    _embedding_service = EmbeddingService()
except ImportError:
    logger.warning("EmbeddingService not found — club retrieval will not work")
    _embedding_service = None


class ClubKnowledgeRetriever:
    """
    High-level retrieval interface for club knowledge (Supabase backend).

    Usage:
        from knowledge_engine.club.retrieval import club_retriever
        results = club_retriever.retrieve("What events are upcoming?",
                                          category="events")
    """

    def __init__(self):
        self.embedding_service = _embedding_service
        logger.info("ClubKnowledgeRetriever initialised (Supabase backend)")

    @property
    def vector_store(self):
        """Lazy access — no crash at import time if env vars are missing."""
        return get_club_vector_store()

    # ------------------------------------------------------------------ #
    # Main retrieval                                                       #
    # ------------------------------------------------------------------ #

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant club documents from Supabase.

        Args:
            query    : Natural-language query string
            top_k    : Number of results (default: CLUB_TOP_K_RESULTS)
            category : Optional filter — 'events' | 'announcements' | 'coordinators'

        Returns:
            [
                {
                    "content" : str,
                    "metadata": dict,   # includes "source", "category", "event_name", …
                    "score"   : float,  # cosine similarity (higher = better)
                    "paper_id": str,
                }
            ]
        """
        if not query or not query.strip():
            logger.warning("Empty query — skipping retrieval")
            return []

        top_k = top_k or club_config.CLUB_TOP_K_RESULTS

        try:
            query_embedding = self._embed_query(query)
            if query_embedding is None:
                logger.error("Failed to generate query embedding")
                return []

            raw_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=top_k,
                category=category,
            )

            results = [
                {
                    "content": r["text"],
                    "metadata": r["metadata"],
                    "score": r["score"],
                    "paper_id": r["paper_id"],
                }
                for r in raw_results
            ]

            logger.info(
                f"Retrieved {len(results)} results for query='{query[:60]}' "
                f"category={category}"
            )
            return results

        except Exception as exc:
            logger.error(f"Error during club retrieval: {exc}", exc_info=True)
            return []

    # ------------------------------------------------------------------ #
    # Status / utility                                                     #
    # ------------------------------------------------------------------ #

    def check_ready(self) -> Dict[str, Any]:
        """Check whether the retriever is fully operational."""
        emb_ok = self.embedding_service is not None

        try:
            stats = self.vector_store.get_stats()
            supa_ok = stats.get("status") != "error"
        except Exception:
            stats = {}
            supa_ok = False

        return {
            "ready": emb_ok and supa_ok,
            "embedding_service_available": emb_ok,
            "supabase_connected": supa_ok,
            "stats": stats,
        }

    def get_last_updated(self) -> str:
        f = club_config.CLUB_LAST_UPDATED_FILE
        if not f.exists():
            return "Never"
        try:
            return f.read_text().strip()
        except Exception:
            return "Unknown"

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _embed_query(self, query: str) -> Optional[np.ndarray]:
        """Return a (D,) float32 embedding for the query."""
        if self.embedding_service is None:
            return None
        try:
            emb = self.embedding_service.embed_text(query)
            if not isinstance(emb, np.ndarray):
                emb = np.array(emb, dtype=np.float32)
            return emb.astype(np.float32)
        except Exception as exc:
            logger.error(f"Error embedding query: {exc}")
            return None


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_club_retriever: Optional[ClubKnowledgeRetriever] = None


def get_club_retriever() -> ClubKnowledgeRetriever:
    global _club_retriever
    if _club_retriever is None:
        _club_retriever = ClubKnowledgeRetriever()
    return _club_retriever


class _LazyRetrieverProxy:
    def __getattr__(self, name):
        return getattr(get_club_retriever(), name)


club_retriever: ClubKnowledgeRetriever = _LazyRetrieverProxy()  # type: ignore[assignment]
