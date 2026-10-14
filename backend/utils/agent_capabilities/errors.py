"""Stable non-content error contracts for guarded owner mutations."""

TRANSCRIPT_EDIT_HTTP_ERRORS = {
    'not_found': (404, 'Conversation not found'),
    'locked': (402, 'Unlimited Plan Required to access this conversation.'),
    'segment_not_found': (404, 'Segment not found'),
    'conflict': (409, 'Transcript changed; refresh before retrying'),
    'correction_limit': (409, 'Transcript correction history is full'),
}
