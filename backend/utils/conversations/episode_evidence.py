"""Pure episode evidence adapters and rendering."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, Sequence, cast

from pydantic import BaseModel

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
