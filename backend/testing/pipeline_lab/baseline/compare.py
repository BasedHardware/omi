"""Baseline normalization, matching and the comparable view. Pure functions over contract JSON.

**Production view.** ``corpus/<day>/baseline/{conversations,memories,action_items}.jsonl``
hold production rows (snapshot shape). They go through the same
:func:`chain.export.normalize_conversation` as the replay, with tasks and memories
grouped by ``conversation_id``, so both sides have one shape.

**Matching.** Id first (M1 replays production's own capture ids). The rest pair by
time overlap: greedy on intersection-over-union of ``[started_at, finished_at]``,
highest first, above ``min_iou`` (default 0.3). Unpaired replay = ``new``, unpaired
production = ``missing``, or ``merged`` (with ``merged_into``) when a v3 replay conversation
lists it in ``baseline_ids`` (it shares recordings with that replay conversation).

**Boundary** differs when either edge moved more than ``BOUNDARY_TOLERANCE_S`` or the pair
was matched by overlap rather than id. **Transcript** compares normalized text.

This is the one pairing and status implementation (RULINGS 10); the inspector reads
``baseline.json`` and only lays out word diffs.

**Status** (DESIGN UX chips): ``discard flipped`` when exactly one side discarded;
``same`` when every compared field is equal; else ``changed``. Every difference is
a production comparison (``vs production``), never a regression verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.contracts import normalize_text
from testing.pipeline_lab.stack.io import parse_time

BOUNDARY_TOLERANCE_S = 30.0

COMPARED_FIELDS = (
    'discarded',
    'boundary',
    'transcript',
    'title',
    'overview',
    'emoji',
    'category',
    'action_items',
    'memories',
    'notifications',
    'segments',
    'hidden',
    'kind',
)


def production_view(
    conversations: Iterable[Mapping[str, Any]],
    *,
    memories: Iterable[Mapping[str, Any]] = (),
    action_items: Iterable[Mapping[str, Any]] = (),
    notifications: Iterable[Mapping[str, Any]] = (),
    people: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    by_conv: dict[str, dict[str, list]] = {}
    for kind, rows in (('memories', memories), ('action_items', action_items), ('notifications', notifications)):
        for row in rows:
            cid = row.get('conversation_id') or (row.get('memory_id') if kind == 'memories' else None)
            if cid:
                by_conv.setdefault(str(cid), {}).setdefault(kind, []).append(row)
    out = []
    for row in conversations:
        cid = str(row.get('id'))
        grouped = by_conv.get(cid, {})
        normalized = normalize_conversation(
            row,
            action_items=grouped.get('action_items', []),
            memories=grouped.get('memories', []),
            notifications=grouped.get('notifications', []),
            lane=row.get('record_lane_owner') or 'unknown',
            baseline_id=cid,
            people=people,
            evaluable={'boundaries': True, 'reason': 'production'},
        )
        out.append(normalized)
    out.sort(key=lambda c: (c.get('started_at') or '', c['id']))
    return out


def _span(conversation: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    start = parse_time(conversation.get('started_at'))
    end = parse_time(conversation.get('finished_at')) or start
    if start is None or end is None:
        return None
    return (start, end) if end >= start else (end, start)


def iou(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    sa, sb = _span(a), _span(b)
    if sa is None or sb is None:
        return 0.0
    inter = (min(sa[1], sb[1]) - max(sa[0], sb[0])).total_seconds()
    if inter <= 0:
        return 0.0
    union = (max(sa[1], sb[1]) - min(sa[0], sb[0])).total_seconds()
    return inter / union if union > 0 else 1.0


@dataclass(frozen=True)
class Match:
    replay_id: str | None
    baseline_id: str | None
    method: str  # id | overlap | unmatched
    iou: float


def match_conversations(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], *, min_iou: float = 0.3
) -> list[Match]:
    prod_by_id = {str(p['id']): p for p in production}
    matches: list[Match] = []
    used_prod: set[str] = set()
    pending_replay = []
    for r in replay:
        rid = str(r['id'])
        candidate = r.get('baseline_id') or rid
        if candidate in prod_by_id and candidate not in used_prod:
            matches.append(Match(rid, candidate, 'id', round(iou(r, prod_by_id[candidate]), 4)))
            used_prod.add(candidate)
        else:
            pending_replay.append(r)
    remaining_prod = [p for p in production if str(p['id']) not in used_prod]
    scored = sorted(
        ((iou(r, p), str(r['id']), str(p['id'])) for r in pending_replay for p in remaining_prod),
        key=lambda row: (-row[0], row[1], row[2]),
    )
    used_replay: set[str] = set()
    for score, rid, pid in scored:
        if score < min_iou:
            break
        if rid in used_replay or pid in used_prod:
            continue
        matches.append(Match(rid, pid, 'overlap', round(score, 4)))
        used_replay.add(rid)
        used_prod.add(pid)
    for r in pending_replay:
        if str(r['id']) not in used_replay:
            matches.append(Match(str(r['id']), None, 'unmatched', 0.0))
    for p in production:
        if str(p['id']) not in used_prod:
            matches.append(Match(None, str(p['id']), 'unmatched', 0.0))
    return matches


def comparable(conversation: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The fields the inspector diffs, reduced to comparable values."""
    if conversation is None:
        return None
    s = conversation.get('structured') or {}
    text = ' '.join((seg.get('text') or '').strip() for seg in conversation.get('segments') or [])
    return {
        'discarded': bool(conversation.get('discarded')),
        'boundary': (conversation.get('started_at'), conversation.get('finished_at')),
        'transcript': normalize_text(text),
        'title': s.get('title') or '',
        'overview': s.get('overview') or '',
        'emoji': s.get('emoji') or '',
        'category': s.get('category') or '',
        'action_items': sorted(item['key'] for item in conversation.get('action_items') or []),
        'memories': sorted(item['key'] for item in conversation.get('memories') or []),
        'notifications': len(conversation.get('notifications') or []),
        'segments': len(conversation.get('segments') or []),
        # v3: what the phone's Home shows. Classic rows carry no ``v3`` block, so both sides agree.
        'hidden': not (conversation.get('v3') or {}).get('visible', True),
        'kind': (conversation.get('v3') or {}).get('kind') or '',
    }


