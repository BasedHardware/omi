#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import google.cloud.firestore as firestore

from database.memory_vector_repair_outbox import (
    build_vector_repair_purge_outbox_records,
    write_vector_repair_purge_outbox_records,
)


class _FailingDocument:
    def set(self, _payload: Any) -> None:
        raise RuntimeError("intentional emulator validation write failure")


class _FailingDb:
    def document(self, _path: str) -> _FailingDocument:
        return _FailingDocument()


def _required_doc(db_client: Any, path: str) -> dict[str, Any]:
    snapshot = db_client.document(path).get()
    if not snapshot.exists:
        raise AssertionError(f"missing expected Firestore document: {path}")
    return snapshot.to_dict() or {}


def _candidate() -> dict[str, Any]:
    return {
        "vector_id": "u1:short_term:mem-stale:rev1",
        "memory_id": "mem-stale",
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


def main() -> int:
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator_host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    uid = "memory-vector-repair-outbox-emulator-user"
    queued_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    db_client: Any = firestore.Client(project=PROJECT_ID)

    records = build_vector_repair_purge_outbox_records(uid=uid, candidates=[_candidate()], queued_at=queued_at)
    if len(records) != 1:
        raise AssertionError(f"expected one outbox record, got {len(records)}")
    record = records[0]
    expected_path_prefix = f"users/{uid}/memory_outbox/"
    if not record["outbox_path"].startswith(expected_path_prefix):
        raise AssertionError("expected users/{uid}/memory_outbox/{record_id} path, " f"got {record['outbox_path']}")
    if record["record_id"] != record["idempotency_key"]:
        raise AssertionError("record_id must equal idempotency_key for stable replay")

    first = write_vector_repair_purge_outbox_records(db_client=db_client, records=records)
    second = write_vector_repair_purge_outbox_records(db_client=db_client, records=records)
    if first != records or second != records:
        raise AssertionError("writer returned a mutated record payload")

    stored = _required_doc(db_client, record["outbox_path"])
    if stored.get("record_id") != record["record_id"]:
        raise AssertionError("stored outbox record_id changed across idempotent set replay")
    if stored.get("idempotency_key") != record["idempotency_key"]:
        raise AssertionError("stored idempotency_key changed across idempotent set replay")
    if stored.get("event_type") != "vector_repair_purge" or stored.get("status") != "pending":
        raise AssertionError("stored record lost vector_repair_purge pending contract")
    if stored.get("attempt_count") != 0 or stored.get("last_error") is not None:
        raise AssertionError("new outbox record must start retry state at attempt_count=0,last_error=None")

    collection_docs = list(db_client.collection(f"users/{uid}/memory_outbox").stream())
    matching = [doc for doc in collection_docs if doc.id == record["record_id"]]
    if len(matching) != 1:
        raise AssertionError(
            f"expected exactly one idempotent memory_outbox document for {record['record_id']}, got {len(matching)}"
        )

    try:
        write_vector_repair_purge_outbox_records(db_client=_FailingDb(), records=records)
    except RuntimeError as exc:
        if "intentional emulator validation write failure" not in str(exc):
            raise
    else:
        raise AssertionError("write failure propagated check failed: writer swallowed an exception")

    print(
        "PASS: memory vector repair/purge outbox idempotent Firestore emulator set validated "
        f"(path={record['outbox_path']}, record_id={record['record_id']}); write failure propagated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
