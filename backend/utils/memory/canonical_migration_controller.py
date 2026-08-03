"""Per-user canonical-memory migration controller and final verifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

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
from models.memory_evidence import SourceState
from models.product_memory import RESTRICTED_SENSITIVITY_LABELS, MemoryItemStatus, MemoryTier, ProcessingState
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
)


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
        evidence_id = _value(value, "evidence_id", None)
        if evidence_id is None and isinstance(value, str):
            evidence_id = value
        if evidence_id is not None and str(evidence_id).strip():
            result.append(str(evidence_id).strip())
    return sorted(set(result))


def _compatibility_eligible(item: Any) -> bool:
    tier = _value(item, "tier")
    tier_value = tier.value if isinstance(tier, MemoryTier) else str(tier)
    if tier_value not in {MemoryTier.short_term.value, MemoryTier.long_term.value}:
        return False
    promotion = _value(item, "promotion", {}) or {}
    content = _value(item, "content", "")
    return (
        _value(item, "status") in {MemoryItemStatus.active, MemoryItemStatus.active.value}
        and _value(item, "processing_state") in {ProcessingState.processed, ProcessingState.processed.value}
        and str(_value(item, "source_state", "active")) in {"SourceState.active", SourceState.active.value}
        and not set(_value(item, "sensitivity_labels", []) or []).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and _value(item, "user_review", None) is not False
        and promotion.get("user_review") is not False
        and isinstance(content, str)
        and bool(content.strip())
    )


def _projection_value(row: Any, key: str) -> Any:
    value = _value(row, key, None)
    if value is not None:
        return value
    payload = _value(row, "payload", {}) or {}
    return _value(payload, key, None)


def _projection_matches_item(row: Any, item: Any, fence: MigrationFence) -> bool:
    """Require payload identity to match the current canonical item, not only its id."""
    if _projection_value(row, "memory_id") != _value(item, "memory_id"):
        return False
    if _projection_value(row, "uid") != _value(item, "uid"):
        return False
    if _projection_value(row, "schema_version") != V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION:
        return False
    if _projection_value(row, "source") != V3_COMPATIBILITY_PROJECTION_SOURCE:
        return False
    if _projection_value(row, "account_generation") != fence.account_generation:
        return False
    if _projection_value(row, "projection_generation") != fence.account_generation:
        return False
    if _projection_value(row, "source_commit_id") != fence.observed_head_commit_id:
        return False
    if _projection_value(row, "projection_commit_id") != f"commit-{fence.observed_head_commit_id}":
        return False
    evidence_fence = f"head-{fence.observed_head_commit_id}"
    if _projection_value(row, "projection_evidence_fence") != evidence_fence:
        return False
    if any(
        _projection_value(row, field) is not True
        for field in ("write_convergence_complete", "delete_convergence_complete", "tombstone_convergence_complete")
    ):
        return False
    payload = _value(row, "memorydb", {}) or _value(row, "payload", {}) or {}
    item_tier = _value(item, "tier")
    item_tier = item_tier.value if hasattr(item_tier, "value") else item_tier
    if not (_value(payload, "content") == _value(item, "content") and _value(payload, "memory_tier") == item_tier):
        return False
    source_review = _value(item, "user_review", None)
    return source_review is None or _value(payload, "user_review") == source_review


def _assertion_matches_item(assertion: Any, item: Any) -> bool:
    if _value(assertion, "status", "active") != "active":
        return False
    if _value(assertion, "memory_id") != _value(item, "memory_id"):
        return False
    if _value(assertion, "item_revision") != _value(item, "item_revision"):
        return False
    if _value(assertion, "content_hash") != _value(item, "content_hash"):
        return False
    if sorted(set(str(value) for value in (_value(assertion, "evidence_ids", []) or []))) != _evidence_ids(item):
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
            or repeat_inventory.head_sequence != fence.observed_head_sequence
        ):
            errors.append("repeat inventory generation/head fence changed")
        if repeat_inventory.fingerprint != fence.inventory_fingerprint:
            errors.append("repeat inventory fingerprint changed")
        if (
            set(repeat_inventory.item_ids) != set(manifest.item_ids)
            or repeat_inventory.item_revisions != manifest.item_revisions
            or repeat_inventory.item_content_hashes != manifest.item_content_hashes
            or {key: sorted(set(value)) for key, value in repeat_inventory.item_evidence_ids.items()}
            != {key: sorted(set(value)) for key, value in manifest.item_evidence_ids.items()}
        ):
            errors.append("repeat inventory item revision/content/evidence fence changed")
    items = list(canonical_items)
    assertions = list(graph_assertions)
    item_by_id: Dict[Any, Any] = {}
    for item in items:
        memory_id = _value(item, "memory_id")
        if _value(item, "uid") != manifest.uid:
            errors.append(f"canonical item uid mismatch: {memory_id}")
        if memory_id not in manifest.item_ids:
            errors.append(f"canonical item is outside manifest: {memory_id}")
        if memory_id in item_by_id:
            errors.append(f"duplicate canonical item outcome: {memory_id}")
        item_by_id[memory_id] = item
    for memory_id in manifest.item_ids:
        item = item_by_id.get(memory_id)
        if item is None:
            errors.append(f"manifest item has no authoritative item or terminal outcome: {memory_id}")
            blocking.append(
                MigrationBlockingState(
                    code=MigrationBlockCode.verification_failed,
                    message="every manifest item must have an authoritative current item or terminal outcome",
                    item_id=str(memory_id),
                )
            )
            continue
        # A terminal outcome may be represented by a work/result row, but a
        # current item must still be at the exact inventory fence whenever its
        # identity fields are present.
        if _value(item, "item_revision", None) != manifest.item_revisions.get(memory_id):
            errors.append(f"canonical item revision fence changed: {memory_id}")
        if _value(item, "content_hash", None) != manifest.item_content_hashes.get(memory_id):
            errors.append(f"canonical item content hash fence changed: {memory_id}")
        if _evidence_ids(item) != sorted(set(manifest.item_evidence_ids.get(memory_id, []))):
            errors.append(f"canonical item evidence fence changed: {memory_id}")
    assertion_by_id: Dict[Any, Any] = {}
    for assertion in assertions:
        memory_id = _value(assertion, "memory_id")
        if _value(assertion, "uid") != manifest.uid:
            errors.append(f"graph assertion uid mismatch: {memory_id}")
        if memory_id not in manifest.item_ids:
            errors.append(f"graph assertion is outside manifest: {memory_id}")
        if memory_id in assertion_by_id:
            errors.append(f"duplicate graph assertion: {memory_id}")
        assertion_by_id[memory_id] = assertion
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
    compatibility_by_id: Dict[Any, Any] = {}
    for row in compatibility:
        memory_id = _projection_value(row, "memory_id")
        if _projection_value(row, "uid") != manifest.uid:
            errors.append(f"compatibility projection uid mismatch: {memory_id}")
        if memory_id in compatibility_by_id:
            errors.append(f"duplicate compatibility projection row: {memory_id}")
        compatibility_by_id[memory_id] = row
    expected_compatibility = {_value(item, "memory_id") for item in items if _compatibility_eligible(item)}
    missing_compat = sorted(str(item_id) for item_id in expected_compatibility - set(compatibility_by_id))
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
    stale_compat = sorted(str(item_id) for item_id in set(compatibility_by_id) - expected_compatibility)
    if stale_compat:
        errors.append("compatibility projection contains unexpected or stale rows: " + ",".join(stale_compat))
        blocking.append(
            MigrationBlockingState(
                code=MigrationBlockCode.projection_not_converged,
                message="compatibility projection must contain only current eligible items",
                retryable=True,
                details={"unexpected_memory_ids": stale_compat},
            )
        )
    stale_payload = sorted(
        str(memory_id)
        for memory_id in expected_compatibility
        if memory_id in compatibility_by_id
        and not _projection_matches_item(compatibility_by_id[memory_id], item_by_id.get(memory_id), fence)
    )
    if stale_payload:
        errors.append("compatibility projection payload is stale: " + ",".join(stale_payload))
        blocking.append(
            MigrationBlockingState(
                code=MigrationBlockCode.projection_not_converged,
                message="compatibility projection payload must match current revision, content, and evidence",
                retryable=True,
                details={"stale_memory_ids": stale_payload},
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

    _PHASE_ORDER = (
        MigrationPhase.inventoried,
        MigrationPhase.write_enrolled,
        MigrationPhase.staged,
        MigrationPhase.canonical_processing,
        MigrationPhase.graph_enrichment,
        MigrationPhase.projection_convergence,
        MigrationPhase.verified,
        MigrationPhase.read_cutover,
    )

    def __init__(self, *, store: Any, hooks: ControllerHooks, lease_ttl_seconds: float = 60.0):
        self.store = store
        self.hooks = hooks
        self.lease_ttl_seconds = lease_ttl_seconds

    def acquire(self, uid: str, owner_id: str) -> MigrationLease:
        return self.store.acquire_lease(uid, owner_id, ttl_seconds=self.lease_ttl_seconds)

    def renew(self, uid: str, lease: MigrationLease) -> MigrationLease:
        return self.store.renew_lease(uid, lease.owner_id, lease.ownership_epoch, ttl_seconds=self.lease_ttl_seconds)

    @classmethod
    def _phase_rank(cls, phase: MigrationPhase) -> int:
        return cls._PHASE_ORDER.index(phase)

    @classmethod
    def _phase_needs_work(
        cls, current: MigrationPhase, target: MigrationPhase, resume_phase: Optional[MigrationPhase]
    ) -> bool:
        if current in {MigrationPhase.failed, MigrationPhase.paused}:
            return resume_phase == target
        if current == MigrationPhase.read_cutover:
            return False
        return cls._phase_rank(current) < cls._phase_rank(target)

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
        if not dry_run:
            required_hooks = {
                "write_enroll": self.hooks.write_enroll,
                "stage": self.hooks.stage,
                "canonical_process": self.hooks.canonical_process,
                "graph_enrich": self.hooks.graph_enrich,
                "projection_converge": self.hooks.projection_converge,
                "verify": self.hooks.verify,
                "read_cutover": self.hooks.read_cutover,
            }
            missing_hooks = sorted(name for name, hook in required_hooks.items() if hook is None)
            if missing_hooks:
                raise MigrationOrchestrationError(
                    "apply mode requires concrete canonical migration hooks: " + ", ".join(missing_hooks)
                )
        inventory = self.inventory(uid=uid, owner_id=owner_id, dry_run=dry_run)
        manifest = CanonicalMigrationManifest.from_inventory(inventory)
        if dry_run:
            return MigrationRunResult(
                uid=uid, phase=MigrationPhase.inventoried, dry_run=True, manifest_id=manifest.manifest_id
            )
        checkpoint = self.store.read_checkpoint(uid)
        if checkpoint is not None and checkpoint.phase == MigrationPhase.read_cutover:
            return MigrationRunResult(
                uid=uid,
                phase=MigrationPhase.read_cutover,
                dry_run=False,
                manifest_id=checkpoint.manifest_id or manifest.manifest_id,
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
        persisted_manifest = self.store.read_manifest(uid, manifest.manifest_id)
        if persisted_manifest is None:
            self.store.write_manifest(manifest)
        else:
            if persisted_manifest.model_dump(exclude={"created_at"}) != manifest.model_dump(exclude={"created_at"}):
                raise MigrationOrchestrationError("persisted manifest fence does not match current inventory")
            manifest = persisted_manifest
        existing_records = {
            record.item_id: record for record in self.store.read_work_records(uid, manifest.manifest_id)
        }
        records: List[CanonicalMigrationWorkRecord] = []
        for item_id in manifest.item_ids:
            expected_fence = (
                manifest.item_revisions[item_id],
                manifest.item_content_hashes[item_id],
                sorted(set(manifest.item_evidence_ids[item_id])),
                manifest.fence.account_generation,
                manifest.fence.source_generation,
            )
            prior = existing_records.get(item_id)
            if prior is not None:
                prior_fence = (
                    prior.item_revision,
                    prior.content_hash,
                    sorted(set(prior.evidence_ids)),
                    prior.account_generation,
                    prior.source_generation,
                )
                if prior_fence != expected_fence:
                    raise MigrationOrchestrationError(f"durable work record fence changed: {item_id}")
                records.append(prior)
            else:
                records.append(
                    CanonicalMigrationWorkRecord(
                        uid=uid,
                        manifest_id=manifest.manifest_id,
                        item_id=item_id,
                        item_revision=manifest.item_revisions[item_id],
                        content_hash=manifest.item_content_hashes[item_id],
                        evidence_ids=list(manifest.item_evidence_ids[item_id]),
                        account_generation=manifest.fence.account_generation,
                        source_generation=manifest.fence.source_generation,
                    )
                )
        for record in records:
            self.store.upsert_work_record(record)
        phases = [
            (MigrationPhase.write_enrolled, self.hooks.write_enroll, manifest),
            (MigrationPhase.staged, self.hooks.stage, manifest),
            (MigrationPhase.canonical_processing, self.hooks.canonical_process, records),
            (MigrationPhase.graph_enrichment, self.hooks.graph_enrich, records),
            (MigrationPhase.projection_convergence, self.hooks.projection_converge, manifest),
        ]
        active_phase: Optional[MigrationPhase] = None
        try:
            for phase, hook, payload in phases:
                current = self.store.read_checkpoint(uid)
                if current is None or not self._phase_needs_work(current.phase, phase, current.resume_phase):
                    continue
                lease = self.renew(uid, lease)
                active_phase = phase
                cast(Callable[[str, Any], None], hook)(
                    uid, payload
                )  # orchestration delegates all writes/LLM work to hooks
                lease = self.renew(uid, lease)
                self.transition(uid=uid, target=phase, owner_id=owner_id, ownership_epoch=lease.ownership_epoch)
                active_phase = None
            if self.hooks.verify is not None:
                lease = self.renew(uid, lease)
                verification = self.hooks.verify(uid, manifest)
                lease = self.renew(uid, lease)
            else:
                verification = MigrationVerificationResult(passed=False, errors=("no verifier hook configured",))
            if verification.passed and verification.fence != manifest.fence:
                verification = MigrationVerificationResult(
                    passed=False,
                    errors=("verifier returned a missing or mismatched migration fence",),
                    fence=verification.fence,
                )
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
                lease = self.renew(uid, lease)
                self.hooks.read_cutover(uid, manifest.fence)
                lease = self.renew(uid, lease)
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
                        current.transition(
                            MigrationPhase.failed,
                            blocking=blocking,
                            lease=current.lease,
                            resume_phase=active_phase,
                        ),
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
