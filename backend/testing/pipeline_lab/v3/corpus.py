"""``corpus add-day`` for conversations v3: the day's recordings and production's v3 result.

Reads ``<snapshot>/v3/`` (written by ``v3/prod_export.py``) when present. Local files only.

Writes, beside the classic corpus files:

- ``v3/recordings.jsonl``: the day's recordings (started in the local day), lab uid, raw
  shape with ``_create_time``/``_update_time``. The v3 replay feeds these;
- ``v3/derived.jsonl``: production's v3 conversations of the day, raw shape (hidden, failed
  and deleted ones included);
- ``v3/meta.json``: counts, when live v3 began that day, backfill runs, legacy rows beside v3;
- ``baseline/v3_conversations.jsonl``: production's v3 conversations in the contract shape
  (``recordings``, ``v3``), with their tasks and memories: the comparison target;
- start state: recordings that started before the day (``v3_pending`` cleared) are added to
  ``start_state/conversations.jsonl`` so an earlier window's recordings resolve.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from testing.pipeline_lab.stack.io import parse_time
from testing.pipeline_lab.v3.export import home_visible, is_v3_conversation, production_v3_view

V3_DIR = 'v3'


def export_dir(snapshot_dir: Path) -> Path:
    return Path(snapshot_dir) / V3_DIR


def has_v3_export(snapshot_dir: Path) -> bool:
    return (export_dir(snapshot_dir) / 'manifest.json').is_file()


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _jsonl(rows: Iterable[Any]) -> bytes:
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + '\n' for row in rows).encode()


def read_day_recordings(store: Any, day_id: str) -> list[dict[str, Any]]:
    from testing.pipeline_lab.store import read_jsonl

    path = store.day_dir(day_id) / V3_DIR / 'recordings.jsonl'
    if not path.is_file():
        raise FileNotFoundError('corpus day has no v3 recordings (add the day from a snapshot with a v3 export)')
    return list(read_jsonl(path))


def day_has_v3(store: Any, day_id: str) -> bool:
    return (store.day_dir(day_id) / V3_DIR / 'recordings.jsonl').is_file()


def v3_corpus(
    snapshot_dir: Path,
    *,
    contains: Callable[[Any], bool],
    day_start: Any,
    remap: Callable[[Iterable[Mapping[str, Any]]], list[dict[str, Any]]],
    memories: Iterable[Mapping[str, Any]] = (),
    action_items: Iterable[Mapping[str, Any]] = (),
    people: Mapping[str, str] | None = None,
    legacy_day_rows: Iterable[Mapping[str, Any]] = (),
) -> tuple[dict[str, bytes], list[dict[str, Any]], dict[str, Any]]:
    """``(blobs, prior_recordings, meta)``. ``memories``/``action_items`` are already remapped
    (all of the snapshot's rows); this keeps the ones whose conversation is a v3 row of the day."""
    base = export_dir(snapshot_dir)
    recordings = remap(_jsonl_rows(base / 'recordings.jsonl'))
    derived_all = remap(_jsonl_rows(base / 'derived.jsonl'))
    day_recordings = sorted(
        (r for r in recordings if contains(r.get('started_at'))), key=lambda r: (str(r.get('started_at')), r['id'])
    )
    start = parse_time(day_start)
    prior = []
    for row in recordings:
        started = parse_time(row.get('started_at'))
        if started is not None and start is not None and started < start:
            prior.append({**row, 'v3_pending': False, 'v3_pending_since': None})
    derived = sorted(
        (r for r in derived_all if is_v3_conversation(r) and contains(r.get('started_at'))),
        key=lambda r: (str(r.get('started_at')), r['id']),
    )
    ids = {str(r['id']) for r in derived}
    day_memories = [m for m in memories if str(m.get('conversation_id') or '') in ids]
    day_tasks = [t for t in action_items if str(t.get('conversation_id') or '') in ids]
    view = production_v3_view(derived, memories=day_memories, action_items=day_tasks, people=people)
    live = [r for r in day_recordings if not r.get('v3_backfill_run')]
    live_since = min((str(r['started_at']) for r in live), default=None)
    legacy_after = [
        r
        for r in legacy_day_rows
        if live_since
        and not r.get('v3_derived')
        and not r.get('recording')
        and str(r.get('started_at') or '') >= live_since
        and not r.get('discarded')
    ]
    meta = {
        'recordings': len(day_recordings),
        'recordings_live': len(live),
        'recordings_backfill_donors': len(day_recordings) - len(live),
        'v3_conversations': len(derived),
        'v3_visible': sum(1 for r in derived if home_visible(r)),
        'v3_backfilled': sum(1 for r in derived if r.get('backfilled')),
        'live_since': live_since,
        'backfill_runs': sorted(
            {str(r['v3_backfill_run']) for r in day_recordings + derived if r.get('v3_backfill_run')}
        ),
        'legacy_kept_rows_after_live': len(legacy_after),
        'prior_recordings': len(prior),
        'memories': len(day_memories),
        'action_items': len(day_tasks),
        'note': (
            'baseline/v3_conversations.jsonl is what v3 produced; legacy rows of the same day are not in it '
            '(before the 2026-11-19 batch-projection admission fix, batch projection also made legacy rows '
            'for admitted owners).'
        ),
    }
    blobs = {
        f'{V3_DIR}/recordings.jsonl': _jsonl(day_recordings),
        f'{V3_DIR}/derived.jsonl': _jsonl(derived),
        f'{V3_DIR}/meta.json': json.dumps(meta, ensure_ascii=False, sort_keys=True).encode(),
        'baseline/v3_conversations.jsonl': _jsonl(view),
    }
    return blobs, prior, meta
