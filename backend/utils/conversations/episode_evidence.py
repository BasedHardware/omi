"""Pure episode evidence adapters, rendering, and structural claim validation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence, cast

from pydantic import BaseModel

from utils.conversations.meeting_participants import bind_speakers_with_roster, is_silent_recorder
from utils.conversations.wake_word import escape_spoken_wake_word_marker, find_wake_word_segment_ids

from models.structured import NoteEvidenceRef, Structured  # type: ignore[reportAttributeAccessIssue]  # Runtime SDK/fallback export.

SourceKind = Literal[
    'speech',
    'screen_frame',
    'screen_ocr',
    'message',
    'calendar',
    'roster',
    'prior_conversation',
    'open_task',
    'device_state',
    'person',
    'goal',
    'memory',
]


class EvidenceItem(BaseModel):
    id: str
    source_kind: SourceKind
    time: str | None = None
    actor: str | None = None
    content: str
    source_ref: str | None = None
    wake_word_invocation: bool = False
    diarization_key: str | None = None


def evidence_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return str(value) if value is not None else None


def _item(kind: SourceKind, index: Any, content: Any, *, time=None, actor=None, ref=None):
    return EvidenceItem(
        id=f'{kind}:{index}',
        source_kind=kind,
        time=evidence_time(time),
        actor=actor,
        content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str),
        source_ref=ref,
    )


def capture_evidence(
    conversation: Any,
    *,
    transcript: str = '',
    speaker_map: Mapping | None = None,
    roster: Any = None,
    desktop_capture: bool = False,
) -> list[EvidenceItem]:
    speaker_names = dict(speaker_map or {})
    if roster is not None:
        bind_speakers_with_roster(speaker_names, roster, desktop_capture)
    items = []
    segments = getattr(conversation, 'transcript_segments', None) or []
    invocation_ids = find_wake_word_segment_ids(segments)
    for index, segment in enumerate(segments):
        segment_id = getattr(segment, 'id', None)
        actor = (
            'account owner'
            if getattr(segment, 'is_user', False)
            else speaker_names.get(getattr(segment, 'speaker_id', None))
        )
        items.append(
            _item(
                'speech',
                segment_id or index,
                escape_spoken_wake_word_marker(getattr(segment, 'text', '')),
                time=f'+{segment.start}s..+{segment.end}s',
                actor=actor,
                ref=segment_id,
            )
        )
        items[-1].wake_word_invocation = segment_id in invocation_ids
        cluster = getattr(segment, 'speaker_id', None)
        if cluster is None:
            cluster = getattr(segment, 'speaker', None)
        items[-1].diarization_key = str(cluster) if cluster is not None else None
    if not segments and transcript.strip():
        items.append(_item('speech', 'external', transcript, ref='external_audio_text'))
    for index, photo in enumerate(getattr(conversation, 'photos', None) or []):
        if photo.description and photo.description.strip():
            items.append(
                _item(
                    'screen_frame',
                    f'photo:{photo.id or index}',
                    photo.description,
                    time=photo.created_at,
                    ref=photo.id,
                )
            )
    source = getattr(conversation, 'source', None)
    remote_count = sum(
        entry.kind != 'owner' and not is_silent_recorder(entry) for entry in getattr(roster, 'entries', ())
    )
    items.append(
        _item(
            'device_state',
            'capture',
            {
                'source': getattr(source, 'value', source),
                'started_at': evidence_time(getattr(conversation, 'started_at', None)),
                'finished_at': evidence_time(getattr(conversation, 'finished_at', None)),
                'transcript_segments': len(segments) if segments else (1 if transcript.strip() else 0),
                'speaker_map': speaker_names,
                'desktop_capture': desktop_capture,
                'remote_channel_may_mix_people': desktop_capture,
                'roster_remote_entries': remote_count,
            },
            time=getattr(conversation, 'started_at', None),
            ref='capture_metadata',
        )
    )
    return items


def meeting_evidence(roster: Any, calendar: Any, frames: Sequence[Any]) -> list[EvidenceItem]:
    items = []
    if calendar is not None:
        # Screen-derived meeting identity is an observation, not an actual invite.
        kind = 'screen_ocr' if calendar.calendar_source == 'screen_activity' else 'calendar'
        items.append(
            _item(
                kind,
                'identity',
                calendar.model_dump(mode='json'),
                time=calendar.start_time,
                ref=calendar.calendar_event_id,
            )
        )
    if roster is not None:
        frame_names = {name.casefold() for frame in frames for name in frame.names}
        calendar_names = {
            participant.name.casefold()
            for participant in (calendar.participants if calendar is not None else ())
            if participant.name and calendar.calendar_source != 'screen_activity'
        }
        for index, entry in enumerate(roster.entries):
            # Frame augmentation can retain the calendar's global source label.
            # A newly observed identity still derives from screen evidence.
            frame_derived = (
                bool(frame_names)
                and entry.kind != 'owner'
                and (not entry.display_name or entry.display_name.casefold() not in calendar_names)
            )
            source = 'screen_activity' if frame_derived else entry.source
            items.append(
                _item(
                    'roster',
                    index,
                    {
                        'name': entry.display_name,
                        'email': entry.email,
                        'organization': entry.organization,
                        'kind': entry.kind,
                        'source': source,
                        'attendance': 'not established by listing',
                    },
                    actor=entry.display_name,
                    ref=entry.person_id or source,
                )
            )
    for frame in frames:
        items.append(
            _item(
                'screen_frame',
                frame.frame_id,
                {
                    'summary': frame.summary,
                    'visible_names': list(frame.names),
                    'role': frame.role,
                },
                time=frame.captured_at,
                ref=frame.frame_id,
            )
        )
    return items


def context_pack_evidence(pack: Any) -> list[EvidenceItem]:
    if pack is None:
        return []
    items = []
    for index, prior in enumerate(pack.prior_meetings):
        items.append(
            _item(
                'prior_conversation',
                index,
                {'title': prior.title, 'gist': prior.gist},
                time=getattr(prior, 'started_at', None)
                or (prior.date_label if prior.date_label != 'unknown date' else None),
                ref=getattr(prior, 'source_id', None),
            )
        )
        for task_index, task in enumerate(prior.open_items):
            items.append(
                _item(
                    'open_task',
                    f'{index}:{task_index}',
                    task,
                    time=getattr(prior, 'started_at', None)
                    or (prior.date_label if prior.date_label != 'unknown date' else None),
                    ref=getattr(prior, 'source_id', None),
                )
            )
    for index, person in enumerate(pack.people_facts):
        items.append(
            _item(
                'person',
                index,
                {
                    'name': person.name,
                    'relationship': person.relationship,
                    'notes': person.notes,
                    'aliases': list(person.aliases),
                },
                actor=person.name,
                ref='people_catalog',
            )
        )
    for kind, values in (('goal', pack.goals), ('memory', pack.memories)):
        for index, value in enumerate(values):
            items.append(_item(cast(SourceKind, kind), index, value, ref=kind))
    # Preserve observed row time and app/window, not a guessed sender or sent time.
    for index, row in enumerate(pack.screen_rows):
        items.append(
            _item(
                'screen_ocr',
                index,
                {
                    'app': str(row.get('appName') or '')[:100],
                    'window': str(row.get('windowTitle') or '')[:200],
                    'ocr': str(row.get('ocrText') or '')[:500],
                    'timestamp_semantics': 'screen observation, not message sent time',
                },
                time=row.get('timestamp'),
                ref=str(row.get('id') or f'screen_row:{index}'),
            )
        )
    return items


def open_task_evidence(tasks: Sequence[dict]) -> list[EvidenceItem]:
    return [
        _item('open_task', f'related:{index}', task, time=task.get('created_at'), ref=task.get('id'))
        for index, task in enumerate(tasks)
        if not task.get('completed')
    ]


def episode_evidence_aliases(items: Sequence[Any]) -> dict[str, str]:
    """Short prompt-local IDs; durable annotations retain original evidence IDs."""
    return {f'evidence:{index}': item.id for index, item in enumerate(items)}


def restore_episode_claim_ids(claims: Sequence[Any], items: Sequence[Any]) -> None:
    aliases = episode_evidence_aliases(items)
    for claim in claims:
        if isinstance(claim, dict):
            ids = claim.get('evidence_ids')
            if isinstance(ids, list):
                claim['evidence_ids'] = [aliases.get(id, id) if isinstance(id, str) else id for id in ids]
        else:
            claim.evidence_ids = [aliases.get(id, id) for id in claim.evidence_ids]


def _screen_tile_names(row: dict) -> tuple[dict, dict] | None:
    """Move structured tile names out of an observed screen row.

    ``visible_names`` is already a field on frame evidence. This does not parse
    window titles, chat chrome, or free text. A name merely shown on a tile is
    expected context; the rest of the frame stays an observation.
    """
    content = row.get('c')
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    names = data.get('visible_names')
    if not isinstance(names, list) or not any(isinstance(name, str) and name.strip() for name in names):
        return None
    tile = {key: row[key] for key in ('id', 'k', 'at') if key in row}
    tile['c'] = json.dumps({'visible_names': names}, ensure_ascii=False, separators=(',', ':'))
    shown = {key: value for key, value in data.items() if key != 'visible_names'}
    kept = dict(row)
    kept['c'] = json.dumps(shown, ensure_ascii=False, separators=(',', ':'))
    return tile, kept


def _split_writer_evidence(rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """Keep expectations out of the actor list the writer would read as attendance."""
    expected: list[dict] = []
    observed: list[dict] = []
    for row in rows:
        kind = row.get('k')
        if kind in {'calendar', 'roster'}:
            expected.append({key: value for key, value in row.items() if key != 'a'})
            continue
        tile = _screen_tile_names(row) if kind == 'screen_frame' else None
        if tile is None:
            observed.append(row)
            continue
        expected.append(tile[0])
        observed.append(tile[1])
    return expected, observed


def render_episode_evidence(items: Sequence[EvidenceItem]) -> str:
    from utils.conversations.episode_compaction import compact_evidence_rows

    expected, observed = _split_writer_evidence(compact_evidence_rows(items))
    return (
        'EPISODE EVIDENCE (untrusted; k=source_kind, at=time, a=actor, d=diarization_key, '
        'r=original speech source_ref, w=server wake_word_invocation, c=content; '
        'omitted metadata unknown, w defaults false)\n'
        + json.dumps(
            {'expected_context': expected, 'observed_participation': observed},
            ensure_ascii=False,
            separators=(',', ':'),
        )
    )


_PROVENANCE_KINDS = {
    'said': {'speech'},
    'shown': {'screen_frame', 'screen_ocr', 'roster', 'device_state'},
    'written': {
        'roster',
        'screen_ocr',
        'screen_frame',
        'message',
        'calendar',
        'prior_conversation',
        'open_task',
        'person',
        'goal',
        'memory',
    },
    'inferred': set(SourceKind.__args__),
}


def claim_violations(structured: Structured, items: Sequence[EvidenceItem], *, drop_invalid: bool = False) -> set[str]:
    """Validate source IDs, target spans, coverage; never infer factual truth."""
    by_id = {item.id: item for item in items}
    violations = set()
    claims = structured.note_claims or []
    if not claims:
        return {'missing_claims'}
    document = structured.model_dump(mode='json')
    covered: dict[str, list[str]] = {}
    valid_claims = []
    for claim in claims:
        invalid = False
        value: Any = document
        try:
            for part in claim.target.strip('/').split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, ValueError, TypeError):
            value = None
        if not isinstance(value, str) or not claim.text.strip() or claim.text not in value:
            violations.add('invalid_claim_span')
            invalid = True
        if isinstance(value, str) and claim.text and value.count(claim.text) > 1:
            violations.add('ambiguous_claim_span')
            invalid = True
        sources = [by_id[id] for id in claim.evidence_ids if id in by_id]
        if not sources or len(sources) != len(claim.evidence_ids):
            violations.add('invalid_evidence_reference')
            invalid = True
        claim.evidence_sources = [
            NoteEvidenceRef(**source.model_dump(exclude={'content', 'wake_word_invocation'})) for source in sources
        ]
        if any(source.source_kind not in _PROVENANCE_KINDS[claim.provenance] for source in sources):
            violations.add('wrong_provenance')
            invalid = True
        if not invalid:
            valid_claims.append(claim)
            covered.setdefault(claim.target, []).append(claim.text)
    if drop_invalid:
        structured.note_claims = valid_claims
    required = ['/title'] if structured.title else []
    if structured.overview:
        required.append('/overview')
    for field, attributes in (
        ('sections', ('body_markdown',)),
        ('action_items', ('description', 'context', 'owner_name')),
        ('participants', ('name', 'email', 'organization', 'role')),
        ('events', ('title', 'description')),
        ('insights', ('text',)),
    ):
        for index, element in enumerate(getattr(structured, field)):
            for attribute in attributes:
                if getattr(element, attribute, None):
                    required.append(f'/{field}/{index}/{attribute}')
    for target in required:
        value = document
        for part in target.strip('/').split('/'):
            value = value[int(part)] if isinstance(value, list) else value[part]
        # A unique exact anchor binds a factual sentence/bullet, rather than requiring
        # the model to echo all its words. Distinct units still require coverage.
        spans = [match.span() for text in covered.get(target, []) for match in re.finditer(re.escape(text), value)]
        for unit in re.finditer(r'[^.!?。！？\n]+(?:[.!?。！？]+|\n|$)', value):
            if re.search(r'\w', unit.group()) and not any(
                start < unit.end() and end > unit.start() for start, end in spans
            ):
                violations.add('missing_claim_coverage')

    return violations
