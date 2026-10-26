"""Render conversation transcripts for LLM prompts with the configured user name.

#5319: ``TranscriptSegment.segments_as_string`` defaults missing ``user_name`` to
``"You"``. Callers that feed transcripts into summary / summarization-app LLMs
must pass the profile name from ``get_user_name`` so the model never sees the
generic label when the user has configured one.

SCA-454: action-item transcripts use the compact cluster-key render. Turns are
``[<segment-id> <cluster>] text`` (run-length: the key is omitted on consecutive
same-cluster turns) and speaker identity is paid for once as ``spk`` map lines in
the shared prompt prefix metadata — never as ``Speaker N:`` dialogue labels, which
summarizer LLMs copy verbatim into titles and overviews.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable, List, Optional, Protocol, Sequence

from config.refactor_modes import serving_for
from database.auth import get_user_name
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.conversations.owner_attribution import (
    OwnerAttributionEvidence,
    may_attribute_to_owner,
    confident_owner_segments,
)
from utils.conversations.wake_word import WAKE_WORD_MARKER, escape_spoken_wake_word_marker, find_wake_word_segment_ids
from utils.speakers.display import DisplayParticipants, display_participants


class _TranscriptSource(Protocol):
    def get_transcript(
        self, include_timestamps: bool, people: Optional[List[Person]] = None, user_name: Optional[str] = None
    ) -> str: ...


@dataclass(frozen=True)
class SpeakerCluster:
    """Hard identity evidence for one ``(speaker_id_scope, speaker_id)`` cluster (#3602).

    ``speaker_id`` is storage-only evidence, never the rendered prompt key; ``scope`` is the
    segment's ``speaker_id_scope``. Merged and multi-source transcripts reuse
    ids across scopes, so evidence is tallied per scope and never pooled.
    ``owner`` is set when a segment is ``is_user``; ``names`` are the stripped,
    distinct names of the people its segments are tagged with, first seen first.
    ``speech_seconds`` sums each segment's ``max(0, end - start)`` (talk share in
    any script); ``words`` counts whitespace words for transcripts without timing.
    """

    speaker_id: int
    scope: Optional[str]
    owner: bool
    names: tuple[str, ...]
    speech_seconds: float
    words: int


class SpeakerMap(dict[str, Optional[str]]):
    """``cluster -> bound name`` mapping that also carries owner-aware identity evidence.

    It is the plain mapping every caller already reads, and the rendered ``spk``
    lines are unchanged. ``owner_name`` is the account owner's real profile name
    (``None`` when only the ``'You'`` fallback is known) and ``clusters`` the
    per-scope ``SpeakerCluster`` evidence in first-appearance order, so title
    naming (#3602) uses only voice/tag bindings and can tell the account owner
    from the people worth naming.
    """

    def __init__(
        self,
        *args: Any,
        owner_name: Optional[str] = None,
        clusters: Iterable[SpeakerCluster] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.owner_name = owner_name
        self.source_segment_ids: Optional[frozenset[str]] = None
        self.clusters: tuple[SpeakerCluster, ...] = tuple(clusters)


def _speech_seconds(segment: Any) -> float:
    try:
        seconds = float(getattr(segment, 'end', 0.0) or 0.0) - float(getattr(segment, 'start', 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.0


def _speaker_map(
    segments: List[Any],
    user_name: str,
    people_map: dict[str, str],
    *,
    owner_name: Optional[str] = None,
    display: DisplayParticipants | None = None,
) -> SpeakerMap:
    """Cluster -> bound display name (None = unresolved), ordered by first appearance.

    A cluster is bound only through hard evidence: ``is_user`` (profile name) or a
    matched ``person_id`` (person name). Names are never invented.
    """
    speaker_map = SpeakerMap(owner_name=owner_name)
    display = display or display_participants(segments, names=people_map, owner_name=user_name)
    tallies: dict[tuple[Optional[str], int], tuple[bool, list[str], float, int]] = {}
    for segment in segments:
        speaker_id = getattr(segment, 'speaker_id', None)
        if speaker_id is None:
            continue
        person_name = display.for_segment(segment).name
        if person_name and person_name.startswith('likely '):
            person_name = None
        prompt_key = display.for_segment(segment).key
        key = (getattr(segment, 'speaker_id_scope', None), speaker_id)
        owner, names, seconds, words = tallies.get(key, (False, [], 0.0, 0))
        tagged = (person_name or '').strip()
        if not getattr(segment, 'is_user', False) and tagged and tagged not in names:
            names.append(tagged)
        tallies[key] = (
            owner or getattr(segment, 'is_user', False),
            names,
            seconds + _speech_seconds(segment),
            words + len((getattr(segment, 'text', '') or '').split()),
        )
        if prompt_key not in speaker_map:
            speaker_map[prompt_key] = display.for_segment(segment).name
    speaker_map.clusters = tuple(
        SpeakerCluster(
            speaker_id=speaker_id,
            scope=scope,
            owner=owner,
            names=tuple(names),
            speech_seconds=seconds,
            words=words,
        )
        for (scope, speaker_id), (owner, names, seconds, words) in tallies.items()
    )
    return speaker_map


def conversation_action_item_speaker_labels(
    uid: str,
    conversation: Any,
    people: Optional[List[Person]] = None,
) -> list[dict[str, str]]:
    """Return the same stable labels rendered into the action-item transcript."""

    user_name = get_user_name(uid, use_default=False) or 'You'
    people_map = {person.id: person.name for person in people} if people else {}
    segments = getattr(conversation, 'transcript_segments', None) or []
    display = display_participants(segments, names=people_map, owner_name=user_name)
    labels: list[dict[str, str]] = []
    for segment in getattr(conversation, 'transcript_segments', None) or []:
        if not getattr(segment, 'id', None):
            continue
        labels.append(
            {
                'segment_id': str(segment.id),
                'speaker_label': display.label(segment),
                'speaker_role': 'primary_user' if segment.is_user else 'other',
            }
        )
    return labels


def memory_transcript_from_segments(
    segments: List[TranscriptSegment],
    *,
    user_name: Optional[str] = None,
    people: Optional[List[Person]] = None,
) -> str:
    """Render memory evidence without turning ambiguous diarization into identity.

    Copies are local to this render; summaries and action items retain their
    existing presentation and the original transcript segments are untouched.
    """
    rendered_segments, owner_note = owner_safe_transcript_segments(segments)
    transcript = TranscriptSegment.segments_as_string(rendered_segments, user_name=user_name, people=people)
    return f"{owner_note}\n{transcript}" if owner_note and transcript else transcript


def _owner_evidence_view(segment: Any) -> Any:
    """Adapt mapping rows to the attribute shape consumed by the shared owner gate."""
    if not isinstance(segment, Mapping):
        return segment
    return SimpleNamespace(
        speaker_id=segment.get('speaker_id'),
        speaker_id_scope=segment.get('speaker_id_scope'),
        is_user=bool(segment.get('is_user', False)),
        _speaker_id_synthesized=bool(segment.get('_speaker_id_synthesized', False)),
    )


def _clear_owner_claim(segment: Any) -> Any:
    """Copy a segment before removing an untrusted owner attribution."""
    if isinstance(segment, Mapping):
        copied = dict(segment)
        copied['is_user'] = False
        copied['person_id'] = None
        return copied
    if hasattr(segment, 'model_copy'):
        return segment.model_copy(update={'is_user': False, 'person_id': None})
    copied = SimpleNamespace(**vars(segment))
    copied.is_user = False
    copied.person_id = None
    return copied


def owner_safe_transcript_segments(
    segments: Sequence[Any], *, evidence_segments: Optional[Sequence[Any]] = None
) -> tuple[list[Any], str]:
    """Strip weak owner labels using the same speaker-cluster rule as memory transcripts.

    ``evidence_segments`` lets a transcript excerpt use the complete conversation as its owner
    evidence. The returned header is empty when the owner has a unique supported cluster.
    """
    selected = list(segments)
    evidence_rows = list(evidence_segments) if evidence_segments is not None else selected
    evidence = OwnerAttributionEvidence.from_segments([_owner_evidence_view(row) for row in evidence_rows])
    rendered = [
        (
            _clear_owner_claim(segment)
            if bool(_owner_evidence_view(segment).is_user)
            and not may_attribute_to_owner(evidence, segment=_owner_evidence_view(segment))
            else segment
        )
        for segment in selected
    ]
    has_text = any(
        (
            str(row.get('text') or '').strip()
            if isinstance(row, Mapping)
            else str(getattr(row, 'text', '') or '').strip()
        )
        for row in rendered
    )
    if has_text and not may_attribute_to_owner(evidence):
        return rendered, (
            f"[Diarization marked {evidence.owner_speaker_ids} of {evidence.distinct_speaker_ids} speaker clusters "
            "as the account owner; owner identity is UNTRUSTED in this transcript — "
            "treat first-person statements as unattributed]"
        )
    return rendered, ''


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
) -> tuple[str, dict[str, Optional[str]]]:
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

    profile_name = get_user_name(uid, use_default=False)
    people_map = {person.id: person.name for person in people} if people else {}
    if serving_for('NOTES_PACKET_V2_MODE', uid):
        from utils.llm.notes_packet import get_evidence
        from utils.llm.notes_language_inputs import in_profile_segments

        return render_cluster_transcript(
            in_profile_segments(segments),
            names=people_map,
            owner_name=profile_name,
            evidence=get_evidence(uid, getattr(conversation, 'id', None)),
            mark_wake_words=mark_wake_words,
            resolution_available=getattr(getattr(conversation, 'speaker_resolution', None), 'status', None)
            != 'unavailable',
        )
    # refactor: superseded by render_cluster_transcript when NOTES_PACKET_V2_MODE=serve
    display = display_participants(
        segments,
        names=people_map,
        owner_name=profile_name or 'You',
        resolution=getattr(conversation, 'speaker_resolution', None),
    )
    speaker_map = _speaker_map(segments, profile_name or 'You', people_map, owner_name=profile_name, display=display)
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
        speaker_key = display.for_segment(segment).key
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
) -> tuple[str, str, dict[str, Optional[str]]]:
    """Return the normal transcript, the compact task transcript, and its speaker map."""
    normal_transcript = conversation_transcript_for_llm(uid, conversation, people)
    compact_transcript, speaker_map = conversation_transcript_and_speaker_map(
        uid, conversation, people, mark_wake_words=True
    )
    return normal_transcript, compact_transcript, speaker_map


__all__ = [
    'SpeakerCluster',
    'SpeakerMap',
    'memory_transcript_from_segments',
    'owner_safe_transcript_segments',
    'conversation_action_item_speaker_labels',
    'conversation_transcript_and_speaker_map',
    'conversation_transcript_for_action_items',
    'conversation_transcript_for_llm',
    'conversation_transcripts_for_llm',
]


def render_cluster_transcript(
    segments: Sequence[Any],
    *,
    names: Mapping[str, str],
    owner_name: Optional[str] = None,
    evidence: Any = None,
    mark_wake_words: bool = False,
    resolution_available: bool = True,
) -> tuple[str, SpeakerMap]:
    """The notes/moments renderer: scoped voice keys, one owner gate and evidence bands.

    Copies are prompt-only. It never rewrites stored segment labels or infers an
    identity from calendar, contacts, story content or a numeric speaker key.
    """
    rows = [SimpleNamespace(**{'is_user': False, **dict(row)}) if isinstance(row, Mapping) else row for row in segments]
    trusted_owner_rows = {id(row) for row in confident_owner_segments(rows)}
    rows = [
        _clear_owner_claim(row) if getattr(row, 'is_user', False) and id(row) not in trusted_owner_rows else row
        for row in rows
    ]
    rows, owner_note = owner_safe_transcript_segments(rows)
    display = display_participants(
        rows,
        names=names,
        owner_name=owner_name or 'You',
        evidence=evidence,
        resolution={'status': 'resolved' if resolution_available else 'unavailable'},
        allow_automatic_names=resolution_available,
    )
    labels = SpeakerMap(owner_name=owner_name)
    labels.clusters = _speaker_map(rows, owner_name or 'You', dict(names), display=display).clusters
    labels.source_segment_ids = frozenset(str(row.id) for row in rows if getattr(row, 'id', None))
    turns = []
    wake_ids = find_wake_word_segment_ids(rows) if mark_wake_words else frozenset()
    for index, row in enumerate(rows):
        text = str(getattr(row, 'text', '') or '').strip()
        if not text:
            continue
        segment_id = str(getattr(row, 'id', None) or f'moment-{index}')
        participant = display.for_segment(row)
        key, name = participant.key, participant.name
        if name and name.startswith('likely '):
            # Suggestions remain useful on speaker-review surfaces, but do not
            # become a named speaker binding in summaries.
            name = None
        # If a fallback cluster has contradictory labels, retain no named claim.
        if key in labels and labels[key] != name:
            labels[key] = None
        elif key not in labels:
            labels[key] = name
        marker = f'{WAKE_WORD_MARKER} ' if segment_id in wake_ids else ''
        if mark_wake_words:
            text = escape_spoken_wake_word_marker(text)
            segment_id = escape_spoken_wake_word_marker(segment_id)
        turns.append(f'[{segment_id} {key}] {marker}{text}')
    metadata = '\n'.join(f'spk {key} {name or "?"}' for key, name in labels.items())
    return '\n'.join(part for part in (owner_note, metadata, '\n\n'.join(turns)) if part), labels
