"""Bounded sync finalization policy. Metadata only; the enrichment outbox owns wakes.

Lifecycle: ops kill switch, default on; owner rollout-meetings; review 2026-11-28.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from functools import cache
import hashlib
import json
import os
from typing import Any

from prometheus_client import Counter, REGISTRY
from utils.observability.reasons import ReasonFamily, SyncProcessingHoldOutcome, reason_label

QUIET_SECONDS = 600
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


def record(outcome: str) -> None:
    _outcomes().labels(
        outcome=reason_label(ReasonFamily.SYNC_PROCESSING_HOLD, outcome, SyncProcessingHoldOutcome)
    ).inc()


def enabled() -> bool:
    return os.getenv('SYNC_PROCESSING_HOLD_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


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


def activity_patch(row: Mapping[str, Any], now: float) -> dict[str, Any]:
    state = dict(row.get(FIELD) or {})
    # A successful full run ends an epoch. The next append starts a bounded new one.
    if not state.get('pending_since'):
        state['pending_since'] = now
    state['held'] = True
    state['last_content_at'] = max(timestamp(state.get('last_content_at')), now)
    return state


def admission(row: Mapping[str, Any], obligation: Mapping[str, Any], *, now: float) -> tuple[str, float | None]:
    """A missing watermark is unknown, never inferred from one uploaded file.

    No existing WAL producer supplies a contiguous device upload watermark. If
    one is attached to this row in future, it must be past finished_at + quiet.
    """
    state = row.get(FIELD) or {}
    first = timestamp(state.get('pending_since')) or float(obligation['first_pending_at'])
    last = max(timestamp(state.get('last_content_at')), timestamp((row.get('smart_merge') or {}).get('last_merged_at')))
    last = last or first
    due = min(last + QUIET_SECONDS, first + MAX_HOLD_SECONDS)
    watermark = state.get('upload_watermark_at')
    gap = timestamp(row.get('finished_at')) + QUIET_SECONDS
    if now < first + MAX_HOLD_SECONDS:
        if now < due:
            return 'quiet_wait', due
        if watermark is not None and timestamp(watermark) < gap:
            return 'watermark_wait', min(now + QUIET_SECONDS, first + MAX_HOLD_SECONDS)
    previous = state.get('full_snapshot')
    if previous:
        current = content_snapshot(row)
        if previous.get('digest') == current['digest']:
            return 'unchanged', None
        if int(state.get('late_runs') or 0) >= MAX_LATE_RUNS:
            return 'late_cap', None
        if (
            current['speech_seconds'] - float(previous.get('speech_seconds') or 0) < 30
            and current['words'] - int(previous.get('words') or 0) < 80
        ):
            return 'immaterial', None
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
    return state
