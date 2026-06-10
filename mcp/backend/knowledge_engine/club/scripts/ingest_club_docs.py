#!/usr/bin/env python3
"""
Club Knowledge — Full Ingestion Script (Supabase backend)

Downloads club documents from Google Drive, parses, chunks, embeds,
and upserts everything into Supabase in one shot.

Usage:
    python -m knowledge_engine.club.scripts.ingest_club_docs

Requirements:
    1. CLUB_DRIVE_FOLDER_ID set in .env
    2. SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) in .env
    3. Service account JSON at credentials/club_service_account.json
    4. Google Drive folder shared with the service account email
"""
import sys
from pathlib import Path

# Allow running as a script from any working directory
project_root = Path(__file__).resolve().parent.parent.parent.parent  # → backend/
sys.path.insert(0, str(project_root))

from knowledge_engine.club.ingestion import ingestion
from utils.logger import logger


def main():
    print("\n" + "=" * 80)
    print("ROBOTICS CLUB KNOWLEDGE — FULL INGESTION (Supabase)")
    print("=" * 80)
    print()

    # ── Pre-flight checks ────────────────────────────────────────────────
    print("Checking configuration…")
    try:
        from knowledge_engine.club.config import club_config

        problems = []
        if not club_config.SUPABASE_URL:
            problems.append("SUPABASE_URL is not set")
        if not club_config.supabase_key:
            problems.append("SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) is not set")
        if not club_config.CLUB_DRIVE_FOLDER_ID:
            problems.append("CLUB_DRIVE_FOLDER_ID is not set")
        if not club_config.CLUB_DRIVE_SERVICE_ACCOUNT_FILE.exists():
            problems.append(
                f"Service account file not found: "
                f"{club_config.CLUB_DRIVE_SERVICE_ACCOUNT_FILE}"
            )

        if problems:
            for p in problems:
                print(f"  ❌ {p}")
            sys.exit(1)

        print(f"  ✓ Supabase URL   : {club_config.SUPABASE_URL}")
        print(f"  ✓ Drive folder ID: {club_config.CLUB_DRIVE_FOLDER_ID[:20]}…")
        print(f"  ✓ Service account: {club_config.CLUB_DRIVE_SERVICE_ACCOUNT_FILE}")
        print()

    except Exception as exc:
        print(f"❌ Configuration error: {exc}")
        sys.exit(1)

    # ── Run pipeline ─────────────────────────────────────────────────────
    print("Starting full ingestion pipeline…\n")
    try:
        result = ingestion.run_full_ingestion(wipe_existing=True)

        print()
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Status : {result['status'].upper()}")
        print()
        s = result["stats"]
        print(f"  Files found      : {s['total_files']}")
        print(f"  Files downloaded : {s['downloaded']}")
        print(f"  Files parsed     : {s['parsed']}")
        print(f"  Chunks created   : {s['total_chunks']}")
        print()

        er = result.get("embed_result", {})
        print(f"  Papers upserted  : {er.get('papers_processed', '?')}")
        print()

        if result.get("errors"):
            print("Errors:")
            for e in result["errors"]:
                print(f"  ⚠  {e}")
            print()

        if result["status"] == "success":
            print("✅ Ingestion completed successfully!")
            print()
            print("Next step:")
            print("  Run: python -m knowledge_engine.club.scripts.test_club_retr")
        elif result["status"] == "partial":
            print("⚠️  Ingestion completed with some errors — check logs.")
        else:
            print("❌ Ingestion failed — check logs.")

        print("=" * 80)
        sys.exit(0 if result["status"] in ("success", "partial") else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Fatal error: {exc}")
        logger.exception("Fatal error during ingestion")
        sys.exit(1)


if __name__ == "__main__":
    main()
