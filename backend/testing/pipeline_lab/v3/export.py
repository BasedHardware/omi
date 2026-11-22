"""v3 conversations in the store contract, and their pairing with production by recording.

A v3 conversation is a window planned over one or more **recordings**; its id is derived from
the owner uid and its start (``uuid5('v3:<uid>:<start>')``), so a replay under the lab uid
never reuses production's id. Pairing is therefore by the recordings both sides share
(production's recording ids are replayed unchanged), then by time overlap:

- ``baseline_ids``: every production v3 conversation that shares a recording with the replay
  conversation and overlaps it in time (several when production split what the replay merged);
- ``baseline_id``: the one of those with the largest time overlap, so the shared pairing in
  ``baseline/compare.py`` matches by id first and keeps its status chips.

The contract row gains two fields for v3 (``contracts.ConversationRecord``): ``recordings``
(source recording ids in order) and ``v3`` (what the phone's Home reads: visibility and its
reason, kind, tile state, notes state). ``structured`` additionally carries the v3 notes'
``sections``, ``participants`` and ``gist`` when present.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.stack.io import iso, parse_time, plain

V3_LANE = 'v3'


def is_v3_conversation(row: Mapping[str, Any]) -> bool:
    return row.get('v3_derived') is True and row.get('recording') is not True


def home_visible(row: Mapping[str, Any]) -> bool:
    """Shown on the phone's Home list (``is_visible_conversation(hide_home=True)`` without discards)."""
    status = row.get('status')
    return bool(
        not row.get('home_hidden')
        and not row.get('deleted')
        and not row.get('discarded')
        and getattr(status, 'value', status) != 'failed'
    )


def v3_block(row: Mapping[str, Any]) -> dict[str, Any]:
    status = row.get('status')
    return {
        'visible': home_visible(row),
        'home_hidden': bool(row.get('home_hidden')),
        'home_hidden_reason': row.get('home_hidden_reason'),
        'kind': row.get('kind'),
        'outline_kind': row.get('outline_kind'),
        'status': getattr(status, 'value', status),
        'tile_state': row.get('tile_state'),
        'notes_written': bool(row.get('v3_notes_written')),
        'process_failed': bool(row.get('v3_process_failed')),
        'process_failure_reason': row.get('v3_process_failure_reason'),
        'manual_end': bool(row.get('manual_end')),
        'backfilled': bool(row.get('backfilled')),
        'backfill_run': row.get('v3_backfill_run'),
        'title_locked': bool(row.get('title_locked')),
        'rewrites': int(row.get('v3_rewrites') or 0),
        'created_delivered': bool(row.get('v3_created_delivered_at')),
        'deleted': bool(row.get('deleted')),
        'summary_covers_through': (
            iso(parse_time(row.get('summary_covers_through')))
            if parse_time(row.get('summary_covers_through'))
            else None
        ),
    }


def normalize_v3_conversation(
    row: Mapping[str, Any],
    *,
    action_items: Iterable[Mapping[str, Any]] = (),
    memories: Iterable[Mapping[str, Any]] = (),
    notifications: Iterable[Mapping[str, Any]] = (),
    llm_call_ids: Iterable[str] = (),
    people: Mapping[str, str] | None = None,
    baseline_id: str | None = None,
    baseline_ids: Sequence[str] | None = None,
    evaluable: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = normalize_conversation(
        row,
        action_items=action_items,
        memories=memories,
        notifications=notifications,
        llm_call_ids=llm_call_ids,
        lane=V3_LANE,
        baseline_id=baseline_id,
        people=people,
        evaluable=evaluable or {'boundaries': True, 'reason': 'v3_builder'},
    )
    value = row.get('structured') or {}
    for key in ('sections', 'participants', 'gist'):
        if value.get(key):
            out['structured'][key] = plain(value[key])
    out['baseline_ids'] = list(baseline_ids) if baseline_ids else None
    out['recordings'] = [str(r) for r in row.get('v3_recording_ids') or []]
    out['v3'] = v3_block(row)
    return out


def _span(row: Mapping[str, Any]):
    start = parse_time(row.get('started_at'))
    end = parse_time(row.get('finished_at')) or start
    return (start, end) if start is not None and end is not None else None


def overlap_seconds(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    sa, sb = _span(a), _span(b)
    if sa is None or sb is None:
        return 0.0
    return max(0.0, (min(sa[1], sb[1]) - max(sa[0], sb[0])).total_seconds())


def pair_by_recordings(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]]
) -> dict[str, tuple[str | None, list[str]]]:
    """``{replay_id: (baseline_id, baseline_ids)}`` from shared recordings and time overlap.

    Rows are contract rows (``recordings`` list) or product rows (``v3_recording_ids``).
    A production row is claimed as ``baseline_id`` by at most one replay row (largest overlap
    first), so the shared id-first matcher never pairs one production row twice.
    """

    def recordings(row: Mapping[str, Any]) -> set[str]:
        return {str(r) for r in (row.get('recordings') or row.get('v3_recording_ids') or [])}

    by_recording: dict[str, list[Mapping[str, Any]]] = {}
    for row in production:
        for rid in recordings(row):
            by_recording.setdefault(rid, []).append(row)
    candidates: dict[str, list[tuple[float, int, str]]] = {}
    for row in replay:
        rid = str(row['id'])
        mine = recordings(row)
        seen: dict[str, tuple[float, int]] = {}
        for recording in mine:
            for prod in by_recording.get(recording, []):
                pid = str(prod['id'])
                shared = len(mine & recordings(prod))
                seen[pid] = (overlap_seconds(row, prod), shared)
        candidates[rid] = sorted(
            ((ov, shared, pid) for pid, (ov, shared) in seen.items() if ov > 0 or shared),
            key=lambda c: (-c[0], -c[1], c[2]),
        )
    out: dict[str, tuple[str | None, list[str]]] = {
        rid: (None, sorted(pid for ov, _, pid in found if ov > 0)) for rid, found in candidates.items()
    }
    ranked = sorted(
        ((ov, shared, rid, pid) for rid, found in candidates.items() for ov, shared, pid in found if ov > 0),
        key=lambda c: (-c[0], -c[1], c[2], c[3]),
    )
    used_replay: set[str] = set()
    used_prod: set[str] = set()
    for _, _, rid, pid in ranked:
        if rid in used_replay or pid in used_prod:
            continue
        out[rid] = (pid, out[rid][1])
        used_replay.add(rid)
        used_prod.add(pid)
    return out


def production_v3_view(
    rows: Iterable[Mapping[str, Any]],
    *,
    memories: Iterable[Mapping[str, Any]] = (),
    action_items: Iterable[Mapping[str, Any]] = (),
    people: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Production's v3 conversations of a day in the replay's shape (``baseline/v3_conversations.jsonl``)."""
    by_conv: dict[str, dict[str, list]] = {}
    for kind, items in (('memories', memories), ('action_items', action_items)):
        for item in items:
            cid = item.get('conversation_id')
            if cid:
                by_conv.setdefault(str(cid), {}).setdefault(kind, []).append(item)
    out = []
    for row in rows:
        if not is_v3_conversation(row):
            continue
        grouped = by_conv.get(str(row.get('id')), {})
        normalized = normalize_v3_conversation(
            row,
            action_items=grouped.get('action_items', []),
            memories=grouped.get('memories', []),
            people=people,
            baseline_id=str(row.get('id')),
            evaluable={'boundaries': True, 'reason': 'production'},
        )
        out.append(normalized)
    out.sort(key=lambda c: (c.get('started_at') or '', c['id']))
    return out
