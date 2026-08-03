"""Per-user canonical-memory migration controller and final verifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

from models.memory_admission import valid_required_processing_receipt
from models.memory_migration import (
    CanonicalMigrationCheckpoint,
    CanonicalMigrationManifest,
    CanonicalMigrationWorkRecord,
    MigrationBlockCode,
    MigrationBlockingState,
    MigrationFence,
    MigrationInventory,
    MigrationLease,
    MigrationPhase,
)
from models.memory_promotion import PromotionGraphPlan
from models.product_memory import RESTRICTED_SENSITIVITY_LABELS, MemoryItemStatus, MemoryTier, ProcessingState


class MigrationOrchestrationError(RuntimeError):
    """A phase could not be completed without weakening a fence."""


@dataclass(frozen=True)
class MigrationVerificationResult:
    passed: bool
    errors: tuple[str, ...] = ()
    blocking: tuple[MigrationBlockingState, ...] = ()
    fence: Optional[MigrationFence] = None
    eligible_item_count: int = 0
    compatibility_item_count: int = 0
    drained_outbox_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "blocking": [item.model_dump(mode="json") for item in self.blocking],
            "eligible_item_count": self.eligible_item_count,
            "compatibility_item_count": self.compatibility_item_count,
            "drained_outbox_count": self.drained_outbox_count,
        }


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _item_eligible(item: Any) -> bool:
    tier = _value(item, "tier")
    tier_value = tier.value if isinstance(tier, MemoryTier) else str(tier)
    status = _value(item, "status")
    status_value = status.value if isinstance(status, MemoryItemStatus) else str(status)
    processing = _value(item, "processing_state")
    processing_value = processing.value if isinstance(processing, ProcessingState) else str(processing)
    source_state = _value(item, "source_state", "active")
    source_state_value = source_state.value if hasattr(source_state, "value") else str(source_state)
    sensitivity = set(_value(item, "sensitivity_labels", []) or [])
    promotion = _value(item, "promotion", {}) or {}
    return (
        tier_value == MemoryTier.long_term.value
        and status_value == MemoryItemStatus.active.value
        and processing_value == ProcessingState.processed.value
        and source_state_value == "active"
        and not sensitivity.intersection(RESTRICTED_SENSITIVITY_LABELS)
        and promotion.get("user_review") is not False
    )


def _evidence_ids(item: Any) -> List[str]:
    raw = _value(item, "evidence", None)
    if raw is None:
        raw = _value(item, "evidence_ids", []) or []
    result = []
    for value in raw:
        result.append(str(_value(value, "evidence_id", value)))
    return sorted(set(result))


def _assertion_matches_item(assertion: Any, item: Any) -> bool:
    if _value(assertion, "status", "active") != "active":
        return False
    if _value(assertion, "memory_id") != _value(item, "memory_id"):
        return False
    if _value(assertion, "item_revision") != _value(item, "item_revision"):
        return False
    if _value(assertion, "content_hash") != _value(item, "content_hash"):
        return False
    if sorted(_value(assertion, "evidence_ids", []) or []) != _evidence_ids(item):
        return False
    plan_raw = (_value(item, "promotion", {}) or {}).get("graph_plan")
    if not isinstance(plan_raw, dict):
        return False
    try:
        plan = PromotionGraphPlan.model_validate(plan_raw)
    except Exception:
        return False
    return (
        _value(assertion, "graph_plan_hash") == plan.plan_hash
        and _value(assertion, "subject_entity_id") == plan.subject_entity_id
        and _value(assertion, "predicate") == plan.predicate
        and _value(assertion, "arguments") == plan.arguments
    )


def verify_migration_postconditions(
    *,
    manifest: CanonicalMigrationManifest,
    canonical_items: Iterable[Any],
    graph_assertions: Iterable[Any],
    compatibility_projection: Iterable[Any],
    outbox_events: Iterable[Any],
    repeat_inventory: Optional[MigrationInventory] = None,
    bounded_delta: bool = False,
) -> MigrationVerificationResult:
    """Verify all read-cutover postconditions at one immutable fence."""
    errors: List[str] = []
    blocking: List[MigrationBlockingState] = []
    fence = manifest.fence
    if not (manifest.stable_inventory or manifest.bounded_delta or bounded_delta):
        if repeat_inventory is None or repeat_inventory.fingerprint != fence.inventory_fingerprint:
            errors.append("inventory is not stable, repeated, or bounded-delta")
            blocking.append(
                MigrationBlockingState(
                    code=MigrationBlockCode.inventory_unstable,
                    message="migration inventory requires a stable repeat or explicit bounded delta",
                    retryable=True,
                )
            )
    if repeat_inventory is not None:
        if (
            repeat_inventory.account_generation != fence.account_generation
            or repeat_inventory.source_generation != fence.source_generation
            or repeat_inventory.head_commit_id != fence.observed_head_commit_id
        ):
            errors.append("repeat inventory generation/head fence changed")
    items = list(canonical_items)
    assertions = list(graph_assertions)
    assertion_by_id = {_value(value, "memory_id"): value for value in assertions}
    eligible = [item for item in items if _item_eligible(item)]
    for item in items:
        promotion = _value(item, "promotion", {}) or {}
        memory_id = _value(item, "memory_id")
        if promotion.get("required") and not valid_required_processing_receipt(
            content=_value(item, "content", "") or "",
            item_revision=int(_value(item, "item_revision", 0) or 0),
            promotion=promotion,
        ):
            errors.append(f"required processing receipt missing or stale: {memory_id}")
            blocking.append(
                MigrationBlockingState(
                    code=MigrationBlockCode.missing_required_processing_receipt,
                    message="required processing receipt is missing or stale; migration cannot fabricate one",
                    item_id=str(memory_id),
                    retryable=False,
                )
            )
    for item in eligible:
        memory_id = _value(item, "memory_id")
        if _value(item, "account_generation", fence.account_generation) != fence.account_generation:
            errors.append(f"item account generation changed after inventory fence: {memory_id}")
        item_sequence = _value(item, "source_commit_sequence", _value(item, "ledger_sequence", 0)) or 0
        if int(item_sequence) > fence.observed_head_sequence:
            errors.append(f"item is newer than migration head fence: {memory_id}")
        assertion = assertion_by_id.get(memory_id)
        if assertion is None or not _assertion_matches_item(assertion, item):
            errors.append(f"graph assertion does not match eligible current item: {memory_id}")
            blocking.append(
                MigrationBlockingState(
                    code=MigrationBlockCode.verification_failed,
                    message="eligible Long-term item lacks an exact current graph assertion",
                    item_id=str(memory_id),
                )
            )
    compatibility = list(compatibility_projection)
    compatibility_ids = {_value(value, "memory_id") for value in compatibility}
    expected_compatibility = {
        _value(item, "memory_id")
        for item in items
        if _value(item, "status") in {MemoryItemStatus.active, MemoryItemStatus.active.value}
        and _value(item, "processing_state") in {ProcessingState.processed, ProcessingState.processed.value}
        and (
            _value(item, "tier")
            in {MemoryTier.short_term, MemoryTier.long_term, MemoryTier.short_term.value, MemoryTier.long_term.value}
        )
    }
    missing_compat = sorted(str(item_id) for item_id in expected_compatibility - compatibility_ids)
    if missing_compat:
        errors.append("compatibility projection incomplete: " + ",".join(missing_compat))
        blocking.append(
            MigrationBlockingState(
                code=MigrationBlockCode.projection_not_converged,
                message="processed Short-term/Long-term items are missing compatibility projection",
                retryable=True,
                details={"missing_memory_ids": missing_compat},
            )
        )
    relevant_outbox = []
    for event in outbox_events:
        sequence = _value(event, "commit_sequence", _value(event, "sequence", 0)) or 0
        generation = _value(event, "account_generation", fence.account_generation)
        status = _value(event, "status", "")
        status = status.value if hasattr(status, "value") else str(status)
        if (
            generation == fence.account_generation
            and int(sequence) <= fence.observed_head_sequence
            and status
            in {
                "pending",
                "processing",
                "retryable_failure",
                "dead_letter",
            }
        ):
            relevant_outbox.append(event)
    if relevant_outbox:
        errors.append("relevant retry/dead-letter/pending outbox remains through migration fence")
        blocking.append(
            MigrationBlockingState(
                code=MigrationBlockCode.outbox_not_drained,
                message="outbox has not converged through the migration head fence",
                retryable=True,
            )
        )
    return MigrationVerificationResult(
        passed=not errors,
        errors=tuple(errors),
        blocking=tuple(blocking),
        fence=fence,
        eligible_item_count=len(eligible),
        compatibility_item_count=len(compatibility),
        drained_outbox_count=len(relevant_outbox),
    )


final_verifier = verify_migration_postconditions


class MigrationCallbacks(Protocol):
    def inventory(self, uid: str) -> MigrationInventory: ...


@dataclass
class ControllerHooks:
    inventory: Callable[[str], MigrationInventory]
    write_enroll: Optional[Callable[[str, CanonicalMigrationManifest], None]] = None
    stage: Optional[Callable[[str, CanonicalMigrationManifest], None]] = None
    canonical_process: Optional[Callable[[str, List[CanonicalMigrationWorkRecord]], None]] = None
    graph_enrich: Optional[Callable[[str, List[CanonicalMigrationWorkRecord]], None]] = None
    projection_converge: Optional[Callable[[str, CanonicalMigrationManifest], None]] = None
    verify: Optional[Callable[[str, CanonicalMigrationManifest], MigrationVerificationResult]] = None
    read_cutover: Optional[Callable[[str, MigrationFence], None]] = None


@dataclass(frozen=True)
class MigrationRunResult:
    uid: str
    phase: MigrationPhase
    dry_run: bool
    manifest_id: Optional[str] = None
    verification: Optional[MigrationVerificationResult] = None
    blocking: Optional[MigrationBlockingState] = None


class CanonicalMigrationController:
    """Lease-owned, resumable orchestration for exactly one user."""

    def __init__(self, *, store: Any, hooks: ControllerHooks, lease_ttl_seconds: float = 60.0):
        self.store = store
        self.hooks = hooks
        self.lease_ttl_seconds = lease_ttl_seconds

    def acquire(self, uid: str, owner_id: str) -> MigrationLease:
        return self.store.acquire_lease(uid, owner_id, ttl_seconds=self.lease_ttl_seconds)

    def renew(self, uid: str, lease: MigrationLease) -> MigrationLease:
        return self.store.renew_lease(uid, lease.owner_id, lease.ownership_epoch, ttl_seconds=self.lease_ttl_seconds)

    def transition(
        self,
        *,
        uid: str,
        target: MigrationPhase,
        owner_id: str,
        ownership_epoch: int,
        blocking: Optional[MigrationBlockingState] = None,
    ) -> CanonicalMigrationCheckpoint:
        current = self.store.read_checkpoint(uid)
        if current is None:
            raise MigrationOrchestrationError("cannot transition without an inventoried checkpoint")
        if (
            current.lease is None
            or current.lease.owner_id != owner_id
            or current.lease.ownership_epoch != ownership_epoch
        ):
            raise MigrationOrchestrationError("migration transition requires current lease epoch")
        next_checkpoint = current.transition(target, blocking=blocking, lease=current.lease)
        return self.store.compare_and_set_checkpoint(
            uid,
            current.version,
            next_checkpoint,
            owner_id=owner_id,
            ownership_epoch=ownership_epoch,
        )

    def inventory(self, *, uid: str, owner_id: str, dry_run: bool = False) -> MigrationInventory:
        inventory = self.hooks.inventory(uid)
        if dry_run:
            return inventory
        fence = MigrationFence(
            account_generation=inventory.account_generation,
            source_generation=inventory.source_generation,
            inventory_id=inventory.inventory_id,
            inventory_fingerprint=inventory.fingerprint,
            observed_head_commit_id=inventory.head_commit_id,
            observed_head_sequence=inventory.head_sequence,
        )
        checkpoint = CanonicalMigrationCheckpoint(uid=uid, phase=MigrationPhase.inventoried, fence=fence)
        existing = self.store.read_checkpoint(uid)
        if existing is None:
            self.store.compare_and_set_checkpoint(uid, -1, checkpoint)
        elif existing.fence != fence:
            raise MigrationOrchestrationError("inventory fence changed for an existing migration")
        return inventory

    def run_user(self, *, uid: str, owner_id: str, dry_run: bool = True, confirm: bool = False) -> MigrationRunResult:
        if not dry_run and not confirm:
            raise ValueError("apply mode requires explicit confirmation")
        inventory = self.inventory(uid=uid, owner_id=owner_id, dry_run=dry_run)
        manifest = CanonicalMigrationManifest.from_inventory(inventory)
        if dry_run:
            return MigrationRunResult(
                uid=uid, phase=MigrationPhase.inventoried, dry_run=True, manifest_id=manifest.manifest_id
            )
        lease = self.acquire(uid, owner_id)
        checkpoint = self.store.read_checkpoint(uid)
        if checkpoint is None:
            raise MigrationOrchestrationError("checkpoint disappeared while acquiring migration lease")
        checkpoint = self.store.compare_and_set_checkpoint(
            uid,
            checkpoint.version,
            checkpoint.model_copy(update={"lease": lease}),
            owner_id=owner_id,
            ownership_epoch=lease.ownership_epoch,
        )
        self.store.write_manifest(manifest)
        records = [
            CanonicalMigrationWorkRecord(
                uid=uid,
                manifest_id=manifest.manifest_id,
                item_id=item_id,
                item_revision=manifest.item_revisions.get(item_id, 0),
                content_hash=manifest.item_content_hashes.get(item_id, f"inventory_missing:{item_id}"),
                evidence_ids=list(manifest.item_evidence_ids.get(item_id, [])),
                account_generation=manifest.fence.account_generation,
                source_generation=manifest.fence.source_generation,
            )
            for item_id in manifest.item_ids
        ]
        for record in records:
            self.store.upsert_work_record(record)
        manifest_phases = [
            (MigrationPhase.write_enrolled, self.hooks.write_enroll, manifest),
            (MigrationPhase.staged, self.hooks.stage, manifest),
            (MigrationPhase.projection_convergence, self.hooks.projection_converge, manifest),
        ]
        work_record_phases = [
            (MigrationPhase.canonical_processing, self.hooks.canonical_process, records),
            (MigrationPhase.graph_enrichment, self.hooks.graph_enrich, records),
        ]
        try:
            for phase, hook, payload in manifest_phases[:2]:
                current = self.store.read_checkpoint(uid)
                if current is None or current.phase == phase:
                    continue
                if current.phase in {MigrationPhase.failed, MigrationPhase.paused}:
                    if current.resume_phase != phase:
                        continue
                if hook is not None:
                    hook(uid, payload)  # orchestration delegates all writes/LLM work to hooks
                self.transition(uid=uid, target=phase, owner_id=owner_id, ownership_epoch=lease.ownership_epoch)
            for phase, hook, payload in work_record_phases:
                current = self.store.read_checkpoint(uid)
                if current is None or current.phase == phase:
                    continue
                if current.phase in {MigrationPhase.failed, MigrationPhase.paused}:
                    if current.resume_phase != phase:
                        continue
                if hook is not None:
                    hook(uid, payload)
                self.transition(uid=uid, target=phase, owner_id=owner_id, ownership_epoch=lease.ownership_epoch)
            for phase, hook, payload in manifest_phases[2:]:
                current = self.store.read_checkpoint(uid)
                if current is None or current.phase == phase:
                    continue
                if current.phase in {MigrationPhase.failed, MigrationPhase.paused}:
                    if current.resume_phase != phase:
                        continue
                if hook is not None:
                    hook(uid, payload)
                self.transition(uid=uid, target=phase, owner_id=owner_id, ownership_epoch=lease.ownership_epoch)
            if self.hooks.verify is not None:
                verification = self.hooks.verify(uid, manifest)
            else:
                verification = MigrationVerificationResult(passed=False, errors=("no verifier hook configured",))
            if not verification.passed:
                blocking = (
                    verification.blocking[0]
                    if verification.blocking
                    else MigrationBlockingState(
                        code=MigrationBlockCode.verification_failed,
                        message="migration postconditions failed",
                        retryable=True,
                    )
                )
                current = self.store.read_checkpoint(uid)
                if current is not None:
                    self.store.compare_and_set_checkpoint(
                        uid,
                        current.version,
                        current.transition(MigrationPhase.paused, blocking=blocking, lease=current.lease),
                        owner_id=owner_id,
                        ownership_epoch=lease.ownership_epoch,
                    )
                return MigrationRunResult(
                    uid=uid,
                    phase=MigrationPhase.paused,
                    dry_run=False,
                    manifest_id=manifest.manifest_id,
                    verification=verification,
                    blocking=blocking,
                )
            self.transition(
                uid=uid, target=MigrationPhase.verified, owner_id=owner_id, ownership_epoch=lease.ownership_epoch
            )
            if self.hooks.read_cutover is not None:
                self.hooks.read_cutover(uid, manifest.fence)
            self.transition(
                uid=uid, target=MigrationPhase.read_cutover, owner_id=owner_id, ownership_epoch=lease.ownership_epoch
            )
            return MigrationRunResult(
                uid=uid,
                phase=MigrationPhase.read_cutover,
                dry_run=False,
                manifest_id=manifest.manifest_id,
                verification=verification,
            )
        except Exception as exc:
            current = self.store.read_checkpoint(uid)
            if current is not None and current.phase not in {MigrationPhase.read_cutover, MigrationPhase.failed}:
                blocking = MigrationBlockingState(
                    code=(
                        MigrationBlockCode.lease_lost
                        if type(exc).__name__ in {"MigrationLeaseLost", "MigrationLeaseUnavailable"}
                        else MigrationBlockCode.verification_failed
                    ),
                    message=type(exc).__name__,
                    retryable=type(exc).__name__ not in {"MigrationLeaseLost", "MigrationLeaseUnavailable"},
                )
                try:
                    self.store.compare_and_set_checkpoint(
                        uid,
                        current.version,
                        current.transition(MigrationPhase.failed, blocking=blocking, lease=current.lease),
                        owner_id=owner_id,
                        ownership_epoch=lease.ownership_epoch,
                    )
                except Exception:
                    pass
            raise


__all__ = [
    "CanonicalMigrationController",
    "ControllerHooks",
    "MigrationOrchestrationError",
    "MigrationRunResult",
    "MigrationVerificationResult",
    "final_verifier",
    "verify_migration_postconditions",
]
