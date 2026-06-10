import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from google.cloud.firestore_v1 import transactional

from models.memories import confidence_fields_for_evidence
from ._client import db

users_collection = 'users'
memory_state_collection = 'memory_state'
memory_state_document = 'head'
memory_commits_collection = 'memory_commits'


class HeadConflict(Exception):
    def __init__(self, expected_parent: Optional[str], current_head: Optional[str]):
        super().__init__(f"Memory ledger head moved from {expected_parent} to {current_head}")
        self.expected_parent = expected_parent
        self.current_head = current_head


def mutation(mutation_type: str, **payload) -> Dict[str, Any]:
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


def _json_default(value: Any):
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
) -> Dict[str, Any]:
    transaction = db.transaction()
    return _append_commit_transaction(
        transaction,
        uid,
        parent_commit_id,
        mutations,
        run_id,
        commit_time,
        projection_writer,
        use_current_head,
    )


def append_commit_with_builder(
    uid: str,
    parent_commit_id: Optional[str],
    mutation_builder: Callable[[Any], Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    commit_time: Optional[datetime] = None,
    use_current_head: bool = False,
) -> Dict[str, Any]:
    transaction = db.transaction()
    return _append_commit_with_builder_transaction(
        transaction,
        uid,
        parent_commit_id,
        mutation_builder,
        run_id,
        commit_time,
        use_current_head,
    )


@transactional
def _append_commit_transaction(
    transaction,
    uid: str,
    parent_commit_id: Optional[str],
    mutations: List[Dict[str, Any]],
    run_id: Optional[str],
    commit_time: Optional[datetime],
    projection_writer: Optional[Callable[[Any], None]],
    use_current_head: bool,
) -> Dict[str, Any]:
    user_ref = db.collection(users_collection).document(uid)
    state_ref = user_ref.collection(memory_state_collection).document(memory_state_document)
    state_snapshot = state_ref.get(transaction=transaction)
    state = state_snapshot.to_dict() if state_snapshot.exists else {}
    current_head = state.get('current_head_commit_id')
    expected_parent = current_head if use_current_head else parent_commit_id

    commit = build_commit(expected_parent, mutations, run_id=run_id, commit_time=commit_time)
    commit_ref = user_ref.collection(memory_commits_collection).document(commit['commit_id'])
    commit_snapshot = commit_ref.get(transaction=transaction)

    if commit_snapshot.exists:
        return {'commit': commit_snapshot.to_dict(), 'applied': False}

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


@transactional
def _append_commit_with_builder_transaction(
    transaction,
    uid: str,
    parent_commit_id: Optional[str],
    mutation_builder: Callable[[Any], Dict[str, Any]],
    run_id: Optional[str],
    commit_time: Optional[datetime],
    use_current_head: bool,
) -> Dict[str, Any]:
    user_ref = db.collection(users_collection).document(uid)
    state_ref = user_ref.collection(memory_state_collection).document(memory_state_document)
    state_snapshot = state_ref.get(transaction=transaction)
    state = state_snapshot.to_dict() if state_snapshot.exists else {}
    current_head = state.get('current_head_commit_id')
    expected_parent = current_head if use_current_head else parent_commit_id

    if current_head != expected_parent:
        raise HeadConflict(expected_parent, current_head)

    built = mutation_builder(transaction)
    mutations = built.get('mutations') or []
    projection_writer = built.get('projection_writer')
    commit = build_commit(expected_parent, mutations, run_id=run_id, commit_time=commit_time)
    commit_ref = user_ref.collection(memory_commits_collection).document(commit['commit_id'])
    commit_snapshot = commit_ref.get(transaction=transaction)

    if commit_snapshot.exists:
        return {'commit': commit_snapshot.to_dict(), 'applied': False}

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
    return (state_snapshot.to_dict() or {}).get('current_head_commit_id')


def fold_commits(commits: List[Dict[str, Any]], valid_time: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    facts: Dict[str, Dict[str, Any]] = {}
    for commit in sorted(
        commits, key=lambda item: item.get('commit_time') or datetime.min.replace(tzinfo=timezone.utc)
    ):
        for item in commit.get('mutations') or []:
            _apply_mutation(facts, item, commit.get('commit_time'))
    if valid_time is None:
        return {fact_id: fact for fact_id, fact in facts.items() if fact.get('invalid_at') is None}
    return {fact_id: fact for fact_id, fact in facts.items() if _fact_valid_at(fact, valid_time)}


def _apply_mutation(facts: Dict[str, Dict[str, Any]], item: Dict[str, Any], commit_time: Optional[datetime]):
    mutation_type = item.get('type')
    if mutation_type == 'add_fact':
        fact = copy.deepcopy(item.get('fact') or {})
        fact_id = fact.get('id')
        if fact_id:
            facts[fact_id] = fact
        return

    fact_id = item.get('fact_id')
    if not fact_id or fact_id not in facts:
        return

    if mutation_type == 'supersede_fact':
        facts[fact_id]['superseded_by'] = item.get('by')
        valid_interval = item.get('valid_interval') or {}
        invalid_at = valid_interval.get('valid_to') or commit_time
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
        _apply_arg_changes(facts[fact_id], item.get('arg_changes') or {})
        return

    if mutation_type == 'add_evidence':
        evidence = facts[fact_id].setdefault('evidence', [])
        new_evidence = item.get('evidence')
        if new_evidence and new_evidence not in evidence:
            evidence.append(copy.deepcopy(new_evidence))
        return

    if mutation_type == 'remove_evidence':
        evidence_id = item.get('evidence_id')
        facts[fact_id]['evidence'] = [
            evidence
            for evidence in facts[fact_id].get('evidence', [])
            if not isinstance(evidence, dict) or evidence.get('evidence_id') != evidence_id
        ]
        return

    if mutation_type == 'tombstone_evidence':
        evidence_id = item.get('evidence_id')
        for evidence in facts[fact_id].get('evidence', []):
            if isinstance(evidence, dict) and evidence.get('evidence_id') == evidence_id:
                evidence['redaction_status'] = 'tombstoned'
                evidence['tombstoned_at'] = item.get('tombstoned_at') or commit_time
                evidence['tombstone_reason'] = item.get('reason')
        active_evidence = [
            evidence
            for evidence in facts[fact_id].get('evidence', [])
            if isinstance(evidence, dict) and evidence.get('redaction_status', 'active') != 'tombstoned'
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


def _apply_arg_changes(fact: Dict[str, Any], arg_changes: Dict[str, Any]):
    arguments = fact.setdefault('arguments', {})
    for key, value in arg_changes.items():
        if key == 'content':
            fact['content'] = value.get('to') if isinstance(value, dict) and 'to' in value else value
            continue
        arguments[key] = value.get('to') if isinstance(value, dict) and 'to' in value else value


def _fact_valid_at(fact: Dict[str, Any], valid_time: datetime) -> bool:
    qualifiers = fact.get('qualifiers') or {}
    valid_from = qualifiers.get('valid_from') or fact.get('valid_at')
    valid_to = qualifiers.get('valid_to') or fact.get('invalid_at')
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
    commits = []
    for doc in commits_ref.order_by('commit_time').stream():
        commit = doc.to_dict()
        if commit_time is None or commit.get('commit_time') <= commit_time:
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
