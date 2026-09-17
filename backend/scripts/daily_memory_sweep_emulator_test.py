#!/usr/bin/env python3
"""Exercise the dark daily-memory sweep against the Firestore emulator.

This is an on-demand, loopback-only interruption/idempotent-retry proof. It exercises a true crash after the
canonical write but before receipt completion, then deletion and generation
contention at the receipt/cursor CAS fences. No production project is touched.
"""

from __future__ import annotations

from contextlib import nullcontext

import os
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from unittest.mock import patch

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
from scripts.jit_qa_sweep_repair import (
    collect_provider_outcome_evidence,
    repair_tombstone,
    JITQASweepRepairError,
)  # noqa: E402
from llm_gateway.gateway import jit_budget  # noqa: E402
from models.daily_sweep_dispatch import SweepDispatchScope  # noqa: E402
from models.memory_contracts import MemoryExtractionError  # noqa: E402
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


def _prove_completed_day_source_scan(db_client: Any, uid: str) -> None:
    """Equal timestamps must not hide a processing row beyond the full-doc cap."""

    started = datetime(2026, 8, 23, 8, tzinfo=timezone.utc)
    collection = db_client.collection(f"users/{uid}/conversations")
    refs = [collection.document(f"c-{i:04d}") for i in range(401)]
    try:
        batch = db_client.batch()
        for index, ref in enumerate(refs):
            batch.set(
                ref,
                {
                    "id": ref.id,
                    "created_at": started,
                    "started_at": started,
                    "finished_at": started + timedelta(minutes=1),
                    "status": "processing" if index == 400 else "completed",
                    "structured": {"title": "Meeting", "overview": "Planning", "category": "personal"},
                    "transcript_segments": [],
                },
            )
        batch.commit()
        window = completed_local_day_window(date(2026, 8, 23), "UTC")
        read = daily_sweep._read_completed_day_conversation_sources(
            uid,
            window,
            db_client=db_client,
            max_conversations=200,
            max_summary_characters=120_000,
        )
        if read.status != "incomplete" or read.reason != "row_not_eligible":
            raise AssertionError("row beyond selection page bypassed eligibility")
        refs[-1].update({"status": "completed"})
        read = daily_sweep._read_completed_day_conversation_sources(
            uid,
            window,
            db_client=db_client,
            max_conversations=8,
            max_summary_characters=8_000,
        )
        if read.status != "complete" or read.rows_seen != 401 or read.rows_used != 8 or not read.truncated:
            raise AssertionError("completed over-budget day did not produce a bounded selection")
        if any(row.conversation_id not in {f"c-{i:04d}" for i in range(16)} for row in read.rows):
            raise AssertionError("equal-timestamp page did not use document-id order")
    finally:
        batch = db_client.batch()
        for ref in refs:
            batch.delete(ref)
        batch.commit()


