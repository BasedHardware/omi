"""
Club Knowledge Ingestion Orchestrator — Supabase backend

Fixes vs original:
  • Uses lazy get_embedding_generator() instead of the module-level singleton.
  • drive_client import is deferred so a missing service-account file
    doesn't crash the whole app on startup.
  • _save_chunks: all file opens now explicitly use encoding='utf-8' so
    PDFs with non-ASCII content don't raise UnicodeDecodeError on Windows.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from knowledge_engine.club.config import club_config
from knowledge_engine.club.parser import parser
from knowledge_engine.club.chunker import chunker
from knowledge_engine.club.embedding_generator import get_embedding_generator

logger = logging.getLogger(__name__)


class ClubKnowledgeIngestion:
    """
    Orchestrates the complete ingestion pipeline for club knowledge.

    run_full_ingestion() — Drive → parse → chunk → embed → Supabase
    run_embed_only()     — re-embed from cached chunks_latest.json
    """

    def __init__(self):
        self.parser = parser
        self.chunker = chunker
        logger.info("ClubKnowledgeIngestion initialised (Supabase backend)")

    @property
    def embedding_generator(self):
        return get_embedding_generator()

    @property
    def drive_client(self):
        """Deferred import so missing credentials don't crash on startup."""
        from knowledge_engine.club.drive_client import get_drive_client
        return get_drive_client()

    # ------------------------------------------------------------------ #
    # Main entry points                                                    #
    # ------------------------------------------------------------------ #

    def run_full_ingestion(self, wipe_existing: bool = True) -> Dict[str, Any]:
        """
        Full pipeline: Drive → parse → chunk → embed → Supabase.

        Args:
            wipe_existing: If True (default), delete all existing club
                           vectors before inserting fresh ones.
        """
        logger.info("=" * 70)
        logger.info("STARTING CLUB KNOWLEDGE FULL INGESTION (Supabase)")
        logger.info("=" * 70)

        result: Dict[str, Any] = {
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "stats": {"total_files": 0, "downloaded": 0, "parsed": 0, "total_chunks": 0},
            "embed_result": {},
            "errors": [],
        }

        try:
            # Step 1: Download from Google Drive
            logger.info("Step 1: Downloading from Google Drive…")
            dl = self.drive_client.download_all_documents()

            result["stats"]["total_files"] = dl["total_files"]
            result["stats"]["downloaded"] = dl["downloaded"]

            if dl["downloaded"] == 0:
                result["errors"].append("No documents downloaded from Google Drive")
                return result

            # Step 2: Parse
            logger.info("Step 2: Parsing documents…")
            parsed_docs = self._parse_documents(dl["files"])
            result["stats"]["parsed"] = len(parsed_docs)

            if not parsed_docs:
                result["errors"].append("No documents successfully parsed")
                return result

            # Step 3: Chunk
            logger.info("Step 3: Chunking documents…")
            chunks = self.chunker.chunk_multiple_documents(parsed_docs)
            result["stats"]["total_chunks"] = len(chunks)

            if not chunks:
                result["errors"].append("No chunks created")
                return result

            # Step 4: Save staging file
            logger.info("Step 4: Saving staging JSON…")
            self._save_chunks(chunks, dl)

            # Step 5: Embed + upsert to Supabase
            logger.info("Step 5: Embedding + upserting to Supabase…")
            embed_result = self.embedding_generator.generate_from_chunks(
                chunks, wipe_first=wipe_existing
            )
            result["embed_result"] = embed_result

            if embed_result.get("errors"):
                result["errors"].extend(embed_result["errors"])

            # Step 6: Timestamp
            self._update_timestamp()

            result["status"] = "partial" if result["errors"] else "success"

            logger.info(
                f"INGESTION COMPLETE: {result['status'].upper()} | "
                f"files={dl['downloaded']}/{dl['total_files']} | "
                f"chunks={len(chunks)}"
            )
            return result

        except Exception as exc:
            logger.error(f"Fatal ingestion error: {exc}", exc_info=True)
            result["errors"].append(str(exc))
            return result

    def run_embed_only(self) -> Dict[str, Any]:
        """
        Re-embed from cached chunks_latest.json without re-downloading Drive.
        Useful after changing the embedding model.
        """
        logger.info("=" * 70)
        logger.info("CLUB KNOWLEDGE — RE-EMBED ONLY (from staging file)")
        logger.info("=" * 70)
        return self.embedding_generator.generate_from_chunks_file()

    # ------------------------------------------------------------------ #
    # Stats helpers                                                        #
    # ------------------------------------------------------------------ #

    def get_last_updated(self) -> str:
        f = club_config.CLUB_LAST_UPDATED_FILE
        return f.read_text().strip() if f.exists() else "Never"

    def get_ingestion_stats(self) -> Dict[str, Any]:
        latest = club_config.CLUB_METADATA_DIR / "ingestion_metadata_latest.json"
        if not latest.exists():
            return {"status": "no_ingestion", "last_updated": "Never"}
        try:
            with open(latest, encoding="utf-8") as f:
                meta = json.load(f)
            return {
                "status": "completed",
                "last_updated": self.get_last_updated(),
                **{k: meta.get(k, 0) for k in [
                    "total_files", "downloaded_files", "total_chunks", "error_count"
                ]},
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _parse_documents(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        parsed = []
        for file_info in files:
            try:
                doc = self.parser.parse_file(
                    Path(file_info["local_path"]), file_info["metadata"]
                )
                if doc:
                    parsed.append(doc)
                else:
                    logger.warning(f"Parse returned None for: {file_info['path']}")
            except Exception as exc:
                logger.error(f"Error parsing {file_info['path']}: {exc}")
        return parsed

    def _save_chunks(self, chunks: List[Dict[str, Any]], dl: Dict[str, Any]) -> None:
        """Persist chunks to dated + latest JSON files.

        All file handles explicitly use encoding='utf-8' so documents with
        non-ASCII / non-cp1252 content (e.g. PDFs with special characters)
        don't raise UnicodeDecodeError on Windows.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        meta_dir = club_config.CLUB_METADATA_DIR

        chunks_ts = meta_dir / f"chunks_{ts}.json"
        meta_ts = meta_dir / f"ingestion_metadata_{ts}.json"

        with open(chunks_ts, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)

        ingestion_meta = {
            "ingestion_timestamp": dl.get("timestamp"),
            "total_files": dl.get("total_files", 0),
            "downloaded_files": dl.get("downloaded", 0),
            "skipped_files": dl.get("skipped", 0),
            "error_count": dl.get("errors", 0),
            "total_chunks": len(chunks),
            "chunk_size": self.chunker.chunk_size,
            "chunk_overlap": self.chunker.chunk_overlap,
            "backend": "Supabase pgvector",
        }

        with open(meta_ts, "w", encoding="utf-8") as f:
            json.dump(ingestion_meta, f, indent=2, ensure_ascii=False)

        # Overwrite "latest" symlink-style files — MUST use utf-8 on both ends
        for src, dst in [
            (chunks_ts, meta_dir / "chunks_latest.json"),
            (meta_ts, meta_dir / "ingestion_metadata_latest.json"),
        ]:
            with open(src, encoding="utf-8") as s, open(dst, "w", encoding="utf-8") as d:
                d.write(s.read())

        logger.info(f"Saved staging files → {chunks_ts}, {meta_ts}")

    def _update_timestamp(self):
        ts = datetime.now().isoformat()
        club_config.CLUB_LAST_UPDATED_FILE.write_text(ts, encoding="utf-8")
        logger.info(f"Updated last_updated timestamp: {ts}")


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_ingestion: "ClubKnowledgeIngestion | None" = None


def get_ingestion() -> ClubKnowledgeIngestion:
    global _ingestion
    if _ingestion is None:
        _ingestion = ClubKnowledgeIngestion()
    return _ingestion


class _LazyIngestionProxy:
    def __getattr__(self, name):
        return getattr(get_ingestion(), name)


ingestion: ClubKnowledgeIngestion = _LazyIngestionProxy()  # type: ignore[assignment]
