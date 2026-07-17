"""Canonical Candidate persistence and atomic task resolution."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.canonical_memory_cohort import is_canonical_memory_user
import database.action_items as action_items_db
from database._client import db
from database.read_boundary import parse_snapshot_or_none, parse_snapshot_strict, parse_snapshots
from models.action_item import EvidenceRef, TaskChangePayload, TaskCreatePayload, TaskOwner, TaskStatus
from models.candidate import (
    CandidateAction,
    CandidateCreate,
    CandidateRecord,
    CandidateResolutionReceipt,
    CandidateStatus,
    CandidateSubjectKind,
)
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

CANDIDATES_COLLECTION = 'candidates'
ACTION_ITEMS_COLLECTION = 'action_items'
CANDIDATE_INTEGRATION_OUTBOX_COLLECTION = 'candidate_integration_outbox'
CANDIDATE_IDEMPOTENCY_ALIASES_COLLECTION = 'candidate_idempotency_aliases'
CANDIDATE_PENDING_CLAIMS_COLLECTION = 'candidate_pending_claims'
CANDIDATE_RESOLUTION_CLAIMS_COLLECTION = 'candidate_resolution_claims'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'
PENDING_CANDIDATE_SEMANTIC_VERSION = 'task-create.v1'
WORKSTREAM_CANDIDATE_SEMANTIC_VERSION = 'workstream-create.v1'
MAX_CANDIDATE_EVIDENCE_REFS = 20
PENDING_CANDIDATE_REUSE_WINDOW = timedelta(days=14)


class CandidateStoreError(RuntimeError):
    pass


class CandidateNotFoundError(CandidateStoreError):
    pass


class CandidateConflictError(CandidateStoreError):
    pass


class CandidateGenerationMismatchError(CandidateStoreError):
    pass


class WorkstreamCandidateResolverUnavailableError(CandidateStoreError):
    pass


@dataclass(frozen=True)
class LegacyPromotionReservation:
    task_id: str
    kind: str


def _stable_contract_id(prefix: str, *parts: object) -> str:
    encoded = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}'


def candidate_id_for_idempotency(uid: str, account_generation: int, idempotency_key: str) -> str:
    return _stable_contract_id('cand', uid, account_generation, idempotency_key)


def task_id_for_candidate(uid: str, account_generation: int, candidate_id: str) -> str:
    return _stable_contract_id('task', uid, account_generation, candidate_id)


def task_id_for_conversation_item(
    uid: str,
    account_generation: int,
    conversation_id: str,
    semantic_key: str,
    occurrence: int,
) -> str:
    return _stable_contract_id(
        'task',
        uid,
        account_generation,
        'conversation',
        conversation_id,
        semantic_key,
        occurrence,
    )


def _candidate_ref(uid: str, candidate_id: str):
    return db.collection('users').document(uid).collection(CANDIDATES_COLLECTION).document(candidate_id)


def _task_ref(uid: str, task_id: str):
    return db.collection('users').document(uid).collection(ACTION_ITEMS_COLLECTION).document(task_id)


def _integration_outbox_ref(uid: str, candidate_id: str):
    return (
        db.collection('users').document(uid).collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION).document(candidate_id)
    )


def _candidate_idempotency_alias_ref(uid: str, key_hash: str):
    return db.collection('users').document(uid).collection(CANDIDATE_IDEMPOTENCY_ALIASES_COLLECTION).document(key_hash)


def _candidate_pending_claim_ref(uid: str, semantic_claim_id: str):
    return (
        db.collection('users').document(uid).collection(CANDIDATE_PENDING_CLAIMS_COLLECTION).document(semantic_claim_id)
    )


def _candidate_resolution_claim_ref(uid: str, candidate_id: str):
    return (
        db.collection('users').document(uid).collection(CANDIDATE_RESOLUTION_CLAIMS_COLLECTION).document(candidate_id)
    )


def _task_control_ref(uid: str):
    return (
        db.collection('users')
        .document(uid)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _validate_write_control(snapshot: Any, *, uid: str, account_generation: int) -> None:
    if not is_canonical_memory_user(uid):
        raise CandidateConflictError('canonical task intelligence is not enabled')
    control = TaskWorkflowControl()
    if snapshot.exists:
        control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
    if control.workflow_mode in (TaskWorkflowMode.off, TaskWorkflowMode.shadow):
        raise CandidateConflictError('task intelligence is not in an active workflow mode')
    if control.account_generation != account_generation:
        raise CandidateGenerationMismatchError('account generation mismatch')


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _claim_owner_is_active(claim: dict[str, Any], *, now: datetime) -> bool:
    lease_expires_at = claim.get('lease_expires_at')
    return claim.get('status') == 'active' and isinstance(lease_expires_at, datetime) and lease_expires_at > now


def _claim_blocks_resolution(claim: dict[str, Any], *, now: datetime) -> bool:
    if claim.get('status') != 'active':
        return False
    if claim.get('phase') == 'mutation_started':
        return True
    return _claim_owner_is_active(claim, now=now)


def _canonical_request_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('Candidate request datetime must be timezone-aware')
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: _canonical_request_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_request_value(item) for item in value]
    return value


def _proposal_request_hash(uid: str, account_generation: int, proposal: CandidateCreate) -> str:
    canonical = _canonical_request_value(proposal.model_dump(mode='python'))
    encoded = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return _stable_contract_id('request', uid, account_generation, encoded)


def _semantic_due_value(value: Any) -> str:
    if value is None:
        return ''
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('semantic due date must be timezone-aware')
    return value.astimezone(timezone.utc).isoformat()


def _task_create_semantic_payload(
    task_change: TaskCreatePayload,
    *,
    goal_id: Optional[str],
    workstream_id: Optional[str],
) -> dict[str, str]:
    return {
        'description': action_items_db.normalize_action_item_description(task_change.description),
        'owner': task_change.owner.value,
        'due_at': _semantic_due_value(task_change.due_at),
        'recurrence_rule': task_change.recurrence_rule or '',
        'recurrence_parent_id': task_change.recurrence_parent_id or '',
        'goal_id': goal_id or '',
        'workstream_id': workstream_id or '',
    }


def pending_candidate_semantic_identity(proposal: CandidateCreate) -> Optional[str]:
    """Return an exact, privacy-safe identity for task-create Candidates only.

    Evidence, source, confidence, due-confidence, and priority are deliberately
    annotations rather than task identity. The conservative identity keeps owner,
    exact due instant, recurrence, and canonical links so distinct work cannot be
    over-merged.
    """

    if proposal.subject_kind != CandidateSubjectKind.task or proposal.proposed_action != CandidateAction.create:
        return None
    task_change = proposal.task_change
    if not isinstance(task_change, TaskCreatePayload):
        return None
    semantic_payload = _task_create_semantic_payload(
        task_change,
        goal_id=proposal.goal_id,
        workstream_id=proposal.workstream_id,
    )
    encoded = json.dumps(semantic_payload, sort_keys=True, separators=(',', ':'))
    return _stable_contract_id('semantic', PENDING_CANDIDATE_SEMANTIC_VERSION, encoded)


def suggested_candidate_semantic_identity(proposal: CandidateCreate) -> Optional[str]:
    """Return the exact user-facing create identity for Suggested deduplication."""

    task_identity = pending_candidate_semantic_identity(proposal)
    if task_identity is not None:
        return task_identity
    if proposal.subject_kind != CandidateSubjectKind.workstream or proposal.proposed_action != CandidateAction.create:
        return None
    workstream = proposal.workstream_proposal
    if workstream is None:
        return None
    semantic_payload = {
        'title': action_items_db.normalize_action_item_description(workstream.title),
        'objective': action_items_db.normalize_action_item_description(workstream.objective),
        'anchor_task': _task_create_semantic_payload(
            workstream.anchor_task,
            goal_id=proposal.goal_id,
            workstream_id=proposal.workstream_id,
        ),
        'goal_id': proposal.goal_id or '',
        'workstream_id': proposal.workstream_id or '',
    }
    encoded = json.dumps(semantic_payload, sort_keys=True, separators=(',', ':'))
    return _stable_contract_id('semantic', WORKSTREAM_CANDIDATE_SEMANTIC_VERSION, encoded)


def _pending_semantic_claim_id(
    uid: str,
    account_generation: int,
    proposal: CandidateCreate,
) -> Optional[str]:
    semantic_identity = pending_candidate_semantic_identity(proposal)
    if semantic_identity is None:
        return None
    return _stable_contract_id(
        'pending',
        uid,
        account_generation,
        semantic_identity,
    )


def _merge_candidate_annotations(existing: CandidateRecord, proposal: CandidateCreate) -> CandidateRecord:
    evidence: list[EvidenceRef] = []
    seen: set[str] = set()
    for evidence_ref in [*existing.evidence_refs, *proposal.evidence_refs]:
        identity = json.dumps(
            evidence_ref.model_dump(mode='json', exclude_none=True),
            sort_keys=True,
            separators=(',', ':'),
        )
        if identity in seen:
            continue
        seen.add(identity)
        evidence.append(evidence_ref)
        if len(evidence) == MAX_CANDIDATE_EVIDENCE_REFS:
            break
    payload = existing.model_dump(mode='python')
    payload.update(
        {
            'capture_confidence': max(existing.capture_confidence, proposal.capture_confidence),
            'ownership_confidence': max(existing.ownership_confidence, proposal.ownership_confidence),
            'evidence_refs': evidence,
        }
    )
    return CandidateRecord.model_validate(payload)


def _merge_task_provenance(current_task: dict[str, Any], evidence_refs: list[EvidenceRef]) -> list[dict[str, Any]]:
    provenance: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_ref in list(current_task.get('provenance') or []) + [
        ref.model_dump(mode='json', exclude_none=True) for ref in evidence_refs
    ]:
        if not isinstance(raw_ref, dict):
            continue
        try:
            normalized_ref = EvidenceRef.model_validate(raw_ref).model_dump(mode='json', exclude_none=True)
        except ValueError:
            normalized_ref = raw_ref
        identity = json.dumps(normalized_ref, sort_keys=True, default=str)
        if identity in seen:
            continue
        seen.add(identity)
        provenance.append(normalized_ref)
    return provenance


def _accepted_task_is_active(task: Optional[dict[str, Any]], *, account_generation: int) -> bool:
    if task is None:
        return False
    raw_generation = task.get('account_generation', 0)
    if not isinstance(raw_generation, int) or isinstance(raw_generation, bool):
        return False
    task_generation = raw_generation
    if task_generation not in {0, account_generation}:
        return False
    status = task.get('status')
    if status is None:
        status = TaskStatus.completed.value if task.get('completed') else TaskStatus.active.value
    return status == TaskStatus.active.value and not task.get('completed', False) and not task.get('deleted', False)


def _accepted_task_matches_semantic_claim(task: dict[str, Any], candidate: CandidateRecord) -> bool:
    if not isinstance(candidate.task_change, TaskCreatePayload):
        return False
    raw_owner = task.get('owner')
    owner = raw_owner.value if isinstance(raw_owner, TaskOwner) else raw_owner
    description = task.get('description')
    if not isinstance(description, str) or not isinstance(owner, str):
        return False
    try:
        current_payload = {
            'description': action_items_db.normalize_action_item_description(description),
            'owner': owner,
            'due_at': _semantic_due_value(task.get('due_at')),
            'recurrence_rule': task.get('recurrence_rule') or '',
            'recurrence_parent_id': task.get('recurrence_parent_id') or '',
            'goal_id': task.get('goal_id') or '',
            'workstream_id': task.get('workstream_id') or '',
        }
        expected_payload = _task_create_semantic_payload(
            candidate.task_change,
            goal_id=candidate.goal_id,
            workstream_id=candidate.workstream_id,
        )
    except (TypeError, ValueError):
        return False
    return current_payload == expected_payload


def _stored_confidence(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def create_candidate(
    uid: str,
    proposal: CandidateCreate,
    *,
    idempotency_key: str,
    account_generation: int,
    now: Optional[datetime] = None,
) -> CandidateRecord:
    """Create one Candidate per request, coalescing exact pending or still-active accepted task creates."""

    if not idempotency_key.strip():
        raise ValueError('idempotency_key is required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')
    now_value = now or datetime.now(timezone.utc)
    key_hash = _stable_contract_id('idem', uid, account_generation, idempotency_key)
    request_hash = _proposal_request_hash(uid, account_generation, proposal)
    candidate_id = candidate_id_for_idempotency(uid, account_generation, idempotency_key)
    semantic_claim_id = _pending_semantic_claim_id(uid, account_generation, proposal)
    record = CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id=candidate_id,
        account_generation=account_generation,
        idempotency_key=key_hash,
        created_at=now_value,
    )
    ref = _candidate_ref(uid, candidate_id)
    alias_ref = _candidate_idempotency_alias_ref(uid, key_hash)
    semantic_claim_ref = _candidate_pending_claim_ref(uid, semantic_claim_id) if semantic_claim_id is not None else None
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)

        alias_snapshot = alias_ref.get(transaction=write_transaction)
        if alias_snapshot.exists:
            alias = _snapshot_dict(alias_snapshot)
            if alias.get('account_generation') != account_generation or alias.get('request_hash') != request_hash:
                raise CandidateConflictError('idempotency key was already used for a different proposal')
            aliased_candidate_id = alias.get('candidate_id')
            if not isinstance(aliased_candidate_id, str) or not aliased_candidate_id:
                raise CandidateConflictError('candidate idempotency alias is malformed')
            aliased_snapshot = _candidate_ref(uid, aliased_candidate_id).get(transaction=write_transaction)
            if not aliased_snapshot.exists:
                raise CandidateConflictError('candidate idempotency alias target is missing')
            aliased = parse_snapshot_strict(CandidateRecord, aliased_snapshot)
            if aliased.account_generation != account_generation:
                raise CandidateConflictError('candidate idempotency alias generation mismatch')
            return aliased

        snapshot = ref.get(transaction=write_transaction)
        if snapshot.exists:
            existing = parse_snapshot_strict(CandidateRecord, snapshot)
            if existing.account_generation != account_generation or existing.idempotency_key != key_hash:
                raise CandidateConflictError('candidate idempotency collision')
            existing_proposal = existing.as_proposal()
            if existing_proposal != proposal:
                raise CandidateConflictError('idempotency key was already used for a different proposal')
            write_transaction.set(
                alias_ref,
                {
                    'candidate_id': existing.candidate_id,
                    'request_hash': request_hash,
                    'account_generation': account_generation,
                    'created_at': now_value,
                },
            )
            return existing

        claimed_candidate: Optional[CandidateRecord] = None
        claimed_ref = None
        claimed_task_ref = None
        claimed_task: Optional[dict[str, Any]] = None
        if semantic_claim_ref is not None:
            claim_snapshot = semantic_claim_ref.get(transaction=write_transaction)
            if claim_snapshot.exists:
                claim = _snapshot_dict(claim_snapshot)
                claimed_candidate_id = claim.get('candidate_id')
                if claim.get('account_generation') == account_generation and isinstance(claimed_candidate_id, str):
                    claimed_ref = _candidate_ref(uid, claimed_candidate_id)
                    claimed_snapshot = claimed_ref.get(transaction=write_transaction)
                    if claimed_snapshot.exists:
                        candidate = parse_snapshot_strict(CandidateRecord, claimed_snapshot)
                        if candidate.account_generation == account_generation:
                            claimed_candidate = candidate
                            if candidate.status == CandidateStatus.accepted and candidate.result_task_id:
                                claimed_task_ref = _task_ref(uid, candidate.result_task_id)
                                claimed_task_snapshot = claimed_task_ref.get(transaction=write_transaction)
                                if claimed_task_snapshot.exists:
                                    claimed_task = _snapshot_dict(claimed_task_snapshot)

        alias_payload = {
            'candidate_id': candidate_id,
            'request_hash': request_hash,
            'account_generation': account_generation,
            'created_at': now_value,
        }
        reusable_active_accept = (
            claimed_candidate is not None
            and claimed_candidate.status == CandidateStatus.accepted
            and claimed_task_ref is not None
            and _accepted_task_is_active(claimed_task, account_generation=account_generation)
            and claimed_task is not None
            and _accepted_task_matches_semantic_claim(claimed_task, claimed_candidate)
        )
        reusable_pending = (
            claimed_candidate is not None
            and claimed_candidate.status == CandidateStatus.pending
            and claimed_candidate.created_at.tzinfo is not None
            and claimed_candidate.created_at >= now_value - PENDING_CANDIDATE_REUSE_WINDOW
        )
        if (
            claimed_candidate is not None
            and (reusable_pending or reusable_active_accept)
            and claimed_ref is not None
            and semantic_claim_ref is not None
        ):
            merged = _merge_candidate_annotations(claimed_candidate, proposal)
            alias_payload['candidate_id'] = merged.candidate_id
            write_transaction.update(
                claimed_ref,
                {
                    'capture_confidence': merged.capture_confidence,
                    'ownership_confidence': merged.ownership_confidence,
                    'evidence_refs': [
                        evidence_ref.model_dump(mode='python', exclude_none=True)
                        for evidence_ref in merged.evidence_refs
                    ],
                },
            )
            if reusable_active_accept and claimed_task_ref is not None and claimed_task is not None:
                write_transaction.update(
                    claimed_task_ref,
                    {
                        'capture_confidence': max(
                            _stored_confidence(claimed_task.get('capture_confidence')), merged.capture_confidence
                        ),
                        'ownership_confidence': max(
                            _stored_confidence(claimed_task.get('ownership_confidence')), merged.ownership_confidence
                        ),
                        'provenance': _merge_task_provenance(claimed_task, merged.evidence_refs),
                        'updated_at': now_value,
                    },
                )
            write_transaction.set(alias_ref, alias_payload)
            write_transaction.set(
                semantic_claim_ref,
                {
                    'candidate_id': merged.candidate_id,
                    'account_generation': account_generation,
                    'semantic_version': PENDING_CANDIDATE_SEMANTIC_VERSION,
                    'last_seen_at': now_value,
                },
            )
            return merged

        write_transaction.set(ref, record.model_dump(mode='python', exclude_none=True))
        write_transaction.set(alias_ref, alias_payload)
        if semantic_claim_ref is not None:
            write_transaction.set(
                semantic_claim_ref,
                {
                    'candidate_id': record.candidate_id,
                    'account_generation': account_generation,
                    'semantic_version': PENDING_CANDIDATE_SEMANTIC_VERSION,
                    'last_seen_at': now_value,
                },
            )
        return record

    return apply(transaction)


def get_candidate(uid: str, candidate_id: str) -> Optional[CandidateRecord]:
    snapshot = _candidate_ref(uid, candidate_id).get()
    if not snapshot.exists:
        return None
    return parse_snapshot_or_none(CandidateRecord, snapshot)


def list_candidates(
    uid: str,
    *,
    status: Optional[CandidateStatus] = None,
    account_generation: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateRecord]:
    query = db.collection('users').document(uid).collection(CANDIDATES_COLLECTION)
    if status is not None:
        query = query.where(filter=FieldFilter('status', '==', status.value))
    if account_generation is not None:
        query = query.where(filter=FieldFilter('account_generation', '==', account_generation))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    if offset:
        query = query.offset(offset)
    query = query.limit(limit)
    return parse_snapshots(CandidateRecord, query.stream())


def _task_create_storage(candidate: CandidateRecord, *, task_id: str, now: datetime) -> dict[str, Any]:
    if not isinstance(candidate.task_change, TaskCreatePayload):
        raise CandidateConflictError('task create Candidate has invalid payload')
    task = candidate.task_change.model_dump(mode='python', exclude_none=True)
    task.update(
        {
            'id': task_id,
            'task_id': task_id,
            'status': TaskStatus.active.value,
            'completed': False,
            'goal_id': candidate.goal_id,
            'workstream_id': candidate.workstream_id,
            'source': candidate.source_surface,
            'provenance': [ref.model_dump(mode='python') for ref in candidate.evidence_refs],
            'capture_confidence': candidate.capture_confidence,
            'ownership_confidence': candidate.ownership_confidence,
            'candidate_id': candidate.candidate_id,
            'account_generation': candidate.account_generation,
            'idempotency_key': candidate.idempotency_key,
            'sort_order': 0,
            'indent_level': 0,
            'created_at': now,
            'updated_at': now,
        }
    )
    return task


def _task_update_storage(candidate: CandidateRecord, *, current_task: dict[str, Any], now: datetime) -> dict[str, Any]:
    if not isinstance(candidate.task_change, TaskChangePayload):
        raise CandidateConflictError('task mutation Candidate has invalid payload')
    patch = candidate.task_change.model_dump(mode='python', exclude_unset=True)
    if candidate.goal_id is not None:
        patch['goal_id'] = candidate.goal_id
    if candidate.workstream_id is not None:
        patch['workstream_id'] = candidate.workstream_id
    patch['provenance'] = _merge_task_provenance(current_task, candidate.evidence_refs)
    if candidate.proposed_action == CandidateAction.complete:
        patch.update(status=TaskStatus.completed.value, completed=True, completed_at=now)
    elif candidate.proposed_action == CandidateAction.cancel:
        patch.update(status=TaskStatus.cancelled.value, completed=False, completed_at=None)
    elif candidate.proposed_action == CandidateAction.supersede:
        patch.update(status=TaskStatus.superseded.value, completed=False, completed_at=None)
    elif 'status' in patch:
        status = TaskStatus(patch['status'])
        patch['status'] = status.value
        patch['completed'] = status == TaskStatus.completed
        patch['completed_at'] = now if status == TaskStatus.completed else None
    patch['updated_at'] = now
    return patch


def resolve_task_candidate(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    expected_task_links: Optional[tuple[Optional[str], Optional[str]]] = None,
    now: Optional[datetime] = None,
) -> CandidateResolutionReceipt:
    """Atomically accept a task Candidate and create/update exactly one task."""

    candidate_ref = _candidate_ref(uid, candidate_id)
    resolved_at = now or datetime.now(timezone.utc)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)
        snapshot = candidate_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = parse_snapshot_strict(CandidateRecord, snapshot)
        if candidate.account_generation != account_generation:
            raise CandidateGenerationMismatchError(candidate_id)
        if candidate.status == CandidateStatus.accepted:
            return CandidateResolutionReceipt(
                candidate_id=candidate_id,
                status=CandidateStatus.accepted,
                receipt_id=_stable_contract_id('receipt', candidate_id, account_generation, 'accepted'),
                task_id=candidate.result_task_id,
                workstream_id=candidate.result_workstream_id,
                newly_resolved=False,
                resolved_at=cast(datetime, candidate.resolved_at),
            )
        if candidate.status != CandidateStatus.pending:
            raise CandidateConflictError(f'Candidate already {candidate.status.value}')
        claim_snapshot = _candidate_resolution_claim_ref(uid, candidate_id).get(transaction=write_transaction)
        if claim_snapshot.exists and _claim_blocks_resolution(_snapshot_dict(claim_snapshot), now=resolved_at):
            raise CandidateConflictError('Candidate resolution is already claimed')
        if candidate.subject_kind == CandidateSubjectKind.workstream:
            raise WorkstreamCandidateResolverUnavailableError('Ticket 04 workstream resolver is not registered')

        if candidate.proposed_action == CandidateAction.create:
            task_id = task_id_for_candidate(uid, account_generation, candidate_id)
            task_ref = _task_ref(uid, task_id)
            task_snapshot = task_ref.get(transaction=write_transaction)
            task_data = _task_create_storage(candidate, task_id=task_id, now=resolved_at)
            try:
                action_items_db.validate_task_relationship_in_transaction(
                    uid,
                    goal_id=candidate.goal_id,
                    workstream_id=candidate.workstream_id,
                    transaction=write_transaction,
                    firestore_client=db,
                    account_generation=account_generation,
                )
            except action_items_db.TaskRelationshipConflictError as exc:
                raise CandidateConflictError(str(exc)) from exc
            if task_snapshot.exists:
                existing_task = _snapshot_dict(task_snapshot)
                if existing_task.get('candidate_id') != candidate_id:
                    raise CandidateConflictError('deterministic task id collision')
            else:
                write_transaction.set(task_ref, task_data)
        else:
            task_id = cast(str, candidate.task_id)
            task_ref = _task_ref(uid, task_id)
            task_snapshot = task_ref.get(transaction=write_transaction)
            if not task_snapshot.exists:
                raise CandidateNotFoundError(f'task:{task_id}')
            current_task = _snapshot_dict(task_snapshot)
            current_task_generation = int(current_task.get('account_generation', 0))
            if current_task_generation not in {0, account_generation}:
                raise CandidateGenerationMismatchError('task account generation mismatch')
            if expected_task_links is not None:
                current_links = (current_task.get('goal_id'), current_task.get('workstream_id'))
                if current_links != expected_task_links:
                    raise CandidateConflictError('task links changed while resolving Candidate')
            task_patch = _task_update_storage(candidate, current_task=current_task, now=resolved_at)
            task_patch['account_generation'] = account_generation
            final_goal_id = task_patch.get('goal_id', current_task.get('goal_id'))
            final_workstream_id = task_patch.get('workstream_id', current_task.get('workstream_id'))
            try:
                action_items_db.validate_task_relationship_in_transaction(
                    uid,
                    goal_id=cast(Optional[str], final_goal_id),
                    workstream_id=cast(Optional[str], final_workstream_id),
                    transaction=write_transaction,
                    firestore_client=db,
                    allow_ended_goal=(final_goal_id, final_workstream_id)
                    == (current_task.get('goal_id'), current_task.get('workstream_id')),
                    account_generation=account_generation,
                )
            except action_items_db.TaskRelationshipConflictError as exc:
                raise CandidateConflictError(str(exc)) from exc
            write_transaction.update(task_ref, task_patch)

        candidate_patch = {
            'status': CandidateStatus.accepted.value,
            'resolution_reason': 'accepted',
            'result_task_id': task_id,
            'resolved_at': resolved_at,
        }
        write_transaction.update(candidate_ref, candidate_patch)
        if candidate.proposed_action == CandidateAction.create:
            write_transaction.set(
                _integration_outbox_ref(uid, candidate_id),
                {
                    'outbox_id': candidate_id,
                    'candidate_id': candidate_id,
                    'task_id': task_id,
                    'account_generation': account_generation,
                    'status': 'pending',
                    'attempt_count': 0,
                    'created_at': resolved_at,
                    'updated_at': resolved_at,
                },
            )
        return CandidateResolutionReceipt(
            candidate_id=candidate_id,
            status=CandidateStatus.accepted,
            receipt_id=_stable_contract_id('receipt', candidate_id, account_generation, 'accepted'),
            task_id=task_id,
            newly_resolved=True,
            resolved_at=resolved_at,
        )

    return apply(transaction)


def claim_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
    lease_seconds: int = 300,
) -> Optional[str]:
    """Claim a durable accepted-task integration side effect for delivery."""

    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    claim_time = now or datetime.now(timezone.utc)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None
        payload = _snapshot_dict(snapshot)
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        control = TaskWorkflowControl()
        if control_snapshot.exists:
            control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        if payload.get('account_generation') != account_generation or control.account_generation != account_generation:
            write_transaction.update(
                outbox_ref,
                {
                    'status': 'suppressed',
                    'resolution_reason': 'account_generation_mismatch',
                    'updated_at': claim_time,
                },
            )
            return None
        if not is_canonical_memory_user(uid):
            return None
        if payload.get('status') in {'completed', 'suppressed'}:
            return None
        if payload.get('status') == 'processing':
            claimed_at = payload.get('claimed_at')
            if isinstance(claimed_at, datetime) and claimed_at + timedelta(seconds=lease_seconds) > claim_time:
                return None
        lease_token = uuid4().hex
        write_transaction.update(
            outbox_ref,
            {
                'status': 'processing',
                'attempt_count': int(payload.get('attempt_count', 0)) + 1,
                'lease_token': lease_token,
                'claimed_at': claim_time,
                'updated_at': claim_time,
            },
        )
        return lease_token

    return apply(transaction)


def complete_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    lease_token: str,
    succeeded: bool,
    now: Optional[datetime] = None,
) -> bool:
    completion_time = now or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return False
        payload = _snapshot_dict(snapshot)
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        control = TaskWorkflowControl()
        if control_snapshot.exists:
            control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        if payload.get('account_generation') != account_generation or control.account_generation != account_generation:
            write_transaction.update(
                outbox_ref,
                {
                    'status': 'suppressed',
                    'resolution_reason': 'account_generation_mismatch',
                    'updated_at': completion_time,
                },
            )
            return False
        if not is_canonical_memory_user(uid):
            return False
        if payload.get('status') != 'processing' or payload.get('lease_token') != lease_token:
            return False
        write_transaction.update(
            outbox_ref,
            {
                'status': 'completed' if succeeded else 'failed',
                'completed_at': completion_time if succeeded else None,
                'lease_token': None,
                'updated_at': completion_time,
            },
        )
        return True

    return apply(transaction)


def list_candidate_integration_dispatches(
    uid: str,
    *,
    account_generation: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = (
        db.collection('users')
        .document(uid)
        .collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION)
        .where(filter=FieldFilter('account_generation', '==', account_generation))
        .where(filter=FieldFilter('status', 'in', ['pending', 'failed', 'processing']))
        .limit(limit)
    )
    return [_snapshot_dict(snapshot) for snapshot in query.stream()]


def resolve_candidate_without_mutation(
    uid: str,
    candidate_id: str,
    *,
    status: CandidateStatus,
    reason: Optional[str],
    account_generation: int,
    now: Optional[datetime] = None,
) -> CandidateResolutionReceipt:
    if status not in {CandidateStatus.rejected, CandidateStatus.expired}:
        raise ValueError('status must be rejected or expired')
    candidate_ref = _candidate_ref(uid, candidate_id)
    resolved_at = now or datetime.now(timezone.utc)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)
        snapshot = candidate_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = parse_snapshot_strict(CandidateRecord, snapshot)
        if candidate.account_generation != account_generation:
            raise CandidateGenerationMismatchError(candidate_id)
        if candidate.status == status:
            return CandidateResolutionReceipt(
                candidate_id=candidate_id,
                status=status,
                receipt_id=_stable_contract_id('receipt', candidate_id, account_generation, status.value),
                newly_resolved=False,
                resolved_at=cast(datetime, candidate.resolved_at),
            )
        if candidate.status != CandidateStatus.pending:
            raise CandidateConflictError(f'Candidate already {candidate.status.value}')
        claim_snapshot = _candidate_resolution_claim_ref(uid, candidate_id).get(transaction=write_transaction)
        if claim_snapshot.exists and _claim_blocks_resolution(_snapshot_dict(claim_snapshot), now=resolved_at):
            raise CandidateConflictError('Candidate resolution is already claimed')
        write_transaction.update(
            candidate_ref,
            {'status': status.value, 'resolution_reason': reason or status.value, 'resolved_at': resolved_at},
        )
        return CandidateResolutionReceipt(
            candidate_id=candidate_id,
            status=status,
            receipt_id=_stable_contract_id('receipt', candidate_id, account_generation, status.value),
            newly_resolved=True,
            resolved_at=resolved_at,
        )

    return apply(transaction)


def reconcile_migrated_candidate(
    uid: str,
    candidate_id: str,
    *,
    status: CandidateStatus,
    account_generation: int,
    result_task_id: Optional[str] = None,
    reason: Optional[str] = None,
    resolved_at: Optional[datetime] = None,
    claim_token: Optional[str] = None,
) -> CandidateRecord:
    """Import legacy terminal history without replaying task mutations or side effects."""

    if status == CandidateStatus.pending:
        raise ValueError('migration reconciliation requires terminal status')
    if status == CandidateStatus.accepted and not result_task_id:
        raise ValueError('accepted migration requires result_task_id')
    candidate_ref = _candidate_ref(uid, candidate_id)
    resolution_time = resolved_at or datetime.now(timezone.utc)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)
        snapshot = candidate_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = parse_snapshot_strict(CandidateRecord, snapshot)
        if candidate.account_generation != account_generation:
            raise CandidateGenerationMismatchError(candidate_id)
        if candidate.status == status:
            return candidate
        if candidate.status != CandidateStatus.pending:
            raise CandidateConflictError(f'Candidate already {candidate.status.value}')
        claim_ref = _candidate_resolution_claim_ref(uid, candidate_id)
        claim_snapshot = claim_ref.get(transaction=write_transaction)
        active_claim = _snapshot_dict(claim_snapshot) if claim_snapshot.exists else {}
        if _claim_blocks_resolution(active_claim, now=resolution_time):
            if claim_token is None or active_claim.get('claim_token') != claim_token:
                raise CandidateConflictError('Candidate resolution is claimed by another operation')
            if not _claim_owner_is_active(active_claim, now=resolution_time):
                raise CandidateConflictError('Candidate resolution claim lease expired')
            if active_claim.get('phase') != 'mutation_started':
                raise CandidateConflictError('Candidate legacy mutation has not started')
            if status != CandidateStatus.accepted or active_claim.get('result_task_id') != result_task_id:
                raise CandidateConflictError('Candidate resolution does not match the claimed legacy mutation')
        elif claim_token is not None:
            raise CandidateConflictError('Candidate resolution claim is missing')
        patch = {
            'status': status.value,
            'resolution_reason': reason or f'legacy_{status.value}',
            'resolved_at': resolution_time,
        }
        if result_task_id:
            patch['result_task_id'] = result_task_id
        write_transaction.update(candidate_ref, patch)
        if claim_token is not None:
            write_transaction.update(
                claim_ref,
                {
                    'status': 'consumed',
                    'consumed_at': resolution_time,
                    'updated_at': resolution_time,
                },
            )
        return CandidateRecord.from_storage({**candidate.model_dump(mode='python'), **patch})

    return apply(transaction)


def claim_candidate_for_legacy_promotion(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
    lease_seconds: int = 60,
    resume_active_claim: bool = False,
) -> str:
    """Fence a pending Candidate before its legacy staged projection mutates task state."""

    candidate_ref = _candidate_ref(uid, candidate_id)
    claim_ref = _candidate_resolution_claim_ref(uid, candidate_id)
    claim_time = now or datetime.now(timezone.utc)
    claim_token = uuid4().hex
    lease_expires_at = claim_time + timedelta(seconds=lease_seconds)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)
        candidate_snapshot = candidate_ref.get(transaction=write_transaction)
        if not candidate_snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = parse_snapshot_strict(CandidateRecord, candidate_snapshot)
        if candidate.account_generation != account_generation:
            raise CandidateGenerationMismatchError(candidate_id)
        if candidate.status != CandidateStatus.pending:
            raise CandidateConflictError(f'Candidate already {candidate.status.value}')
        claim_snapshot = claim_ref.get(transaction=write_transaction)
        if claim_snapshot.exists:
            claim = _snapshot_dict(claim_snapshot)
            if _claim_owner_is_active(claim, now=claim_time):
                if resume_active_claim and isinstance(claim.get('claim_token'), str):
                    return cast(str, claim['claim_token'])
                raise CandidateConflictError('Candidate has an active resolution claim')
            if claim.get('status') == 'active' and claim.get('phase') == 'mutation_started':
                result_task_id = claim.get('result_task_id')
                if not isinstance(result_task_id, str) or not result_task_id:
                    raise CandidateConflictError('Candidate mutation claim has no reserved task')
                write_transaction.update(
                    claim_ref,
                    {
                        'claim_token': claim_token,
                        'lease_expires_at': lease_expires_at,
                        'reclaimed_at': claim_time,
                        'updated_at': claim_time,
                    },
                )
                return claim_token
        write_transaction.set(
            claim_ref,
            {
                'candidate_id': candidate_id,
                'claim_kind': 'legacy_promotion',
                'claim_token': claim_token,
                'account_generation': account_generation,
                'status': 'active',
                'phase': 'pre_mutation',
                'lease_expires_at': lease_expires_at,
                'created_at': claim_time,
                'updated_at': claim_time,
            },
        )
        return claim_token

    return apply(transaction)


def begin_candidate_legacy_promotion(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    claim_token: str,
    result_task_id: str,
    preferred_existing_task_id: Optional[str] = None,
    legacy_mutation_already_committed: bool = False,
    now: Optional[datetime] = None,
    lease_seconds: int = 60,
) -> LegacyPromotionReservation:
    """Persist the non-expiring resolution fence immediately before a legacy task write."""

    if not result_task_id:
        raise ValueError('result_task_id is required')
    candidate_ref = _candidate_ref(uid, candidate_id)
    claim_ref = _candidate_resolution_claim_ref(uid, candidate_id)
    mutation_time = now or datetime.now(timezone.utc)
    lease_expires_at = mutation_time + timedelta(seconds=lease_seconds)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        _validate_write_control(control_snapshot, uid=uid, account_generation=account_generation)
        candidate_snapshot = candidate_ref.get(transaction=write_transaction)
        if not candidate_snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = parse_snapshot_strict(CandidateRecord, candidate_snapshot)
        if candidate.account_generation != account_generation:
            raise CandidateGenerationMismatchError(candidate_id)
        if candidate.status != CandidateStatus.pending:
            raise CandidateConflictError(f'Candidate already {candidate.status.value}')

        claim_snapshot = claim_ref.get(transaction=write_transaction)
        if not claim_snapshot.exists:
            raise CandidateConflictError('Candidate resolution claim is missing')
        claim = _snapshot_dict(claim_snapshot)
        if claim.get('status') != 'active' or claim.get('claim_token') != claim_token:
            raise CandidateConflictError('Candidate resolution is claimed by another operation')
        if not _claim_owner_is_active(claim, now=mutation_time):
            raise CandidateConflictError('Candidate resolution claim lease expired')
        if claim.get('phase') == 'mutation_started':
            reserved_task_id = claim.get('result_task_id')
            if not isinstance(reserved_task_id, str) or not reserved_task_id:
                raise CandidateConflictError('Candidate mutation claim has no reserved task')
            reservation_kind = claim.get('reservation_kind')
            if reservation_kind not in {'create', 'existing', 'committed'}:
                raise CandidateConflictError('Candidate mutation claim has no reservation kind')
            return LegacyPromotionReservation(task_id=reserved_task_id, kind=cast(str, reservation_kind))
        if claim.get('phase', 'pre_mutation') != 'pre_mutation':
            raise CandidateConflictError('Candidate resolution claim has an invalid phase')

        reserved_task_id = result_task_id
        reservation_kind = 'committed' if legacy_mutation_already_committed else 'create'
        if preferred_existing_task_id is not None and not legacy_mutation_already_committed:
            preferred_snapshot = _task_ref(uid, preferred_existing_task_id).get(transaction=write_transaction)
            preferred_task = _snapshot_dict(preferred_snapshot) if preferred_snapshot.exists else {}
            preferred_is_active = (
                preferred_snapshot.exists
                and preferred_task.get('completed') is False
                and not preferred_task.get('deleted', False)
                and preferred_task.get('status', TaskStatus.active.value) == TaskStatus.active.value
            )
            if preferred_is_active:
                reserved_task_id = preferred_existing_task_id
                reservation_kind = 'existing'

        write_transaction.update(
            claim_ref,
            {
                'phase': 'mutation_started',
                'result_task_id': reserved_task_id,
                'reservation_kind': reservation_kind,
                'mutation_started_at': mutation_time,
                'lease_expires_at': lease_expires_at,
                'updated_at': mutation_time,
            },
        )
        return LegacyPromotionReservation(task_id=reserved_task_id, kind=reservation_kind)

    return apply(transaction)


__all__ = [
    'CandidateConflictError',
    'CandidateGenerationMismatchError',
    'CandidateNotFoundError',
    'CandidateStoreError',
    'LegacyPromotionReservation',
    'WorkstreamCandidateResolverUnavailableError',
    'candidate_id_for_idempotency',
    'begin_candidate_legacy_promotion',
    'claim_candidate_integration_dispatch',
    'claim_candidate_for_legacy_promotion',
    'complete_candidate_integration_dispatch',
    'create_candidate',
    'get_candidate',
    'list_candidate_integration_dispatches',
    'list_candidates',
    'pending_candidate_semantic_identity',
    'reconcile_migrated_candidate',
    'resolve_candidate_without_mutation',
    'resolve_task_candidate',
    'task_id_for_candidate',
]
