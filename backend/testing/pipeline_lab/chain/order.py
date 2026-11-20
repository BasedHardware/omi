"""Which conversations run, in which order, at which frozen instant, from which row.

**Instant** (DESIGN L3): the conversation's production finalization instant. The
snapshot has no single field for it, so the first present of these is used and the
source is recorded per conversation:

1. ``notes_written_at``   - when production wrote the notes (closest to finalization)
2. ``summary_completed_at``
3. ``finalized_at`` / ``completed_at``
4. ``finished_at`` + ``fallback_lag`` (default 60 s)
5. ``started_at``/``created_at`` + ``fallback_lag`` (last resort, flagged)

**Order**: by instant, ties by ``started_at`` then id, so the 7-day task dedup,
memory intake and goal progress see exactly the conversations production had seen.

**Pre-finalization row**: the stored transcript and capture facts, with every
derived field removed and ``status: in_progress``, so the real finalizer admits it
as a fresh capture end. ``record_lane_owner`` is dropped on purpose: in M1 the
transcript is already there, and a server-batch owner would route the row to the
batch-archive branch that waits for audio custody. The lane is still reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from testing.pipeline_lab.stack.io import parse_time

INSTANT_FIELDS = ('notes_written_at', 'summary_completed_at', 'finalized_at', 'completed_at')

# Capture facts a fresh capture end carries. Everything else is derived and dropped.
CAPTURE_FIELDS = frozenset(
    {
        'id',
        'created_at',
        'started_at',
        'finished_at',
        'transcript_segments',
        'language',
        'source',
        'geolocation',
        'photos',
        'external_data',
        'client_platform',
        'uses_custom_stt',
        'data_protection_level',
        'audio_files',
        'private_cloud_sync_enabled',
        'visibility',
        'session_id',
        'capture_timezone',
    }
)


@dataclass(frozen=True)
class ChainItem:
    conversation_id: str
    instant: datetime
    instant_source: str
    started_at: datetime | None
    finished_at: datetime | None
    lane: str
    row: Mapping[str, Any]


def finalization_instant(
    row: Mapping[str, Any], *, fallback_lag: timedelta = timedelta(seconds=60)
) -> tuple[datetime, str]:
    for name in INSTANT_FIELDS:
        value = parse_time(row.get(name))
        if value is not None:
            return value, name
    finished = parse_time(row.get('finished_at'))
    if finished is not None:
        return finished + fallback_lag, 'finished_at+lag'
    for name in ('started_at', 'created_at'):
        value = parse_time(row.get(name))
        if value is not None:
            return value + fallback_lag, f'{name}+lag'
    raise ValueError('conversation has no usable time field')


def lane_of(row: Mapping[str, Any]) -> str:
    owner = row.get('record_lane_owner')
    if owner:
        return str(owner)
    source = row.get('source')
    return f'source:{source}' if source else 'unknown'


def plan_chain(
    rows: Iterable[Mapping[str, Any]], *, fallback_lag: timedelta = timedelta(seconds=60)
) -> list[ChainItem]:
    items = []
    for row in rows:
        instant, source = finalization_instant(row, fallback_lag=fallback_lag)
        items.append(
            ChainItem(
                conversation_id=str(row['id']),
                instant=instant,
                instant_source=source,
                started_at=parse_time(row.get('started_at') or row.get('created_at')),
                finished_at=parse_time(row.get('finished_at')),
                lane=lane_of(row),
                row=row,
            )
        )
    items.sort(key=lambda item: (item.instant, item.started_at or item.instant, item.conversation_id))
    return items


def pre_finalization_row(row: Mapping[str, Any], *, keep: frozenset[str] = CAPTURE_FIELDS) -> dict[str, Any]:
    out = {key: value for key, value in row.items() if key in keep}
    out['status'] = 'in_progress'
    out['discarded'] = False
    out['structured'] = {}
    return out
