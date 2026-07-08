import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, cast

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database._client import get_firestore_client
from utils.mcp_scopes import (
    MCP_APP_KEY_MEMORY_GRANTS_DOC_ID,
    MCP_DEFAULT_APP_ID,
    MCP_MEMORY_CONTROL_COLLECTION,
    MCP_MEMORY_GRANT_SCOPES,
    normalize_mcp_scopes,
)


def _normalized_scopes(scopes: list[str] | None) -> list[str]:
    return normalize_mcp_scopes(scopes)


def _grant_ok(grant: Any) -> bool:
    if not isinstance(grant, dict):
        return False
    grant_dict = cast(dict[str, Any], grant)
    return (
        grant_dict.get("enabled") is True
        and grant_dict.get("write") is True
        and grant_dict.get("default_read") is True
        and set(MCP_MEMORY_GRANT_SCOPES).issubset(set(grant_dict.get("scopes") or []))
    )


def _read_key_grant(db: Any, uid: str, app_id: str, key_id: str, grant_cache: dict[str, Any]) -> Any:
    if uid not in grant_cache:
        snap = (
            db.collection("users")
            .document(uid)
            .collection(MCP_MEMORY_CONTROL_COLLECTION)
            .document(MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
            .get()
        )
        grant_cache[uid] = cast(dict[str, Any], snap.to_dict() if getattr(snap, "exists", False) else {})
    return grant_cache[uid].get("grants", {}).get("mcp", {}).get("apps", {}).get(app_id, {}).get("keys", {}).get(key_id)


def _write_full_access(db: Any, uid: str, key_ref: Any, key_id: str, app_id: str, scopes: list[str]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key_ref.update({"id": key_id, "app_id": app_id, "scopes": scopes, "updated_at": now})
    (
        db.collection("users")
        .document(uid)
        .collection(MCP_MEMORY_CONTROL_COLLECTION)
        .document(MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
        .set(
            {
                "grants": {
                    "mcp": {
                        "apps": {
                            app_id: {
                                "keys": {
                                    key_id: {
                                        "enabled": True,
                                        "scopes": MCP_MEMORY_GRANT_SCOPES,
                                        "default_read": True,
                                        "archive_read": False,
                                        "write": True,
                                    }
                                }
                            }
                        }
                    }
                },
                "updated_at": now,
            },
            merge=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventory and backfill MCP keys so agent MCP keys are full-access by default."
    )
    parser.add_argument("--apply", action="store_true", help="Write repairs. Default is dry-run inventory only.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of MCP keys to inspect.")
    args = parser.parse_args()

    db: Any = get_firestore_client()
    counts: defaultdict[str, int] = defaultdict(int)
    grant_cache: dict[str, Any] = {}
    query = db.collection("mcp_api_keys").select(["id", "user_id", "app_id", "scopes"])
    if args.limit:
        query = query.limit(args.limit)

    for doc in query.stream():
        data = cast(dict[str, Any], doc.to_dict() or {})
        counts["total_mcp_key_docs"] += 1

        key_id = str(data.get("id") or doc.id)
        uid = data.get("user_id")
        app_id = str(data.get("app_id") or MCP_DEFAULT_APP_ID)
        scopes = _normalized_scopes(data.get("scopes"))

        needs_key_update = False
        if not data.get("id"):
            counts["missing_id"] += 1
            needs_key_update = True
        if not data.get("app_id"):
            counts["missing_app_id"] += 1
            needs_key_update = True
        raw_scopes = data.get("scopes")
        if not isinstance(raw_scopes, list):
            counts["missing_scopes"] += 1
            needs_key_update = True
        stored_scopes = cast(list[Any], raw_scopes) if isinstance(raw_scopes, list) else []
        if "memories.write" not in set(stored_scopes):
            counts["missing_memories_write"] += 1
            needs_key_update = True
        if not uid:
            counts["missing_user_id"] += 1
            continue

        grant = _read_key_grant(db, uid, app_id, key_id, grant_cache)
        needs_grant_update = not _grant_ok(grant)
        if needs_grant_update:
            counts["missing_or_incomplete_memory_grant"] += 1

        if needs_key_update or needs_grant_update:
            counts["keys_needing_backfill"] += 1
            if args.apply:
                _write_full_access(db, uid, doc.reference, key_id, app_id, scopes)
    counts["unique_users_checked_for_grants"] = len(grant_cache)
    counts["dry_run"] = not args.apply
    print(dict(counts))


if __name__ == "__main__":
    main()
