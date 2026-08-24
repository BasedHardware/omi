#!/usr/bin/env python3
"""Exercise the dark daily-memory sweep against the Firestore emulator.

This is an on-demand, loopback-only interruption/idempotent-retry proof. It exercises a true crash after the
canonical write but before receipt completion, then deletion and generation
contention at the receipt/cursor CAS fences. No production project is touched.
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
import utils.memory.daily_memory_sweep as daily_sweep  # noqa: E402


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


def _packet(uid: str, control: MemoryControlState) -> DailySweepInput:
    return DailySweepInput(
        uid=uid,
        local_date=date(2026, 8, 23),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        timezone_name="America/New_York",
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


def _seed(
    db_client: Any, uid: str, now: datetime, *, source_generation: int = 7
) -> tuple[MemoryControlState, DailySweepInput]:
    collections = MemoryCollections(uid=uid)
    control = MemoryControlState(
        uid=uid,
        head_commit_id="daily-sweep-head",
        account_generation=11,
        source_generation=source_generation,
        updated_at=now,
    )
    db_client.document(collections.memory_apply_control_state).set(control.model_dump(mode="json"))
    return control, _packet(uid, control)


def _canonical_counts(db_client: Any, collections: MemoryCollections) -> dict[str, int]:
    return {
        path: len(_collection_ids(db_client, getattr(collections, path)))
        for path in ("memory_items", "memory_operations", "memory_commits", "memory_outbox")
    }


def _delete_user_documents(db_client: Any, collections: MemoryCollections) -> None:
    for collection_path in collections.all_collection_paths():
        for snapshot in db_client.collection(collection_path).stream():
            snapshot.reference.delete()
    for path in (collections.memory_apply_control_state,):
        db_client.document(path).delete()
    db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").delete()


def main() -> int:
    _assert_emulator_only()
    db_client: Any = firestore.Client(project=PROJECT_ID)
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    authority = SweepAuthorityState(enabled=True)
    uids: list[str] = []
    try:
        # Crash-after-canonical-before-receipt: the pending claimant is safely
        # replayable and canonical apply remains the sole write authority.
        uid = f"daily-memory-sweep-crash-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        original_finish = getattr(daily_sweep, "_finish_receipt")
        crashed = False

        def crash_once(*args: Any, **kwargs: Any) -> None:
            nonlocal crashed
            if not crashed:
                crashed = True
                raise RuntimeError("simulated process crash after canonical apply")
            original_finish(*args, **kwargs)

        setattr(daily_sweep, "_finish_receipt", crash_once)
        try:
            run_daily_memory_sweep(
                uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
            )
        except RuntimeError as exc:
            if "simulated process crash" not in str(exc):
                raise
        finally:
            setattr(daily_sweep, "_finish_receipt", original_finish)
        before = _canonical_counts(db_client, collections)
        pending = _collection_ids(db_client, collections.daily_memory_sweep_receipts)
        if len(pending) != 1:
            raise AssertionError(f"crash did not leave one pending receipt: {pending}")
        concurrent = run_daily_memory_sweep(
            uid,
            "America/New_York",
            now,
            {packet.local_date: packet},
            db_client=db_client,
            authority=authority,
            claimant="different-concurrent-runner",
        )
        if concurrent.blocked_reason != "source_idempotency_conflict":
            raise AssertionError(f"concurrent receipt claimant was not fenced: {concurrent}")
        replay = run_daily_memory_sweep(
            uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
        )
        if replay.status != "committed" or replay.committed_count != 0 or replay.skipped_count != 1:
            raise AssertionError(f"crash replay did not complete pending receipt: {replay}")
        if _canonical_counts(db_client, collections) != before:
            raise AssertionError("crash replay added canonical records")

        # Deletion contention closes receipt completion after canonical apply;
        # wipe then proves no cursor/receipt auxiliary document is recreated.
        uid = f"daily-memory-sweep-delete-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        original_finish = getattr(daily_sweep, "_finish_receipt")

        def delete_before_finish(*args: Any, **kwargs: Any) -> None:
            db_client.document(f"account_deletions/{uid}").set({"wipe_status": "running"})
            original_finish(*args, **kwargs)

        setattr(daily_sweep, "_finish_receipt", delete_before_finish)
        output = run_daily_memory_sweep(
            uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
        )
        setattr(daily_sweep, "_finish_receipt", original_finish)
        if output.status != "blocked" or output.blocked_reason != "receipt_completion_fence_closed":
            raise AssertionError(f"deletion contention was not fenced: {output}")
        _delete_user_documents(db_client, collections)
        retry = run_daily_memory_sweep(
            uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
        )
        if retry.status != "blocked" or retry.blocked_reason != "account_deletion_fence":
            raise AssertionError(f"post-wipe retry was not blocked: {retry}")
        if _collection_ids(db_client, collections.daily_memory_sweep_receipts):
            raise AssertionError("post-wipe retry recreated sweep receipts")
        if db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").get().exists:
            raise AssertionError("post-wipe retry recreated sweep cursor")

        # Source-generation contention uses the same transaction fence and is
        # distinct from an account-deletion marker.
        uid = f"daily-memory-sweep-generation-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        original_finish = getattr(daily_sweep, "_finish_receipt")

        def bump_generation_before_finish(*args: Any, **kwargs: Any) -> None:
            bumped = control.model_copy(update={"source_generation": control.source_generation + 1})
            db_client.document(collections.memory_apply_control_state).set(bumped.model_dump(mode="json"))
            original_finish(*args, **kwargs)

        setattr(daily_sweep, "_finish_receipt", bump_generation_before_finish)
        output = run_daily_memory_sweep(
            uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
        )
        setattr(daily_sweep, "_finish_receipt", original_finish)
        if output.status != "blocked" or output.blocked_reason != "receipt_completion_fence_closed":
            raise AssertionError(f"generation contention was not fenced: {output}")
        if db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").get().exists:
            raise AssertionError("generation contention advanced sweep cursor")
        first = run_daily_memory_sweep(
            uid, "America/New_York", now, {packet.local_date: packet}, db_client=db_client, authority=authority
        )
        if first.blocked_reason != "input_generation_mismatch":
            raise AssertionError(f"generation mismatch retry unexpectedly wrote: {first}")
        print("PASS: daily memory sweep Firestore emulator retry/interruption proof (crash/deletion/generation)")
        return 0
    finally:
        for uid in uids:
            cleanup = MemoryCollections(uid=uid)
            _delete_user_documents(db_client, cleanup)
            db_client.document(f"account_deletions/{uid}").delete()


if __name__ == "__main__":
    raise SystemExit(main())
