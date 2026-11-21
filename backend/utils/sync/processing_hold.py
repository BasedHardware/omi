"""Bounded sync finalization policy. Metadata only; the enrichment outbox owns wakes.

Lifecycle: ops kill switch, default on; owner rollout-meetings; review 2026-11-28.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from functools import cache
import hashlib
import json
import os
from typing import Any

from prometheus_client import Counter, Histogram, REGISTRY
from config.merge_before_processing import enabled as merge_before_processing_enabled
from utils.observability.reasons import ReasonFamily, SyncProcessingHoldOutcome, reason_label

QUIET_SECONDS = 600
MIN_QUIET_SECONDS = 120
MAX_HOLD_SECONDS = 3600
MAX_LATE_RUNS = 1
FIELD = 'sync_processing_hold'


class ProcessingDeferred(RuntimeError):
    """Keep durable custody while a processing prerequisite is unavailable."""

    def __init__(self, reason: str, available_at: float):
        super().__init__(reason)
        self.reason = reason
        self.available_at = available_at


@cache
def _outcomes() -> Counter:
    # Pure assignment/archive imports need no collector registration. Reuse the
    # process collector if an isolated loader re-executes this policy module.
    try:
        return Counter('omi_sync_processing_hold_total', 'Sync full-processing admission outcomes', ['outcome'])
    except ValueError:
        return REGISTRY._names_to_collectors['omi_sync_processing_hold_total']  # type: ignore[attr-defined]


@cache
def _arrival_gap() -> Histogram:
    name = 'omi_sync_content_arrival_gap_seconds'
    try:
        return Histogram(
            name,
            'Seconds between consecutive content arrivals on one held sync conversation',
            buckets=(5, 15, 30, 60, 120, 180, 240, 300, 450, 600, 900, 1800, 3600),
        )
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


def record(outcome: str) -> None:
    _outcomes().labels(
        outcome=reason_label(ReasonFamily.SYNC_PROCESSING_HOLD, outcome, SyncProcessingHoldOutcome)
    ).inc()


def enabled() -> bool:
    return os.getenv('SYNC_PROCESSING_HOLD_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def quiet_seconds() -> int:
    """Arrival-quiet window before full processing, read per call.

    Clients that send no end-of-recording proof wait this long after the last
    content arrival. ``SYNC_PROCESSING_QUIET_SECONDS`` tunes it without a
    release; a missing or malformed value keeps the 600 s default, and the
    value is clamped to [120, 600] so a typo can neither remove the debounce
    nor lengthen the wait.
    """
    try:
        value = int(os.getenv('SYNC_PROCESSING_QUIET_SECONDS', str(QUIET_SECONDS)))
    except (TypeError, ValueError):
        return QUIET_SECONDS
    return max(MIN_QUIET_SECONDS, min(QUIET_SECONDS, value))


def enabled_for(row: Mapping[str, Any]) -> bool:
    # Outbox/context provenance owns this epoch. A mixed obligation remains
    # held while either independently enabled producer still needs its window.
    if 'sync_hold' in row:
        sync_requested = row.get('sync_hold_requested') or not row.get('merge_hold')
        return bool((row.get('merge_hold') and merge_before_processing_enabled()) or (sync_requested and enabled()))
    state = row.get(FIELD) or {}
    if state.get('merge_first'):
        return merge_before_processing_enabled() or bool(
            (row.get('sync_relevance') is not None or row.get('sync_live_target')) and enabled()
        )
    return enabled()


def owns_runtime() -> bool:
    # The shared enrichment outbox is intentionally production/emulator-only.
    # Dev hosts must retain their local eager path, never write the prod outbox.
    return os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'prod' or bool(os.getenv('FIRESTORE_EMULATOR_HOST'))


def scheduling_enabled() -> bool:
    return enabled() and owns_runtime()


def sync_sourced(row: Mapping[str, Any]) -> bool:
    return FIELD in row or row.get('sync_relevance') is not None or bool(row.get('sync_live_target'))


def timestamp(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value or 0)


def content_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    segments = row.get('transcript_segments') or []
    # IDs/offsets can change during rebase; content identity must survive that.
    texts = [str(s.get('text') or '').strip() for s in segments]
    intervals = sorted((float(s.get('start') or 0), float(s.get('end') or 0)) for s in segments)
    seconds, end = 0.0, float('-inf')
    for start, finish in intervals:
        seconds += max(0, finish - max(start, end))
        end = max(end, finish)
    return {
        'digest': hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest(),
        'words': sum(len(text.split()) for text in texts),
        'speech_seconds': seconds,
        'revision': row.get('sync_content_revision'),
    }


CLOCK_OFFSET_FIELD = 'content_clock_offset'
CLOCK_END_FIELD = 'content_clock_end'


def activity_patch(
    row: Mapping[str, Any], now: float, *, clock_offset: float = 0.0, owns_end: bool = False
) -> dict[str, Any]:
    """The hold state after one content arrival.

    Uploaded audio from a phone whose clock runs ahead is stored shifted onto
    the server clock by a per-request offset (``capture_clock_offset``). When
    this arrival sets the row's end (``owns_end``), that offset is kept beside
    the end it applies to, so the end-of-recording proof can compare the row
    with the phone's own clock. An unshifted arrival that sets the end clears
    it; an arrival that does not set the end leaves it alone. Nothing is
    written for a row that was never shifted.
    """
    state = dict(row.get(FIELD) or {})
    if owns_end:
        if clock_offset > 0:
            state[CLOCK_OFFSET_FIELD] = float(clock_offset)
            state[CLOCK_END_FIELD] = timestamp(row.get('finished_at'))
        else:
            state.pop(CLOCK_OFFSET_FIELD, None)
            state.pop(CLOCK_END_FIELD, None)
    # A successful full run ends an epoch. The next append starts a bounded new one.
    if not state.get('pending_since'):
        state['pending_since'] = now
    elif timestamp(state.get('last_content_at')):
        # The share of gaps longer than a candidate quiet window is the late
        # re-run rate that window would buy. Content-free; a retried assignment
        # transaction may observe one gap twice, which a distribution tolerates.
        try:
            _arrival_gap().observe(max(0.0, now - timestamp(state.get('last_content_at'))))
        except Exception:  # Metrics must never break assignment.
            pass
    state['held'] = True
    state['last_content_at'] = max(timestamp(state.get('last_content_at')), now)
    return state


def admission(
    row: Mapping[str, Any],
    obligation: Mapping[str, Any],
    *,
    now: float,
    end_proven: Callable[[], bool] | None = None,
) -> tuple[str, float | None]:
    """A missing watermark is unknown, never inferred from one uploaded file.

    ``end_proven`` is asked only when this call would otherwise wait. A true
    answer means the phone has proven the recording ended and its speech has
    landed (``utils.sync.capture_end.proof``), so the wait is skipped and the
    outcome is ``end_proof``. The unchanged, immaterial and late-cap rules still
    apply. No answer, or a false one, leaves the quiet rule exactly as it was.
    """
    state = row.get(FIELD) or {}
    first = timestamp(state.get('pending_since')) or float(obligation['first_pending_at'])
    last = max(timestamp(state.get('last_content_at')), timestamp((row.get('smart_merge') or {}).get('last_merged_at')))
    last = last or first
    quiet = quiet_seconds()
    due = min(last + quiet, first + MAX_HOLD_SECONDS)
    watermark = state.get('upload_watermark_at')
    gap = timestamp(row.get('finished_at')) + quiet
    waiting: tuple[str, float | None] | None = None
    if now < first + MAX_HOLD_SECONDS:
        if now < due:
            waiting = ('quiet_wait', due)
        elif watermark is not None and timestamp(watermark) < gap:
            waiting = ('watermark_wait', min(now + quiet, first + MAX_HOLD_SECONDS))
    if waiting is not None and not (end_proven is not None and end_proven()):
        return waiting
    previous = state.get('full_snapshot')
    if previous:
        current = content_snapshot(row)
        unprocessed_donor = bool(state.get('unprocessed_donor'))
        if previous.get('digest') == current['digest'] and not unprocessed_donor:
            return 'unchanged', None
        if not unprocessed_donor and int(state.get('late_runs') or 0) >= MAX_LATE_RUNS:
            return 'late_cap', None
        if (
            not unprocessed_donor
            and current['speech_seconds'] - float(previous.get('speech_seconds') or 0) < 30
            and current['words'] - int(previous.get('words') or 0) < 80
        ):
            return 'immaterial', None
    if waiting is not None:
        return 'end_proof', None
    return ('max_hold' if now >= first + MAX_HOLD_SECONDS else 'ready'), None


def completion_patch(
    existing: Mapping[str, Any], snapshot: Mapping[str, Any], *, automatic: bool = True
) -> dict[str, Any]:
    state = dict(existing.get(FIELD) or {})
    previous = state.get('full_snapshot') or {}
    state['late_runs'] = int(state.get('late_runs') or 0) + int(
        automatic and bool(previous) and previous.get('digest') != snapshot.get('digest')
    )
    state.update(full_snapshot=dict(snapshot), pending_since=None, held=False)
    state.pop('unprocessed_donor', None)
    return state
