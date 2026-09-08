#!/usr/bin/env python3
"""Exercise the dark daily-memory sweep against the Firestore emulator.

This is an on-demand, loopback-only interruption/idempotent-retry proof. It exercises a true crash after the
canonical write but before receipt completion, then deletion and generation
contention at the receipt/cursor CAS fences. No production project is touched.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import date, datetime, timedelta, timezone
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
from models.memory_apply import MemoryControlState, WriterMode  # noqa: E402
from utils.memory.daily_memory_sweep import (  # noqa: E402
    DailySweepCandidate,
    DailySweepInput,
    SweepAuthorityState,
    _invoke_model_once,
    completed_local_day_window,
    run_daily_memory_sweep,
)
import utils.memory.daily_memory_sweep as daily_sweep  # noqa: E402
import utils.memory.canonical_memory_adapter as canonical_adapter  # noqa: E402


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
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "America/New_York")
    return DailySweepInput(
        uid=uid,
        local_date=local_date,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        timezone_name="America/New_York",
        window_id=window.window_id,
        window_start_utc=window.start_utc,
        window_end_utc=window.end_utc,
        complete=True,
        candidates=(
            DailySweepCandidate(
                candidate_id="fact-release-role",
                kind="fact",
                content="Alice owns release review",
                source_id="conversation-1",
                source_type="conversation",
                source_refs=("conversation:conversation-1",),
                slot="occupation",
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
        writer_mode=WriterMode.ledger,
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
            uid,
            "America/New_York",
            now + timedelta(days=1),
            {packet.local_date: packet},
            db_client=db_client,
            authority=authority,
        )
        if replay.status != "committed" or replay.committed_count != 0 or replay.skipped_count != 1:
            raise AssertionError(f"crash replay did not complete pending receipt: {replay}")
        if _canonical_counts(db_client, collections) != before:
            raise AssertionError("crash replay added canonical records")

        # Canonical deletion race: pause after the canonical preflight has
        # returned, publish the deletion marker, then let the real apply path
        # proceed. The shared Firestore apply transaction must read that marker
        # and refuse the write; a preflight-only fence would recreate memory.
        uid = f"daily-memory-sweep-canonical-race-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        entered = threading.Event()
        release = threading.Event()
        original_ensure = getattr(canonical_adapter, "_ensure_control_state")

        def gated_ensure(*args: Any, **kwargs: Any) -> Any:
            result = original_ensure(*args, **kwargs)
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("canonical race test gate timed out")
            return result

        setattr(canonical_adapter, "_ensure_control_state", gated_ensure)
        result_holder: list[Any] = []

        def run_race() -> None:
            try:
                result_holder.append(
                    run_daily_memory_sweep(
                        uid,
                        "America/New_York",
                        now,
                        {packet.local_date: packet},
                        db_client=db_client,
                        authority=authority,
                        claimant="canonical-race-runner",
                    )
                )
            except Exception as exc:  # expected canonical deletion fence
                result_holder.append(exc)

        race_thread = threading.Thread(target=run_race)
        race_thread.start()
        if not entered.wait(timeout=10):
            raise AssertionError("canonical apply race did not reach preflight gate")
        db_client.document(f"account_deletions/{uid}").set({"wipe_status": "running"})
        release.set()
        race_thread.join(timeout=10)
        setattr(canonical_adapter, "_ensure_control_state", original_ensure)
        if race_thread.is_alive() or not result_holder:
            raise AssertionError("canonical apply race did not finish")
        if _collection_ids(db_client, collections.memory_items):
            raise AssertionError("canonical apply recreated an item after deletion marker")

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

        # Source-generation rollover preserves the completed-day identity and
        # accepts only a packet stamped with the new live generation.
        uid = f"daily-memory-sweep-rollover-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now, source_generation=7)
        prior_day = date(2026, 8, 22)
        prior_window = daily_sweep.completed_local_day_window(prior_day, "America/New_York")
        db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").set(
            {
                "schema_version": "daily_memory_sweep_cursor.v1",
                "uid": uid,
                "account_generation": control.account_generation,
                "source_generation": control.source_generation,
                "generation": 3,
                "timezone_name": "America/New_York",
                "last_completed_local_date": prior_day.isoformat(),
                "last_completed_window_id": prior_window.window_id,
                "last_completed_window_start_utc": prior_window.start_utc,
                "last_completed_window_end_utc": prior_window.end_utc,
                "updated_at": now,
            }
        )
        bumped = control.model_copy(update={"source_generation": control.source_generation + 1})
        db_client.document(collections.memory_apply_control_state).set(bumped.model_dump(mode="json"))
        new_window = daily_sweep.completed_local_day_window(packet.local_date, "America/New_York")
        fresh_packet = packet.model_copy(
            update={
                "source_generation": bumped.source_generation,
                "window_id": new_window.window_id,
                "window_start_utc": new_window.start_utc,
                "window_end_utc": new_window.end_utc,
            }
        )
        rollover = run_daily_memory_sweep(
            uid,
            "America/New_York",
            now,
            {fresh_packet.local_date: fresh_packet},
            db_client=db_client,
            authority=authority,
        )
        if rollover.status != "committed":
            raise AssertionError(f"source-generation rollover did not recover: {rollover}")
        rolled_cursor = db_client.document(f"{collections.user_root}/memory_control/daily_memory_sweep").get().to_dict()
        if (
            rolled_cursor.get("source_generation") != bumped.source_generation
            or rolled_cursor.get("last_completed_local_date") != packet.local_date.isoformat()
        ):
            raise AssertionError("source-generation rollover lost completed-day identity")

        # Two real runners share one source packet; unique leases allow only
        # one canonical result and never duplicate the memory row.
        uid = f"daily-memory-sweep-overlap-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        overlap_results: list[Any] = []

        def run_overlap() -> None:
            try:
                overlap_results.append(
                    run_daily_memory_sweep(
                        uid,
                        "America/New_York",
                        now,
                        {packet.local_date: packet},
                        db_client=db_client,
                        authority=authority,
                    )
                )
            except Exception as exc:
                overlap_results.append(exc)

        workers = [threading.Thread(target=run_overlap) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        if any(worker.is_alive() for worker in workers) or len(overlap_results) != 2:
            raise AssertionError("overlapping runners did not finish")
        if len(_collection_ids(db_client, collections.memory_items)) > 1:
            raise AssertionError("overlapping runners duplicated canonical memory")

        # Paid-model/account-wipe race: the real Firestore transaction first
        # claims one durable, top-level invocation identity. The simulated
        # provider then publishes the deletion fence and removes all user
        # documents before returning. Finalization must write no user payload,
        # and retrying the exact identity must not invoke the paid provider a
        # second time.
        uid = f"daily-memory-sweep-paid-wipe-{uuid4().hex}"
        uids.append(uid)
        collections = MemoryCollections(uid=uid)
        control, packet = _seed(db_client, uid, now)
        paid_calls = 0
        invocation_id = f"paid-wipe-{uuid4().hex}"

        def paid_builder_then_wipe() -> tuple[dict[str, Any], ...]:
            nonlocal paid_calls
            paid_calls += 1
            db_client.document(f"account_deletions/{uid}").set({"wipe_status": "running"})
            _delete_user_documents(db_client, collections)
            return ({"candidate_id": "must-not-survive-wipe"},)

        identity = {
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "sweep_generation": 0,
            "window_id": packet.window_id,
            "now": now,
        }
        first_model_result = _invoke_model_once(
            db_client,
            uid,
            invocation_id,
            candidate_builder=paid_builder_then_wipe,
            **identity,
        )
        second_model_result = _invoke_model_once(
            db_client,
            uid,
            invocation_id,
            candidate_builder=paid_builder_then_wipe,
            **identity,
        )
        if first_model_result is not None or second_model_result is not None:
            raise AssertionError("paid model output escaped the account-wipe fence")
        if paid_calls != 1:
            raise AssertionError(f"paid provider invoked {paid_calls} times across wipe/retry")
        if db_client.document(f"users/{uid}/{daily_sweep.MODEL_INVOCATION_PATH}/{invocation_id}").get().exists:
            raise AssertionError("model finalization recreated user payload after account wipe")
        durable_fence = db_client.document(f"{daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION}/{invocation_id}").get()
        durable_payload = durable_fence.to_dict() if durable_fence.exists else {}
        if durable_payload.get("state") != "indeterminate" or "candidate_page" in durable_payload:
            raise AssertionError(f"durable paid-call fence is not content-free/closed: {durable_payload}")

        print(
            "PASS: daily memory sweep Firestore emulator retry/interruption proof "
            "(crash/deletion/generation/paid-wipe)"
        )
        return 0
    finally:
        for uid in uids:
            cleanup = MemoryCollections(uid=uid)
            _delete_user_documents(db_client, cleanup)
            db_client.document(f"account_deletions/{uid}").delete()
        for snapshot in db_client.collection(daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION).stream():
            snapshot.reference.delete()


if __name__ == "__main__":
    raise SystemExit(main())
