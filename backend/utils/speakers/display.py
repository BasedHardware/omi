"""The presentation boundary: raw voice identities never become names or prompt keys.

Keep storage and correction IDs untouched. Build once from the whole conversation
(or episode) before selecting excerpts. Names require segment bindings or the
speaker-evidence policy's label-eligible decision; roster candidates are not labels.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
import hashlib
import json
import re
from typing import Any

from utils.speaker_display import SpeakerLabeler
from utils.speakers.display_metrics import record_count_guard
from utils.speakers.policy import MIN_EVIDENCE_SECONDS

MAX_UNNAMED_VOICES = 8
MIN_VOICE_SECONDS = 3.0


@dataclass(frozen=True, repr=False)
class DiarizationLabel:
    """Opaque storage identity; explicit raw_for_transport is only for wire adapters."""

    raw_for_transport: int | str | None
    scope: str | None = None

    def __str__(self) -> str:
        raise TypeError('Resolve DiarizationLabel through display_participants')

    def __repr__(self) -> str:
        return '<DiarizationLabel>'


def field(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def _seconds(row: Any) -> float:
    try:
        value = float(field(row, 'end', 0) or 0) - float(field(row, 'start', 0) or 0)
    except (ValueError, TypeError):
        return 0.0
    return value if isfinite(value) and value > 0 else 0.0


def _clean_name(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    value = name.strip()
    return (
        value if value and not re.fullmatch(r'(?:speaker[ _]?[A-Z0-9]+|unknown speaker|speaker)', value, re.I) else None
    )


@dataclass(frozen=True)
class DisplayParticipant:
    key: str
    label: str
    name: str | None
    countable: bool
    speech_seconds: float


def _projection_key(row: Any) -> tuple:
    raw = field(row, 'speaker_id')
    raw = raw if isinstance(raw, (int, str)) and not isinstance(raw, bool) else None
    scope = field(row, 'speaker_id_scope')
    scope = scope if isinstance(scope, str) else None
    sid, person = field(row, 'id'), field(row, 'person_id')
    return (
        sid if isinstance(sid, str) else None,
        DiarizationLabel(raw, scope),
        person if isinstance(person, str) else None,
        bool(field(row, 'is_user', False)),
    )


class DisplayParticipants:
    def __init__(
        self, rows: Sequence[Any], participants: list[DisplayParticipant], voice_order: Sequence[str] = ()
    ) -> None:
        self.voice_order = tuple(voice_order)
        self._rows = {id(row): (_projection_key(row), participant) for row, participant in zip(rows, participants)}
        self._identities = {_projection_key(row): participant for row, participant in zip(rows, participants)}
        self.participants = tuple({p.key: p for p in participants}.values())

    def for_segment(self, row: Any) -> DisplayParticipant:
        # Lazy sequences and wire adapters may materialize new objects on each pass.
        # An object id alone is not identity: Python can reuse it after a row is freed.
        key = _projection_key(row)
        entry = self._rows.get(id(row))
        if entry is not None and entry[0] == key:
            return entry[1]
        return self._identities.get(key, DisplayParticipant('unresolved', 'Unknown speaker', None, False, 0))

    def label(self, row: Any) -> str:
        return self.for_segment(row).label


def prompt_speaker_map(transcript: str, mapping: Mapping[Any, str | None]) -> tuple[str, dict[str, str | None]]:
    """Normalize legacy callers at the prompt boundary; numeric map keys are storage IDs."""
    if all(isinstance(key, str) and re.fullmatch(r'c\d+|others', key) for key in mapping):
        return transcript, dict(mapping)
    keys = {str(key): f'c{index}' for index, key in enumerate(mapping)}
    if keys:
        pattern = re.compile(r'(?m)^(\[[^]\n]*? )(' + '|'.join(re.escape(key) for key in keys) + r')(\])')
        transcript = pattern.sub(lambda match: match[1] + keys[match[2]] + match[3], transcript)
    return transcript, {keys[str(key)]: value for key, value in mapping.items()}


def sanitize_speaker_text(text: str) -> str:
    """Generated prose and replayed state cannot reintroduce old numeric placeholders."""
    return re.sub(r'(?i)\b(?:speaker|spk)[ _](?:c?\d+)\b', 'a speaker', text)


def evidence_voice_keys(evidence: Any) -> dict[str, str]:
    """One safe keyspace for both transcript turns and the separate evidence packet."""
    return {cluster.id: f'c{index}' for index, cluster in enumerate(evidence.clusters)} if evidence else {}


def display_participants(
    segments: Sequence[Any],
    *,
    names: Mapping[str, str] | None = None,
    owner_name: str = 'You',
    evidence: Any = None,
    resolution: Any = None,
    voice_order: Sequence[str] | None = None,
    display_scope: str | None = None,
    allow_automatic_names: bool = True,
    defer_short_voices: bool = False,
) -> DisplayParticipants:
    """Resolve names, small first-appearance labels and bounded unknown voices once.

    With defer_short_voices, unknown voices take no ordinal/ledger slot until
    five seconds of non-overlapping placed speech (or acoustic cluster evidence).
    This is display qualification, never acoustic proof that two voices are one.
    Unknown voices count only with resolved/capture evidence. At >8 unknown
    clusters retain up to seven with >=3 speech seconds, collapse the rest into
    Others, and emit one counter per projection. This is a display mitigation,
    never an acoustic merge or a change to stored identity/correction keys.
    """
    rows = list(segments)
    owner_name = _clean_name(owner_name) or 'You'
    names = names or {}
    clusters = {}
    evidence_available = evidence is not None and field(evidence, 'status') != 'unavailable'
    if evidence_available:
        for cluster in evidence.clusters:
            for segment_id in cluster.segment_ids:
                clusters[segment_id] = cluster
    keys, row_names = [], []
    seconds: dict[Any, float] = {}
    protected = set()
    if evidence_available:
        for cluster in evidence.clusters:
            key = ('evidence', cluster.id)
            seconds[key] = cluster.speech_seconds
            if any(
                c.label_eligible
                and c.band != 'unknown'
                and (c.person_id == 'owner' or _clean_name(c.name or names.get(c.person_id)))
                for c in cluster.candidates
            ):
                protected.add(key)
    labeler = SpeakerLabeler()
    # An episode stores only a bounded list of opaque hashes, never transcript text.
    # The list is excluded by both render_state and the public Episode schema.
    order = list(voice_order or ())[: MAX_UNNAMED_VOICES + 1]
    for token in order[:MAX_UNNAMED_VOICES]:
        labeler.label(token)
    labels = {}
    tokens = {}
    intervals: dict[Any, list[tuple[float, float]]] = {}
    for index, row in enumerate(rows):
        cluster = clusters.get(field(row, 'id'))
        raw = field(row, 'speaker_id')
        raw = raw if isinstance(raw, (int, str)) and not isinstance(raw, bool) else None
        scope = field(row, 'speaker_id_scope')
        scope = scope if isinstance(scope, str) else None
        key = ('evidence', cluster.id) if cluster else DiarizationLabel(raw, scope)
        if raw is None and cluster is None:
            key = ('missing', index)
        token = hashlib.sha256(
            json.dumps([display_scope, scope, raw, cluster.id if cluster else None], sort_keys=True).encode()
        ).hexdigest()
        tokens[key] = token
        name = None
        if evidence_available:
            candidate = (
                max(
                    (c for c in cluster.candidates if c.label_eligible and c.band != 'unknown'),
                    key=lambda c: c.probability,
                    default=None,
                )
                if cluster
                else None
            )
            if candidate:
                candidate_name = (
                    owner_name if candidate.person_id == 'owner' else candidate.name or names.get(candidate.person_id)
                )
                name = _clean_name(candidate_name)
                if name and candidate.band == 'likely':
                    name = 'likely ' + name
        else:
            name = (
                owner_name
                if field(row, 'is_user', False)
                else _clean_name(names.get(str(field(row, 'person_id') or '')))
            )
            # Names injected by the trusted people projection for episode moments.
            if not name:
                name = _clean_name(field(row, 'person_name')) if field(row, 'person_id') else None
        if not evidence_available and not allow_automatic_names:
            name = None
        if field(row, 'speaker_label_source') == 'manual':
            name = (
                owner_name
                if field(row, 'is_user', False)
                else (
                    _clean_name(names.get(str(field(row, 'person_id') or '')))
                    or (_clean_name(field(row, 'person_name')) if field(row, 'person_id') else None)
                )
            )
        if raw == 99:
            name = 'Omi'
        if name:
            protected.add(key)
        keys.append(key)
        row_names.append(name)
        seconds[key] = seconds.get(key, 0.0) + _seconds(row)
        if defer_short_voices:
            try:
                start, end = float(field(row, 'start')), float(field(row, 'end'))
                if isfinite(start) and isfinite(end) and 0 <= start < end:
                    intervals.setdefault(key, []).append((start, end))
            except (TypeError, ValueError):
                pass
    # A revised/overlapping turn cannot buy more display evidence. Unplaced
    # (-1) text stays unnamed without inventing audio placement or voice identity.
    display_seconds = {}
    for key, ranges in intervals.items():
        covered_end, duration = float('-inf'), 0.0
        for start, end in sorted(ranges):
            duration += max(0.0, end - max(start, covered_end))
            covered_end = max(covered_end, end)
        display_seconds[key] = duration
    for row, key, name in zip(rows, keys, row_names):
        raw = field(row, 'speaker_id')
        cluster = clusters.get(field(row, 'id'))
        token = tokens[key]
        # A segment-bound name is never the fallback for an unbound excerpt.
        # Live named rows also must not spend anonymous ledger slots.
        if name and voice_order is not None:
            continue
        if key not in labels and not (field(row, 'is_user', False) and name) and raw != 99:
            if raw is None and cluster is None:
                labels[key] = 'Unknown speaker'
            elif (
                defer_short_voices
                and not name
                and token not in order
                and (cluster.speech_seconds if cluster else display_seconds.get(key, 0.0)) < MIN_EVIDENCE_SECONDS
            ):
                labels[key] = 'Unknown speaker'
            elif voice_order is None:
                labels[key] = labeler.label(token)
            else:
                if token not in order and len(order) <= MAX_UNNAMED_VOICES:
                    order.append(token)
                labels[key] = labeler.label(token) if token in order[:MAX_UNNAMED_VOICES] else 'Others'
    if evidence_available:
        for row, key in zip(rows, keys):
            cluster = clusters.get(field(row, 'id'))
            if cluster:
                seconds[key] = cluster.speech_seconds
    unknown = [key for key in seconds if key not in protected]
    collapsed = set()
    overflow = voice_order is not None and len(order) > MAX_UNNAMED_VOICES
    if len(unknown) > MAX_UNNAMED_VOICES or overflow:
        retained = sorted(unknown, key=lambda key: -seconds[key])
        retained = set([key for key in retained if seconds[key] >= MIN_VOICE_SECONDS][: MAX_UNNAMED_VOICES - 1])
        collapsed = set(unknown) - retained
        if overflow:
            collapsed.update(key for key in unknown if tokens.get(key) not in order[: MAX_UNNAMED_VOICES - 1])
        record_count_guard()
    evidence_keys = evidence_voice_keys(evidence) if evidence_available else {}
    prompt_keys = {}
    for key in dict.fromkeys(keys):
        prompt_keys[key] = (
            evidence_keys[key[1]]
            if isinstance(key, tuple) and key[0] == 'evidence'
            else f'c{len(evidence_keys) + len(prompt_keys)}'
        )
    countable = field(resolution, 'status') in ('resolved', 'capture') or (
        evidence_available and evidence.status == 'resolved'
    )
    eligible_ids = field(resolution, 'participant_speaker_ids')
    participants = [
        DisplayParticipant(
            key='others' if key in collapsed and not name else prompt_keys[key],
            label=name or ('Others' if key in collapsed else labels[key]),
            name=name,
            countable=name != 'Omi'
            and (
                bool(name)
                or bool(
                    countable
                    and key not in collapsed
                    and not (isinstance(key, tuple) and key[0] == 'missing')
                    and (eligible_ids is None or field(row, 'speaker_id') in eligible_ids)
                )
            ),
            speech_seconds=seconds[key],
        )
        for row, key, name in zip(rows, keys, row_names)
    ]
    return DisplayParticipants(rows, participants, order)


def developer_speaker_names(segments: Sequence[Any], *, names: Mapping[str, str], owner_name: str) -> list[str]:
    """Preserve released developer API values while UI/MCP use display_participants.

    Named contacts do not consume unknown-label slots in this wire contract.
    Raw speaker IDs remain transport keys, never interpolated into a name.
    """
    labeler = SpeakerLabeler()
    result = []
    for segment in segments:
        person_id = str(field(segment, 'person_id') or '')
        if field(segment, 'is_user', False):
            result.append(owner_name)
        elif person_id in names:
            result.append(names[person_id])
        elif field(segment, 'speaker_id') is not None:
            result.append(labeler.label((field(segment, 'speaker_id_scope'), field(segment, 'speaker_id'))))
        else:
            result.append('Unknown speaker')
    return result
