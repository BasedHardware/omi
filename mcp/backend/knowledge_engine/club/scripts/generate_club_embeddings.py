#!/usr/bin/env python3
"""
Club Knowledge — Re-embed Script (Supabase backend)

Re-embeds club documents from the cached chunks_latest.json without
re-downloading anything from Google Drive.

Use this when:
  • You want to refresh Supabase after changing the embedding model.
  • You already have a fresh chunks_latest.json and just need to push
    embeddings to Supabase.

Usage:
    python -m knowledge_engine.club.scripts.generate_club_embeddings

For a full Drive → embed pipeline use ingest_club_docs.py instead.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from knowledge_engine.club.ingestion import ingestion
from knowledge_engine.club.vector_store import club_vector_store
from utils.logger import logger


def main():
    print("\n" + "=" * 80)
    print("ROBOTICS CLUB KNOWLEDGE — RE-EMBED (Supabase)")
    print("=" * 80)
    print()

    # ── Pre-flight ───────────────────────────────────────────────────────
    try:
        from knowledge_engine.club.config import club_config

        chunks_file = club_config.CLUB_METADATA_DIR / "chunks_latest.json"

        problems = []
        if not club_config.SUPABASE_URL:
            problems.append("SUPABASE_URL is not set")
        if not club_config.supabase_key:
            problems.append("SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) is not set")
        if not chunks_file.exists():
            problems.append(
                f"Staging file not found: {chunks_file}\n"
                "   Run ingest_club_docs.py first."
            )

        if problems:
            for p in problems:
                print(f"  ❌ {p}")
            sys.exit(1)

        print(f"  ✓ Staging file : {chunks_file}")
        print(f"  ✓ Supabase URL : {club_config.SUPABASE_URL}")
        print()

    except Exception as exc:
        print(f"❌ Configuration error: {exc}")
        sys.exit(1)

    # ── Verify embedding service ─────────────────────────────────────────
    try:
        from knowledge_engine.embedding_service import EmbeddingService
        svc = EmbeddingService()
        test_emb = svc.embed_texts(["test"])
        print(f"  ✓ Embedding service ready (dim={test_emb.shape[1]})")
        print()
    except Exception as exc:
        print(f"  ❌ Embedding service error: {exc}")
        sys.exit(1)

    # ── Run re-embed ─────────────────────────────────────────────────────
    print("Starting re-embed from staging file…\n")
    try:
        result = ingestion.run_embed_only()

        print()
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Status          : {result['status'].upper()}")
        print(f"Chunks processed: {result.get('num_chunks', '?')}")
        print(f"Papers upserted : {result.get('papers_processed', '?')}")
        print()

        if result.get("errors"):
            print("Errors:")
            for e in result["errors"]:
                print(f"  ⚠  {e}")
            print()

        # Show current Supabase stats
        print("Supabase stats after re-embed:")
        stats = club_vector_store.get_stats()
        print(f"  Total papers  : {stats.get('total_papers', '?')}")
        print(f"  Total chunks  : {stats.get('total_chunks', '?')}")
        if stats.get("category_counts"):
            for cat, cnt in stats["category_counts"].items():
                print(f"    {cat}: {cnt}")
        print()

        if result["status"] in ("success", "partial"):
            print("✅ Re-embed complete!")
            print()
            print("Next step:")
            print("  python -m knowledge_engine.club.scripts.test_club_retr")
        else:
            print("❌ Re-embed failed — check logs.")

        print("=" * 80)
        sys.exit(0 if result["status"] in ("success", "partial") else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Fatal error: {exc}")
        logger.exception("Fatal error during re-embed")
        sys.exit(1)


if __name__ == "__main__":
    main()
