import copy
import hashlib
import json
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from database import projection_repair
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from models.memories import confidence_fields_for_evidence
from ._client import db

T = TypeVar("T")


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Create an isolated SDK transaction wrapper for every invocation.

    Firestore's ``_Transactional`` wrapper stores mutable retry IDs. Reusing one
    module-level instance across request threads can cross-contaminate retries,
    so defer constructing it until each call while preserving the typed surface.
    """

    @wraps(func)
    def invoke(transaction: Any, *args: Any, **kwargs: Any) -> T:
        wrapped = cast(Callable[..., T], transactional(func))
        return wrapped(transaction, *args, **kwargs)

    return invoke


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for Firestore DocumentSnapshot.to_dict() (SDK stub gap)."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


users_collection = 'users'
memory_state_collection = 'memory_state'
memory_state_document = 'head'
memory_commits_collection = 'memory_commits'


class HeadConflict(Exception):
    def __init__(self, expected_parent: Optional[str], current_head: Optional[str]):
        super().__init__(f"Memory ledger head moved from {expected_parent} to {current_head}")
        self.expected_parent = expected_parent
        self.current_head = current_head


def mutation(mutation_type: str, **payload: Any) -> Dict[str, Any]:
    return {'type': mutation_type, **payload}


def add_fact(fact: Dict[str, Any]) -> Dict[str, Any]:
    return mutation('add_fact', fact=normalize_fact_for_ledger(fact))


def normalize_fact_for_ledger(fact: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(fact)
    qualifiers = normalized.setdefault('qualifiers', {})
    if normalized.get('valid_at') is not None and qualifiers.get('valid_from') is None:
        qualifiers['valid_from'] = normalized.get('valid_at')
    if normalized.get('invalid_at') is not None and qualifiers.get('valid_to') is None:
        qualifiers['valid_to'] = normalized.get('invalid_at')
    return normalized


def supersede_fact(
    fact_id: str,
    by: Optional[str],
    kind: str = 'contradict',
    valid_interval: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return mutation('supersede_fact', fact_id=fact_id, by=by, kind=kind, valid_interval=valid_interval or {})


def refine_fact(fact_id: str, arg_changes: Dict[str, Any]) -> Dict[str, Any]:
    return mutation('refine_fact', fact_id=fact_id, arg_changes=copy.deepcopy(arg_changes))


def retract_fact(fact_id: str, reason: str = '') -> Dict[str, Any]:
    return mutation('retract_fact', fact_id=fact_id, reason=reason)


def add_evidence(fact_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    return mutation('add_evidence', fact_id=fact_id, evidence=copy.deepcopy(evidence))


def remove_evidence(fact_id: str, evidence_id: str) -> Dict[str, Any]:
    return mutation('remove_evidence', fact_id=fact_id, evidence_id=evidence_id)


def tombstone_evidence(
    fact_id: str,
    evidence_id: str,
    tombstoned_at: Optional[datetime] = None,
    reason: str = 'source_tombstoned',
) -> Dict[str, Any]:
    return mutation(
        'tombstone_evidence',
        fact_id=fact_id,
        evidence_id=evidence_id,
        tombstoned_at=tombstoned_at,
        reason=reason,
    )


def merge_entities(
    entity_a: str,
    entity_b: str,
    evidence: Optional[Dict[str, Any]] = None,
    confidence: float = 0.5,
) -> Dict[str, Any]:
    return mutation(
        'merge_entities',
        entity_a=entity_a,
        entity_b=entity_b,
        evidence=copy.deepcopy(evidence or {}),
        confidence=confidence,
    )


def split_entity(entity_id: str, into: List[Dict[str, Any]], reason: str = '') -> Dict[str, Any]:
    return mutation('split_entity', entity_id=entity_id, into=copy.deepcopy(into), reason=reason)


def reassign_fact_subject(fact_id: str, old: Optional[str], new: Optional[str]) -> Dict[str, Any]:
    return mutation('reassign_fact_subject', fact_id=fact_id, old=old, new=new)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=_json_default)


def commit_id_for(parent_commit_id: Optional[str], mutations: List[Dict[str, Any]]) -> str:
    payload = {'parent_commit_id': parent_commit_id, 'mutations': mutations}
    return hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()


def build_commit(
    parent_commit_id: Optional[str],
    mutations: List[Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    commit_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    commit_time = commit_time or datetime.now(timezone.utc)
    commit_id = commit_id_for(parent_commit_id, mutations)
    return {
        'commit_id': commit_id,
        'parent_commit_id': parent_commit_id,
        'commit_time': commit_time,
        'run_id': run_id,
        'mutations': copy.deepcopy(mutations),
    }


def append_commit_to_history(
    state: Dict[str, Any],
    commits: Dict[str, Dict[str, Any]],
    parent_commit_id: Optional[str],
    mutations: List[Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    commit_time: Optional[datetime] = None,
    use_current_head: bool = False,
) -> Dict[str, Any]:
    current_head = state.get('current_head_commit_id')
    expected_parent = current_head if use_current_head else parent_commit_id
    commit = build_commit(expected_parent, mutations, run_id=run_id, commit_time=commit_time)

    if commit['commit_id'] in commits:
        return {'commit': commits[commit['commit_id']], 'applied': False}

    if current_head != expected_parent:
        raise HeadConflict(expected_parent, current_head)

    commits[commit['commit_id']] = commit
    state['current_head_commit_id'] = commit['commit_id']
    state['projection_version'] = 1
    state['updated_at'] = commit['commit_time']
    return {'commit': commit, 'applied': True}


def append_commit(
    uid: str,
    parent_commit_id: Optional[str],
    mutations: List[Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    commit_time: Optional[datetime] = None,
    projection_writer: Optional[Callable[[Any], None]] = None,
    use_current_head: bool = False,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    database: Any = firestore_client or db
    result = run_with_transaction_contention_retry(
        database.transaction,
        lambda transaction: _append_commit_transaction(
            transaction,
            database,
            uid,
            parent_commit_id,
            mutations,
            run_id,
            commit_time,
            projection_writer,
            use_current_head,
        ),
        operation_name="memory_ledger_append",
    )
    if result.get('applied'):
        projection_repair.enqueue_projection_repairs(uid, result.get('commit'), firestore_client=database)
    return result


def append_commit_with_builder(
    uid: str,
    parent_commit_id: Optional[str],
    mutation_builder: Callable[[Any], Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    commit_time: Optional[datetime] = None,
    use_current_head: bool = False,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    database: Any = firestore_client or db
    result = run_with_transaction_contention_retry(
        database.transaction,
        lambda transaction: _append_commit_with_builder_transaction(
            transaction,
            database,
            uid,
            parent_commit_id,
            mutation_builder,
            run_id,
            commit_time,
            use_current_head,
        ),
        operation_name="memory_ledger_append_with_builder",
    )
    if result.get('applied'):
        projection_repair.enqueue_projection_repairs(uid, result.get('commit'), firestore_client=database)
    return result


@_typed_transactional
def _append_commit_transaction(
    transaction: Any,
    database: Any,
    uid: str,
    parent_commit_id: Optional[str],
    mutations: List[Dict[str, Any]],
    run_id: Optional[str],
    commit_time: Optional[datetime],
    projection_writer: Optional[Callable[[Any], None]],
    use_current_head: bool,
) -> Dict[str, Any]:
    user_ref = database.collection(users_collection).document(uid)
    state_ref = user_ref.collection(memory_state_collection).document(memory_state_document)
    state_snapshot = state_ref.get(transaction=transaction)
    state: Dict[str, Any] = _typed_doc(state_snapshot) if state_snapshot.exists else {}
    current_head = state.get('current_head_commit_id')
    expected_parent = current_head if use_current_head else parent_commit_id

    commit = build_commit(expected_parent, mutations, run_id=run_id, commit_time=commit_time)
    commit_ref = user_ref.collection(memory_commits_collection).document(commit['commit_id'])
    commit_snapshot = commit_ref.get(transaction=transaction)

    if commit_snapshot.exists:
        return {'commit': _typed_doc(commit_snapshot), 'applied': False}

    if current_head != expected_parent:
        raise HeadConflict(expected_parent, current_head)

    if projection_writer:
        projection_writer(transaction)

    transaction.set(commit_ref, commit)
    transaction.set(
        state_ref,
        {
            'current_head_commit_id': commit['commit_id'],
            'projection_version': 1,
            'updated_at': commit['commit_time'],
        },
    )
    return {'commit': commit, 'applied': True}


@_typed_transactional
def _append_commit_with_builder_transaction(
    transaction: Any,
    database: Any,
    uid: str,
    parent_commit_id: Optional[str],
    mutation_builder: Callable[[Any], Dict[str, Any]],
    run_id: Optional[str],
    commit_time: Optional[datetime],
    use_current_head: bool,
) -> Dict[str, Any]:
    user_ref = database.collection(users_collection).document(uid)
    state_ref = user_ref.collection(memory_state_collection).document(memory_state_document)
    state_snapshot = state_ref.get(transaction=transaction)
    state: Dict[str, Any] = _typed_doc(state_snapshot) if state_snapshot.exists else {}
    current_head = state.get('current_head_commit_id')
    expected_parent = current_head if use_current_head else parent_commit_id

    if current_head != expected_parent:
        raise HeadConflict(expected_parent, current_head)

    built = mutation_builder(transaction)
    mutations: List[Dict[str, Any]] = cast(List[Dict[str, Any]], built.get('mutations') or [])
    projection_writer = built.get('projection_writer')
    commit = build_commit(expected_parent, mutations, run_id=run_id, commit_time=commit_time)
    commit_ref = user_ref.collection(memory_commits_collection).document(commit['commit_id'])
    commit_snapshot = commit_ref.get(transaction=transaction)

    if commit_snapshot.exists:
        return {'commit': _typed_doc(commit_snapshot), 'applied': False}

    if projection_writer:
        projection_writer(transaction)

    transaction.set(commit_ref, commit)
    transaction.set(
        state_ref,
        {
            'current_head_commit_id': commit['commit_id'],
            'projection_version': 1,
            'updated_at': commit['commit_time'],
        },
    )
    return {'commit': commit, 'applied': True}


def read_head(uid: str) -> Optional[str]:
    state_ref = (
        db.collection(users_collection)
        .document(uid)
        .collection(memory_state_collection)
        .document(memory_state_document)
    )
    state_snapshot = state_ref.get()
    if not state_snapshot.exists:
        return None
    state: Dict[str, Any] = _typed_doc(state_snapshot)
    return state.get('current_head_commit_id')


def fold_commits(commits: List[Dict[str, Any]], valid_time: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    facts: Dict[str, Dict[str, Any]] = {}
    for commit in sorted(
        commits, key=lambda item: item.get('commit_time') or datetime.min.replace(tzinfo=timezone.utc)
    ):
        mutations: List[Dict[str, Any]] = cast(List[Dict[str, Any]], commit.get('mutations') or [])
        for item in mutations:
            _apply_mutation(facts, item, commit.get('commit_time'))
    if valid_time is None:
        return {fact_id: fact for fact_id, fact in facts.items() if fact.get('invalid_at') is None}
    return {fact_id: fact for fact_id, fact in facts.items() if _fact_valid_at(fact, valid_time)}


def _resolve_arg_change(value: Any) -> Any:
    if isinstance(value, dict) and "to" in value:
        return cast(Dict[str, Any], value).get("to")
    return cast(Any, value)


def _apply_mutation(facts: Dict[str, Dict[str, Any]], item: Dict[str, Any], commit_time: Optional[datetime]) -> None:
    mutation_type = item.get('type')
    if mutation_type == 'add_fact':
        fact: Dict[str, Any] = cast(Dict[str, Any], copy.deepcopy(item.get('fact') or {}))
        fact_id = fact.get('id')
        if fact_id:
            facts[fact_id] = fact
        return

    fact_id = item.get('fact_id')
    if not fact_id or fact_id not in facts:
        return

    if mutation_type == 'supersede_fact':
        facts[fact_id]['superseded_by'] = item.get('by')
        valid_interval: Dict[str, Any] = cast(Dict[str, Any], item.get('valid_interval') or {})
        invalid_at: Any = valid_interval.get('valid_to') or commit_time
        facts[fact_id]['invalid_at'] = invalid_at
        facts[fact_id].setdefault('qualifiers', {})['valid_to'] = invalid_at
        return

    if mutation_type == 'retract_fact':
        facts[fact_id]['invalid_at'] = commit_time
        facts[fact_id]['retraction_reason'] = item.get('reason')
        facts[fact_id]['redaction_status'] = 'payload_tombstoned'
        facts[fact_id]['content'] = None
        facts[fact_id]['arguments'] = {}
        return

    if mutation_type == 'refine_fact':
        _apply_arg_changes(facts[fact_id], cast(Dict[str, Any], item.get('arg_changes') or {}))
        return

    if mutation_type == 'add_evidence':
        evidence: Any = facts[fact_id].setdefault('evidence', [])
        new_evidence = item.get('evidence')
        if new_evidence and new_evidence not in evidence:
            evidence.append(copy.deepcopy(new_evidence))
        return

    if mutation_type == 'remove_evidence':
        evidence_id = item.get('evidence_id')
        evidence_items: Any = facts[fact_id].get('evidence') or []
        facts[fact_id]['evidence'] = [
            evidence
            for evidence in evidence_items
            if not isinstance(evidence, dict) or cast(Dict[str, Any], evidence).get('evidence_id') != evidence_id
        ]
        return

    if mutation_type == 'tombstone_evidence':
        evidence_id = item.get('evidence_id')
        current_evidence: Any = facts[fact_id].get('evidence') or []
        for evidence in current_evidence:
            if isinstance(evidence, dict) and cast(Dict[str, Any], evidence).get('evidence_id') == evidence_id:
                evidence_dict: Dict[str, Any] = cast(Dict[str, Any], evidence)
                evidence_dict['redaction_status'] = 'tombstoned'
                evidence_dict['tombstoned_at'] = item.get('tombstoned_at') or commit_time
                evidence_dict['tombstone_reason'] = item.get('reason')
        active_evidence: List[Dict[str, Any]] = [
            cast(Dict[str, Any], evidence)
            for evidence in current_evidence
            if isinstance(evidence, dict)
            and cast(Dict[str, Any], evidence).get('redaction_status', 'active') != 'tombstoned'
        ]
        facts[fact_id].update(
            confidence_fields_for_evidence(
                active_evidence,
                facts[fact_id].get('subject_attribution', 'unknown'),
                existing_capture_confidence=facts[fact_id].get('capture_confidence'),
            )
        )
        return

    if mutation_type == 'reassign_fact_subject':
        facts[fact_id]['subject_entity_id'] = item.get('new')


def _apply_arg_changes(fact: Dict[str, Any], arg_changes: Dict[str, Any]) -> None:
    arguments: Any = fact.setdefault('arguments', {})
    for key, value in arg_changes.items():
        resolved: Any = _resolve_arg_change(value)
        if key == 'content':
            fact['content'] = resolved
            continue
        arguments[key] = resolved


def _fact_valid_at(fact: Dict[str, Any], valid_time: datetime) -> bool:
    qualifiers: Dict[str, Any] = cast(Dict[str, Any], fact.get('qualifiers') or {})
    valid_from: Any = qualifiers.get('valid_from') or fact.get('valid_at')
    valid_to: Any = qualifiers.get('valid_to') or fact.get('invalid_at')
    if isinstance(valid_from, datetime) and valid_time < valid_from:
        return False
    if isinstance(valid_to, datetime) and valid_time > valid_to:
        return False
    return True


def replay_to(
    uid: str,
    commit_time: Optional[datetime] = None,
    valid_time: Optional[datetime] = None,
) -> Dict[str, Dict[str, Any]]:
    commits_ref = db.collection(users_collection).document(uid).collection(memory_commits_collection)
    commits: List[Dict[str, Any]] = []
    for doc in commits_ref.order_by('commit_time').stream():
        commit: Dict[str, Any] = _typed_doc(doc)
        commit_time_value: Any = commit.get('commit_time')
        if commit_time is None or commit_time_value <= commit_time:
            commits.append(commit)
    return fold_commits(commits, valid_time=valid_time)


def diff(commit_a: Dict[str, Any], commit_b: Dict[str, Any]) -> List[Dict[str, Any]]:
    if commit_b.get('parent_commit_id') == commit_a.get('commit_id'):
        return copy.deepcopy(commit_b.get('mutations') or [])
    return []


def diff_commits(
    commits: List[Dict[str, Any]], from_commit_id: Optional[str], to_commit_id: str
) -> List[Dict[str, Any]]:
    by_parent: Dict[Optional[str], Dict[str, Any]] = {commit.get('parent_commit_id'): commit for commit in commits}
    out: List[Dict[str, Any]] = []
    cursor = from_commit_id
    while cursor != to_commit_id and cursor in by_parent:
        next_commit = by_parent[cursor]
        out.extend(copy.deepcopy(next_commit.get('mutations') or []))
        cursor = next_commit.get('commit_id')
    return out if cursor == to_commit_id else []
