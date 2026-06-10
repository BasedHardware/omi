"""
Club Knowledge Embedding Generator — Supabase backend

Fixes vs original:
  • Uses lazy get_club_vector_store() instead of the module-level singleton
    so a missing env var doesn't crash on import.
  • EmbeddingService import is guarded with a clear error message.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime

from knowledge_engine.club.config import club_config
from knowledge_engine.club.vector_store import get_club_vector_store

logger = logging.getLogger(__name__)

try:
    from knowledge_engine.embedding_service import EmbeddingService
    _embedding_service = EmbeddingService()
    logger.info("✓ EmbeddingService loaded for club embedding generator")
except ImportError as exc:
    logger.warning(f"EmbeddingService import failed: {exc}")
    _embedding_service = None


def _paper_id_for_source(source_path: str) -> str:
    """
    Deterministic UUID-like paper_id from a Drive file path.
    Ensures re-embeds overwrite existing rows instead of duplicating them.
    """
    digest = hashlib.sha256(source_path.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


class ClubEmbeddingGenerator:
    """
    Generates embeddings for club knowledge chunks and upserts them into
    Supabase.

    Two modes:
      1. generate_from_chunks_file()  — reads staging JSON, embeds, upserts
      2. generate_from_chunks()       — accepts in-memory chunk list directly
    """

    def __init__(self):
        self.embedding_service = _embedding_service
        self.metadata_dir = club_config.CLUB_METADATA_DIR
        logger.info("ClubEmbeddingGenerator initialised (Supabase backend)")

    @property
    def vector_store(self):
        """Lazy access so missing env vars don't crash at import time."""
        return get_club_vector_store()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def generate_from_chunks_file(
        self, chunks_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Full re-embed from a JSON staging file.

        Wipes all existing club vectors, then re-upserts everything fresh.
        """
        logger.info("=" * 70)
        logger.info("CLUB KNOWLEDGE — FULL RE-EMBED (Supabase)")
        logger.info("=" * 70)

        result: Dict[str, Any] = {
            "status": "failed",
            "num_chunks": 0,
            "papers_processed": 0,
            "errors": [],
        }

        chunks = self._load_chunks(chunks_file)
        if not chunks:
            result["errors"].append("No chunks found in staging file")
            return result

        result["num_chunks"] = len(chunks)
        groups = self._group_by_source(chunks)
        logger.info(f"Grouped {len(chunks)} chunks into {len(groups)} papers")

        logger.info("Deleting existing club vectors from Supabase…")
        self.vector_store.delete_all_club_docs()

        ok_count = 0
        for source_path, source_chunks in groups.items():
            upsert_result = self._embed_and_upsert(source_path, source_chunks)
            if upsert_result["success"]:
                ok_count += 1
            else:
                result["errors"].append(
                    f"{source_path}: {upsert_result.get('error', 'unknown error')}"
                )

        result["papers_processed"] = ok_count
        result["status"] = "success" if not result["errors"] else (
            "partial" if ok_count > 0 else "failed"
        )

        self._save_metadata(len(chunks), ok_count)
        self._update_timestamp()

        logger.info(
            f"Re-embed complete: {ok_count}/{len(groups)} papers, "
            f"{len(chunks)} chunks, status={result['status']}"
        )
        return result

    def generate_from_chunks(
        self, chunks: List[Dict[str, Any]], wipe_first: bool = False
    ) -> Dict[str, Any]:
        """
        Embed an in-memory chunk list and upsert into Supabase.
        Called directly by ClubKnowledgeIngestion after chunking.
        """
        result: Dict[str, Any] = {
            "status": "failed",
            "num_chunks": len(chunks),
            "papers_processed": 0,
            "errors": [],
        }

        if not chunks:
            result["errors"].append("Empty chunk list")
            return result

        if wipe_first:
            self.vector_store.delete_all_club_docs()

        groups = self._group_by_source(chunks)
        ok_count = 0
        for source_path, source_chunks in groups.items():
            upsert_result = self._embed_and_upsert(source_path, source_chunks)
            if upsert_result["success"]:
                ok_count += 1
            else:
                result["errors"].append(
                    f"{source_path}: {upsert_result.get('error', 'unknown error')}"
                )

        result["papers_processed"] = ok_count
        result["status"] = "success" if not result["errors"] else (
            "partial" if ok_count > 0 else "failed"
        )
        return result

    def get_embedding_stats(self) -> Dict[str, Any]:
        """Return stats about the current club knowledge base."""
        return self.vector_store.get_stats()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _embed_and_upsert(
        self, source_path: str, chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if self.embedding_service is None:
            return {
                "success": False,
                "error": (
                    "EmbeddingService not available. "
                    "Install sentence-transformers:  pip install sentence-transformers"
                ),
            }

        try:
            texts = [c["text"] for c in chunks]
            embeddings = self.embedding_service.embed_texts(texts)

            if not isinstance(embeddings, np.ndarray):
                embeddings = np.array(embeddings, dtype=np.float32)

            if embeddings.ndim != 2:
                return {
                    "success": False,
                    "error": f"Unexpected embedding shape {embeddings.shape}",
                }

            paper_id = _paper_id_for_source(source_path)
            filename = Path(source_path).name

            return self.vector_store.upsert_documents(
                embeddings=embeddings.astype(np.float32),
                chunks=chunks,
                paper_id=paper_id,
                filename=filename,
            )

        except Exception as exc:
            logger.error(f"Embed+upsert failed for '{source_path}': {exc}")
            return {"success": False, "error": str(exc)}

    def _group_by_source(
        self, chunks: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in chunks:
            source = chunk.get("metadata", {}).get("source", "unknown")
            groups.setdefault(source, []).append(chunk)
        return groups

    def _load_chunks(self, chunks_file: Optional[Path] = None) -> List[Dict[str, Any]]:
        if chunks_file is None:
            chunks_file = self.metadata_dir / "chunks_latest.json"
        if not chunks_file.exists():
            logger.error(f"Chunks file not found: {chunks_file}")
            return []
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)
            logger.info(f"Loaded {len(chunks)} chunks from {chunks_file}")
            return chunks
        except Exception as exc:
            logger.error(f"Error loading chunks: {exc}")
            return []

    def _save_metadata(self, num_chunks: int, papers_processed: int):
        meta = {
            "timestamp": datetime.now().isoformat(),
            "backend": "Supabase pgvector",
            "num_chunks": num_chunks,
            "papers_processed": papers_processed,
        }
        meta_file = self.metadata_dir / "embedding_metadata.json"
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        logger.info(f"Saved embedding metadata → {meta_file}")

    def _update_timestamp(self):
        ts = datetime.now().isoformat()
        club_config.CLUB_LAST_UPDATED_FILE.write_text(ts)
        logger.info(f"Updated last_updated timestamp: {ts}")


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_embedding_generator: Optional[ClubEmbeddingGenerator] = None


def get_embedding_generator() -> ClubEmbeddingGenerator:
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = ClubEmbeddingGenerator()
    return _embedding_generator


class _LazyGeneratorProxy:
    def __getattr__(self, name):
        return getattr(get_embedding_generator(), name)


embedding_generator: ClubEmbeddingGenerator = _LazyGeneratorProxy()  # type: ignore[assignment]
