"""Which recordings a v3 replay feeds, in which order, at which virtual instant, as which row.

A v3 day's input is its **recordings** (rows production marked ``recording: true``): the
builder plans conversations from their speech. Production saw each one when its transcript
had landed and its capture finalized (``recording_short_path`` -> ``triggers.changed``).
The snapshot keeps no single field for that moment, so the first present of these is used
and the source is recorded per recording:

1. ``terminal_family_at``             - the recording reached its terminal state;
2. ``record_sealed_at`` + ``lag``     - the batch lane sealed the audio (epoch seconds);
3. ``finished_at`` + ``lag``          - last resort (default lag 60 s, flagged).

A stamp more than ``MAX_STAMP_LAG`` (30 min) after ``finished_at`` is skipped: on rows a backfill
converted, ``terminal_family_at`` records the legacy row's later re-finalization.

``mode='finish'`` ignores the production stamps and uses ``finished_at + lag`` for every
recording (an idealized, latency-free day).

**Pre-v3 row.** The recording is fed as a fresh capture end: capture facts only
(``chain.order.CAPTURE_FIELDS``: transcript, audio files, times, source, protection level),
``status: in_progress``, no v3 markers, no claims and no backfill stamps. The product then
decides admission itself (``triggers.mark_new``) and finalization routes it through
``recording_short_path``. A user's explicit stop (``v3_manual_end``) is a capture fact and
is replayed after finalization.

**Partial updates.** A live capture's row exists from its first second, and production writes
its speech as it is transcribed (``database.conversations.update_conversation_segments``, which
re-arms the builder through ``triggers.changed``). The snapshot keeps only the final transcript,
not when each segment landed, so with ``partial_step`` set the plan models it: segment ``i`` lands
at ``started_at + end_i + partial_lag``, and a partial arrival carries every segment landed so
far, at most one per ``partial_step`` (a segment landing inside the step waits for the next slot). Only rows created before their capture finished get
partials (an offline upload lands whole), and every partial comes before the recording's own
arrival, which still finalizes the full capture.

Rows production deleted or merged away (``deleted``, ``sync_merged_into``) are skipped and
reported; an in-progress recording with no speech is skipped too (it never fed a line).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from testing.pipeline_lab.chain.order import CAPTURE_FIELDS, pre_finalization_row
from testing.pipeline_lab.stack.io import parse_time
from utils.conversations.v3.word_floor import text_word_count

DEFAULT_LAG = timedelta(seconds=60)
# A production stamp further than this after ``finished_at`` is not the capture's arrival (backfill
# donors carry their legacy row's late re-finalization in ``terminal_family_at``: hours, not minutes).
MAX_STAMP_LAG = timedelta(minutes=30)
MODES = ('production', 'finish')
DEFAULT_PARTIAL_STEP = timedelta(seconds=60)


@dataclass(frozen=True)
class Arrival:
    recording_id: str
    instant: datetime
    instant_source: str
    started_at: datetime | None
    finished_at: datetime | None
    lane: str
    words: int
    manual_end: bool
    backfill_donor: bool  # production converted this row in a backfill pass, not live
    row: Mapping[str, Any] = field(repr=False)
    segments: int | None = None  # a partial update: the first N speech segments; None = the finished capture

    @property
    def partial(self) -> bool:
        return self.segments is not None


@dataclass
class FeedPlan:
    arrivals: list[Arrival]
    skipped: dict[str, list[str]]

    def summary(self) -> dict[str, Any]:
        sources: dict[str, int] = {}
        for arrival in self.arrivals:
            sources[arrival.instant_source] = sources.get(arrival.instant_source, 0) + 1
        partials = [a for a in self.arrivals if a.partial]
        sources = {k: v for k, v in sources.items() if k != 'partial'}
        return {
            'arrivals': len(self.arrivals) - len(partials),
            'partial_updates': len(partials),
            'recordings_with_partials': len({a.recording_id for a in partials}),
            'backfill_donors': sum(1 for a in self.arrivals if a.backfill_donor and not a.partial),
            'manual_end': sum(1 for a in self.arrivals if a.manual_end and not a.partial),
            'instant_sources': sources,
            'skipped': {reason: len(ids) for reason, ids in self.skipped.items()},
        }


def word_count(row: Mapping[str, Any]) -> int:
    return sum(text_word_count(str(s.get('text') or '')) for s in row.get('transcript_segments') or [])


def _epoch(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return parse_time(value)
    return datetime.fromtimestamp(float(value), timezone.utc)


def arrival_instant(row: Mapping[str, Any], *, lag: timedelta = DEFAULT_LAG, mode: str = 'production'):
    """``(instant, source)`` at which production's v3 builder first had this recording's speech."""
    if mode not in MODES:
        raise ValueError(f'unknown arrival mode {mode!r}')
    finished = parse_time(row.get('finished_at'))

    def plausible(stamp: datetime | None) -> bool:
        return stamp is not None and (finished is None or stamp - finished <= MAX_STAMP_LAG)

    if mode == 'production':
        terminal = parse_time(row.get('terminal_family_at'))
        if plausible(terminal):
            return terminal, 'terminal_family_at'
        sealed = _epoch(row.get('record_sealed_at'))
        if plausible(sealed):
            return max(sealed, finished or sealed) + lag, 'record_sealed_at+lag'
    if finished is not None:
        return finished + lag, 'finished_at+lag'
    started = parse_time(row.get('started_at') or row.get('created_at'))
    if started is None:
        raise ValueError('recording has no usable time field')
    return started + lag, 'started_at+lag'


def speech_segments(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The row's segments with text, in speech order (the order partial updates deliver them)."""
    segments = [dict(s) for s in row.get('transcript_segments') or [] if str(s.get('text') or '').strip()]
    return sorted(segments, key=lambda s: (float(s.get('start') or 0), float(s.get('end') or 0)))


