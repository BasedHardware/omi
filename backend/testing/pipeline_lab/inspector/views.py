"""JSON views the inspector API serves: run list, day overview, day panel, conversation detail, verdicts.

Pure functions of a ``Reader``; the HTTP layer only routes and encodes. Agents can call these
directly or read the same JSON from the server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from testing.pipeline_lab.inspector.reader import (
    ITEM_KINDS,
    MARKS,
    MAX_NOTE_CHARS,
    BadRequest,
    NotFound,
    Reader,
    baseline_ids_of,
    boundary_key,
    conversation_pairs,
    daily_summary_key,
    day_window,
    memory_key,
    new_verdict_id,
    notification_key,
    pair_items,
    safe_id,
    seconds_between,
    speaker_key,
    summary_key,
    task_key,
    transcript_key,
    transcript_text,
    utc_iso,
)


def _counts(conv: Mapping[str, Any]) -> dict[str, int]:
    return {
        'tasks': len(conv.get('action_items') or []),
        'memories': len(conv.get('memories') or []),
        'pushes': len(conv.get('notifications') or []),
    }


def _brief(conv: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not conv:
        return None
    structured = conv.get('structured') or {}
    return {
        'id': conv.get('id'),
        'started_at': conv.get('started_at'),
        'finished_at': conv.get('finished_at'),
        'title': structured.get('title') or '',
        'emoji': structured.get('emoji') or '',
        'discarded': bool(conv.get('discarded')),
    }


def run_summary(reader: Reader, run: Mapping[str, Any]) -> dict[str, Any]:
    day = reader.corpus_day(run.get('day_id') or '')
    out = {
        key: run.get(key)
        for key in (
            'run_id',
            'day_id',
            'ref',
            'commit',
            'backend_tree',
            'status',
            'started_at',
            'finished_at',
            'spend_usd',
            'budget_usd',
            'start_state',
        )
    }
    out['date'] = day.get('date')
    out['timezone'] = day.get('timezone')
    out['wall_seconds'] = seconds_between(run.get('started_at'), run.get('finished_at'))
    return out


def runs_list(reader: Reader) -> list[dict[str, Any]]:
    rows = []
    for run_id in reader.run_ids():
        try:
            run = reader.run(run_id)
        except NotFound:
            continue
        summary = run_summary(reader, run)
        try:
            pairing = reader.pairing(run)
            statuses: dict[str, int] = {}
            for row in pairing['rows']:
                statuses[row['status']] = statuses.get(row['status'], 0) + 1
            statuses['missing'] = len(pairing['missing'])
            summary['statuses'] = statuses
            summary['conversations'] = len(pairing['rows'])
        except NotFound:
            summary['statuses'] = {}
        rows.append(summary)
    rows.sort(key=lambda r: (r.get('started_at') or '', r.get('run_id') or ''), reverse=True)
    return rows


def _verdict_index(reader: Reader, day_id: str) -> dict[Optional[str], list[dict[str, Any]]]:
    index: dict[Optional[str], list[dict[str, Any]]] = {}
    for row in reader.verdicts(day_id=day_id):
        index.setdefault(row.get('conversation_id'), []).append(row)
    return index


def _verdicts_for(index: Mapping[Optional[str], list], *ids: Optional[str]) -> list[dict[str, Any]]:
    out = []
    for cid in ids:
        if cid:
            out.extend(index.get(cid, []))
    return out


def run_overview(reader: Reader, run_id: str) -> dict[str, Any]:
    """Day page: header facts, the two timeline rows and the conversation list (missing rows included)."""
    run = reader.run(run_id)
    day = reader.corpus_day(run['day_id'])
    pairing = reader.pairing(run)
    verdicts = _verdict_index(reader, run['day_id'])
    rows = []
    for row in pairing['rows']:
        conv = row['replay']
        twins = [pairing['by_id'][b] for b in baseline_ids_of(conv) if b in pairing['by_id']]
        marks = _verdicts_for(verdicts, conv.get('id'))
        rows.append(
            {
                **(_brief(conv) or {}),
                'kind': 'replay',
                'lane': conv.get('lane'),
                'duration': seconds_between(conv.get('started_at'), conv.get('finished_at')),
                'discard_reason': conv.get('discard_reason'),
                'status': row['status'],
                'reasons': row['reasons'],
                'counts': _counts(conv),
                'baseline': [_brief(t) for t in twins],
                'evaluable': conv.get('evaluable') or {'boundaries': True, 'reason': ''},
                'verdicts': {m: sum(1 for v in marks if v.get('mark') == m) for m in MARKS},
            }
        )
    for conv in pairing['missing']:
        marks = _verdicts_for(verdicts, conv.get('id'))
        rows.append(
            {
                **(_brief(conv) or {}),
                'kind': 'production',
                'lane': conv.get('lane'),
                'duration': seconds_between(conv.get('started_at'), conv.get('finished_at')),
                'discard_reason': conv.get('discard_reason'),
                'status': 'missing',
                'reasons': [],
                'counts': _counts(conv),
                'baseline': [_brief(conv)],
                'evaluable': conv.get('evaluable') or {'boundaries': True, 'reason': ''},
                'verdicts': {m: sum(1 for v in marks if v.get('mark') == m) for m in MARKS},
            }
        )
    rows.sort(key=lambda r: (r.get('started_at') or '', r['kind'] != 'replay'))
    status_of_baseline: dict[str, str] = {}
    for row in rows:
        for twin in row['baseline']:
            if twin and twin.get('id'):
                status_of_baseline.setdefault(twin['id'], row['status'])
    production = [
        {**(_brief(b) or {}), 'status': status_of_baseline.get(b.get('id'), 'missing')}
        for b in reader.baseline_conversations(run['day_id'])
    ]
    coverage = day.get('coverage') or {}
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row['status']] = statuses.get(row['status'], 0) + 1
    return {
        'run': {**run_summary(reader, run), 'overlay': run.get('overlay') or {}, 'warnings': run.get('warnings') or []},
        'run_detail': {k: run.get(k) for k in ('timings', 'stages')},
        'day': {
            'day_id': run['day_id'],
            'date': day.get('date'),
            'timezone': day.get('timezone'),
            'window': day_window(day.get('date'), day.get('timezone')),
            'coverage': coverage,
        },
        'statuses': statuses,
        'conversations': rows,
        'timeline': {'replay': rows, 'production': production, 'gaps': coverage.get('gaps') or []},
    }


def _summary_text(value: Any) -> dict[str, Any]:
    if value is None:
        return {'title': '', 'overview': '', 'highlights': []}
    if isinstance(value, str):
        return {'title': '', 'overview': value, 'highlights': []}
    if isinstance(value, Mapping):
        return {
            'title': value.get('title') or value.get('headline') or '',
            'overview': value.get('overview') or value.get('summary') or value.get('text') or '',
            'highlights': list(value.get('highlights') or []),
            'raw': value,
        }
    return {'title': '', 'overview': str(value), 'highlights': []}


def day_panel(reader: Reader, run_id: str) -> dict[str, Any]:
    run = reader.run(run_id)
    day_id = run['day_id']
    run_day = reader.run_day(run_id)
    production_summary = reader.baseline_daily_summary(day_id)
    replay_summary = run_day.get('daily_summary')
    production_pushes = reader.baseline(day_id, 'notifications.jsonl')
    replay_pushes = list(run_day.get('notifications') or [])
    if not replay_pushes:
        replay_pushes = [
            dict(n, conversation_id=c.get('id'))
            for c in reader.conversations(run_id)
            for n in c.get('notifications') or []
        ]
    log = pair_items(replay_pushes, production_pushes, notification_key, lambda n: f"{n.get('title')} {n.get('body')}")
    log.sort(key=lambda p: ((p['replay'] or p['baseline'] or {}).get('at') or ''))
    verdicts = [v for v in reader.verdicts(day_id=day_id) if v.get('item_kind') == 'daily_summary']
    return {
        'daily_summary': {
            'key': daily_summary_key(replay_summary) if replay_summary is not None else None,
            'replay': _summary_text(replay_summary) if replay_summary is not None else None,
            'baseline': _summary_text(production_summary) if production_summary is not None else None,
            'verdicts': verdicts,
        },
        'goals': run_day.get('goals') or [],
        'memory_delta': run_day.get('memory_delta') or {'added': [], 'updated': [], 'removed': []},
        'notifications': log,
    }


def _item_keys(conv: Optional[Mapping[str, Any]]) -> Optional[dict[str, str]]:
    if not conv:
        return None
    return {
        'summary': summary_key(conv.get('structured')),
        'transcript': transcript_key(conv),
        'speaker': speaker_key(conv),
        'boundary': boundary_key(conv),
    }


def conversation_detail(reader: Reader, run_id: str, conversation_id: str) -> dict[str, Any]:
    run = reader.run(run_id)
    conv = reader.conversation(run_id, conversation_id)
    by_id = {b['id']: b for b in reader.baseline_conversations(run['day_id']) if b.get('id')}
    twins = [by_id[b] for b in baseline_ids_of(conv) if b in by_id]
    twin = _merge_twins(twins)
    pairing = reader.pairing(run)
    row = next((r for r in pairing['rows'] if r['replay'].get('id') == conversation_id), None)
    index = _verdict_index(reader, run['day_id'])
    return {
        'run_id': run_id,
        'kind': 'replay',
        'status': row['status'] if row else ('new' if not twins else 'changed'),
        'reasons': row['reasons'] if row else [],
        'replay': conv,
        'baseline': twin,
        'baselines': [_brief(t) for t in twins],
        'keys': {'replay': _item_keys(conv), 'baseline': _item_keys(twin)},
        'pairs': conversation_pairs(conv, twin),
        'transcripts': {'replay': transcript_text(conv), 'baseline': transcript_text(twin) if twin else None},
        'audio': reader.audio_for(run['day_id'], conv),
        'llm_calls': reader.llm_calls(run_id, conversation_id, conv.get('llm_call_ids') or []),
        'verdicts': _verdicts_for(index, conversation_id),
    }


def production_detail(reader: Reader, run_id: str, baseline_id: str) -> dict[str, Any]:
    """A production conversation the replay did not reproduce (status ``missing``)."""
    run = reader.run(run_id)
    safe_id(baseline_id)
    twin = next((b for b in reader.baseline_conversations(run['day_id']) if b.get('id') == baseline_id), None)
    if twin is None:
        raise NotFound('production conversation not found')
    index = _verdict_index(reader, run['day_id'])
    return {
        'run_id': run_id,
        'kind': 'production',
        'status': 'missing',
        'reasons': [],
        'replay': None,
        'baseline': twin,
        'baselines': [_brief(twin)],
        'keys': {'replay': None, 'baseline': _item_keys(twin)},
        'pairs': conversation_pairs({}, twin),
        'transcripts': {'replay': None, 'baseline': transcript_text(twin)},
        'audio': reader.audio_for(run['day_id'], twin),
        'llm_calls': [],
        'verdicts': _verdicts_for(index, baseline_id),
    }


def _merge_twins(twins: list[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """One production view for a replay that merged several production conversations."""
    if not twins:
        return None
    if len(twins) == 1:
        return dict(twins[0])
    first, last = twins[0], twins[-1]
    offset_of = [seconds_between(first.get('started_at'), t.get('started_at')) or 0.0 for t in twins]
    segments = []
    for twin, offset in zip(twins, offset_of):
        for seg in twin.get('segments') or []:
            segments.append({**seg, 'start': (seg.get('start') or 0) + offset, 'end': (seg.get('end') or 0) + offset})
    structured = dict(first.get('structured') or {})
    structured['title'] = ' + '.join((t.get('structured') or {}).get('title') or '' for t in twins)
    structured['overview'] = '\n\n'.join((t.get('structured') or {}).get('overview') or '' for t in twins)
    merged = dict(first)
    merged.update(
        {
            'id': first.get('id'),
            'merged_ids': [t.get('id') for t in twins],
            'finished_at': last.get('finished_at'),
            'discarded': all(bool(t.get('discarded')) for t in twins),
            'segments': segments,
            'structured': structured,
            'action_items': [i for t in twins for i in t.get('action_items') or []],
            'memories': [i for t in twins for i in t.get('memories') or []],
            'notifications': [i for t in twins for i in t.get('notifications') or []],
        }
    )
    return merged


def llm_calls(reader: Reader, run_id: str, conversation_id: Optional[str]) -> list[dict[str, Any]]:
    reader.run(run_id)
    if conversation_id is None:
        return reader.llm_calls(run_id)
    return reader.llm_calls(run_id, safe_id(conversation_id))


def baseline_view(reader: Reader, day_id: str) -> dict[str, Any]:
    safe_id(day_id, 'day id')
    return {
        'day': reader.corpus_day(day_id),
        'conversations': reader.baseline_conversations(day_id),
        'memories': reader.baseline(day_id, 'memories.jsonl'),
        'action_items': reader.baseline(day_id, 'action_items.jsonl'),
        'notifications': reader.baseline(day_id, 'notifications.jsonl'),
        'daily_summary': reader.baseline_daily_summary(day_id),
    }


# ---- verdicts ------------------------------------------------------------------------------


def _find(items: list[Mapping[str, Any]], key: str, key_of) -> Optional[Mapping[str, Any]]:
    return next((i for i in items if key_of(i) == key), None)


def _locate_in(conv: Mapping[str, Any], kind: str, key: str) -> Optional[Any]:
    if kind == 'summary' and summary_key(conv.get('structured')) == key:
        structured = conv.get('structured') or {}
        return {'title': structured.get('title'), 'overview': structured.get('overview')}
    if kind == 'task':
        return _find(conv.get('action_items') or [], key, task_key)
    if kind == 'memory':
        return _find(conv.get('memories') or [], key, memory_key)
    if kind == 'notification':
        return _find(conv.get('notifications') or [], key, notification_key)
    if kind == 'boundary' and boundary_key(conv) == key:
        return {'started_at': conv.get('started_at'), 'finished_at': conv.get('finished_at')}
    if kind == 'transcript' and transcript_key(conv) == key:
        return {'text': transcript_text(conv)[:2000]}
    if kind == 'speaker' and speaker_key(conv) == key:
        names = []
        for seg in conv.get('segments') or []:
            label = seg.get('speaker_name') or seg.get('speaker')
            if label not in names:
                names.append(label)
        return {'speakers': names}
    return None


def locate_item(
    reader: Reader, run: Mapping[str, Any], conversation_id: Optional[str], kind: str, key: str
) -> dict[str, Any]:
    """The item a verdict names, as a small snapshot; ``NotFound`` if it is not in this run or its baseline."""
    day_id = run['day_id']
    if kind == 'daily_summary':
        replay = reader.run_day(run['run_id']).get('daily_summary')
        if replay is not None and daily_summary_key(replay) == key:
            return {'side': 'replay', 'value': replay}
        production = reader.baseline_daily_summary(day_id)
        if production is not None and daily_summary_key(production) == key:
            return {'side': 'production', 'value': production}
        raise NotFound('daily summary not found')
    if not conversation_id:
        raise BadRequest('conversation_id is required for this item kind')
    safe_id(conversation_id)
    baseline = {b['id']: b for b in reader.baseline_conversations(day_id) if b.get('id')}
    try:
        conv: Optional[Mapping[str, Any]] = reader.conversation(run['run_id'], conversation_id)
    except NotFound:
        conv = None
    if conv is not None:
        found = _locate_in(conv, kind, key)
        if found is not None:
            return {'side': 'replay', 'value': found}
        for bid in baseline_ids_of(conv):
            if bid in baseline:
                found = _locate_in(baseline[bid], kind, key)
                if found is not None:
                    return {'side': 'production', 'baseline_id': bid, 'value': found}
    elif conversation_id in baseline:
        found = _locate_in(baseline[conversation_id], kind, key)
        if found is not None:
            return {'side': 'production', 'baseline_id': conversation_id, 'value': found}
    raise NotFound('item not found')


def build_verdict(reader: Reader, payload: Any, reviewer: Optional[str] = None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BadRequest('expected a JSON object')
    run_id = payload.get('run_id')
    kind = payload.get('item_kind')
    key = payload.get('item_key')
    mark = payload.get('mark')
    note = payload.get('note') or ''
    conversation_id = payload.get('conversation_id') or None
    if not isinstance(run_id, str):
        raise BadRequest('run_id is required')
    if kind not in ITEM_KINDS:
        raise BadRequest(f'item_kind must be one of {", ".join(ITEM_KINDS)}')
    if mark not in MARKS:
        raise BadRequest('mark must be good or bad')
    if not isinstance(key, str) or not key or len(key) > 128:
        raise BadRequest('item_key is required')
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        raise BadRequest(f'note must be text of at most {MAX_NOTE_CHARS} characters')
    if conversation_id is not None and not isinstance(conversation_id, str):
        raise BadRequest('conversation_id must be a string')
    run = reader.run(run_id)
    snapshot = locate_item(reader, run, conversation_id, kind, key)
    row = {
        'id': new_verdict_id(),
        'at': utc_iso(datetime.now(timezone.utc)),
        'run_id': run_id,
        'day_id': run['day_id'],
        'ref': run.get('ref') or '',
        'conversation_id': conversation_id if kind != 'daily_summary' else None,
        'item_kind': kind,
        'item_key': key,
        'mark': mark,
        'note': note.strip(),
        'item_snapshot': snapshot,
    }
    if reviewer:
        row['reviewer'] = reviewer
    return row
