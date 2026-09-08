"""Render conversation transcripts for LLM prompts with the configured user name.

#5319: ``TranscriptSegment.segments_as_string`` defaults missing ``user_name`` to
``"User"``. Callers that feed transcripts into summary / summarization-app LLMs
must pass the profile name from ``get_user_name`` so the model never sees the
generic label when the user has configured one.

SCA-454: action-item transcripts use the compact cluster-key render. Turns are
``[<segment-id> <cluster>] text`` (run-length: the key is omitted on consecutive
same-cluster turns) and speaker identity is paid for once as ``spk`` map lines in
the shared prompt prefix metadata — never as ``Speaker N:`` dialogue labels, which
summarizer LLMs copy verbatim into titles and overviews.
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


def _speaker_map(segments: List[Any], user_name: str, people_map: dict[str, str]) -> dict[int, Optional[str]]:
    """Cluster -> bound display name (None = unresolved), ordered by first appearance.

    A cluster is bound only through hard evidence: ``is_user`` (profile name) or a
    matched ``person_id`` (person name). Names are never invented.
    """
    speaker_map: dict[int, Optional[str]] = {}
    for segment in segments:
        speaker_id = getattr(segment, 'speaker_id', None)
        if speaker_id is None or speaker_id in speaker_map:
            continue
        if segment.is_user:
            speaker_map[speaker_id] = user_name
        else:
            speaker_map[speaker_id] = people_map.get(segment.person_id) if segment.person_id else None
    return speaker_map


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


_UNSET = object()


def conversation_transcript_and_speaker_map(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
    *,
    mark_wake_words: bool = False,
) -> tuple[str, dict[int, Optional[str]]]:
    """Render the compact cluster-key transcript plus its ``spk`` map (SCA-454).

    Turns are ``[<segment-id> <cluster>] text``; consecutive turns by the same
    cluster omit the key (``[<segment-id>] text``). There are no timestamps and no
    ``Name:`` labels — citations key on the segment id, and speaker identity is
    delivered once through the map (``spk <cluster> <name|?>`` metadata lines in
    the shared prompt prefix), so the summarizer never sees a copyable
    ``Speaker N:`` dialogue label. Bound names still appear in the map and may be
    used in prose.
    """
    segments = getattr(conversation, 'transcript_segments', None) or []
    if not segments:
        return conversation_transcript_for_llm(uid, conversation, people), {}

    user_name = get_user_name(uid, use_default=False) or 'User'
    people_map = {person.id: person.name for person in people} if people else {}
    speaker_map = _speaker_map(segments, user_name, people_map)
    wake_word_segment_ids = find_wake_word_segment_ids(segments) if mark_wake_words else frozenset()
    lines: list[str] = []
    previous_speaker: Any = _UNSET
    for segment in segments:
        segment_id = getattr(segment, 'id', None)
        if not segment_id:
            continue
        segment_id = str(segment_id)
        marker = f'{WAKE_WORD_MARKER} ' if segment_id in wake_word_segment_ids else ''
        segment_text = segment.text.strip()
        if mark_wake_words:
            segment_id = escape_spoken_wake_word_marker(segment_id)
            segment_text = escape_spoken_wake_word_marker(segment_text)
        speaker_key = segment.speaker_id
        header = f'[{segment_id}]' if speaker_key == previous_speaker else f'[{segment_id} {speaker_key}]'
        lines.append(f'{header} {marker}{segment_text}')
        previous_speaker = speaker_key
    return '\n\n'.join(lines), speaker_map


def conversation_transcript_for_action_items(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
    *,
    mark_wake_words: bool = False,
) -> str:
    """Render stable segment IDs so extracted tasks can retain exact transcript provenance."""
    return conversation_transcript_and_speaker_map(uid, conversation, people, mark_wake_words=mark_wake_words)[0]


def conversation_transcripts_for_llm(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
) -> tuple[str, str, dict[int, Optional[str]]]:
    """Return the normal transcript, the compact task transcript, and its speaker map."""
    normal_transcript = conversation_transcript_for_llm(uid, conversation, people)
    compact_transcript, speaker_map = conversation_transcript_and_speaker_map(
        uid, conversation, people, mark_wake_words=True
    )
    return normal_transcript, compact_transcript, speaker_map


__all__ = [
    'conversation_action_item_speaker_labels',
    'conversation_transcript_and_speaker_map',
    'conversation_transcript_for_action_items',
    'conversation_transcript_for_llm',
    'conversation_transcripts_for_llm',
]
