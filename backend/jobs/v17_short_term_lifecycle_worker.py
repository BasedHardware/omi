from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from models.v17_product_memory import V17MemoryItem
from utils.memory.short_term_lifecycle import (
    ShortTermDisposition,
    ShortTermLifecycleDecision,
    ShortTermLifecycleOutcome,
    evaluate_short_term_lifecycle,
)


@dataclass(frozen=True)
class ShortTermLifecycleTransitionRecord:
    uid: str
    memory_item_id: str
    outcome: str
    reason: str
    run_id: str
    evaluated_at: str
    audit_metadata: Dict
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
    created_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=list)
    existing_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=list)
    skipped_memory_ids: List[str] = field(default_factory=list)

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


def _current_time(now: Optional[datetime]) -> datetime:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError('short-term lifecycle worker timestamp must be timezone-aware')
    return current_time.astimezone(timezone.utc)


def _coerce_dispositions(
    dispositions: Optional[Mapping[str, ShortTermDisposition | str]],
) -> Dict[str, ShortTermDisposition | str]:
    return dict(dispositions or {})


def _source_refs(item: V17MemoryItem) -> List[Dict[str, Optional[str]]]:
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


def _canonical_json(payload: Dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)


def _sha256(payload: Dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()


def _transition_required(decision: ShortTermLifecycleDecision) -> bool:
    if decision.outcome != ShortTermLifecycleOutcome.remain_short_term:
        return True
    if decision.requires_lifecycle_decision:
        return True
    return not decision.default_access_allowed


def build_short_term_lifecycle_transition_record(
    item: V17MemoryItem,
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
    idempotency_payload = {
        'policy_version': audit_metadata['policy_version'],
        'uid': item.uid,
        'memory_item_id': item.memory_id,
        'outcome': decision.outcome.value,
        'reason': reason,
        'evaluated_at': evaluated_at,
        'source_refs': audit_metadata['source_refs'],
    }
    fingerprint_payload = {
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
    item: V17MemoryItem,
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
    items: Iterable[V17MemoryItem],
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
