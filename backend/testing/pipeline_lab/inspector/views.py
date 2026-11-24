"""JSON views the inspector API serves: run list, day overview, day panel, conversation detail, verdicts.

Pure functions of a ``Reader``; the HTTP layer only routes and encodes. Agents can call these
directly or read the same JSON from the server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from testing.pipeline_lab.baseline import compare
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
    home_hidden,
    memory_key,
    new_verdict_id,
    notification_key,
    pair_items,
    pipeline_of,
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
        **_v3_brief(conv),
    }


def _v3_brief(conv: Mapping[str, Any]) -> dict[str, Any]:
    """v3 rows: Home visibility, its reason, the outline kind and how many recordings fed it."""
    block = conv.get('v3')
    if not isinstance(block, Mapping):
        return {}
    return {
        'hidden': home_hidden(conv),
        'hidden_reason': block.get('home_hidden_reason'),
        'v3_kind': block.get('kind'),
        'recordings': len(conv.get('recordings') or []),
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
    out['stt'] = run.get('stt')
    out['engine'] = run.get('chain_engine')
    out['pipeline'] = pipeline_of(run)
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
            view = reader.comparison(run)
            summary['statuses'] = dict(view['digest']['kinds'])
            summary['conversations'] = view['digest']['conversations']['replay']
            summary['worth'] = view['digest']['tags']['worth']
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


def _cell(conv: Mapping[str, Any], side: str, verdicts: Mapping[Optional[str], list]) -> dict[str, Any]:
    """One conversation as a cell of the paired day list."""
    marks = _verdicts_for(verdicts, conv.get('id'), *baseline_ids_of(conv))
    block = conv.get('v3') if isinstance(conv.get('v3'), Mapping) else {}
    return {
        **(_brief(conv) or {}),
        'side': side,
        'duration': seconds_between(conv.get('started_at'), conv.get('finished_at')),
        'discard_reason': conv.get('discard_reason'),
        'home': compare.on_home(conv),
        'home_reason': compare.home_reason(conv),
        'counts': _counts(conv),
        'backfilled': bool(block.get('backfilled')),
        'evaluable': conv.get('evaluable') or {'boundaries': True, 'reason': ''},
        'verdicts': {m: sum(1 for v in marks if v.get('mark') == m) for m in MARKS},
    }


def _status_of(group: Mapping[str, Any]) -> str:
    """The one status word a conversation shows: its group's kind (``content`` reads as ``changed``)."""
    return 'changed' if group['kind'] == 'content' else group['kind']


def run_overview(reader: Reader, run_id: str) -> dict[str, Any]:
    """Day page: header facts, the digest, the paired groups, and a flat conversation list for agents.

    Every count comes from ``compare``'s digest, which counts groups per tag; the UI filters groups
    by the same tags, so a chip's number is always the number of rows it shows.
    """
    run = reader.run(run_id)
    day = reader.corpus_day(run['day_id'])
    view = reader.comparison(run)
    verdicts = _verdict_index(reader, run['day_id'])
    replay_by_id = {c['id']: c for c in reader.conversations(run_id)}
    prod_by_id = {b['id']: b for b in reader.baseline_conversations(run['day_id'], pipeline_of(run)) if b.get('id')}
    groups, flat = [], []
    for group in view['groups']:
        left = [_cell(prod_by_id[i], 'production', verdicts) for i in group['production'] if i in prod_by_id]
        right = [_cell(replay_by_id[i], 'replay', verdicts) for i in group['replay'] if i in replay_by_id]
        if not left and not right:
            continue  # a cached comparison group whose rows are gone from both sides
        open_ = {'kind': 'replay', 'id': right[0]['id']} if right else {'kind': 'production', 'id': left[0]['id']}
        groups.append(
            {
                key: group.get(key)
                for key in ('id', 'kind', 'marker', 'change', 'score', 'tags', 'home', 'started_at', 'finished_at')
            }
            | {'substantive': group.get('substantive') or [], 'cosmetic': group.get('cosmetic') or []}
            | {'production': left, 'replay': right, 'open': open_}
        )
        status = _status_of(group)
        for cell in right:
            flat.append(
                {
                    **cell,
                    'kind': 'replay',
                    'group': group['id'],
                    'status': status,
                    'change': group['change'],
                    'baseline': [_brief(prod_by_id[i]) for i in group['production'] if i in prod_by_id],
                }
            )
        if not right:
            for cell in left:
                flat.append(
                    {
                        **cell,
                        'kind': 'production',
                        'group': group['id'],
                        'status': status,
                        'change': group['change'],
                        'baseline': [_brief(prod_by_id[cell['id']])],
                    }
                )
    coverage = day.get('coverage') or {}
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
        'digest': view['digest'],
        'statuses': {_status_of({'kind': k}): n for k, n in view['digest']['kinds'].items() if n},
        'groups': groups,
        'conversations': flat,
        'timeline': {'gaps': coverage.get('gaps') or []},
    }


