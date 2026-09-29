"""Prepare a summary gesture for the existing, separate Candidate accept API."""

import database.candidates as candidates_db
from database._client import get_firestore_client
from database.summary_task_links import SummaryTaskConflictError, read_summary_task_row
from models.candidate import CandidateRecord, CandidateStatus, SummaryTaskReference
from utils.task_intelligence import candidate_service


def prepare_summary_task(
    uid: str,
    selected: SummaryTaskReference,
    *,
    idempotency_key: str,
    account_generation: int,
) -> CandidateRecord:
    row = read_summary_task_row(uid, selected)
    if row.item.target_task_id:
        # Reopened summaries and lost accept responses replay their saved task;
        # a completed/edited task is not grounds to create another one.
        task = (
            get_firestore_client()
            .collection('users')
            .document(uid)
            .collection('action_items')
            .document(row.item.target_task_id)
            .get()
        )
        data = task.to_dict() if task.exists else None
        candidate_id = data.get('candidate_id') if data else None
        candidate = (
            candidates_db.get_candidate(uid, candidate_id) if isinstance(candidate_id, str) and candidate_id else None
        )
        if (
            candidate is None
            or candidate.account_generation != account_generation
            or candidate.status != CandidateStatus.accepted
            or candidate.result_task_id != row.item.target_task_id
        ):
            raise SummaryTaskConflictError('Linked task is unavailable; refresh the conversation')
        return candidate
    # A new key belongs to this explicit gesture. Concurrent/retried prepares
    # coalesce with the extraction's exact semantic claim; stale pending claims
    # may be replaced by fresh user intent, never silently accepted.
    return candidate_service.create_candidate(
        uid,
        row.proposal(),
        idempotency_key=idempotency_key,
        account_generation=account_generation,
    )