def partial_points(
    row: Mapping[str, Any], final: datetime, *, step: timedelta, lag: timedelta = DEFAULT_LAG
) -> list[tuple[datetime, int]]:
    """``(instant, segments landed)`` for each partial update of a live capture, before ``final``."""
    origin = parse_time(row.get('started_at'))
    created = parse_time(row.get('created_at'))
    finished = parse_time(row.get('finished_at'))
    if origin is None or created is None or finished is None or created >= finished:
        return []
    lands: list[datetime] = []
    for segment in speech_segments(row):
        land = origin + timedelta(seconds=max(float(segment.get('end') or 0), float(segment.get('start') or 0))) + lag
        lands.append(max([land, *lands[-1:]]))
    # A segment landing inside the step after the previous write waits for the next write slot,
    # so the tail of the speech still lands before the recording's own arrival.
    points: list[tuple[datetime, int]] = []
    delivered = 0
    while delivered < len(lands):
        at = lands[delivered] if not points else max(lands[delivered], points[-1][0] + step)
        if at >= final:
            break
        delivered = sum(1 for land in lands if land <= at)
        points.append((at, delivered))
    return points


def skip_reason(row: Mapping[str, Any]) -> str | None:
    if row.get('deleted'):
        return 'deleted'
    if row.get('sync_merged_into'):
        return 'merged_away'
    if not row.get('started_at'):
        return 'no_start'
    if row.get('status') == 'in_progress' and not row.get('transcript_segments'):
        return 'in_progress_no_speech'
    return None


def plan_arrivals(
    rows: Iterable[Mapping[str, Any]],
    *,
    lag: timedelta = DEFAULT_LAG,
    mode: str = 'production',
    partial_step: timedelta | None = None,
    partial_lag: timedelta = DEFAULT_LAG,
) -> FeedPlan:
    arrivals: list[Arrival] = []
    skipped: dict[str, list[str]] = {}
    for row in rows:
        reason = skip_reason(row)
        if reason is not None:
            skipped.setdefault(reason, []).append(str(row.get('id')))
            continue
        instant, source = arrival_instant(row, lag=lag, mode=mode)
        final = Arrival(
            recording_id=str(row['id']),
            instant=instant,
            instant_source=source,
            started_at=parse_time(row.get('started_at')),
            finished_at=parse_time(row.get('finished_at')),
            lane=str(row.get('record_lane_owner') or f'source:{row.get("source") or "unknown"}'),
            words=word_count(row),
            manual_end=row.get('v3_manual_end') is True,
            backfill_donor=bool(row.get('v3_backfill_run')),
            row=row,
        )
        if partial_step is not None:
            segments = speech_segments(row)
            for at, count in partial_points(row, instant, step=partial_step, lag=partial_lag):
                arrivals.append(
                    replace(
                        final,
                        instant=at,
                        instant_source='partial',
                        manual_end=False,
                        words=sum(text_word_count(str(s.get('text') or '')) for s in segments[:count]),
                        segments=count,
                    )
                )
        arrivals.append(final)
    # A recording's partials precede its own arrival (strictly earlier instants); ties between
    # recordings keep start order, then the partial before a finished capture.
    arrivals.sort(key=lambda a: (a.instant, a.started_at or a.instant, a.recording_id, not a.partial))
    return FeedPlan(arrivals=arrivals, skipped=skipped)


# Kept beyond chain's capture facts: the capture's own clock and stop marker inputs.
V3_CAPTURE_FIELDS = CAPTURE_FIELDS | frozenset({'recorded_start', 'recorded_end'})


def pre_v3_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """The recording as a fresh capture end: capture facts only, no v3 or derived state."""
    return pre_finalization_row(row, keep=V3_CAPTURE_FIELDS)
