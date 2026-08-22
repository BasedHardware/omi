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
from utils.conversations.wake_word import WAKE_WORD_MARKER, escape_spoken_wake_word_marker, find_wake_word_segment_ids


class _TranscriptSource(Protocol):
    def get_transcript(
        self, include_timestamps: bool, people: Optional[List[Person]] = None, user_name: Optional[str] = None
    ) -> str: ...


def _speaker_label(segment: Any, user_name: str, people_map: dict[str, str]) -> str:
    if segment.is_user:
        return user_name
    speaker_name = people_map.get(segment.person_id) if segment.person_id else None
    return speaker_name or f'Speaker {segment.speaker_id}'


def conversation_action_item_speaker_labels(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
) -> list[dict[str, str]]:
    """Return the same stable labels rendered into the action-item transcript."""

    user_name = get_user_name(uid, use_default=False) or 'User'
    people_map = {person.id: person.name for person in people} if people else {}
    labels: list[dict[str, str]] = []
    for segment in getattr(conversation, 'transcript_segments', None) or []:
        if not getattr(segment, 'id', None):
            continue
        labels.append(
            {
                'segment_id': str(segment.id),
                'speaker_label': _speaker_label(segment, user_name, people_map),
                'speaker_role': 'primary_user' if segment.is_user else 'other',
            }
        )
    return labels


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
    *,
    mark_wake_words: bool = False,
) -> str:
    """Render stable segment IDs so extracted tasks can retain exact transcript provenance."""
    segments = getattr(conversation, 'transcript_segments', None) or []
    if not segments:
        return conversation_transcript_for_llm(uid, conversation, people)

    user_name = get_user_name(uid, use_default=False) or 'User'
    people_map = {person.id: person.name for person in people} if people else {}
    wake_word_segment_ids = find_wake_word_segment_ids(segments) if mark_wake_words else frozenset()
    lines: list[str] = []
    for segment in segments:
        segment_id = getattr(segment, 'id', None)
        if not segment_id:
            continue
        segment_id = str(segment_id)
        speaker_name = _speaker_label(segment, user_name, people_map)
        marker = f'{WAKE_WORD_MARKER} ' if segment_id in wake_word_segment_ids else ''
        segment_text = segment.text.strip()
        if mark_wake_words:
            segment_id = escape_spoken_wake_word_marker(segment_id)
            speaker_name = escape_spoken_wake_word_marker(speaker_name)
            segment_text = escape_spoken_wake_word_marker(segment_text)
        lines.append(
            f'[segment:{segment_id} {segment.start:.3f}-{segment.end:.3f}] {marker}' f'{speaker_name}: {segment_text}'
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
        conversation_transcript_for_action_items(uid, conversation, people, mark_wake_words=True),
    )


__all__ = [
    'conversation_action_item_speaker_labels',
    'conversation_transcript_for_action_items',
    'conversation_transcript_for_llm',
    'conversation_transcripts_for_llm',
]
