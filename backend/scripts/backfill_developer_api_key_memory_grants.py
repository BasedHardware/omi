#!/usr/bin/env python3
"""Seed missing app/key memory grants for Developer API keys created before seeding landed.

Developer API keys created before commit 8e03144a (2026-06-27) have no entry under
``users/{uid}/memory_control/app_key_memory_grants``. The grant gate
(``authorize_memory_external_default_memory_read``) fails closed when no grant document is
found, so those keys receive a permanent 403 from ``GET /v1/dev/user/memories`` regardless
of the scopes on the key, while ``/conversations`` and ``/action-items`` keep working.

This grants nothing new. It materialises the grant each key's own scopes already imply, by
making exactly the call the create path in ``database/dev_api_key.py`` makes:

    grant_default_read = has_scope(scopes, Scopes.MEMORIES_READ)
    grant_write = has_scope(scopes, Scopes.MEMORIES_WRITE)
    if grant_default_read or grant_write:
        seed_developer_api_key_memory_grant(...)

Scope resolution deliberately goes through ``utils.scopes.has_scope``, the same authority
the request path uses, rather than a literal membership test. That matters for one legacy
shape: ``has_scope(None, ...)`` treats a key with no stored ``scopes`` field as read-only,
which includes ``memories:read``. Such a key can already read memories at the request
layer, so it needs the grant too, and a literal ``'memories:read' in scopes`` test would
skip it. Write is never inferred that way — ``memories:write`` is not a read-only scope.

Keys that already hold a grant for the same app/key are left untouched, so re-running is
safe. Dry run is the default and performs no writes.

Usage:
    python scripts/backfill_developer_api_key_memory_grants.py              # dry run
    python scripts/backfill_developer_api_key_memory_grants.py --limit 200  # bounded dry run
    python scripts/backfill_developer_api_key_memory_grants.py --apply      # write grants
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Optional, cast

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database._client import get_firestore_client
from database.memory_app_key_grants import (
    DEVELOPER_API_CONSUMER,
    DEVELOPER_API_DEFAULT_APP_ID,
    read_app_key_memory_grants_state,
    seed_developer_api_key_memory_grant,
)
from utils.scopes import Scopes, has_scope

# Developer API keys created before this instant predate the create-path grant seeding
# (commit 8e03144a, 2026-06-27 22:54:46 +0700). Keys created after it are seeded on create.
SEEDING_LANDED_AT = datetime(2026, 6, 27, 15, 54, 46, tzinfo=timezone.utc)


def _stored_scopes(value: Any) -> Optional[list[str]]:
    """The key's stored scopes, or None when the field is absent/unusable.

    None is meaningful, not an error: `has_scope` treats it as the legacy read-only
    default, so it must be preserved rather than coerced to an empty list.
    """
    if not isinstance(value, list):
        return None
    items = cast(list[Any], value)
    return [scope for scope in items if isinstance(scope, str) and scope]


def _created_before_seeding(created_at: Any) -> Optional[bool]:
    """Whether the key predates grant seeding, or None when the timestamp is unusable."""
    if not isinstance(created_at, datetime):
        return None
    # Firestore returns tz-aware datetimes; treat a naive value as UTC rather than crashing
    # on the comparison, so one malformed row cannot abort the scan.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at < SEEDING_LANDED_AT


def _has_grant(db: Any, uid: str, key_id: str, grant_cache: dict[str, Any]) -> bool:
    """Whether this uid already holds any grant entry for this Developer API key."""
    if uid not in grant_cache:
        state = read_app_key_memory_grants_state(uid, db_client=db)
        grant_cache[uid] = state.state if state.present and not state.malformed else {}
    return (
        cast(dict[str, Any], grant_cache[uid])
        .get("grants", {})
        .get(DEVELOPER_API_CONSUMER, {})
        .get("apps", {})
        .get(DEVELOPER_API_DEFAULT_APP_ID, {})
        .get("keys", {})
        .get(key_id)
        is not None
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventory and backfill app/key memory grants for pre-seeding Developer API keys."
    )
    parser.add_argument("--apply", action="store_true", help="Write grants. Default is dry-run inventory only.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of Developer API keys to inspect.")
    args = parser.parse_args()

    db: Any = get_firestore_client()
    counts: defaultdict[str, int] = defaultdict(int)
    grant_cache: dict[str, Any] = {}
    would_seed_uids: set[str] = set()

    query = db.collection("dev_api_keys").select(["id", "user_id", "scopes", "created_at"])
    if args.limit:
        query = query.limit(args.limit)

    for doc in query.stream():
        data = cast(dict[str, Any], doc.to_dict() or {})
        counts["total_dev_key_docs"] += 1

        key_id = str(data.get("id") or doc.id)
        uid = data.get("user_id")
        if not uid or not isinstance(uid, str):
            counts["skipped_missing_user_id"] += 1
            continue

        created_before = _created_before_seeding(data.get("created_at"))
        if created_before is None:
            # Cannot prove the key predates seeding, so leave it alone rather than guess.
            counts["skipped_unusable_created_at"] += 1
            continue
        if not created_before:
            counts["skipped_created_after_seeding"] += 1
            continue

        scopes = _stored_scopes(data.get("scopes"))
        if scopes is None:
            counts["absent_scopes_treated_as_read_only"] += 1
        grant_default_read = has_scope(scopes, Scopes.MEMORIES_READ)
        grant_write = has_scope(scopes, Scopes.MEMORIES_WRITE)
        if not (grant_default_read or grant_write):
            counts["skipped_no_memory_scope"] += 1
            continue

        counts["pre_seeding_keys_with_memory_scope"] += 1
        if _has_grant(db, uid, key_id, grant_cache):
            counts["already_granted"] += 1
            continue

        counts["keys_needing_backfill"] += 1
        counts["grant_default_read" if grant_default_read else "grant_write_only"] += 1
        would_seed_uids.add(uid)

        if args.apply:
            seed_developer_api_key_memory_grant(
                uid,
                key_id,
                default_read=grant_default_read,
                write=grant_write,
                db_client=db,
            )
            counts["grants_written"] += 1
            # This uid's cached grant document is now stale; drop it so a second key for the
            # same uid is checked against the written state instead of the pre-write copy.
            grant_cache.pop(uid, None)

    counts["distinct_users_needing_backfill"] = len(would_seed_uids)
    counts["unique_users_read_for_grants"] = len(grant_cache)
    counts["dry_run"] = not args.apply
    print(dict(counts))


if __name__ == "__main__":
    main()
