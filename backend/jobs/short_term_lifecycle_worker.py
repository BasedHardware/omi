"""Canonical short-term lifecycle worker (WS-G9).

Neutral ``short_term_lifecycle_worker`` is the source of truth.
Legacy ``short_term_lifecycle_worker`` remains an importable alias.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, cast

from database.memory_collections import MemoryCollections
from models.product_memory import MemoryTier, MemoryItem
from utils.memory.short_term_lifecycle import (
    ShortTermDisposition,
    ShortTermLifecycleDecision,
    ShortTermLifecycleOutcome,
    evaluate_short_term_lifecycle,
)

JsonDict = Dict[str, Any]


def _empty_transition_records() -> List["ShortTermLifecycleTransitionRecord"]:
    return []


def _empty_memory_ids() -> List[str]:
    return []


@dataclass(frozen=True)
class ShortTermLifecycleTransitionRecord:
    uid: str
    memory_item_id: str
    outcome: str
    reason: str
    run_id: str
    evaluated_at: str
    audit_metadata: JsonDict
    idempotency_key: str
    fingerprint: str


@dataclass(frozen=True)
class ShortTermLifecyclePersistResult:
    record: ShortTermLifecycleTransitionRecord
    created: bool


class ShortTermLifecycleTransitionStore(Protocol):
    def persist_short_term_lifecycle_transition(
        self, record: ShortTermLifecycleTransitionRecord
    ) -> ShortTermLifecyclePersistResult: ...


@dataclass
class ShortTermLifecycleWorkerReport:
    created_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=_empty_transition_records)
    existing_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=_empty_transition_records)
    skipped_memory_ids: List[str] = field(default_factory=_empty_memory_ids)

    @property
    def created_count(self) -> int:
        return len(self.created_records)

    @property
    def existing_count(self) -> int:
        return len(self.existing_records)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_memory_ids)


class InMemoryShortTermLifecycleTransitionStore:
    """Deterministic fake store matching the worker persistence contract.

    Production callers can provide a Firestore-backed store with the same single
    `persist_short_term_lifecycle_transition` method. The fake deliberately
    rejects same-key/different-payload writes to catch non-idempotent worker
    drift in unit tests and local harnesses.
    """

    def __init__(self) -> None:
        self._records_by_key: Dict[str, ShortTermLifecycleTransitionRecord] = {}

    def persist_short_term_lifecycle_transition(
        self, record: ShortTermLifecycleTransitionRecord
    ) -> ShortTermLifecyclePersistResult:
        existing = self._records_by_key.get(record.idempotency_key)
        if existing is not None:
            if existing.fingerprint != record.fingerprint:
                raise ValueError(f'short-term lifecycle idempotency key collision for {record.idempotency_key}')
            return ShortTermLifecyclePersistResult(record=existing, created=False)
        self._records_by_key[record.idempotency_key] = record
        return ShortTermLifecyclePersistResult(record=record, created=True)

    def count(self) -> int:
        return len(self._records_by_key)

    def records(self) -> List[ShortTermLifecycleTransitionRecord]:
        return list(self._records_by_key.values())

    def record_for_memory_id(self, memory_item_id: str) -> ShortTermLifecycleTransitionRecord:
        matches = [record for record in self._records_by_key.values() if record.memory_item_id == memory_item_id]
        if len(matches) != 1:
            raise KeyError(memory_item_id)
        return matches[0]


class FirestoreShortTermLifecycleTransitionStore:
    """Firestore-backed lifecycle transition/audit store.

    Records are stored under `users/{uid}/short_term_lifecycle_transitions`
    using deterministic document IDs derived from the uid and worker
    idempotency key. Replays return the existing record, while same-key payload
    drift fails closed before writing.
    """

    def __init__(self, *, db_client: Any, now: Optional[datetime] = None) -> None:
        self._db_client = db_client
        self._now = now

    def persist_short_term_lifecycle_transition(
        self, record: ShortTermLifecycleTransitionRecord
    ) -> ShortTermLifecyclePersistResult:
        transaction = self._db_client.transaction()
        return _run_short_term_lifecycle_transaction(
            transaction,
            _persist_short_term_lifecycle_transition_transaction,
            self._db_client,
            record,
            self._now,
        )


def _persist_short_term_lifecycle_transition_transaction(
    transaction: Any,
    db_client: Any,
    record: ShortTermLifecycleTransitionRecord,
    now: Optional[datetime],
) -> ShortTermLifecyclePersistResult:
    transition_id = _stable_transition_id(record.uid, record.idempotency_key)
    collections = MemoryCollections(uid=record.uid)
    transition_ref = db_client.document(f'{collections.short_term_lifecycle_transitions}/{transition_id}')
    snapshot = transition_ref.get(transaction=transaction)

    if snapshot.exists:
        data = cast(JsonDict, snapshot.to_dict() or {})
        if data.get('fingerprint') != record.fingerprint:
            raise ValueError('short-term lifecycle idempotency key payload mismatch')
        return ShortTermLifecyclePersistResult(record=_record_from_firestore_data(data), created=False)

    payload = _firestore_transition_payload(record, transition_id=transition_id, now=now)
    transaction.set(transition_ref, payload)
    return ShortTermLifecyclePersistResult(record=record, created=True)


def _run_short_term_lifecycle_transaction(
    transaction: Any,
    func: Callable[..., ShortTermLifecyclePersistResult],
    *args: Any,
) -> ShortTermLifecyclePersistResult:
    if hasattr(transaction, '_begin'):
        transaction._begin()
    try:
        result = func(transaction, *args)
        if hasattr(transaction, '_commit'):
            transaction._commit()
        return result
    except Exception:
        if hasattr(transaction, '_rollback'):
            transaction._rollback()
        raise
    finally:
        if hasattr(transaction, '_clean_up'):
            transaction._clean_up()


def _current_time(now: Optional[datetime]) -> datetime:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError('short-term lifecycle worker timestamp must be timezone-aware')
    return current_time.astimezone(timezone.utc)


def _coerce_dispositions(
    dispositions: Optional[Mapping[str, ShortTermDisposition | str]],
) -> Dict[str, ShortTermDisposition | str]:
    return dict(dispositions or {})


def fetch_short_term_memory_items_firestore(
    *, uid: str, db_client: Any, limit: Optional[int] = None
) -> List[MemoryItem]:
    """Fetch authoritative Short-term memory memory_items for a user.

    The lifecycle runner only evaluates `memory_items` in the Short-term tier;
    Long-term and Archive are intentionally excluded at the Firestore query seam
    so Archive cannot become default-visible through lifecycle scheduling.
    """

    if not uid or not uid.strip():
        raise ValueError('short-term lifecycle firestore fetch uid must be non-empty')
    if limit is not None and limit <= 0:
        raise ValueError('short-term lifecycle firestore fetch limit must be positive')

    query = db_client.collection(MemoryCollections(uid=uid).memory_items).where(
        'tier', '==', MemoryTier.short_term.value
    )
    snapshots = query.stream()
    items: List[MemoryItem] = []
    for snapshot in snapshots:
        item = MemoryItem(**cast(JsonDict, snapshot.to_dict() or {}))
        if item.uid != uid:
            raise ValueError(f'short-term lifecycle firestore fetch uid mismatch for {item.memory_id}')
        if item.tier == MemoryTier.short_term:
            items.append(item)
    items = sorted(items, key=lambda item: item.memory_id)
    if limit is not None:
        return items[:limit]
    return items


def run_short_term_lifecycle_firestore(
    *,
    uid: str,
    db_client: Any,
    run_id: str,
    now: Optional[datetime] = None,
    limit: Optional[int] = None,
    dispositions: Optional[Mapping[str, ShortTermDisposition | str]] = None,
) -> ShortTermLifecycleWorkerReport:
    """Concrete Firestore lifecycle runner for authoritative Short-term items."""

    current_time = _current_time(now)
    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=db_client, limit=limit)
    store = FirestoreShortTermLifecycleTransitionStore(db_client=db_client, now=current_time)
    return process_short_term_lifecycle_items(
        items,
        store=store,
        now=current_time,
        run_id=run_id,
        dispositions=dispositions,
    )


def _source_refs(item: MemoryItem) -> List[Dict[str, Optional[str]]]:
    refs: List[Dict[str, Optional[str]]] = []
    for evidence in item.evidence:
        refs.append(
            {
                'evidence_id': evidence.evidence_id,
                'source_id': evidence.source_id,
                'source_type': evidence.source_type,
                'source_version': evidence.source_version,
                'source_state': evidence.source_state.value,
            }
        )
    return refs


def _canonical_json(payload: JsonDict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)


def _sha256(payload: JsonDict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()


def _stable_transition_id(uid: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f'{uid}:{idempotency_key}'.encode('utf-8')).hexdigest()
    return f'stl_{digest[:32]}'


def _created_at_iso(now: Optional[datetime]) -> str:
    created_at = _current_time(now)
    return created_at.isoformat()


def _firestore_transition_payload(
    record: ShortTermLifecycleTransitionRecord,
    *,
    transition_id: str,
    now: Optional[datetime],
) -> JsonDict:
    source_refs = list(cast(List[Dict[str, Optional[str]]], record.audit_metadata.get('source_refs') or []))
    return {
        'transition_id': transition_id,
        'uid': record.uid,
        'memory_item_id': record.memory_item_id,
        'outcome': record.outcome,
        'reason': record.reason,
        'run_id': record.run_id,
        'evaluated_at': record.evaluated_at,
        'audit_metadata': record.audit_metadata,
        'source_refs': source_refs,
        'idempotency_key': record.idempotency_key,
        'fingerprint': record.fingerprint,
        'default_access_allowed': bool(record.audit_metadata.get('default_access_allowed', False)),
        'archive_default_visible': False,
        'created_at': _created_at_iso(now),
    }


def _record_from_firestore_data(data: JsonDict) -> ShortTermLifecycleTransitionRecord:
    return ShortTermLifecycleTransitionRecord(
        uid=data['uid'],
        memory_item_id=data['memory_item_id'],
        outcome=data['outcome'],
        reason=data['reason'],
        run_id=data['run_id'],
        evaluated_at=data['evaluated_at'],
        audit_metadata=dict(data.get('audit_metadata') or {}),
        idempotency_key=data['idempotency_key'],
        fingerprint=data['fingerprint'],
    )


def _transition_required(decision: ShortTermLifecycleDecision) -> bool:
    if decision.outcome != ShortTermLifecycleOutcome.remain_short_term:
        return True
    if decision.requires_lifecycle_decision:
        return True
    return not decision.default_access_allowed


def build_short_term_lifecycle_transition_record(
    item: MemoryItem,
    *,
    decision: ShortTermLifecycleDecision,
    run_id: str,
) -> ShortTermLifecycleTransitionRecord:
    if not run_id or not run_id.strip():
        raise ValueError('short-term lifecycle transition run_id must be non-empty')

    audit_metadata = dict(decision.audit_metadata)
    audit_metadata['outcome'] = decision.outcome.value
    audit_metadata['requires_lifecycle_decision'] = decision.requires_lifecycle_decision
    audit_metadata['default_access_allowed'] = decision.default_access_allowed
    audit_metadata['source_refs'] = _source_refs(item)

    reason = str(audit_metadata['decision_reason'])
    evaluated_at = str(audit_metadata['evaluated_at'])
    idempotency_payload: JsonDict = {
        'policy_version': audit_metadata['policy_version'],
        'uid': item.uid,
        'memory_item_id': item.memory_id,
        'outcome': decision.outcome.value,
        'reason': reason,
        'evaluated_at': evaluated_at,
        'source_refs': audit_metadata['source_refs'],
    }
    fingerprint_payload: JsonDict = {
        'uid': item.uid,
        'memory_item_id': item.memory_id,
        'outcome': decision.outcome.value,
        'reason': reason,
        'run_id': run_id,
        'audit_metadata': audit_metadata,
    }
    idempotency_key = (
        f"short-term-lifecycle:{item.uid}:{item.memory_id}:" f"{decision.outcome.value}:{_sha256(idempotency_payload)}"
    )
    return ShortTermLifecycleTransitionRecord(
        uid=item.uid,
        memory_item_id=item.memory_id,
        outcome=decision.outcome.value,
        reason=reason,
        run_id=run_id,
        evaluated_at=evaluated_at,
        audit_metadata=audit_metadata,
        idempotency_key=idempotency_key,
        fingerprint=_sha256(fingerprint_payload),
    )


def process_short_term_lifecycle_item(
    item: MemoryItem,
    *,
    store: ShortTermLifecycleTransitionStore,
    now: Optional[datetime] = None,
    run_id: str,
    disposition: Optional[ShortTermDisposition | str] = None,
) -> Tuple[Optional[ShortTermLifecycleTransitionRecord], bool]:
    decision = evaluate_short_term_lifecycle(item, now=_current_time(now), disposition=disposition)
    if not _transition_required(decision):
        return None, False
    record = build_short_term_lifecycle_transition_record(item, decision=decision, run_id=run_id)
    result = store.persist_short_term_lifecycle_transition(record)
    return result.record, result.created


def process_short_term_lifecycle_items(
    items: Iterable[MemoryItem],
    *,
    store: ShortTermLifecycleTransitionStore,
    now: Optional[datetime] = None,
    run_id: str,
    dispositions: Optional[Mapping[str, ShortTermDisposition | str]] = None,
) -> ShortTermLifecycleWorkerReport:
    current_time = _current_time(now)
    disposition_by_memory_id = _coerce_dispositions(dispositions)
    report = ShortTermLifecycleWorkerReport()

    for item in items:
        record, created = process_short_term_lifecycle_item(
            item,
            store=store,
            now=current_time,
            run_id=run_id,
            disposition=disposition_by_memory_id.get(item.memory_id),
        )
        if record is None:
            report.skipped_memory_ids.append(item.memory_id)
        elif created:
            report.created_records.append(record)
        else:
            report.existing_records.append(record)

    return report


__all__ = [
    "FirestoreShortTermLifecycleTransitionStore",
    "InMemoryShortTermLifecycleTransitionStore",
    "ShortTermLifecyclePersistResult",
    "ShortTermLifecycleTransitionRecord",
    "ShortTermLifecycleTransitionStore",
    "ShortTermLifecycleWorkerReport",
    "build_short_term_lifecycle_transition_record",
    "fetch_short_term_memory_items_firestore",
    "process_short_term_lifecycle_item",
    "process_short_term_lifecycle_items",
    "run_short_term_lifecycle_firestore",
]
