import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, cast

from config.memory_confidence import CONFIDENCE_BANDS
from database import memories as memories_db
from database import memory_ledger
from database import short_term_memories as short_term_db
from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    persist_non_active_route_outcome,
)
from database.read_boundary import parse_snapshot_or_none
from database.store import get_document_store
from models.memory_review import build_memory_review_conflict
from models.product_memory import MemoryItem, MemoryItemStatus


def _store():
    return get_document_store()


users_collection = 'users'
review_queue_collection = 'memory_review_queue'
review_queue_state_collection = 'memory_state'
corrections_collection = 'memory_corrections'
memories_collection = 'memories'
memory_items_collection = 'memory_items'
REVIEW_PURGE_ARRAY_CONTAINS_ANY_CHUNK_SIZE = 30
REVIEW_PURGE_PAGE_SIZE = 100
REVIEW_LIST_PAGE_SIZE = 100
REVIEW_LIST_STALE_PAGE_ALLOWANCE = 2
REVIEW_LIST_MAX_LIMIT = 500
REVIEW_LIST_LEGACY_SCAN_LIMIT = 100
REVIEW_LIST_LEGACY_CURSOR_SCHEMA_VERSION = 'memory_review_legacy_scan_cursor.v1'
REVIEW_LIST_LEGACY_CREATED_AT_SENTINEL = datetime.min.replace(tzinfo=timezone.utc)
_UNREAD_SOURCE_SNAPSHOT = object()

ACTION_POLICY: Dict[str, Set[str]] = {
    'accepted': {'answers', 'actions'},
    'pending': {'answers_with_disclaimer'},
    'pending_review': {'answers_with_disclaimer'},
    'contradicted': {'uncertainty_history'},
    'rejected': {'audit_debug'},
    'dropped': set(),
    'tombstoned': set(),
    'source_tombstoned': set(),
}


def permitted_uses(status: str) -> Set[str]:
    return ACTION_POLICY.get(status or 'accepted', ACTION_POLICY['accepted'])


def can_use_for_action(status: str, action_kind: str) -> bool:
    if action_kind == 'irreversible':
        return 'actions' in permitted_uses(status)
    return bool(permitted_uses(status))


def impact_score(new_fact: Dict[str, Any], conflict_fact: Dict[str, Any]) -> float:
    qualifiers_raw: object = new_fact.get('qualifiers')
    qualifiers: Dict[str, Any] = cast(Dict[str, Any], qualifiers_raw) if isinstance(qualifiers_raw, dict) else {}
    importance = qualifiers.get('importance', new_fact.get('importance', 0.5))
    new_veracity: float = cast(float, new_fact.get('veracity') or 0.0)
    conflict_veracity: float = cast(float, conflict_fact.get('veracity') or 0.0)
    return float(importance) * abs(conflict_veracity - new_veracity)


def should_escalate_conflict(new_fact: Dict[str, Any], conflict_fact: Dict[str, Any]) -> bool:
    new_veracity: float = cast(float, new_fact.get('veracity') or 0.0)
    conflict_veracity: float = cast(float, conflict_fact.get('veracity') or 0.0)
    ambiguous = new_veracity < CONFIDENCE_BANDS['medium'] and conflict_veracity >= CONFIDENCE_BANDS['high']
    return ambiguous and impact_score(new_fact, conflict_fact) >= 0.1


def create_review_conflict(
    uid: str,
    *,
    fact: Dict[str, Any],
    conflict_with: List[str],
    source_commit_id: Optional[str] = None,
    source_short_term_id: Optional[str] = None,
    impact: Optional[float] = None,
    ttl_hours: int = 72,
) -> Dict[str, Any]:
    item = build_memory_review_conflict(
        fact=fact,
        conflict_with=conflict_with,
        source_commit_id=source_commit_id,
        source_short_term_id=source_short_term_id,
        impact=impact,
        ttl_hours=ttl_hours,
    )
    _store().set(f'{users_collection}/{uid}/{review_queue_collection}/{item["review_id"]}', item)
    return item


