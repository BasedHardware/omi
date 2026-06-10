"""
Club Knowledge Vector Store — Supabase backend

Fixes vs original:
  • ClubVectorStore is no longer instantiated at module level.
    The singleton `club_vector_store` is created lazily via
    get_club_vector_store() so a missing env var doesn't crash
    every module that does `from knowledge_engine.club import ...`.
  • search() signature aligns with the updated match_document_chunks RPC.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class ClubVectorStore:
    """
    Supabase-backed vector store for club knowledge.

    Schema (shared with user RAG):
        papers(id, filename, user_id, source, processed, upload_date)
        document_chunks(id, paper_id, chunk_text, chunk_index,
                        start_char, end_char, embedding, metadata)

    Club rows: source = 'club', user_id = NULL.
    """

    SOURCE_TAG = "club"

    def __init__(self, supabase_url: str, supabase_key: str):
        if not supabase_url or not supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) "
                "must be set in the environment."
            )
        self.client: Client = create_client(supabase_url, supabase_key)
        logger.info("ClubVectorStore (Supabase) initialised")

    # ------------------------------------------------------------------ #
    # Write path                                                           #
    # ------------------------------------------------------------------ #

    def upsert_documents(
        self,
        embeddings: np.ndarray,
        chunks: List[Dict[str, Any]],
        paper_id: str,
        filename: str,
    ) -> Dict[str, Any]:
        """
        Upsert chunks for one Drive file.  Existing rows for this paper_id
        are deleted first so re-runs are idempotent.

        Args:
            embeddings : (N, D) float32 array
            chunks     : list of {"text": str, "metadata": dict}
            paper_id   : stable ID derived from Drive file path
            filename   : human-readable name for the papers row
        """
        if embeddings.shape[0] != len(chunks):
            raise ValueError(
                f"Embedding count ({embeddings.shape[0]}) != chunk count ({len(chunks)})"
            )

        try:
            # 1. Upsert paper record
            self.client.table("papers").upsert(
                {
                    "id": paper_id,
                    "filename": filename,
                    "user_id": None,
                    "source": self.SOURCE_TAG,
                    "processed": True,
                }
            ).execute()

            # 2. Delete old chunks for clean re-embed
            self.client.table("document_chunks").delete().eq(
                "paper_id", paper_id
            ).execute()

            # 3. Insert new chunks
            records = [
                {
                    "paper_id": paper_id,
                    "chunk_text": chunk["text"],
                    "chunk_index": i,
                    "start_char": chunk.get("start_char", 0),
                    "end_char": chunk.get("end_char", 0),
                    "embedding": emb.tolist(),
                    "metadata": chunk.get("metadata", {}),
                }
                for i, (emb, chunk) in enumerate(zip(embeddings, chunks))
            ]

            if records:
                self.client.table("document_chunks").insert(records).execute()

            logger.info(
                f"Upserted {len(records)} chunks for club paper '{filename}' ({paper_id})"
            )
            return {
                "success": True,
                "chunks_upserted": len(records),
                "paper_id": paper_id,
            }

        except Exception as exc:
            logger.error(f"Error upserting club documents: {exc}")
            return {"success": False, "error": str(exc), "chunks_upserted": 0}

    def delete_paper(self, paper_id: str) -> Dict[str, Any]:
        """Delete one club paper and its chunks."""
        try:
            self.client.table("papers").delete().eq("id", paper_id).execute()
            return {"success": True, "paper_id": paper_id}
        except Exception as exc:
            logger.error(f"Error deleting club paper {paper_id}: {exc}")
            return {"success": False, "error": str(exc)}

    def delete_all_club_docs(self) -> Dict[str, Any]:
        """Wipe all club documents — used before a full re-embed."""
        try:
            resp = (
                self.client.table("papers")
                .select("id")
                .eq("source", self.SOURCE_TAG)
                .execute()
            )
            ids = [row["id"] for row in (resp.data or [])]
            for pid in ids:
                self.client.table("papers").delete().eq("id", pid).execute()
            logger.info(f"Deleted {len(ids)} club papers from Supabase")
            return {"success": True, "papers_deleted": len(ids)}
        except Exception as exc:
            logger.error(f"Error deleting all club docs: {exc}")
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Read path                                                            #
    # ------------------------------------------------------------------ #

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over club chunks via the match_document_chunks RPC.

        Args:
            query_embedding : (D,) or (1, D) float32 array
            top_k           : max results
            category        : optional filter ('events' | 'announcements' | 'coordinators')

        Returns:
            [{"text": str, "metadata": dict, "score": float, "paper_id": str}, ...]
        """
        if isinstance(query_embedding, np.ndarray):
            if query_embedding.ndim == 2:
                query_embedding = query_embedding[0]
            embedding_list = query_embedding.tolist()
        else:
            embedding_list = list(query_embedding)

        try:
            resp = self.client.rpc(
                "match_document_chunks",
                {
                    "query_embedding": embedding_list,
                    "match_count": top_k,
                    "user_id_filter": None,
                    "paper_id_filter": None,
                    "source_filter": self.SOURCE_TAG,
                    "category_filter": category,  # None → no category filter
                },
            ).execute()

            return [
                {
                    "text": row["chunk_text"],
                    "metadata": row.get("metadata") or {},
                    "score": row["similarity"],
                    "paper_id": row["paper_id"],
                }
                for row in (resp.data or [])
            ]

        except Exception as exc:
            logger.error(f"Error searching club vector store: {exc}")
            return []

    # ------------------------------------------------------------------ #
    # Utility                                                              #
    # ------------------------------------------------------------------ #

    def get_all_papers(self) -> List[Dict[str, Any]]:
        """Return all club paper records."""
        try:
            resp = (
                self.client.table("papers")
                .select("*")
                .eq("source", self.SOURCE_TAG)
                .execute()
            )
            return resp.data or []
        except Exception as exc:
            logger.error(f"Error fetching club papers: {exc}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Basic statistics about the club knowledge base."""
        try:
            papers_resp = (
                self.client.table("papers")
                .select("id", count="exact")
                .eq("source", self.SOURCE_TAG)
                .execute()
            )
            paper_count = papers_resp.count or 0

            papers = self.get_all_papers()
            paper_ids = [p["id"] for p in papers]

            chunk_count = 0
            category_counts: Dict[str, int] = {}

            if paper_ids:
                chunks_resp = (
                    self.client.table("document_chunks")
                    .select("metadata")
                    .in_("paper_id", paper_ids)
                    .limit(1000)
                    .execute()
                )
                chunk_count = len(chunks_resp.data or [])
                for row in chunks_resp.data or []:
                    cat = (row.get("metadata") or {}).get("category", "unknown")
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            return {
                "status": "ready",
                "backend": "Supabase pgvector",
                "total_papers": paper_count,
                "total_chunks": chunk_count,
                "category_counts": category_counts,
            }

        except Exception as exc:
            logger.error(f"Error getting club stats: {exc}")
            return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Lazy singleton — avoids crashing on import when env vars are absent.
# ---------------------------------------------------------------------------
_club_vector_store: Optional[ClubVectorStore] = None


def get_club_vector_store() -> ClubVectorStore:
    """Return the shared ClubVectorStore, creating it on first call."""
    global _club_vector_store
    if _club_vector_store is None:
        from knowledge_engine.club.config import club_config
        _club_vector_store = ClubVectorStore(
            supabase_url=club_config.SUPABASE_URL,
            supabase_key=club_config.supabase_key,
        )
    return _club_vector_store


# Backward-compat alias — existing code that does `from ... import club_vector_store`
# will trigger the lazy init at first attribute access, not at import time.
class _LazyStoreProxy:
    """Transparent proxy that forwards attribute access to the real store."""

    def __getattr__(self, name):
        return getattr(get_club_vector_store(), name)

    def __repr__(self):
        return repr(get_club_vector_store())


club_vector_store: ClubVectorStore = _LazyStoreProxy()  # type: ignore[assignment]
