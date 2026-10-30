"""Pure lifecycle projection with no customer content in its output."""

from datetime import datetime
from typing import Any

from models.conversation_enums import ConversationStatus, PostProcessingStatus
from models.support import SupportTraceRow


def project_support_trace(conversation: dict[str, Any]) -> SupportTraceRow:
    status = conversation['status']
    postprocessing = conversation.get('postprocessing') or {}
    post_status = conversation.get('postprocessing_status', postprocessing.get('status'))
    processed = post_status == PostProcessingStatus.completed or (
        status == ConversationStatus.completed
        and post_status in (None, PostProcessingStatus.not_started, PostProcessingStatus.completed)
    )
    discarded = bool(conversation.get('discarded'))
    deleted = bool(conversation.get('deleted'))
    failed = status == ConversationStatus.failed or post_status == PostProcessingStatus.failed
    failure_stage = None
    if failed:
        failure_stage = 'save' if processed else 'process'

    started_at = conversation['started_at']
    finished_at = conversation.get('finished_at')
    duration = None
    if isinstance(started_at, datetime) and isinstance(finished_at, datetime):
        duration = max(0.0, (finished_at - started_at).total_seconds())

    audio = conversation.get('audio_files')
    transcript_fields = ('transcript', 'transcript_segments', 'segments')
    # The server reader never fetches transcript payloads. Its existing storage
    # marker proves a nonempty compressed field (even an encoded empty list).
    # Legacy documents without that marker conservatively report false.
    has_transcript = (
        any(conversation.get(field) for field in transcript_fields)
        if any(field in conversation for field in transcript_fields)
        else conversation.get('transcript_segments_compressed') is True
    )
    return SupportTraceRow(
        conversation_id=conversation['id'],
        started_at=started_at,
        duration_seconds=duration,
        status=status,
        postprocessing_status=post_status,
        captured=True,
        synced=True,
        processed=processed,
        saved=processed and status == ConversationStatus.completed and not discarded and not deleted,
        discarded=discarded,
        deleted=deleted,
        failed=failed,
        failure_stage=failure_stage,
        audio_present=isinstance(audio, list) and bool(audio),
        has_transcript=has_transcript,
    )