def purge_stale_review_conflicts_for_memories(
    uid: str,
    memory_ids: List[str],
    *,
    reason: str = "source_memory_deleted",
) -> List[str]:
    """Tombstone and redact indexed review projections that reference removed memories."""
    target_ids: Set[str] = {memory_id for memory_id in memory_ids if memory_id}
    if not target_ids:
        return []

    now = datetime.now(timezone.utc)
    purged: Set[str] = set()
    # The port scans the containing collection neutrally; the coarse index lanes and
    # array_contains_any chunking used against raw Firestore collapse into a single scan plus
    # the same referenced-id intersection re-check that already backed the indexed query.
    for doc in _store().query(f'{users_collection}/{uid}/{review_queue_collection}'):
        raw: object = doc.to_dict()
        item: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        referenced = _review_referenced_memory_ids(item)
        if not referenced.intersection(target_ids):
            continue

        candidate_raw: object = item.get('candidate')
        candidate: Dict[str, Any] = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
        candidate_id: Any = candidate.get('id')
        redacted_candidate = {'id': candidate_id} if candidate_id else {}
        has_previous_status = 'previous_status' in item
        already_redacted = (
            item.get('status') == 'tombstoned'
            and has_previous_status
            and candidate == redacted_candidate
            and item.get('permitted_uses') == []
            and all(field in item for field in ('reason', 'resolved_at', 'updated_at'))
        )
        if not already_redacted:
            was_tombstoned = item.get('status') == 'tombstoned'
            _store().update(
                doc.path,
                {
                    'status': 'tombstoned',
                    'previous_status': (
                        item.get('previous_status') if has_previous_status else item.get('status')
                    ),
                    'reason': item.get('reason') if was_tombstoned and 'reason' in item else reason,
                    'candidate': redacted_candidate,
                    'permitted_uses': [],
                    'resolved_at': (item.get('resolved_at') if was_tombstoned and 'resolved_at' in item else now),
                    'updated_at': (item.get('updated_at') if was_tombstoned and 'updated_at' in item else now),
                },
            )
        purged.add(str(item.get('review_id') or doc.id))
    return sorted(purged)


def _review_referenced_memory_ids(item: Dict[str, Any]) -> Set[str]:
    referenced: Set[str] = set()
    fact_id = item.get('fact_id')
    if isinstance(fact_id, str) and fact_id:
        referenced.add(fact_id)
    candidate_raw: object = item.get('candidate')
    candidate = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
    candidate_id = candidate.get('id')
    if isinstance(candidate_id, str) and candidate_id:
        referenced.add(candidate_id)
    for field_name in ('conflict_with', 'referenced_memory_ids'):
        values_raw: object = item.get(field_name)
        if isinstance(values_raw, list):
            referenced.update(value for value in cast(List[Any], values_raw) if isinstance(value, str) and value)
    return referenced


def _review_conflict_sort_key(item: Dict[str, Any]) -> tuple[float, datetime]:
    impact_value: float = cast(float, item.get('impact') or 0.0)
    # Use a tz-aware sentinel: stored created_at is tz-aware, and on an impact tie the sort compares
    # the datetimes, so a naive datetime.min would raise "can't compare naive and aware" -> 500.
    created_value: datetime = cast(datetime, item.get('created_at') or REVIEW_LIST_LEGACY_CREATED_AT_SENTINEL)
    return (impact_value, created_value)


def _authoritative_canonical_review_projection(
    uid: str,
    item: Dict[str, Any],
    *,
    source_snapshot: Any = _UNREAD_SOURCE_SNAPSHOT,
) -> Dict[str, Any]:
    """Fail closed when a derived canonical review no longer owns its source item."""
    if not _is_canonical_review_item(item):
        return item
    memory_id = str(item.get('fact_id') or '').strip()
    candidate_raw: object = item.get('candidate')
    candidate = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
    candidate_id = memory_id or str(candidate.get('id') or '').strip()
    redacted = {
        **item,
        'candidate': {'id': candidate_id} if candidate_id else {},
        'permitted_uses': [],
    }
    if item.get('status') not in {'pending', 'pending_review'}:
        return redacted
    if not memory_id:
        return {**redacted, 'status': 'tombstoned', 'reason': 'canonical_review_identity_missing'}
    snapshot = source_snapshot
    if snapshot is _UNREAD_SOURCE_SNAPSHOT:
        snapshot = _store().get(f'{users_collection}/{uid}/{memory_items_collection}/{memory_id}')
    if not getattr(snapshot, 'exists', False):
        return {**redacted, 'status': 'tombstoned', 'reason': 'canonical_review_source_missing'}
    source = parse_snapshot_or_none(MemoryItem, snapshot)
    if source is None:
        return {**redacted, 'status': 'tombstoned', 'reason': 'canonical_review_source_invalid'}
    if (
        source.status != MemoryItemStatus.active
        or source.ledger_commit_id != item.get('source_commit_id')
        or source.item_revision != item.get('source_item_revision')
        or source.content_hash != item.get('source_content_hash')
        or (source.promotion or {}).get('route') != 'review'
    ):
        return {**redacted, 'status': 'tombstoned', 'reason': 'canonical_review_source_stale'}
    return item