def _set_diff(replay: Sequence[str], production: Sequence[str]) -> dict[str, list[str]]:
    r, p = set(replay), set(production)
    return {'added': sorted(r - p), 'removed': sorted(p - r)}


def _edge_shift(a: Any, b: Any) -> float | None:
    left, right = parse_time(a), parse_time(b)
    if left is None or right is None:
        return None if (left is None) != (right is None) else 0.0
    return abs((left - right).total_seconds())


def boundary_moved(replay: Mapping[str, Any], production: Mapping[str, Any], method: str = 'id') -> bool:
    if method == 'overlap':
        return True
    for name in ('started_at', 'finished_at'):
        shift = _edge_shift(replay.get(name), production.get(name))
        if shift is None or shift > BOUNDARY_TOLERANCE_S:
            return True
    return False


def compare_pair(
    replay: Mapping[str, Any] | None, production: Mapping[str, Any] | None, *, method: str = 'id'
) -> dict[str, Any]:
    left, right = comparable(replay), comparable(production)
    if left is None:
        return {'status': 'missing', 'changed_fields': [], 'diff': {}}
    if right is None:
        return {'status': 'new', 'changed_fields': [], 'diff': {}}
    changed = [
        name
        for name in COMPARED_FIELDS
        if (boundary_moved(replay, production, method) if name == 'boundary' else left[name] != right[name])
    ]
    diff: dict[str, Any] = {}
    for name in changed:
        if name in ('action_items', 'memories'):
            diff[name] = _set_diff(left[name], right[name])
        elif name == 'transcript':
            diff[name] = {'changed': True}  # the inspector renders the word diff from both files
        else:
            diff[name] = {'replay': left[name], 'production': right[name]}
    if left['discarded'] != right['discarded']:
        status = 'discard flipped'
    elif not changed:
        status = 'same'
    else:
        status = 'changed'
    return {'status': status, 'changed_fields': changed, 'diff': diff, 'label': 'vs production'}


def baseline_view(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], *, min_iou: float = 0.3
) -> dict[str, Any]:
    """``runs/<run_id>/baseline.json``: one row per matched/unmatched conversation, plus counts."""
    replay_by_id = {str(r['id']): r for r in replay}
    prod_by_id = {str(p['id']): p for p in production}
    # v3: a replay conversation lists every production conversation sharing its recordings. A production
    # row that pairs with nothing else but is listed there was merged into that replay, not lost.
    listed_by: dict[str, str] = {}
    for r in replay:
        for bid in r.get('baseline_ids') or []:
            listed_by.setdefault(str(bid), str(r['id']))
    rows = []
    for match in match_conversations(replay, production, min_iou=min_iou):
        r = replay_by_id.get(match.replay_id) if match.replay_id else None
        p = prod_by_id.get(match.baseline_id) if match.baseline_id else None
        rows.append(
            {
                'replay_id': match.replay_id,
                'baseline_id': match.baseline_id,
                'match': match.method,
                'iou': match.iou,
                'started_at': (r or p or {}).get('started_at'),
                **compare_pair(r, p, method=match.method),
            }
        )
        if r is None and match.baseline_id in listed_by:
            rows[-1].update(status='merged', merged_into=listed_by[match.baseline_id])
    rows.sort(key=lambda row: (row.get('started_at') or '', row.get('replay_id') or row.get('baseline_id') or ''))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return {'fields_compared': list(COMPARED_FIELDS), 'counts': counts, 'conversations': rows}
