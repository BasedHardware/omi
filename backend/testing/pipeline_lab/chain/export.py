"""Normalize product rows into the store contract's conversation JSON (DESIGN).

Pure functions over plain dicts so the same code normalizes a replayed conversation
(read back from the emulator) and a production one (from the snapshot baseline);
``baseline/`` diffs exactly these shapes.

    {id, baseline_id|null, lane, started_at, finished_at, discarded, discard_reason, language,
     segments:[{start, end, speaker, speaker_name, is_user, text}],
     structured:{title, overview, emoji, category, events:[...]},
     action_items:[{key, description, due_at, completed}], memories:[{key, content, category}],
     notifications:[{at, title, body, trigger}], llm_call_ids:[...], evaluable:{boundaries, reason}}
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from testing.pipeline_lab.contracts import memory_key, task_key, wire_speaker_label
from testing.pipeline_lab.stack.io import iso, parse_time, plain


def _time(value: Any) -> str | None:
    parsed = parse_time(value)
    return iso(parsed) if parsed is not None else None


def discard_reason(row: Mapping[str, Any]) -> str | None:
    if not row.get('discarded'):
        return None
    for key in ('discard_reason', 'discarded_reason'):
        if row.get(key):
            return str(row[key])
    decision = row.get('relevance_decision')
    if isinstance(decision, Mapping):
        reason = decision.get('reason') or decision.get('verdict')
        if reason:
            return str(reason)
    return 'unknown'


def segments(row: Mapping[str, Any], people: Mapping[str, str] | None = None, owner_name: str = 'You') -> list[dict]:
    people = people or {}
    out = []
    for segment in row.get('transcript_segments') or []:
        if not isinstance(segment, Mapping):
            continue
        is_user = bool(segment.get('is_user'))
        speaker = segment.get('speaker') or (
            wire_speaker_label(segment['speaker_id']) if isinstance(segment.get('speaker_id'), int) else None
        )
        name = owner_name if is_user else people.get(str(segment.get('person_id') or ''), None)
        out.append(
            {
                'start': float(segment.get('start') or 0.0),
                'end': float(segment.get('end') or 0.0),
                'speaker': speaker,
                'speaker_name': name or speaker,
                'is_user': is_user,
                'text': segment.get('text') or '',
            }
        )
    return out


def structured(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get('structured') or {}
    return {
        'title': value.get('title') or '',
        'overview': value.get('overview') or '',
        'emoji': value.get('emoji') or '',
        'category': value.get('category') or '',
        'events': plain(value.get('events') or []),
    }


def action_item(row: Mapping[str, Any]) -> dict[str, Any]:
    description = (row.get('description') or '').strip()
    return {
        'key': task_key(description),
        'description': description,
        'due_at': _time(row.get('due_at')),
        'completed': bool(row.get('completed')),
    }


def memory(row: Mapping[str, Any]) -> dict[str, Any]:
    content = (row.get('content') or '').strip()
    return {
        'key': memory_key(content),
        'content': content,
        'category': str(row.get('category') or ''),
    }


def notification(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'at': row.get('fire_at') or row.get('at'),
        'title': row.get('title'),
        'body': row.get('body'),
        'trigger': row.get('trigger'),
    }


def _live(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row for row in rows if not row.get('deleted') and not row.get('invalid_at') and not row.get('superseded_by')
    ]


def normalize_conversation(
    row: Mapping[str, Any],
    *,
    action_items: Iterable[Mapping[str, Any]] = (),
    memories: Iterable[Mapping[str, Any]] = (),
    notifications: Iterable[Mapping[str, Any]] = (),
    llm_call_ids: Iterable[str] = (),
    lane: str | None = None,
    baseline_id: str | None = None,
    people: Mapping[str, str] | None = None,
    evaluable: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One conversation in the contract shape. Tasks and memories fall back to the row's own."""
    items = list(action_items)
    if not items:
        items = list((row.get('structured') or {}).get('action_items') or [])
    tasks = sorted((action_item(item) for item in _live(items)), key=lambda t: t['key'])
    mems = sorted((memory(item) for item in _live(memories)), key=lambda m: m['key'])
    return {
        'id': str(row.get('id')),
        'baseline_id': baseline_id,
        'lane': lane or row.get('record_lane_owner') or 'unknown',
        'started_at': _time(row.get('started_at') or row.get('created_at')),
        'finished_at': _time(row.get('finished_at')),
        'discarded': bool(row.get('discarded')),
        'discard_reason': discard_reason(row),
        'language': row.get('language'),
        'segments': segments(row, people),
        'structured': structured(row),
        'action_items': tasks,
        'memories': mems,
        'notifications': sorted((notification(n) for n in notifications), key=lambda n: str(n.get('at') or '')),
        'llm_call_ids': list(llm_call_ids),
        'evaluable': dict(evaluable or {'boundaries': False, 'reason': 'stored_transcript_boundaries'}),
    }
