"""Refresh the daily benchmark-selected LLM model route table."""

import argparse
import asyncio
import json

from routers.auto_model import refresh_model_routes


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Refresh backend LLM auto-router routes")
    parser.add_argument("--no-persist", action="store_true", help="build the route table without writing Firestore")
    parser.add_argument("--use-cache", action="store_true", help="reuse a current persisted route table if one exists")
    args = parser.parse_args()

    route_table = await refresh_model_routes(force=not args.use_cache, persist=not args.no_persist)
    print(
        json.dumps(
            {
                "profile": route_table.get("profile"),
                "updated_at": route_table.get("updated_at"),
                "expires_at": route_table.get("expires_at"),
                "summary": route_table.get("summary"),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
