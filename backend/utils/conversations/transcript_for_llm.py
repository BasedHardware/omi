"""Render conversation transcripts for LLM prompts with the configured user name.

#5319: ``TranscriptSegment.segments_as_string`` defaults missing ``user_name`` to
``"User"``. Callers that feed transcripts into summary / summarization-app LLMs
must pass the profile name from ``get_user_name`` so the model never sees the
generic label when the user has configured one.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol

from database.auth import get_user_name
from models.other import Person


class _TranscriptSource(Protocol):
    def get_transcript(
        self, include_timestamps: bool, people: Optional[List[Person]] = None, user_name: Optional[str] = None
    ) -> str: ...


def conversation_transcript_for_llm(
    uid: str,
    conversation: _TranscriptSource,
    people: Optional[List[Person]] = None,
    *,
    include_timestamps: bool = False,
) -> str:
    """Build a transcript string for LLM prompts using the user's configured name."""
    user_name = get_user_name(uid, use_default=False)
    return conversation.get_transcript(include_timestamps, people=people, user_name=user_name)


def conversation_transcript_for_action_items(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
) -> str:
    """Render stable segment IDs so extracted tasks can retain exact transcript provenance."""
    segments = getattr(conversation, 'transcript_segments', None) or []
    if not segments:
        return conversation_transcript_for_llm(uid, conversation, people)

    user_name = get_user_name(uid, use_default=False) or 'User'
    people_map = {person.id: person.name for person in people} if people else {}
    lines: list[str] = []
    for segment in segments:
        segment_id = getattr(segment, 'id', None)
        if not segment_id:
            continue
        speaker_name = user_name
        if not segment.is_user:
            speaker_name = people_map.get(segment.person_id) if segment.person_id else None
            speaker_name = speaker_name or f'Speaker {segment.speaker_id}'
        lines.append(
            f'[segment:{segment_id} {segment.start:.3f}-{segment.end:.3f}] ' f'{speaker_name}: {segment.text.strip()}'
        )
    return '\n\n'.join(lines)


def conversation_transcripts_for_llm(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
) -> tuple[str, str]:
    """Return the normal transcript and the segment-labelled task transcript."""
    return (
        conversation_transcript_for_llm(uid, conversation, people),
        conversation_transcript_for_action_items(uid, conversation, people),
    )
