"""Pure eligibility gate; optional context retrieval stays lazily loaded."""

from typing import Any, Mapping, Optional

from models.calendar_context import CalendarMeetingContext
from utils.conversations.meeting_treatment import deduplicated_transcribed_speech_seconds

MIN_CLUSTER_COUNT = 2
MIN_SPEECH_SECONDS = 300


def should_gather_meeting_context(conversation: Any, resolved_context: Optional[CalendarMeetingContext]) -> bool:
    """Whether this conversation is meeting-like enough to pay for context reads.

    True for a desktop meeting-role capture, whenever meeting identity already
    resolved, or when the transcript shows a real multi-party conversation
    (>= 2 speaker clusters and >= 300 seconds of deduplicated speech). The rich
    flag check itself stays at the call site so this stays a pure gate.
    """
    source = getattr(conversation, 'source', None)
    external_data = getattr(conversation, 'external_data', None) or {}
    if (
        getattr(source, 'value', source) == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
    ):
        return True
    if resolved_context is not None:
        return True
    segments = getattr(conversation, 'transcript_segments', None) or []
    cluster_ids = {
        getattr(segment, 'speaker_id', None) for segment in segments if getattr(segment, 'speaker_id', None) is not None
    }
    if len(cluster_ids) < MIN_CLUSTER_COUNT:
        return False
    return deduplicated_transcribed_speech_seconds(segments) >= MIN_SPEECH_SECONDS
