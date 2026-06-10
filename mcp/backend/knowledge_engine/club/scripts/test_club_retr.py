#!/usr/bin/env python3
"""
Club Knowledge — Retrieval Test Script (Supabase backend)

Usage:
    python -m knowledge_engine.club.scripts.test_club_retr
    python -m knowledge_engine.club.scripts.test_club_retr --interactive
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from knowledge_engine.club.retrieval import club_retriever
from utils.logger import logger


def test_retrieval():
    print("\n" + "=" * 80)
    print("CLUB KNOWLEDGE RETRIEVAL TEST (Supabase backend)")
    print("=" * 80)
    print()

    # ── System status ────────────────────────────────────────────────────
    print("Checking system status…")
    status = club_retriever.check_ready()

    print(f"  Ready                    : {status['ready']}")
    print(f"  Embedding service        : {status['embedding_service_available']}")
    print(f"  Supabase connected       : {status['supabase_connected']}")

    if status.get("stats"):
        st = status["stats"]
        print(f"\n  Supabase stats:")
        print(f"    Total papers  : {st.get('total_papers', '?')}")
        print(f"    Total chunks  : {st.get('total_chunks', '?')}")
        if st.get("category_counts"):
            print("    By category:")
            for cat, cnt in st["category_counts"].items():
                print(f"      {cat}: {cnt}")

    print()

    if not status["ready"]:
        print("❌ System not ready!")
        if not status["embedding_service_available"]:
            print("   Configure EmbeddingService in knowledge_engine/embedding_service.py")
        if not status["supabase_connected"]:
            print("   Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
            print("   Then run: python -m knowledge_engine.club.scripts.ingest_club_docs")
        sys.exit(1)

    print("✅ System ready!")
    print()

    # ── Test queries ─────────────────────────────────────────────────────
    test_cases = [
        {
            "query": "What are the ongoing events?",
            "category": "events",
            "description": "Events filter",
        },
        {
            "query": "Who is the coordinator for RoboSprint?",
            "category": "coordinators",
            "description": "Coordinators filter",
        },
        {
            "query": "What are the latest announcements?",
            "category": "announcements",
            "description": "Announcements filter",
        },
        {
            "query": "Tell me about the problem statement for autonomous robots",
            "category": None,
            "description": "No category filter",
        },
    ]

    print("=" * 80)
    print("RUNNING TEST QUERIES")
    print("=" * 80)

    for i, tc in enumerate(test_cases, 1):
        print(f"\n{'─'*70}")
        print(f"Test {i}: {tc['description']}")
        print(f"  Query    : \"{tc['query']}\"")
        print(f"  Category : {tc['category']}")
        print()

        try:
            results = club_retriever.retrieve(
                query=tc["query"],
                category=tc["category"],
                top_k=3,
            )

            print(f"  Results: {len(results)} found")
            print()

            for j, r in enumerate(results, 1):
                print(f"    [{j}] score={r['score']:.4f}")
                print(f"        source   : {r['metadata'].get('source', '?')}")
                print(f"        category : {r['metadata'].get('category', '?')}")
                if r["metadata"].get("event_name"):
                    print(f"        event    : {r['metadata']['event_name']}")
                preview = r["content"][:160].replace("\n", " ")
                if len(r["content"]) > 160:
                    preview += "…"
                print(f"        content  : {preview}")
                print()

        except Exception as exc:
            print(f"  ❌ Error: {exc}")
            logger.exception(exc)

    print("=" * 80)
    print(f"📅 Knowledge last updated: {club_retriever.get_last_updated()}")
    print()


def interactive_mode():
    print("\n" + "=" * 80)
    print("INTERACTIVE QUERY MODE")
    print("=" * 80)
    print("Commands: 'quit' | 'exit' | 'q'  to stop")
    print()

    while True:
        try:
            query = input("🔍 Query: ").strip()
            if not query:
                continue
            if query.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            cat_raw = input("   Category [events/announcements/coordinators/none]: ").strip().lower()
            category = cat_raw if cat_raw in ("events", "announcements", "coordinators") else None

            print()
            results = club_retriever.retrieve(query, category=category, top_k=5)

            if not results:
                print("  ⚠️  No results found\n")
            else:
                print(f"  Found {len(results)} result(s):\n")
                for i, r in enumerate(results, 1):
                    print(f"  {i}. {r['metadata'].get('source', '?')}  (score={r['score']:.4f})")
                    print(f"     {r['content'][:200]}…\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as exc:
            print(f"Error: {exc}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        test_retrieval()


if __name__ == "__main__":
    main()
