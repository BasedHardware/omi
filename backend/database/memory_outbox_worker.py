"""Bounded consumer for canonical memory projection and vector outbox events.

The canonical Firestore item is always reloaded before an external projection
write.  Event payloads carry only fences and intent; they are never used as a
source of memory content.

Side effects are injected deliberately.  The database layer cannot import the
``utils.memory`` adapters without reversing the backend import hierarchy, and
the worker requires each adapter to return ``True`` before it writes a
``delivered`` acknowledgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast

from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1 import transactional as _firestore_transactional  # type: ignore[reportAssignmentType,reportUnknownMemberType]

from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from database.durable_queue import (
    ProcessOutcome,
    QueuePolicy,
    decide_attempt,
    drain_isolated,
    oldest_ready_age_seconds,
)
from database.firestore_index_registry import (
    DUE_MEMORY_OUTBOX_QUERY,
    EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
)
from database.memory_collections import MemoryCollections
from database.read_boundary import MalformedDocError, parse_snapshot_strict
from models.memory_apply import (
    MemoryControlState,
    MemoryOutboxEvent,
    MemoryOutboxEventType,
    MemoryOutboxStatus,
)
from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
)

_SUPPORTED_EVENT_TYPES = frozenset(
    {
        MemoryOutboxEventType.projection_sync.value,
        MemoryOutboxEventType.vector_sync.value,
    }
)
_DUE_STATUSES = (
    MemoryOutboxStatus.pending.value,
    MemoryOutboxStatus.retryable_failure.value,
)
_PROVIDER_CONVERGENCE_ATTEMPTS = 5
_PROVIDER_STATE_RACE_ERROR = "provider_state_changed_during_delivery"
_PROVIDER_REPAIR_REQUIRED_ERROR_CODES = frozenset(
    {
        _PROVIDER_STATE_RACE_ERROR,
        "projection_upsert_failed",
        "projection_delete_failed",
        "vector_upsert_failed",
        "vector_delete_failed",
    }
)


@dataclass(frozen=True)
class CanonicalMemoryOutboxWorkerConfig:
    """Server-owned bounds for one canonical outbox worker tick."""

    worker_id: str
    limit: int = 25
    scan_limit: int = 100
    lease_seconds: int = 300
    max_attempts: int = 5
    base_backoff_seconds: int = 30
    max_backoff_seconds: int = 1800


@dataclass(frozen=True)
class CanonicalMemoryOutboxSideEffects:
    """Strict adapters used by the canonical outbox consumer.

    Every callback must be idempotent and return exactly ``True`` only when the
    desired external state is present.  This explicit contract prevents legacy
    best-effort helpers from turning a swallowed provider failure into a
    delivered acknowledgement.
    """

    projection_upsert: Callable[[MemoryItem, int], bool]
    projection_delete: Callable[[str, str, int], bool]
    vector_upsert: Callable[[MemoryItem, str], bool]
    vector_delete: Callable[[str, str], bool]


@dataclass(frozen=True)
class LeasedMemoryOutboxEvent:
    """One claimed document plus the ownership epoch required for settlement."""

    path: str
    document_id: str
    raw_event: Dict[str, Any]
    worker_id: str
    lease_epoch: int


@dataclass(frozen=True)
class _ProcessOutcome:
    settled_reason: str
    side_effect_action: Optional[str] = None
    stale: bool = False
    barrier: bool = False


@dataclass(frozen=True)
class _AuthoritativeProjectionState:
    """Current canonical state whose exact provider effect must converge."""

    account_generation: int
    item: Optional[MemoryItem]
    projection_writes_blocked: bool = False

    @property
    def fence(self) -> Tuple[Any, ...]:
        if self.item is None:
            return (self.account_generation, self.projection_writes_blocked, None)
        return (
            self.account_generation,
            self.projection_writes_blocked,
            self.item.uid,
            self.item.account_generation,
            self.item.item_revision,
            self.item.content_hash,
            self.item.ledger_commit_id,
            self.item.tier.value,
            self.item.status.value,
            self.item.processing_state.value,
            self.item.source_state.value,
            tuple(sorted(self.item.sensitivity_labels)),
            (self.item.promotion or {}).get("user_review"),
        )


class _ProcessingFailure(Exception):
    """Sanitized processing failure safe to persist on an outbox document."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def run_canonical_memory_outbox_worker_tick(
    *,
    db_client: Any,
    uid: str,
    config: CanonicalMemoryOutboxWorkerConfig,
    side_effects: CanonicalMemoryOutboxSideEffects,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Lease, process, and settle at most ``config.limit`` normal outbox events.

    This is the production integration seam.  It performs Firestore queries and
    ownership-fenced transactions itself; a scheduler or Cloud Run job only
    needs to supply a Firestore client, one uid, server-owned bounds, and strict
    projection/vector adapters.
    """

    observed_now = _observed_now(now)
    _validate_tick_inputs(uid=uid, config=config, side_effects=side_effects)
    summary = _empty_summary(uid=uid, config=config)

    try:
        leases = lease_canonical_memory_outbox_events(
            db_client=db_client,
            uid=uid,
            worker_id=config.worker_id,
            limit=config.limit,
            scan_limit=config.scan_limit,
            lease_seconds=config.lease_seconds,
            now=observed_now,
        )
    except Exception:
        summary["errors"].append({"stage": "lease", "code": "lease_query_failed"})
        return summary

    summary["leased_count"] = len(leases)
    created_ats = [
        lease.raw_event.get("created_at") for lease in leases if isinstance(lease.raw_event.get("created_at"), datetime)
    ]
    summary["oldest_ready_age_seconds"] = oldest_ready_age_seconds(created_ats, now=observed_now)

    def process_one(lease: Any) -> ProcessOutcome:
        try:
            outcome = _process_leased_event(
                db_client=db_client,
                requested_uid=uid,
                lease=lease,
                side_effects=side_effects,
            )
        except _ProcessingFailure as exc:
            _settle_failure(
                db_client=db_client,
                lease=lease,
                config=config,
                error_code=exc.code,
                now=observed_now,
                summary=summary,
            )
            return ProcessOutcome.retry(exc.code, reason=exc.code)
        except Exception:
            _settle_failure(
                db_client=db_client,
                lease=lease,
                config=config,
                error_code="processing_failed",
                now=observed_now,
                summary=summary,
            )
            return ProcessOutcome.retry("processing_failed", reason="processing_failed")

        delivered = _ack_leased_event(
            db_client=db_client,
            lease=lease,
            patch={
                "status": MemoryOutboxStatus.delivered.value,
                "delivered_at": observed_now,
                "updated_at": observed_now,
                "settled_reason": outcome.settled_reason,
                "side_effect_action": outcome.side_effect_action,
                "last_error": None,
                "last_error_code": None,
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )
        if not delivered:
            summary["ack_failed_count"] += 1
            summary["errors"].append(
                {
                    "stage": "delivered_ack",
                    "event_id": lease.document_id,
                    "code": "lease_ownership_lost",
                }
            )
            return ProcessOutcome.retry("lease_ownership_lost", reason="lease_ownership_lost")

        summary["delivered_count"] += 1
        summary["stale_settled_count"] += int(outcome.stale)
        summary["barrier_count"] += int(outcome.barrier)
        summary["actions"].append(
            {
                "event_id": lease.document_id,
                "action": outcome.side_effect_action or outcome.settled_reason,
            }
        )
        return ProcessOutcome.ack()

    drain_isolated(leases, process_one)
    return summary


def lease_canonical_memory_outbox_events(
    *,
    db_client: Any,
    uid: str,
    worker_id: str,
    limit: int = 25,
    scan_limit: int = 100,
    lease_seconds: int = 300,
    now: Optional[datetime] = None,
) -> List[LeasedMemoryOutboxEvent]:
    """Claim due normal events and expired normal-event leases.

    Pending and retryable events use the existing ``status, available_at``
    Firestore index.  Expired processing leases use the existing
    ``event_type, status, lease_expires_at`` index.  Candidate scanning and
    successful claims are both bounded.
    """

    observed_now = _observed_now(now)
    if not uid.strip():
        raise ValueError("uid is required")
    if not worker_id.strip():
        raise ValueError("worker_id is required")
    if limit < 1:
        raise ValueError("limit must be positive")
    if scan_limit < limit:
        raise ValueError("scan_limit must be at least limit")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    collection_path = MemoryCollections(uid=uid).memory_outbox
    collection = db_client.collection(collection_path)
    snapshots: Dict[str, Any] = {}

    for status in _DUE_STATUSES:
        query = DUE_MEMORY_OUTBOX_QUERY.build(
            collection,
            {"status": status, "available_at": observed_now},
            field_filter_factory=FieldFilter,
        ).limit(scan_limit)
        _collect_supported_snapshots(snapshots, query.stream(), collection_path=collection_path)

    for event_type in _SUPPORTED_EVENT_TYPES:
        query = EXPIRED_MEMORY_OUTBOX_LEASE_QUERY.build(
            collection,
            {
                "event_type": event_type,
                "status": MemoryOutboxStatus.processing.value,
                "lease_expires_at": observed_now,
            },
            field_filter_factory=FieldFilter,
        ).limit(scan_limit)
        _collect_supported_snapshots(snapshots, query.stream(), collection_path=collection_path)

    ordered = sorted(snapshots.items(), key=lambda item: _candidate_sort_key(item[0], item[1]))
    lease_expires_at = observed_now + timedelta(seconds=lease_seconds)
    claimed: List[LeasedMemoryOutboxEvent] = []
    for path, _ in ordered:
        if len(claimed) >= limit:
            break
        lease = _run_transaction(
            db_client,
            _claim_event_transaction,
            db_client,
            path,
            worker_id,
            observed_now,
            lease_expires_at,
        )
        if lease is not None:
            claimed.append(lease)
    return claimed


def _collect_supported_snapshots(
    output: Dict[str, Any],
    snapshots: Iterable[Any],
    *,
    collection_path: str,
) -> None:
    for snapshot in snapshots:
        raw = _snapshot_dict(snapshot)
        if _enum_value(raw.get("event_type")) not in _SUPPORTED_EVENT_TYPES:
            continue
        path = _snapshot_path(snapshot, collection_path)
        output[path] = snapshot


def _candidate_sort_key(path: str, snapshot: Any) -> Tuple[datetime, int, str]:
    raw = _snapshot_dict(snapshot)
    timestamp = _coerce_timestamp(raw.get("available_at")) or _coerce_timestamp(raw.get("lease_expires_at"))
    return (
        timestamp or datetime.max.replace(tzinfo=timezone.utc),
        _safe_nonnegative_int(raw.get("commit_sequence")),
        path,
    )


def _claim_event_transaction(
    transaction: Any,
    db_client: Any,
    path: str,
    worker_id: str,
    now: datetime,
    lease_expires_at: datetime,
) -> Optional[LeasedMemoryOutboxEvent]:
    ref = db_client.document(path)
    snapshot = ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        return None
    raw = _snapshot_dict(snapshot)
    if not _is_claimable(raw, now=now):
        return None

    lease_epoch = _safe_nonnegative_int(raw.get("lease_epoch")) + 1
    transaction.update(
        ref,
        {
            "status": MemoryOutboxStatus.processing.value,
            "lease_owner": worker_id,
            "lease_epoch": lease_epoch,
            "leased_at": now,
            "lease_expires_at": lease_expires_at,
            "updated_at": now,
        },
    )
    return LeasedMemoryOutboxEvent(
        path=path,
        document_id=path.rsplit("/", 1)[-1],
        raw_event=raw,
        worker_id=worker_id,
        lease_epoch=lease_epoch,
    )


def _is_claimable(raw: Dict[str, Any], *, now: datetime) -> bool:
    if _enum_value(raw.get("event_type")) not in _SUPPORTED_EVENT_TYPES:
        return False
    status = _enum_value(raw.get("status"))
    if status in _DUE_STATUSES:
        available_at = _coerce_timestamp(raw.get("available_at"))
        return available_at is not None and available_at <= now
    if status == MemoryOutboxStatus.processing.value:
        lease_expires_at = _coerce_timestamp(raw.get("lease_expires_at"))
        return lease_expires_at is not None and lease_expires_at <= now
    return False


def _process_leased_event(
    *,
    db_client: Any,
    requested_uid: str,
    lease: LeasedMemoryOutboxEvent,
    side_effects: CanonicalMemoryOutboxSideEffects,
) -> _ProcessOutcome:
    try:
        event = parse_snapshot_strict(
            MemoryOutboxEvent,
            lease,
            payload_from_snapshot=lambda leased_event: leased_event.raw_event,
        )
    except MalformedDocError:
        raise _ProcessingFailure("invalid_event") from None
    if event.uid != requested_uid:
        raise _ProcessingFailure("event_uid_mismatch")
    if event.event_id != lease.document_id:
        raise _ProcessingFailure("event_id_mismatch")

    action = event.payload.get("action")
    if action == "barrier":
        if event.memory_id is not None:
            raise _ProcessingFailure("invalid_barrier_event")
    elif action not in {"upsert", "delete"}:
        raise _ProcessingFailure("invalid_event_action")

    if action == "barrier":
        control = _load_control_state(db_client=db_client, uid=requested_uid)
        if event.account_generation != control.account_generation:
            return _ProcessOutcome(settled_reason="stale_account_generation", stale=True, barrier=True)
        if event.source_generation != control.source_generation:
            return _ProcessOutcome(settled_reason="stale_source_generation", stale=True, barrier=True)
        return _ProcessOutcome(settled_reason="barrier", barrier=True)

    memory_id = event.memory_id
    if memory_id is None or event.payload.get("memory_id") != memory_id:
        raise _ProcessingFailure("event_memory_id_mismatch")

    expected_revision = event.payload.get("item_revision")
    expected_content_hash = event.payload.get("content_hash")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
        or not isinstance(expected_content_hash, str)
        or not expected_content_hash.strip()
    ):
        raise _ProcessingFailure("invalid_event_fence")

    state = _load_authoritative_projection_state(
        db_client=db_client,
        uid=requested_uid,
        memory_id=memory_id,
    )
    reclaimed_processing_lease = _enum_value(lease.raw_event.get("status")) == MemoryOutboxStatus.processing.value
    repair_authoritative_state = (
        reclaimed_processing_lease or lease.raw_event.get("last_error_code") in _PROVIDER_REPAIR_REQUIRED_ERROR_CODES
    )
    if event.account_generation != state.account_generation and not repair_authoritative_state:
        return _ProcessOutcome(settled_reason="stale_account_generation", stale=True)

    item = state.item
    if item is None:
        # Strongly consistent Firestore absence is authoritative.  Deleting an
        # idempotent projection also repairs an upsert whose item disappeared
        # before this worker acquired it.
        return _deliver_authoritative_projection_state(
            db_client=db_client,
            event=event,
            side_effects=side_effects,
            uid=requested_uid,
            memory_id=memory_id,
            initial_state=state,
            use_event_commit_id_on_first_write=False,
        )

    event_fence_matches_item = (
        item.account_generation == event.account_generation
        and item.item_revision == expected_revision
        and item.content_hash == expected_content_hash
    )
    if item.account_generation != event.account_generation and not repair_authoritative_state:
        return _ProcessOutcome(settled_reason="stale_item_account_generation", stale=True)
    if item.item_revision != expected_revision and not repair_authoritative_state:
        return _ProcessOutcome(settled_reason="stale_item_revision", stale=True)
    if item.content_hash != expected_content_hash and not repair_authoritative_state:
        return _ProcessOutcome(settled_reason="stale_content_hash", stale=True)

    return _deliver_authoritative_projection_state(
        db_client=db_client,
        event=event,
        side_effects=side_effects,
        uid=requested_uid,
        memory_id=memory_id,
        initial_state=state,
        use_event_commit_id_on_first_write=event_fence_matches_item,
    )


def _deliver_authoritative_projection_state(
    *,
    db_client: Any,
    event: MemoryOutboxEvent,
    side_effects: CanonicalMemoryOutboxSideEffects,
    uid: str,
    memory_id: str,
    initial_state: _AuthoritativeProjectionState,
    use_event_commit_id_on_first_write: bool,
) -> _ProcessOutcome:
    """Converge the provider and prove the canonical fence stayed unchanged.

    Provider APIs do not expose a shared compare-and-set primitive.  A second
    outbox run can therefore publish a newer revision while an older provider
    request is in flight.  Reloading after every write and repairing to the
    newest authoritative state prevents the older request from winning that
    race.  Exhaustion is retryable, and the retry deliberately repairs the
    current state even though the original event fence is then stale.
    """

    state = initial_state
    for attempt in range(_PROVIDER_CONVERGENCE_ATTEMPTS):
        side_effect_action = _perform_authoritative_side_effect(
            event=event,
            side_effects=side_effects,
            uid=uid,
            memory_id=memory_id,
            state=state,
            use_event_commit_id=use_event_commit_id_on_first_write and attempt == 0,
        )
        try:
            observed_state = _load_authoritative_projection_state(
                db_client=db_client,
                uid=uid,
                memory_id=memory_id,
            )
        except _ProcessingFailure:
            # The provider may already have accepted the write.  A retry must
            # therefore reconcile current state instead of stale-settling the
            # original event after an inconclusive verification read.
            raise _ProcessingFailure(_PROVIDER_STATE_RACE_ERROR) from None
        if observed_state.fence == state.fence:
            return _ProcessOutcome(settled_reason="projected", side_effect_action=side_effect_action)
        state = observed_state

    raise _ProcessingFailure(_PROVIDER_STATE_RACE_ERROR)


def _perform_authoritative_side_effect(
    *,
    event: MemoryOutboxEvent,
    side_effects: CanonicalMemoryOutboxSideEffects,
    uid: str,
    memory_id: str,
    state: _AuthoritativeProjectionState,
    use_event_commit_id: bool,
) -> str:
    item = (
        state.item
        if not state.projection_writes_blocked
        and state.item is not None
        and state.item.account_generation == state.account_generation
        else None
    )
    if event.event_type == MemoryOutboxEventType.projection_sync:
        if item is not None and _is_search_projection_indexable(item):
            _require_side_effect_success(
                lambda: side_effects.projection_upsert(item, state.account_generation),
                error_code="projection_upsert_failed",
            )
            return "projection_upsert"
        _require_side_effect_success(
            lambda: side_effects.projection_delete(uid, memory_id, state.account_generation),
            error_code="projection_delete_failed",
        )
        return "projection_delete"
    if event.event_type == MemoryOutboxEventType.vector_sync:
        if item is not None and _is_vector_indexable(item):
            projection_commit_id = event.commit_id if use_event_commit_id else item.ledger_commit_id or event.commit_id
            _require_side_effect_success(
                lambda: side_effects.vector_upsert(item, projection_commit_id),
                error_code="vector_upsert_failed",
            )
            return "vector_upsert"
        _require_side_effect_success(
            lambda: side_effects.vector_delete(uid, memory_id),
            error_code="vector_delete_failed",
        )
        return "vector_delete"
    raise _ProcessingFailure("unsupported_event_type")


def _is_search_projection_indexable(item: MemoryItem) -> bool:
    return (
        item.tier in {MemoryTier.short_term, MemoryTier.long_term}
        and item.status == MemoryItemStatus.active
        and item.processing_state == ProcessingState.processed
        and item.source_state == SourceState.active
        and (item.promotion or {}).get("user_review") is not False
        and not set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and bool((item.content or "").strip())
    )


def _is_vector_indexable(item: MemoryItem) -> bool:
    return (
        item.tier in {MemoryTier.short_term, MemoryTier.long_term}
        and item.status == MemoryItemStatus.active
        and item.processing_state == ProcessingState.processed
        and item.source_state == SourceState.active
        and (item.promotion or {}).get("user_review") is not False
        and not set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and bool((item.content or "").strip())
    )


def _require_side_effect_success(callback: Callable[[], bool], *, error_code: str) -> None:
    try:
        succeeded = callback()
    except Exception:
        raise _ProcessingFailure(error_code) from None
    if succeeded is not True:
        raise _ProcessingFailure(error_code)


def _load_control_state(*, db_client: Any, uid: str) -> MemoryControlState:
    path = MemoryCollections(uid=uid).memory_apply_control_state
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        raise _ProcessingFailure("missing_control_state")
    try:
        return parse_snapshot_strict(MemoryControlState, snapshot)
    except MalformedDocError:
        raise _ProcessingFailure("invalid_control_state") from None


def _load_memory_item(*, db_client: Any, uid: str, memory_id: str) -> Optional[MemoryItem]:
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        return None
    try:
        return parse_snapshot_strict(MemoryItem, snapshot)
    except MalformedDocError:
        raise _ProcessingFailure("invalid_authoritative_item") from None


def _load_authoritative_projection_state(
    *,
    db_client: Any,
    uid: str,
    memory_id: str,
) -> _AuthoritativeProjectionState:
    deletion_fence = read_account_deletion_projection_fence(uid, db_client=db_client)
    control = _load_control_state(db_client=db_client, uid=uid)
    item = _load_memory_item(db_client=db_client, uid=uid, memory_id=memory_id)
    if item is not None and item.uid != uid:
        raise _ProcessingFailure("authoritative_item_uid_mismatch")
    return _AuthoritativeProjectionState(
        account_generation=control.account_generation,
        item=item,
        projection_writes_blocked=deletion_fence.blocks_projection_writes,
    )


def _settle_failure(
    *,
    db_client: Any,
    lease: LeasedMemoryOutboxEvent,
    config: CanonicalMemoryOutboxWorkerConfig,
    error_code: str,
    now: datetime,
    summary: Dict[str, Any],
) -> None:
    prior_attempt_count = _safe_nonnegative_int(lease.raw_event.get("attempt_count"))
    decision = decide_attempt(
        attempt_count=prior_attempt_count + 1,
        outcome=ProcessOutcome.retry(error_code, reason=error_code),
        policy=QueuePolicy(
            max_attempts=config.max_attempts,
            base_backoff_seconds=float(config.base_backoff_seconds),
            max_backoff_seconds=float(config.max_backoff_seconds),
        ),
        now=now,
    )
    status = MemoryOutboxStatus.dead_letter.value if decision.terminal else MemoryOutboxStatus.retryable_failure.value
    patch: Dict[str, Any] = {
        "status": status,
        "attempt_count": decision.attempt_count,
        "last_error": None,
        "last_error_code": error_code,
        "last_error_text": decision.error_text,
        "failed_at": now,
        "updated_at": now,
        "lease_owner": None,
        "lease_expires_at": None,
    }
    if decision.available_at is not None:
        patch["available_at"] = decision.available_at
    if decision.terminal:
        patch["dead_letter_reason"] = decision.reason

    acknowledged = _ack_leased_event(db_client=db_client, lease=lease, patch=patch)
    if not acknowledged:
        summary["ack_failed_count"] += 1
        summary["errors"].append(
            {
                "stage": "failure_ack",
                "event_id": lease.document_id,
                "code": "lease_ownership_lost",
            }
        )
        return

    count_key = "dead_letter_count" if decision.terminal else "retryable_failure_count"
    summary[count_key] += 1
    summary["errors"].append(
        {
            "stage": "process",
            "event_id": lease.document_id,
            "code": error_code,
        }
    )


def _ack_leased_event(
    *,
    db_client: Any,
    lease: LeasedMemoryOutboxEvent,
    patch: Dict[str, Any],
) -> bool:
    try:
        return bool(
            _run_transaction(
                db_client,
                _ack_event_transaction,
                db_client,
                lease.path,
                lease.worker_id,
                lease.lease_epoch,
                patch,
            )
        )
    except Exception:
        return False


def _ack_event_transaction(
    transaction: Any,
    db_client: Any,
    path: str,
    worker_id: str,
    lease_epoch: int,
    patch: Dict[str, Any],
) -> bool:
    ref = db_client.document(path)
    snapshot = ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        return False
    raw = _snapshot_dict(snapshot)
    if (
        _enum_value(raw.get("status")) != MemoryOutboxStatus.processing.value
        or raw.get("lease_owner") != worker_id
        or _safe_nonnegative_int(raw.get("lease_epoch")) != lease_epoch
    ):
        return False
    transaction.update(ref, dict(patch))
    return True


def _run_transaction(db_client: Any, callback: Callable[..., Any], *args: Any) -> Any:
    transaction = db_client.transaction()
    if transaction.__class__.__module__.startswith("google.cloud.firestore"):
        wrapped = cast(Callable[..., Any], _firestore_transactional(callback))
        return wrapped(transaction, *args)

    if hasattr(transaction, "_begin"):
        transaction._begin()
    try:
        result = callback(transaction, *args)
        if hasattr(transaction, "_commit"):
            transaction._commit()
        return result
    except Exception:
        if hasattr(transaction, "_rollback"):
            transaction._rollback()
        raise
    finally:
        if hasattr(transaction, "_clean_up"):
            transaction._clean_up()


def _validate_tick_inputs(
    *,
    uid: str,
    config: CanonicalMemoryOutboxWorkerConfig,
    side_effects: CanonicalMemoryOutboxSideEffects,
) -> None:
    if not uid.strip():
        raise ValueError("uid is required")
    if not config.worker_id.strip():
        raise ValueError("config.worker_id is required")
    if config.limit < 1:
        raise ValueError("config.limit must be positive")
    if config.scan_limit < config.limit:
        raise ValueError("config.scan_limit must be at least config.limit")
    if config.lease_seconds < 1:
        raise ValueError("config.lease_seconds must be positive")
    if config.max_attempts < 1:
        raise ValueError("config.max_attempts must be positive")
    if config.base_backoff_seconds < 1:
        raise ValueError("config.base_backoff_seconds must be positive")
    if config.max_backoff_seconds < config.base_backoff_seconds:
        raise ValueError("config.max_backoff_seconds must be at least base_backoff_seconds")


def _empty_summary(*, uid: str, config: CanonicalMemoryOutboxWorkerConfig) -> Dict[str, Any]:
    return {
        "uid": uid,
        "worker_id": config.worker_id,
        "leased_count": 0,
        "delivered_count": 0,
        "stale_settled_count": 0,
        "barrier_count": 0,
        "retryable_failure_count": 0,
        "dead_letter_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": [],
    }


def _snapshot_dict(snapshot: Any) -> Dict[str, Any]:
    raw: object = snapshot.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _snapshot_path(snapshot: Any, collection_path: str) -> str:
    reference = getattr(snapshot, "reference", None)
    path = getattr(reference, "path", None)
    if isinstance(path, str) and path.strip():
        return path
    return f"{collection_path}/{snapshot.id}"


def _coerce_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    return None


def _observed_now(value: Optional[datetime]) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return observed.astimezone(timezone.utc)


def _safe_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


__all__ = [
    "CanonicalMemoryOutboxSideEffects",
    "CanonicalMemoryOutboxWorkerConfig",
    "LeasedMemoryOutboxEvent",
    "lease_canonical_memory_outbox_events",
    "run_canonical_memory_outbox_worker_tick",
]