def _highlight(value: Any) -> Any:
    """A daily-summary highlight as ``{emoji, topic, summary}`` (product rows) or plain text."""
    if isinstance(value, Mapping):
        return {
            'emoji': value.get('emoji') or '',
            'topic': value.get('topic') or value.get('title') or '',
            'summary': value.get('summary') or value.get('text') or value.get('content') or '',
        }
    return str(value)


def _summary_text(value: Any) -> dict[str, Any]:
    if value is None:
        return {'title': '', 'overview': '', 'highlights': []}
    if isinstance(value, str):
        return {'title': '', 'overview': value, 'highlights': []}
    if isinstance(value, Mapping):
        return {
            'title': value.get('title') or value.get('headline') or '',
            'overview': value.get('overview') or value.get('summary') or value.get('text') or '',
            'highlights': [_highlight(x) for x in value.get('highlights') or []],
            'raw': value,
        }
    return {'title': '', 'overview': str(value), 'highlights': []}


def _goal(goal: Any) -> Any:
    if not isinstance(goal, Mapping):
        return goal
    before, after = goal.get('progress_before'), goal.get('progress_after')
    return {**goal, 'changed': before != after}


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
    failure = None
    if replay_summary is None:
        found = [w for w in run.get('warnings') or [] if isinstance(w, str) and w.startswith('daily_summary')]
        stage = ((run.get('stages') or {}).get('daily_summary') or {}).get('status')
        failure = found[0] if found else (f'daily_summary stage {stage}' if stage and stage != 'complete' else None)
    goals = [_goal(g) for g in run_day.get('goals') or []]
    return {
        'daily_summary': {
            'key': daily_summary_key(replay_summary) if replay_summary is not None else None,
            'replay': _summary_text(replay_summary) if replay_summary is not None else None,
            'replay_failure': failure,
            'baseline': _summary_text(production_summary) if production_summary is not None else None,
            'verdicts': verdicts,
        },
        'goals': goals,
        'goals_changed': sum(1 for g in goals if isinstance(g, Mapping) and g.get('changed')),
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


def _home_side(conv: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not conv:
        return None
    return {
        'id': conv.get('id'),
        'title': (conv.get('structured') or {}).get('title') or '',
        'started_at': conv.get('started_at'),
        'home': compare.on_home(conv),
        'home_reason': compare.home_reason(conv),
    }


def _group_of(view: Mapping[str, Any], side: str, conversation_id: str) -> Optional[dict[str, Any]]:
    return next((g for g in view['groups'] if conversation_id in (g.get(side) or [])), None)


def _comparison(conv: Optional[Mapping[str, Any]], twin: Optional[Mapping[str, Any]], group) -> dict[str, Any]:
    """Every compared field, its two values and its class, so a difference is never invisible."""
    left, right = compare.comparable(conv), compare.comparable(twin)
    if conv and twin:
        if group and len(group['production']) == 1 and len(group['replay']) == 1:
            fields = group.get('fields') or {}
        else:  # this page's replay against the production it was built over
            fields = compare.compare_pair(conv, twin, method='overlap')['fields']
    else:
        fields = {}
    out = []
    for name in compare.FIELDS:
        found = fields.get(name)
        out.append(
            {
                'field': name,
                'replay': (left or {}).get(name),
                'production': (right or {}).get(name),
                'class': found['class'] if found else 'same',
                'detail': found or {},
            }
        )
    return {'fields': out, 'kind': group['kind'] if group else None}


def conversation_detail(reader: Reader, run_id: str, conversation_id: str) -> dict[str, Any]:
    run = reader.run(run_id)
    conv = reader.conversation(run_id, conversation_id)
    by_id = {b['id']: b for b in reader.baseline_conversations(run['day_id'], pipeline_of(run)) if b.get('id')}
    view = reader.comparison(run)
    group = _group_of(view, 'replay', conversation_id)
    in_group = set(group['production']) if group else set()
    linked = [b for b in baseline_ids_of(conv) if b in by_id]
    # The production this page compares against: its own links inside its group (weak links to
    # another group's conversations would mix two stretches), else the group's production side.
    ids = [b for b in linked if b in in_group] or [b for b in (group or {}).get('production') or [] if b in by_id]
    twins = [by_id[b] for b in ids]
    twin = _merge_twins(twins)
    index = _verdict_index(reader, run['day_id'])
    siblings = [i for i in (group or {}).get('replay') or [] if i != conversation_id]
    return {
        'run_id': run_id,
        'kind': 'replay',
        'status': _status_of(group) if group else ('new' if not twins else 'changed'),
        'group': _group_summary(group),
        'siblings': [_brief(reader.conversation(run_id, i)) for i in siblings],
        'home': {'replay': _home_side(conv), 'production': [_home_side(t) for t in twins]},
        'compare': _comparison(conv, twin, group),
        'replay': conv,
        'baseline': twin,
        'baselines': [_brief(t) for t in twins],
        'keys': {'replay': _item_keys(conv), 'baseline': _item_keys(twin)},
        'pairs': conversation_pairs(conv, twin),
        'transcripts': {'replay': transcript_text(conv), 'baseline': transcript_text(twin) if twin else None},
        'audio': reader.audio_for(run['day_id'], conv),
        'llm_calls': reader.llm_calls(run_id, conversation_id, conv.get('llm_call_ids') or []),
        'verdicts': _verdicts_for(index, conversation_id, *baseline_ids_of(conv)),
    }


def _group_summary(group: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not group:
        return None
    return {
        key: group.get(key)
        for key in ('id', 'kind', 'marker', 'change', 'tags', 'home', 'production', 'replay', 'substantive', 'cosmetic')
    }


def production_detail(reader: Reader, run_id: str, baseline_id: str) -> dict[str, Any]:
    """A production conversation the replay did not reproduce (status ``missing``)."""
    run = reader.run(run_id)
    safe_id(baseline_id)
    twin = next(
        (b for b in reader.baseline_conversations(run['day_id'], pipeline_of(run)) if b.get('id') == baseline_id),
        None,
    )
    if twin is None:
        raise NotFound('production conversation not found')
    group = _group_of(reader.comparison(run), 'production', baseline_id)
    index = _verdict_index(reader, run['day_id'])
    return {
        'run_id': run_id,
        'kind': 'production',
        'status': _status_of(group) if group else 'missing',
        'group': _group_summary(group),
        'siblings': [],
        'home': {'replay': None, 'production': [_home_side(twin)]},
        'compare': _comparison(None, twin, group),
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
    if any(t.get('recordings') for t in twins):
        merged['recordings'] = list(dict.fromkeys(r for t in twins for r in t.get('recordings') or []))
        structured['sections'] = [x for t in twins for x in (t.get('structured') or {}).get('sections') or []]
        if isinstance(first.get('v3'), Mapping):
            merged['v3'] = {**first['v3'], 'visible': any((t.get('v3') or {}).get('visible') for t in twins)}
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
        'v3_conversations': reader.baseline_conversations(day_id, 'v3'),
        'memories': reader.baseline(day_id, 'memories.jsonl'),
        'action_items': reader.baseline(day_id, 'action_items.jsonl'),
        'notifications': reader.baseline(day_id, 'notifications.jsonl'),
        'daily_summary': reader.baseline_daily_summary(day_id),
    }


# ---- verdicts ------------------------------------------------------------------------------


def verdict_open(reader: Reader, row: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Where a verdict's item lives in its run: ``{kind: replay|production|day, run_id, id}``.

    Verdicts store the production id when one exists (RULINGS 4), which is not a replay file in a v3
    run; the link resolves it to the replay conversation the mark was made on, else the replay
    conversation grouped with that production one, else the production page.
    """
    run_id = row.get('run_id')
    if not isinstance(run_id, str):
        return None
    try:
        run = reader.run(run_id)
    except NotFound:
        return None
    cid = row.get('conversation_id')
    if not cid or row.get('item_kind') == 'daily_summary':
        return {'kind': 'day', 'run_id': run_id, 'id': None}
    replay_ids = {c['id'] for c in reader.conversations(run_id)}
    for candidate in (row.get('replay_conversation_id'), cid):
        if isinstance(candidate, str) and candidate in replay_ids:
            return {'kind': 'replay', 'run_id': run_id, 'id': candidate}
    group = _group_of(reader.comparison(run), 'production', cid)
    if group and group.get('replay'):
        return {'kind': 'replay', 'run_id': run_id, 'id': group['replay'][0]}
    return {'kind': 'production', 'run_id': run_id, 'id': cid}


def with_open_link(reader: Reader, row: Mapping[str, Any]) -> dict[str, Any]:
    return {**row, 'open': verdict_open(reader, row)}


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
            if not seg.get('is_user') and str(label or '').startswith('BATCH_UNASSIGNED_'):
                label = 'Unassigned speaker'  # batch diarization's per-segment abstention, not a person
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
    baseline = {b['id']: b for b in reader.baseline_conversations(day_id, pipeline_of(run)) if b.get('id')}
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
    if mark not in MARKS and mark != 'clear':
        raise BadRequest('mark must be good, bad or clear')
    if not isinstance(key, str) or not key or len(key) > 128:
        raise BadRequest('item_key is required')
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        raise BadRequest(f'note must be text of at most {MAX_NOTE_CHARS} characters')
    if conversation_id is not None and not isinstance(conversation_id, str):
        raise BadRequest('conversation_id must be a string')
    run = reader.run(run_id)
    snapshot = locate_item(reader, run, conversation_id, kind, key)
    replay_id = None
    if conversation_id is not None and kind != 'daily_summary':
        # RULINGS 4: store the production id when the conversation has one, so the mark follows the item.
        try:
            twins = baseline_ids_of(reader.conversation(run_id, conversation_id))
        except NotFound:
            twins = []
        if twins and twins[0] != conversation_id:
            replay_id, conversation_id = conversation_id, twins[0]
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
    if replay_id:
        row['replay_conversation_id'] = replay_id
    if reviewer:
        row['reviewer'] = reviewer
    return row