def _prove_window_admission_and_skip(db_client: Any, uid: str, now: datetime) -> None:
    control, _ = _seed(db_client, uid, now)
    identity = dict(
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        sweep_generation=1,
        window_id="round4-window",
    )
    entered, finish = threading.Event(), threading.Event()
    calls: list[str] = []
    results: list[Any] = []

    def provider() -> tuple:
        calls.append("first")
        entered.set()
        if not finish.wait(10):
            raise AssertionError("admission overlap timed out")
        return ()

    def first() -> None:
        results.append(
            _invoke_model_once(
                db_client,
                uid,
                lambda: "round4-first",
                candidate_builder=provider,
                input_digest="original",
                now=now,
                **identity,
            )
        )

    with patch.object(daily_sweep, "_MODEL_INVOCATION_LOCK", nullcontext()):
        worker = threading.Thread(target=first)
        worker.start()
        try:
            if not entered.wait(10):
                raise AssertionError("admitted worker failed to dispatch")
            evidence: dict[str, Any] = {}
            second = _invoke_model_once(
                db_client,
                uid,
                lambda: "round4-future-identity",
                candidate_builder=lambda: calls.append("second") or (),
                input_digest="original",
                now=now,
                invocation_evidence=evidence,
                **identity,
            )
            if second is not None or evidence.get("failure_reason") != "window_admission_busy":
                raise AssertionError("real admission transaction did not serialize overlap")
        finally:
            finish.set()
            worker.join(10)
    if results != [()] or calls != ["first"]:
        raise AssertionError("admission dispatched more than once")
    replay = _invoke_model_once(
        db_client,
        uid,
        lambda: "round4-future-identity",
        candidate_builder=lambda: calls.append("third") or (),
        input_digest="original",
        now=now,
        **identity,
    )
    if replay != () or calls != ["first"]:
        raise AssertionError("released admission lost its durable identity binding")

    legacy = db_client.document(f"{daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION}/round4-pre-lock")
    legacy.set({"uid": uid, "claimed_at": now, "state": "pending"})
    try:
        daily_sweep.assert_no_live_pre_lock_claims(db_client, now=now, uids=(uid,))
    except RuntimeError as error:
        if str(error) != "pre_lock_claim_live":
            raise
    else:
        raise AssertionError("pre-lock live claim passed rollout assertion")
    daily_sweep.assert_no_live_pre_lock_claims(db_client, now=now + daily_sweep.MODEL_INVOCATION_LEASE, uids=(uid,))
    legacy.delete()

    fence = db_client.document(f"{daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION}/round4-first").get().to_dict()
    attested_at = (
        now + daily_sweep.MODEL_INVOCATION_LEASE + daily_sweep.MODEL_INVOCATION_REPAIR_MARGIN + timedelta(seconds=1)
    )
    evidence = {
        "provider_outcome": "operator_attested_skip_window",
        "window_disposition": "abandoned",
        "provider_dispatch_status": "not_attested",
        "accounting_checked": False,
        "confirmation": daily_sweep.SKIP_WINDOW_ATTESTATION_CONFIRMATION,
        "attested_by": "emulator-operator",
        "evidence_reference": "emulator:round4",
        "attested_at": attested_at.isoformat(),
        "claimed_at": now.isoformat(),
        "claim_id": fence["claim_id"],
        "claim_identity": {"uid": uid, "invocation_id": "round4-first", **identity},
    }
    daily_sweep.repair_daily_sweep_model_invocation(
        db_client,
        uid=uid,
        invocation_id="round4-first",
        provider_outcome_evidence=evidence,
        repair_authority="emulator-operator",
        now=attested_at,
    )
    if not daily_sweep._consume_attested_window_skip(db_client, uid, **identity):
        raise AssertionError("real transaction failed to consume skip attestation")
    if not daily_sweep._consume_attested_window_skip(db_client, uid, **identity):
        raise AssertionError("skip outcome did not survive retry")


def _prove_selected_source_lock_projection(db_client: Any, uid: str) -> None:
    ref = db_client.document(f"users/{uid}/conversations/privacy-projection")
    try:
        ref.set({"is_locked": False, "transcript": "must not be projected"})
        if ref.get(field_paths=["is_locked"]).to_dict() != {"is_locked": False}:
            raise AssertionError("privacy projection transferred unrequested content")
        daily_sweep._assert_selected_sources_unlocked(db_client, uid, ("privacy-projection",))
        ref.update({"is_locked": True})
        try:
            daily_sweep._assert_selected_sources_unlocked(db_client, uid, ("privacy-projection",))
        except MemoryExtractionError as error:
            if error.extractor != "source_locked_before_dispatch":
                raise
        else:
            raise AssertionError("fresh lock did not block the provider boundary")
    finally:
        ref.delete()


