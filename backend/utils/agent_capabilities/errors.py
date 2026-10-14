"""Stable non-content error contracts for guarded owner mutations."""

TRANSCRIPT_EDIT_HTTP_ERRORS = {
    'not_found': (404, 'Conversation not found'),
    'locked': (402, 'Unlimited Plan Required to access this conversation.'),
    'segment_not_found': (404, 'Segment not found'),
    'conflict': (409, 'Transcript changed; refresh before retrying'),
    'correction_limit': (409, 'Transcript correction history is full'),
}

CONFLICT_CODES = {
    'Dream memory changed': 'agent_memory_changed',
    'Dream task changed': 'agent_task_changed',
    'Dream task generation changed': 'agent_generation_changed',
    'Cleanup task generation changed': 'agent_generation_changed',
    'Dream conversation changed': 'agent_conversation_changed',
    'Dream person changed': 'agent_person_changed',
    'Dream title was set by the user': 'agent_user_title_protected',
    'Agent summary changed': 'agent_summary_changed',
    'Dream summary changed': 'agent_summary_changed',
    'Dream entity summary changed': 'agent_summary_changed',
    'Duplicate facts must share visibility and subject': 'agent_memory_scope_mismatch',
    'Replacement must share privacy, subject and attribute': 'agent_memory_scope_mismatch',
    'Only active canonical facts may be proposed': 'agent_memory_inactive',
    'Dream proposal evidence changed': 'agent_evidence_changed',
    'Dream proposal target changed': 'agent_target_changed',
    'Dream proposal evidence unavailable': 'agent_evidence_unavailable',
    'Dream proposal evidence changed during apply': 'agent_evidence_changed',
    'Dream target unavailable': 'agent_target_unavailable',
    'Cleanup target unavailable': 'agent_target_unavailable',
    'Dream conversation unavailable': 'agent_target_unavailable',
    'review_surface_disabled': 'agent_review_disabled',
}

SCHEMA_MESSAGES = frozenset(
    {
        'An edit requires a nonblank reason',
        'Only memory supersession may carry effective_from',
        'A merge needs a distinct other ref and preserves its text',
        'Dismissal and retirement change status only',
        'Language requires a bounded tag, not a second record',
        'Retirement changes status only',
        'Supersede requires exactly one of other or after',
        'Memory hygiene requires a reason',
        'Only merge edits may name a second record',
        'Text edits require corrected text in after',
        'Spelling edits require exact wrong text in before',
        'Summary edits require a conversation target',
        'Summary edits require their conversation as evidence and no other target',
        'Summary edits require a short changed value',
        'End must follow start',
        'Time filters require UTC offsets',
        'Exactly the matching question payload is required',
    }
)


def schema_feedback(row):
    message = row['msg']
    if row['type'] == 'value_error':
        message = message.removeprefix('Value error, ')
        if message not in SCHEMA_MESSAGES:
            return {}
    return {'message': message}


def rejection_code(error):
    message = str(error)
    if message in CONFLICT_CODES:
        return CONFLICT_CODES[message]
    if message.startswith(('dream_', 'agent_')) and len(message) < 80 and message.replace('_', '').isalnum():
        return message
    return 'dream_stale_or_unavailable'
