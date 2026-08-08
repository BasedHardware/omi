"""Scheduler-owned enrollment and bounded staging for canonical-memory cohorts.

LIFECYCLE: permanent

The code-owned cohort selector is the only entitlement input.  This coordinator
turns the exact inert state created by canonical onboarding into the existing
write-stage control document, then delegates historical rows to the bounded,
checkpointed backfill owner.  It intentionally never opens global read gates or
marks a user projection-ready: read cutover needs its own trusted generation and
compatibility-projection proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database import document_store
from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from scripts.enroll_canonical_memory_user import build_user_control_state
from utils.memory.canonical_legacy_backfill import (
    CanonicalLegacyBackfillConfig,
    CanonicalLegacyBackfillPage,
    run_canonical_legacy_backfill_page,
)
from utils.memory.bulk_legacy_backfill import FirestoreCheckpointStore, MigrationState
from utils.memory.canonical_memory_onboarding import (
    ONBOARDING_ACCOUNT_GENERATION,
    CanonicalMemoryOnboardingReport,
    reconcile_canonical_memory_onboarding,
)
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationReadError,
    read_memory_v3_trusted_account_generation,
)
from utils.memory.v3.limited_rollout_config import build_whitelisted_user_control_state


@dataclass(frozen=True)
class CanonicalCohortLifecycleReport:
    onboarding: CanonicalMemoryOnboardingReport
    write_enrolled_uids: tuple[str, ...]
    preserved_uids: tuple[str, ...]
    backfill_ready_uids: tuple[str, ...]
    generation_reconciled_uids: tuple[str, ...]
    backfill: CanonicalLegacyBackfillPage
    generation_reconcile_errors: tuple[str, ...] = ()


def _inert_control_payload(uid: str) -> dict[str, Any]:
    return build_whitelisted_user_control_state(
        uid=uid,
        account_generation=ONBOARDING_ACCOUNT_GENERATION,
        mode=MemoryRolloutMode.off,
        projection_ready=False,
        default_memory_grant=False,
        archive_grant=False,
    )


def _write_control_payload(
    uid: str,
    *,
    account_generation: int = ONBOARDING_ACCOUNT_GENERATION,
) -> dict[str, Any]:
    """Build the existing write-stage contract without read access."""
    return build_user_control_state(
        uid=uid,
        stage="write",
        account_generation=account_generation,
        default_memory_grant=False,
        archive_grant=False,
    )


def _is_existing_write_or_read_control(*, uid: str, payload: dict[str, Any]) -> bool:
    expected = _write_control_payload(uid)
    if payload.get("uid") != uid or payload.get("schema_version") != expected["schema_version"]:
        return False
    if payload.get("mode") not in {"write", "read"}:
        return False
    if payload.get("persistent_memory_writes_started") is not True or payload.get("writes_blocked") is not False:
        return False
    gates = payload.get("stage_gates")
    return isinstance(gates, dict) and gates.get("shadow") == "passed" and gates.get("write") == "passed"


def _is_scheduler_owned_write_control(*, uid: str, payload: dict[str, Any]) -> bool:
    account_generation = payload.get("account_generation")
    return (
        not isinstance(account_generation, bool)
        and isinstance(account_generation, int)
        and account_generation >= 0
        and payload == _write_control_payload(uid, account_generation=account_generation)
    )


def _enroll_inert_user_for_writes_txn(tx: Any, control_path: str, *, uid: str) -> bool:
    snapshot = tx.get(control_path)
    if getattr(snapshot, "exists", False) is not True:
        raise RuntimeError("missing_onboarded_control_state")
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        raise RuntimeError("malformed_onboarded_control_state")
    if payload == _inert_control_payload(uid):
        tx.set(control_path, _write_control_payload(uid))
        return True
    if _is_existing_write_or_read_control(uid=uid, payload=payload):
        return False
    raise RuntimeError("unsupported_canonical_rollout_state")


def _enroll_inert_user_for_writes(*, uid: str) -> bool:
    """Advance only the exact scheduler-created inert control state.

    A pre-existing rollout document is not an activation request.  Matching the
    complete inert payload makes the scheduler idempotent and ensures a manual,
    malformed, or already-progressed state is never silently overwritten.
    """
    control_path = MemoryCollections(uid=uid).memory_control_state
    return document_store.run_transaction(lambda tx: _enroll_inert_user_for_writes_txn(tx, control_path, uid=uid))


def _reconcile_terminal_backfill_generation_txn(tx: Any, control_path: str, *, uid: str) -> bool:
    snapshot = tx.get(control_path)
    if getattr(snapshot, "exists", False) is not True:
        raise RuntimeError("missing_write_control_after_backfill")
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        raise RuntimeError("malformed_write_control_after_backfill")
    if not _is_scheduler_owned_write_control(uid=uid, payload=payload):
        # Read controls and manual write controls need their own explicit
        # rollout ceremony.  Updating either here could reopen a stale read.
        return False
    # The trusted state head and control write are in the same transaction. If
    # either changes, the store retries the callback instead of committing a
    # stale generation into the scheduler-owned control state. Read ownership
    # first so manual/read controls never depend on a scheduler-only head.
    trusted = read_memory_v3_trusted_account_generation(uid=uid, tx=tx)
    account_generation = trusted.require_account_generation()
    tx.set(control_path, _write_control_payload(uid, account_generation=account_generation))
    return True


def _reconcile_terminal_backfill_generation(*, uid: str) -> bool:
    """Fence the scheduler-owned write control to the trusted post-backfill head."""
    control_path = MemoryCollections(uid=uid).memory_control_state
    return document_store.run_transaction(
        lambda tx: _reconcile_terminal_backfill_generation_txn(tx, control_path, uid=uid)
    )


def run_canonical_cohort_lifecycle() -> CanonicalCohortLifecycleReport:
    """Onboard, safely enroll, and stage one bounded page for the code cohort."""
    onboarding = reconcile_canonical_memory_onboarding()
    write_enrolled: list[str] = []
    preserved: list[str] = []
    for uid in list_canonical_cohort_uids():
        if _enroll_inert_user_for_writes(uid=uid):
            write_enrolled.append(uid)
        else:
            preserved.append(uid)

    backfill = run_canonical_legacy_backfill_page(config=CanonicalLegacyBackfillConfig(dry_run=False))
    checkpoint_store = FirestoreCheckpointStore()
    backfill_ready = tuple(
        uid for uid in list_canonical_cohort_uids() if checkpoint_store.read(uid).state == MigrationState.read_ready
    )
    # One principal's malformed or missing trusted state must fail closed for
    # that principal only. Raising here starved every other cohort user's
    # lifecycle progression on each scheduled run.
    generation_reconciled: list[str] = []
    reconcile_errors: list[str] = []
    for uid in backfill_ready:
        try:
            if _reconcile_terminal_backfill_generation(uid=uid):
                generation_reconciled.append(uid)
        except V3TrustedAccountGenerationReadError as exc:
            if exc.reason == V3AccountGenerationFailureReason.MISSING_STATE_HEAD:
                # A read_ready checkpoint without a migrated state head is a
                # legacy principal that has not produced one yet: preserved,
                # reconciled once the head exists, and not a cohort error.
                continue
            reconcile_errors.append(f"uid={uid}: generation_reconcile:{exc.reason.value}")
        except RuntimeError as exc:
            reconcile_errors.append(f"uid={uid}: generation_reconcile:{exc}")
    return CanonicalCohortLifecycleReport(
        onboarding=onboarding,
        write_enrolled_uids=tuple(write_enrolled),
        preserved_uids=tuple(preserved),
        backfill_ready_uids=backfill_ready,
        generation_reconciled_uids=tuple(generation_reconciled),
        backfill=backfill,
        generation_reconcile_errors=tuple(reconcile_errors),
    )


__all__ = [
    "CanonicalCohortLifecycleReport",
    "run_canonical_cohort_lifecycle",
]
