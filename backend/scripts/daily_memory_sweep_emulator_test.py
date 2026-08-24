#!/usr/bin/env python3
"""Exercise the dark daily-memory sweep against the Firestore emulator.

This is an on-demand, loopback-only proof.  It commits one synthetic ledger
fact, deletes only the synthetic sweep cursor to model an interruption after
the canonical write, then replays the same source packet.  The source receipt
and canonical operation must make the replay idempotent, with no second memory
item, operation, commit, or outbox event.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-daily-memory-sweep")
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_daily_memory_sweep_emulator_key_32_bytes")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402

from database.memory_collections import MemoryCollections  # noqa: E402
from models.memory_apply import MemoryControlState  # noqa: E402
from utils.memory.daily_memory_sweep import (  # noqa: E402
    DailySweepCandidate,
    DailySweepInput,
    SweepAuthorityState,
    run_daily_memory_sweep,
)


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _collection_ids(db_client: Any, path: str) -> set[str]:
    return {snapshot.id for snapshot in db_client.collection(path).stream()}


def main() -> int:
    _assert_emulator_only()
    uid = f"daily-memory-sweep-emulator-{uuid4().hex}"
    db_client: Any = firestore.Client(project=PROJECT_ID)
    collections = MemoryCollections(uid=uid)
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    control = MemoryControlState(
        uid=uid,
        head_commit_id="daily-sweep-head",
        account_generation=11,
        source_generation=7,
        updated_at=now,
    )
    db_client.document(collections.memory_apply_control_state).set(control.model_dump(mode="json"))
    packet = DailySweepInput(
        uid=uid,
        local_date=date(2026, 8, 23),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        candidates=(
            DailySweepCandidate(
                candidate_id="fact-release-role",
                kind="fact",
                content="Alice owns release review",
                source_id="conversation-1",
                source_type="conversation",
                source_refs=("conversation:conversation-1",),
                slot="release_role",
            ),
        ),
    )
    authority = SweepAuthorityState(enabled=True)
    try:
        first = run_daily_memory_sweep(
            uid,
            "America/New_York",
            now,
            {packet.local_date: packet},
            db_client=db_client,
            authority=authority,
        )
        if first.status != "committed" or first.committed_count != 1:
            raise AssertionError(f"first sweep did not commit one fact: {first}")
        before = {
            "items": _collection_ids(db_client, collections.memory_items),
            "operations": _collection_ids(db_client, collections.memory_operations),
            "commits": _collection_ids(db_client, collections.memory_commits),
            "outbox": _collection_ids(db_client, collections.memory_outbox),
        }

        # The canonical write and receipt survived, but the cursor did not.
        # This is the crash/restart boundary the runner must recover from.
        db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").delete()
        replay = run_daily_memory_sweep(
            uid,
            "America/New_York",
            now,
            {packet.local_date: packet},
            db_client=db_client,
            authority=authority,
        )
        if replay.status != "committed" or replay.idempotent_count != 1 or replay.committed_count != 0:
            raise AssertionError(f"replay was not an exact idempotent no-op: {replay}")
        after = {
            "items": _collection_ids(db_client, collections.memory_items),
            "operations": _collection_ids(db_client, collections.memory_operations),
            "commits": _collection_ids(db_client, collections.memory_commits),
            "outbox": _collection_ids(db_client, collections.memory_outbox),
        }
        if after != before:
            raise AssertionError(f"replay added canonical records: before={before}, after={after}")
        print("PASS: daily memory sweep Firestore emulator retry/interruption proof")
        return 0
    finally:
        for collection_path in (
            collections.daily_memory_sweep_receipts,
            *collections.all_collection_paths(),
        ):
            for snapshot in db_client.collection(collection_path).stream():
                snapshot.reference.delete()
        db_client.document(collections.user_root).delete()


if __name__ == "__main__":
    raise SystemExit(main())