def main() -> int:
    _assert_emulator_only()
    db_client: Any = firestore.Client(project=PROJECT_ID)
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    authority = SweepAuthorityState(enabled=True)
    uids: list[str] = []
    try:
        admission_uid = f"daily-memory-sweep-admission-{uuid4().hex}"
        uids.append(admission_uid)
        _prove_window_admission_and_skip(db_client, admission_uid, now)
        _prove_selected_source_lock_projection(db_client, admission_uid)
        _prove_completed_day_source_scan(db_client, f"daily-memory-sweep-source-{uuid4().hex}")
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

        # The certified preparation boundary releases transactionally. Competing
        # processes then contend on the released fence, without the local lock.
        uid = f"daily-memory-sweep-release-{uuid4().hex}"
        uids.append(uid)
        control, packet = _seed(db_client, uid, now)
        invocation_id = f"pre-dispatch-{uuid4().hex}"
        identity = {
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "sweep_generation": 0,
            "window_id": packet.window_id,
            "now": now,
        }

        @SweepDispatchScope.certify_pre_dispatch
        def preparation_failure() -> tuple[dict[str, Any], ...]:
            raise MemoryExtractionError("daily_sweep_summary_input_budget")

        if (
            _invoke_model_once(
                db_client,
                uid,
                invocation_id,
                candidate_builder=preparation_failure,
                input_digest="before-release",
                **identity,
            )
            is not None
        ):
            raise AssertionError("pre-dispatch failure returned output")
        ref = db_client.document(f"{daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION}/{invocation_id}")
        released = ref.get().to_dict()
        if released.get("state") != "pre_dispatch_released" or released.get("pre_dispatch_releases") != 1:
            raise AssertionError("pre-dispatch failure did not release durably")
        paid_calls_after_release: list[int] = []
        release_errors: list[Exception] = []
        release_barrier = threading.Barrier(2)

        def release_worker(input_digest: str) -> None:
            try:
                release_barrier.wait(timeout=10)
                _invoke_model_once(
                    db_client,
                    uid,
                    invocation_id,
                    candidate_builder=lambda: paid_calls_after_release.append(1) or ({"candidate_id": "one"},),
                    input_digest=input_digest,
                    **identity,
                )
            except Exception as exc:
                release_errors.append(exc)

        saved_lock = daily_sweep._MODEL_INVOCATION_LOCK
        daily_sweep._MODEL_INVOCATION_LOCK = nullcontext()
        try:
            workers = [threading.Thread(target=release_worker, args=(f"selection-{i}",)) for i in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=15)
        finally:
            daily_sweep._MODEL_INVOCATION_LOCK = saved_lock
        if release_errors or any(worker.is_alive() for worker in workers) or paid_calls_after_release != [1]:
            raise AssertionError(
                f"released claim contention failed: {release_errors}, calls={paid_calls_after_release}"
            )
        if ref.get().to_dict().get("state") != "returned":
            raise AssertionError("reclaimed output did not finalize")
        bound_digest = ref.get().to_dict().get("input_digest")
        payload_ref = db_client.document(f"users/{uid}/{daily_sweep.MODEL_INVOCATION_PATH}/{invocation_id}")
        if (
            bound_digest not in {"selection-0", "selection-1"}
            or payload_ref.get().to_dict().get("input_digest") != bound_digest
        ):
            raise AssertionError("reclaimed output lost the transactionally bound source digest")
        for changed_digest in ("late-row", "deleted-row", "enriched-row"):
            result = _invoke_model_once(
                db_client,
                uid,
                invocation_id,
                candidate_builder=lambda: paid_calls_after_release.append(2) or (),
                input_digest=changed_digest,
                **identity,
            )
            if result is not None or paid_calls_after_release != [1]:
                raise AssertionError("mutated source reopened a possibly dispatched window")
        replayed = _invoke_model_once(
            db_client,
            uid,
            invocation_id,
            candidate_builder=lambda: paid_calls_after_release.append(3) or (),
            input_digest=bound_digest,
            **identity,
        )
        if replayed != ({"candidate_id": "one"},) or paid_calls_after_release != [1]:
            raise AssertionError("unchanged source did not reuse its returned output")

        # A historical transcript-keyed fence must block admission of a new
        # window-keyed identity, even when account cleanup removed its payload.
        payload_ref.delete()
        legacy_retry = _invoke_model_once(
            db_client,
            uid,
            "new-window-identity-" + uuid4().hex,
            candidate_builder=lambda: paid_calls_after_release.append(4) or (),
            input_digest="changed-after-old-deployment",
            **identity,
        )
        if legacy_retry is not None or paid_calls_after_release != [1]:
            raise AssertionError("historical invocation fence was bypassed by the window identity")

        # Real document cursors must read past a full foreign accounting page.
        accounting_refs = []
        accounting_prefix = uuid4().hex
        try:
            for index in range(56):
                accounting_ref = db_client.collection("llm_gateway_attempts").document(
                    f"{accounting_prefix}-{index:03d}"
                )
                accounting_refs.append(accounting_ref)
                accounting_ref.set(
                    {
                        "date": now.date().isoformat(),
                        "occurred_at": now,
                        "user_uid": uid if index == 55 else "foreign-emulator-user",
                        "feature": "memories",
                        "request_id": f"emulator-request-{index}",
                        "jit_run_id": "emulator-run",
                        "outcome": "error",
                    }
                )
            evidence = collect_provider_outcome_evidence(
                db_client,
                uid=uid,
                claimed_at=now - timedelta(minutes=1),
                now=now + timedelta(hours=1),
            )
            if [attempt["request_id"] for attempt in evidence["attempts"]] != ["emulator-request-55"]:
                raise AssertionError("accounting pagination missed the matching attempt after 55 foreign rows")
        finally:
            for accounting_ref in accounting_refs:
                accounting_ref.delete()

        # Durable JIT reservation + simulated provider dispatch + lost accounting
        # must never authorize repair by ledger absence, even after lease expiry.
        lost_invocation_id = f"lost-accounting-{uuid4().hex}"
        lost_run_id = f"lost-accounting-{uuid4().hex}"
        reservation_refs = []
        dispatched = []
        try:

            def reserved_provider_crash() -> tuple[dict[str, Any], ...]:
                with patch.object(jit_budget, "_client", return_value=db_client):
                    reservation = jit_budget.reserve_jit_provider_attempt(
                        owner_uid=uid,
                        run_id=lost_run_id,
                        contract_version="jit-cloud-qa-v1",
                        max_attempts=1,
                        max_spend_micro_usd=50_000,
                        provider="openai",
                        model="gpt-5.6-luna",
                        input_tokens=100,
                        cached_input_tokens=0,
                        output_tokens=10,
                        cache_write_tokens=0,
                    )
                if reservation is None:
                    raise AssertionError("emulator provider reservation was rejected")
                dispatched.append(1)
                raise RuntimeError("simulated process death after provider; no accounting write")

            if (
                _invoke_model_once(
                    db_client,
                    uid,
                    lost_invocation_id,
                    candidate_builder=reserved_provider_crash,
                    **{**identity, "window_id": "lost-accounting-window"},
                )
                is not None
            ):
                raise AssertionError("crashed invocation returned output")
            reservation_refs = [
                snapshot.reference
                for snapshot in db_client.collection("jit_cloud_qa_budgets_v1").stream()
                if snapshot.to_dict().get("run_id") == lost_run_id
            ]
            if dispatched != [1] or len(reservation_refs) != 1:
                raise AssertionError("lost-accounting scenario did not reserve and dispatch exactly once")
            try:
                repair_tombstone(
                    db_client,
                    uid=uid,
                    invocation_id=lost_invocation_id,
                    repair_authority="emulator:operator",
                    now=now + timedelta(hours=1),
                )
            except JITQASweepRepairError as exc:
                if "accounting absence is not proof" not in str(exc):
                    raise
            else:
                raise AssertionError("lost provider accounting authorized duplicate dispatch")
            repair_ref = db_client.document(
                f"users/{uid}/{daily_sweep.MODEL_INVOCATION_REPAIR_PATH}/{lost_invocation_id}"
            )
            if repair_ref.get().exists:
                raise AssertionError("unsafe absence repair receipt was created")
        finally:
            for reservation_ref in reservation_refs:
                reservation_ref.delete()

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
            "(crash/deletion/generation/paid-wipe/pre-dispatch-release-contention/source-digest-binding/legacy-fence/source-projection/accounting-pagination/lost-accounting-refusal/window-admission/pre-lock-preflight/attested-skip/lock-projection)"
        )
        return 0
    finally:
        for uid in uids:
            cleanup = MemoryCollections(uid=uid)
            _delete_user_documents(db_client, cleanup)
            db_client.document(f"account_deletions/{uid}").delete()
        for snapshot in db_client.collection(daily_sweep.WINDOW_ADMISSION_COLLECTION).stream():
            snapshot.reference.delete()
        for snapshot in db_client.collection(daily_sweep.MODEL_INVOCATION_FENCE_COLLECTION).stream():
            snapshot.reference.delete()


if __name__ == "__main__":
    raise SystemExit(main())
