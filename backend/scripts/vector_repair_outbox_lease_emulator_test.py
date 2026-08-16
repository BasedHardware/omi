#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import google.cloud.firestore as firestore

from database.memory_vector_repair_outbox import build_vector_repair_purge_outbox_records
from database.memory_vector_repair_outbox_worker import lease_vector_repair_purge_outbox_records


def _candidate() -> dict[str, Any]:
    return {
        "vector_id": "u1:short_term:mem-lease-stale:rev1",
        "memory_id": "mem-lease-stale",
        "reason": "stale_item_revision",
        "decision": "delete_stale_vector",
        "required_projection_commit_id": "projection-commit-current",
        "observed_projection_commit_id": "projection-commit-current",
        "required_account_generation": 7,
        "observed_account_generation": 7,
        "authoritative_account_generation": 7,
        "observed_item_revision": 1,
        "authoritative_item_revision": 2,
        "observed_source_commit_id": "source-old",
        "authoritative_source_commit_id": "source-new",
        "observed_content_hash": "hash-old",
        "authoritative_content_hash": "hash-new",
    }


def _claim_once(uid: str, worker_id: str, now: datetime, barrier: Barrier) -> list[dict[str, Any]]:
    db_client = firestore.Client(project=PROJECT_ID)
    barrier.wait(timeout=15)
    return lease_vector_repair_purge_outbox_records(
        db_client=db_client,
        uid=uid,
        worker_id=worker_id,
        limit=1,
        lease_seconds=30,
        now=now,
    )


def main() -> int:
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator_host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    uid = "memory-vector-repair-outbox-lease-emulator-user"
    now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    db_client: Any = firestore.Client(project=PROJECT_ID)
    records = build_vector_repair_purge_outbox_records(uid=uid, candidates=[_candidate()], queued_at=now)
    if len(records) != 1:
        raise AssertionError(f"expected one outbox record, got {len(records)}")
    record = records[0]
    db_client.document(record["outbox_path"]).set(dict(record))

    worker_count = 8
    barrier = Barrier(worker_count)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_claim_once, uid, f"lease-worker-{idx}", now, barrier) for idx in range(worker_count)
        ]
        lease_batches = [future.result(timeout=30) for future in futures]

    claimed_records = [leased for batch in lease_batches for leased in batch]
    # Contention contract: at most one competing transaction may claim/action the same pending record.
    if len(claimed_records) > 1:
        raise AssertionError(f"expected at most one leased record under contention, got {len(claimed_records)}")
    if len(claimed_records) != 1:
        raise AssertionError(f"expected exactly one leased record under contention, got {len(claimed_records)}")
    if claimed_records[0].get("record_id") != record["record_id"]:
        raise AssertionError("leased record_id changed under contention")
    if claimed_records[0].get("status") != "pending":
        raise AssertionError("leased worker payload must preserve original pending status")

    stored: dict[str, Any] = db_client.document(record["outbox_path"]).get().to_dict() or {}
    if stored.get("status") != "in_progress":
        raise AssertionError(f"expected stored record status in_progress after lease, got {stored.get('status')}")
    lease_owner = stored.get("lease_owner")
    claimed_worker_ids = {f"lease-worker-{idx}" for idx in range(worker_count)}
    if lease_owner not in claimed_worker_ids:
        raise AssertionError(f"stored lease_owner {lease_owner!r} was not one of the competing workers")
    if stored.get("lease_expires_at") is None or stored.get("locked_at") is None or stored.get("leased_at") is None:
        raise AssertionError("stored leased record is missing lease timestamps")

    print(
        "PASS: memory vector repair/purge outbox transactional lease contention validated "
        f"(path={record['outbox_path']}, record_id={record['record_id']}, claimed={len(claimed_records)}, "
        f"lease_owner={lease_owner}); at most one worker claimed the pending record"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
