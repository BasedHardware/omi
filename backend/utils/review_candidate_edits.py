"""Review's optional task edits stay inside the existing Candidate transaction."""

from models.action_item import TaskCreatePayload
from models.candidate import CandidateAction, CandidateRecord, CandidateSubjectKind
from database.candidates import CandidateConflictError


def edited_candidate(candidate: CandidateRecord, edits: dict) -> CandidateRecord:
    if candidate.subject_kind != CandidateSubjectKind.task or candidate.proposed_action != CandidateAction.create:
        raise CandidateConflictError('Review edits require a task-create candidate')
    if not set(edits) <= {'edited_description', 'due_at', 'workstream_id'}:
        raise CandidateConflictError('Unsupported task edits')
    payload = candidate.task_change.model_dump(mode='python')
    if 'edited_description' in edits:
        description = (edits['edited_description'] or '').strip()
        if not description:
            raise CandidateConflictError('Task description must not be blank')
        payload['description'] = description
    if 'due_at' in edits:
        payload['due_at'] = edits['due_at']
    updates = {'task_change': TaskCreatePayload.model_validate(payload)}
    if 'workstream_id' in edits:
        updates['workstream_id'] = edits['workstream_id']
    return candidate.model_copy(update=updates)