def _authoritative_canonical_review_page(uid: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch canonical source reads so each bounded queue page costs one source round trip."""
    canonical_memory_ids = sorted(
        {
            str(item.get('fact_id') or '').strip()
            for item in items
            if _is_canonical_review_item(item)
            and item.get('status') in {'pending', 'pending_review'}
            and str(item.get('fact_id') or '').strip()
        }
    )
    source_snapshots: Dict[str, Any] = {memory_id: None for memory_id in canonical_memory_ids}
    if canonical_memory_ids:
        for snapshot in _store().get_many(f'{users_collection}/{uid}/{memory_items_collection}', canonical_memory_ids):
            source_id = str(getattr(snapshot, 'id', '') or '').strip()
            if source_id in source_snapshots:
                source_snapshots[source_id] = snapshot

    projected: List[Dict[str, Any]] = []
    for item in items:
        if _is_canonical_review_item(item):
            memory_id = str(item.get('fact_id') or '').strip()
            projected.append(
                _authoritative_canonical_review_projection(
                    uid,
                    item,
                    source_snapshot=source_snapshots.get(memory_id),
                )
            )
        else:
            projected.append(item)
    return projected


def _stale_review_self_heal_update(
    item: Dict[str, Any],
    projected: Dict[str, Any],
    *,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """Build the idempotent redaction that removes one stale row from pending scans."""
    if (
        not _is_canonical_review_item(item)
        or item.get('status') not in {'pending', 'pending_review'}
        or projected.get('status') != 'tombstoned'
    ):
        return None
    return {
        'status': 'tombstoned',
        'previous_status': item.get('previous_status', item.get('status')),
        'reason': projected.get('reason') or 'canonical_review_source_stale',
        'candidate': projected.get('candidate') or {},
        'permitted_uses': [],
        'resolved_at': item.get('resolved_at') or now,
        'updated_at': now,
    }


def _repair_scanned_review_documents(
    documents: List[Any],
    original_items: List[Dict[str, Any]],
    projected_items: List[Dict[str, Any]],
    *,
    backfill_rank_fields: bool = False,
) -> None:
    """Redact stale rows and drain sparse rows into the normal ranked query."""
    now = datetime.now(timezone.utc)
    for document, item, projected in zip(documents, original_items, projected_items):
        update = _stale_review_self_heal_update(item, projected, now=now) or {}
        if backfill_rank_fields:
            if 'impact' not in item:
                update['impact'] = 0.0
            if 'created_at' not in item:
                update['created_at'] = REVIEW_LIST_LEGACY_CREATED_AT_SENTINEL
        if not update:
            continue
        # The port exposes no last-write revision precondition; the neutral equivalent of the
        # optimistic compare-and-set is an unconditional path-addressed update.
        _store().update(document.path, update)


def list_review_conflicts(uid: str, status: str = 'pending', limit: int = 100) -> List[Dict[str, Any]]:
    effective_limit = max(0, min(int(limit), REVIEW_LIST_MAX_LIMIT))
    if effective_limit == 0:
        return []

    filters = [('status', '==', status)] if status else None
    documents = list(_store().query(f'{users_collection}/{uid}/{review_queue_collection}', filters=filters))

    page_items: List[Dict[str, Any]] = []
    for document in documents:
        raw: object = document.to_dict()
        item: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        item.setdefault('review_id', document.id)
        page_items.append(item)
    projected_items = _authoritative_canonical_review_page(uid, page_items)

    # Self-heal stale canonical rows and backfill legacy rows missing the ranked fields. The
    # Firestore ranked-query and rotating legacy-cursor lanes existed only because order_by drops
    # documents missing an ordered field; a neutral collection scan returns every row, so one
    # repair pass over the scanned documents subsumes both lanes.
    if status:
        _repair_scanned_review_documents(
            documents,
            page_items,
            projected_items,
            backfill_rank_fields=True,
        )

    items: List[Dict[str, Any]] = []
    review_ids: Set[str] = set()
    for item in projected_items:
        if status and item.get('status') != status:
            continue
        review_id = str(item.get('review_id') or '').strip()
        if review_id in review_ids:
            continue
        if review_id:
            review_ids.add(review_id)
        items.append(item)

    items.sort(
        key=lambda item: (
            *_review_conflict_sort_key(item),
            str(item.get('review_id') or ''),
        ),
        reverse=True,
    )
    return items[:effective_limit]


def get_review_conflict(uid: str, review_id: str) -> Optional[Dict[str, Any]]:
    doc = _store().get(f'{users_collection}/{uid}/{review_queue_collection}/{review_id}')
    if not doc.exists:
        return None
    raw: object = doc.to_dict()
    item: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    item.setdefault('review_id', review_id)
    return _authoritative_canonical_review_projection(uid, item)


def timeout_decision(item: Dict[str, Any], current_veracity: float) -> str:
    if current_veracity >= CONFIDENCE_BANDS['high']:
        return 'accept'
    return 'drop'


def accepted_fact(candidate: Dict[str, Any]) -> Dict[str, Any]:
    fact = copy.deepcopy(candidate)
    fact['status'] = 'accepted'
    fact.pop('review_conflict', None)
    qualifiers = fact.setdefault('qualifiers', {})
    qualifiers['status'] = 'accepted'
    qualifiers['epistemic_status'] = 'accepted'
    return fact


def _is_canonical_review_item(item: Dict[str, Any]) -> bool:
    return item.get("authority") == "canonical_memory"


def _append_canonical_resolution_commit(
    uid: str,
    item: Dict[str, Any],
    decision: str,
    correction: Optional[Dict[str, Any]],
    reason: str,
) -> Optional[Dict[str, Any]]:
    """Resolve a canonical review through its sole mutation authority."""
    from utils.memory.canonical_memory_adapter import resolve_canonical_memory_review

    review_id = str(item.get("review_id") or "")
    memory_id = str(item.get("fact_id") or "")
    if not review_id or not memory_id:
        raise ValueError("canonical review item is missing its identity")
    return resolve_canonical_memory_review(
        uid,
        memory_id,
        review_id=review_id,
        decision=decision,
        correction=correction,
        reason=reason,
    )


def resolution_mutations(
    item: Dict[str, Any], decision: str, correction: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    fact_id: Any = item.get('fact_id')
    candidate_raw: object = item.get('candidate')
    candidate: Dict[str, Any] = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
    conflict_with_raw: object = item.get('conflict_with')
    conflict_with: List[str] = cast(List[str], conflict_with_raw) if isinstance(conflict_with_raw, list) else []
    if decision == 'accept':
        return [memory_ledger.add_fact(accepted_fact(candidate))] + [
            memory_ledger.supersede_fact(existing_id, by=fact_id, kind='contradict') for existing_id in conflict_with
        ]
    if decision == 'reject':
        return [memory_ledger.retract_fact(fact_id, reason='review_rejected')]
    if decision == 'correct':
        correction_dict: Dict[str, Any] = correction if correction is not None else {}
        target_id: Any = correction_dict.get('target_fact_id') or fact_id
        arg_changes_raw: object = correction_dict.get('arg_changes')
        arg_changes: Dict[str, Any] = cast(Dict[str, Any], arg_changes_raw) if isinstance(arg_changes_raw, dict) else {}
        return [memory_ledger.refine_fact(target_id, arg_changes)]
    return []


def record_correction(
    uid: str,
    *,
    item: Dict[str, Any],
    decision: str,
    prior_head_diff: List[Dict[str, Any]],
    final_correction: Optional[Dict[str, Any]] = None,
    reason: str = '',
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    correction_id = f"correction:{item.get('review_id')}:{decision}"
    candidate_raw: object = item.get('candidate')
    candidate: Dict[str, Any] = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
    final: Dict[str, Any] = final_correction if final_correction is not None else {}
    record: Dict[str, Any] = {
        'correction_id': correction_id,
        'review_id': item.get('review_id'),
        'candidate': item.get('candidate'),
        'evidence_set': candidate.get('evidence', []),
        'prior_head_state': prior_head_diff,
        'final_correction': final,
        'decision': decision,
        'reason': reason,
        'created_at': now,
    }
    _store().set(f'{users_collection}/{uid}/{corrections_collection}/{correction_id}', record)
    return record


def resolve_review_conflict(
    uid: str,
    review_id: str,
    decision: str,
    *,
    correction: Optional[Dict[str, Any]] = None,
    reason: str = '',
    current_veracity: Optional[float] = None,
) -> Dict[str, Any]:
    item = get_review_conflict(uid, review_id)
    if item is None:
        return {'status': 'not_found', 'commit': None, 'correction': None}
    if item.get('status') not in ('pending', 'pending_review'):
        stale_canonical = _is_canonical_review_item(item) and str(item.get('reason') or '').startswith(
            'canonical_review_source_'
        )
        return {
            'status': 'stale_review' if stale_canonical else 'already_resolved',
            'commit': None,
            'correction': None,
            'item': item,
        }

    effective_decision = decision
    if decision == 'timeout':
        effective_decision = timeout_decision(
            item, current_veracity if current_veracity is not None else item.get('veracity') or 0.0
        )

    canonical_review = _is_canonical_review_item(item)
    mutations: List[Dict[str, Any]] = []
    if canonical_review:
        from database.memory_apply_store import CanonicalReviewResolutionConflict

        try:
            commit_result = _append_canonical_resolution_commit(
                uid,
                item,
                effective_decision,
                correction,
                reason,
            )
        except CanonicalReviewResolutionConflict as exc:
            return {
                'status': exc.status,
                'decision': (exc.review_item or {}).get('decision'),
                'commit': None,
                'correction': None,
                'item': exc.review_item or item,
            }
        resolved_item = get_review_conflict(uid, review_id)
        commit_result_dict: Dict[str, Any] = commit_result if commit_result is not None else {}
        canonical_status_by_decision = {
            'accept': 'accepted',
            'correct': 'accepted',
            'reject': 'rejected',
            'drop': 'dropped',
        }
        return {
            'status': 'resolved',
            'decision': effective_decision,
            'commit': commit_result_dict.get('commit'),
            'correction': None,
            'item': resolved_item
            or {
                **item,
                'status': canonical_status_by_decision[effective_decision],
                'decision': effective_decision,
                'candidate': {'id': item.get('fact_id')},
                'permitted_uses': [],
            },
        }

    mutations = [] if effective_decision == 'drop' else resolution_mutations(item, effective_decision, correction)
    commit_result = append_resolution_commit(uid, item, effective_decision, correction, mutations)
    _persist_non_active_review_resolution(uid, item, effective_decision, reason, commit_result)

    now = datetime.now(timezone.utc)
    status_by_decision = {
        'accept': 'accepted',
        'reject': 'rejected',
        'correct': 'accepted',
        'drop': 'dropped',
    }
    commit_result_dict: Dict[str, Any] = commit_result if commit_result is not None else {}
    commit_raw: object = commit_result_dict.get('commit')
    commit_obj: Dict[str, Any] = cast(Dict[str, Any], commit_raw) if isinstance(commit_raw, dict) else {}
    update: Dict[str, Any] = {
        'status': status_by_decision.get(effective_decision, effective_decision),
        'decision': effective_decision,
        'reason': reason,
        'resolved_at': now,
        'updated_at': now,
        'resolution_commit_id': commit_obj.get('commit_id'),
    }
    _store().update(f'{users_collection}/{uid}/{review_queue_collection}/{review_id}', update)
    if item.get('source_short_term_id'):
        short_term_db.mark_consolidated(uid, item['source_short_term_id'], update.get('resolution_commit_id'))

    correction_record: Optional[Dict[str, Any]] = None
    if effective_decision in ('accept', 'reject', 'correct'):
        correction_record = record_correction(
            uid,
            item=item,
            decision=effective_decision,
            prior_head_diff=mutations,
            final_correction=correction,
            reason=reason,
        )

    return {
        'status': 'resolved',
        'decision': effective_decision,
        'commit': commit_result_dict.get('commit'),
        'correction': correction_record,
        'item': {**item, **update},
    }


def _persist_non_active_review_resolution(
    uid: str,
    item: Dict[str, Any],
    decision: str,
    reason: str,
    commit_result: Optional[Dict[str, Any]],
) -> None:
    route_by_decision = {
        'reject': NonActiveRoute.reject,
        'drop': NonActiveRoute.skip,
    }
    route = route_by_decision.get(decision)
    if route is None:
        return

    review_id = item.get('review_id') or item.get('fact_id') or 'unknown_review'
    commit_result_dict: Dict[str, Any] = commit_result if commit_result is not None else {}
    commit_raw: object = commit_result_dict.get('commit')
    commit_obj: Dict[str, Any] = cast(Dict[str, Any], commit_raw) if isinstance(commit_raw, dict) else {}
    resolution_commit_id: Any = commit_obj.get('commit_id')
    persist_non_active_route_outcome(
        NonActiveRouteOutcome(
            uid=uid,
            route=route,
            idempotency_key=f"review_queue:{review_id}:{decision}",
            source_ids=_review_resolution_source_ids(item),
            reason=reason or f"review_queue_{decision}",
            run_id=f"review_queue:{review_id}",
            patch_id=None,
            audit_metadata={
                'route_store_source': 'review_queue',
                'decision': decision,
                'review_id': review_id,
                'fact_id': item.get('fact_id'),
                'conflict_with': item.get('conflict_with') or [],
                'source_commit_id': item.get('source_commit_id'),
                'source_short_term_id': item.get('source_short_term_id'),
                'resolution_commit_id': resolution_commit_id,
            },
        )
    )


def _review_resolution_source_ids(item: Dict[str, Any]) -> List[str]:
    source_ids: List[Any] = [
        item.get('review_id'),
        item.get('fact_id'),
        item.get('source_commit_id'),
        item.get('source_short_term_id'),
    ]
    candidate_raw: object = item.get('candidate')
    candidate: Dict[str, Any] = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
    evidence_iterable: List[Any] = cast(List[Any], candidate.get('evidence') or candidate.get('evidence_set') or [])
    for evidence in evidence_iterable:
        if isinstance(evidence, dict):
            evidence_dict: Dict[str, Any] = cast(Dict[str, Any], evidence)
            source_ids.append(evidence_dict.get('evidence_id'))
            source_ids.append(evidence_dict.get('source_id'))
        elif evidence:
            source_ids.append(str(evidence))
    return sorted({source_id for source_id in source_ids if source_id})


def append_resolution_commit(
    uid: str,
    item: Dict[str, Any],
    decision: str,
    correction: Optional[Dict[str, Any]],
    mutations: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if decision == 'drop' or not mutations:
        return None
    if decision == 'accept':
        candidate_raw: object = item.get('candidate')
        candidate: Dict[str, Any] = cast(Dict[str, Any], candidate_raw) if isinstance(candidate_raw, dict) else {}
        conflict_with_raw: object = item.get('conflict_with')
        conflict_with: List[str] = cast(List[str], conflict_with_raw) if isinstance(conflict_with_raw, list) else []
        return memories_db.merge_contradict_memory(
            uid,
            accepted_fact(candidate),
            conflict_with,
        )
    if decision == 'correct':
        correction_dict: Dict[str, Any] = correction if correction is not None else {}
        target_id: Any = correction_dict.get('target_fact_id') or item.get('fact_id')
        arg_changes_raw: object = correction_dict.get('arg_changes')
        arg_changes: Dict[str, Any] = cast(Dict[str, Any], arg_changes_raw) if isinstance(arg_changes_raw, dict) else {}
        return memories_db.refine_memory(uid, target_id, arg_changes)
    if decision == 'reject':
        now = datetime.now(timezone.utc)
        fact_id: Any = item.get('fact_id')
        memory_path = f'{users_collection}/{uid}/{memories_collection}/{fact_id}'

        def write_projection(tx: Any) -> None:
            snapshot = tx.get(memory_path)
            if snapshot.exists:
                tx.update(memory_path, {'invalid_at': now, 'updated_at': now, 'review_status': 'rejected'})

        return memory_ledger.append_commit(
            uid,
            None,
            mutations,
            run_id=f"review_queue:{item.get('review_id')}",
            commit_time=now,
            projection_writer=write_projection,
            use_current_head=True,
        )
    return memory_ledger.append_commit(
        uid,
        None,
        mutations,
        run_id=f"review_queue:{item.get('review_id')}",
        use_current_head=True,
    )


def resolve_expired_review_conflicts(
    uid: str,
    *,
    now: Optional[datetime] = None,
    current_veracity_by_fact: Optional[Dict[str, float]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    veracity_map: Dict[str, float] = current_veracity_by_fact if current_veracity_by_fact is not None else {}
    resolved: List[Dict[str, Any]] = []
    for item in list_review_conflicts(uid, status='pending', limit=limit):
        expires_at = item.get('expires_at')
        if expires_at and expires_at > now:
            continue
        fact_id: str = cast(str, item.get('fact_id'))
        veracity_default: float = cast(float, item.get('veracity') or 0.0)
        current_veracity: float = veracity_map.get(fact_id, veracity_default)
        resolved.append(
            resolve_review_conflict(
                uid,
                cast(str, item.get('review_id')),
                'timeout',
                current_veracity=current_veracity,
                reason='review_timeout',
            )
        )
    return resolved
