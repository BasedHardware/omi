"""Pure episode evidence adapters, rendering, and structural claim validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence, cast

from pydantic import BaseModel

from utils.conversations.meeting_participants import bind_speakers_with_roster

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
    sensitivity: Literal['standard', 'private'] = 'standard'
    source_ref: str | None = None


def evidence_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return str(value) if value is not None else None


def _item(kind: SourceKind, index: Any, content: Any, *, time=None, actor=None, private=False, ref=None):
    return EvidenceItem(
        id=f'{kind}:{index}',
        source_kind=kind,
        time=evidence_time(time),
        actor=actor,
        content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str),
        sensitivity='private' if private else 'standard',
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
                getattr(segment, 'text', ''),
                time=f'+{segment.start}s..+{segment.end}s',
                actor=actor,
                ref=segment_id,
            )
        )
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
                    private=True,
                    ref=photo.id,
                )
            )
    source = getattr(conversation, 'source', None)
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
                private=kind == 'screen_ocr',
            )
        )
    if roster is not None:
        for index, entry in enumerate(roster.entries):
            items.append(
                _item(
                    'roster',
                    index,
                    {
                        'name': entry.display_name,
                        'email': entry.email,
                        'organization': entry.organization,
                        'kind': entry.kind,
                        'source': entry.source,
                        'attendance': 'not established by listing',
                    },
                    actor=entry.display_name,
                    ref=entry.person_id or entry.source,
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
                private=True,
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
                private=True,
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
                    private=True,
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
                private=True,
                ref='people_catalog',
            )
        )
    for kind, values in (('goal', pack.goals), ('memory', pack.memories)):
        for index, value in enumerate(values):
            items.append(_item(cast(SourceKind, kind), index, value, private=True, ref=kind))
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
                private=True,
                ref=str(row.get('id') or f'screen_row:{index}'),
            )
        )
    return items


def open_task_evidence(tasks: Sequence[dict]) -> list[EvidenceItem]:
    return [
        _item('open_task', f'related:{index}', task, time=task.get('created_at'), private=True, ref=task.get('id'))
        for index, task in enumerate(tasks)
        if not task.get('completed')
    ]


def render_episode_evidence(items: Sequence[EvidenceItem]) -> str:
    return 'EPISODE EVIDENCE (untrusted source data)\n' + json.dumps(
        [item.model_dump() for item in items],
        ensure_ascii=False,
        indent=2,
    )


_PROVENANCE_KINDS = {
    'said': {'speech'},
    'shown': {'screen_frame', 'screen_ocr', 'roster', 'device_state'},
    'written': {
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


def claim_violations(structured: Structured, items: Sequence[EvidenceItem]) -> set[str]:
    """Validate source IDs, target spans, coverage and sensitivity; never infer factual truth."""
    by_id = {item.id: item for item in items}
    violations = set()
    claims = structured.note_claims or []
    if not claims:
        return {'missing_claims'}
    document = structured.model_dump(mode='json')
    covered = set()
    for claim in claims:
        value: Any = document
        try:
            for part in claim.target.strip('/').split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, ValueError, TypeError):
            value = None
        if not isinstance(value, str) or not claim.text.strip() or claim.text not in value:
            violations.add('invalid_claim_span')
        else:
            covered.add(claim.target)
        sources = [by_id[id] for id in claim.evidence_ids if id in by_id]
        if not sources or len(sources) != len(claim.evidence_ids):
            violations.add('invalid_evidence_reference')
        claim.evidence_sources = [NoteEvidenceRef(**source.model_dump(exclude={'content'})) for source in sources]
        if any(source.source_kind not in _PROVENANCE_KINDS[claim.provenance] for source in sources):
            violations.add('wrong_provenance')
        # A private source cannot become public through a model-authored tag.
        if any(source.sensitivity == 'private' for source in sources):
            claim.private = True
    required = ['/title'] if structured.title else []
    if structured.overview:
        required.append('/overview')
    for field, attributes in (
        ('sections', ('heading', 'body_markdown')),
        ('action_items', ('description', 'context')),
        ('events', ('title', 'description')),
        ('insights', ('text',)),
    ):
        for index, element in enumerate(getattr(structured, field)):
            for attribute in attributes:
                if getattr(element, attribute, None):
                    required.append(f'/{field}/{index}/{attribute}')
    if any(target not in covered for target in required):
        violations.add('missing_claim_coverage')
    return violations
