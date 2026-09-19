"""Non-destructive cross-source overlap hints at durable finalization (#3244).

Overlap is evidence of a possible shared meeting, not proof of identical speech.
Keep both transcripts, discard state, and derived work independent. Longer wall
windows are primary; equal windows use the document ID for stable ordering.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from database import conversations as conversations_db
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
MIN_OVERLAP_SECONDS = 60.0
MIN_WINDOW_COVERAGE = 0.5
CANDIDATE_PAGE_LIMIT = 100


@dataclass(frozen=True)
class CaptureRecord:
    conversation_id: str
    started_at: datetime
    finished_at: datetime
    source: str

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def primary_rank(self) -> tuple[float, str]:
        return (-self.duration_seconds, self.conversation_id)


def capture_record(record: Any) -> CaptureRecord | None:
    def field(name):
        return record.get(name) if isinstance(record, Mapping) else getattr(record, name, None)

    if field('discarded') or field('status') != 'completed':
        return None
    start, finish = field('started_at'), field('finished_at')
    if not isinstance(start, datetime) or not isinstance(finish, datetime):
        return None
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    finish = finish if finish.tzinfo else finish.replace(tzinfo=timezone.utc)
    source = getattr(field('source'), 'value', field('source'))
    if finish <= start or not source or not field('id'):
        return None
    return CaptureRecord(str(field('id')), start, finish, str(source))


def overlap_match(a: CaptureRecord, b: CaptureRecord, *, seconds: float, ratio: float) -> dict | None:
    if a.conversation_id == b.conversation_id or a.source == b.source:
        return None
    overlap = (min(a.finished_at, b.finished_at) - max(a.started_at, b.started_at)).total_seconds()
    coverage = overlap / min(a.duration_seconds, b.duration_seconds)
    if overlap <= seconds or coverage <= ratio:
        return None
    return {'method': 'wall_clock_overlap', 'overlap_seconds': overlap, 'overlap_ratio': coverage}


def _threshold(name: str, default: float, maximum: float = math.inf) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError('invalid overlap threshold')
    return value


def link_duplicate_captures(uid: str, conversation: Any) -> None:
    """Link a completed pair regardless of which device finalized last.

    The existing bounded status/finished_at query needs no new Firestore index.
    The transaction rechecks both snapshots, including discard, before writing.
    A failed optional hint must not prevent the original capture from completing.
    """
    candidate = capture_record(conversation)
    if candidate is None:
        return
    try:
        seconds = _threshold('CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS', MIN_OVERLAP_SECONDS)
        ratio = _threshold('CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO', MIN_WINDOW_COVERAGE, 1.0)
        rows = conversations_db.get_conversations_finished_after(
            uid, status='completed', finished_after=candidate.started_at, limit=CANDIDATE_PAGE_LIMIT
        )
        if len(rows) == CANDIDATE_PAGE_LIMIT:
            _record_degraded()
        # Largest windows first, so a secondary with several matches gets the
        # most complete observed capture. Existing pointers are idempotent.
        others = sorted(filter(None, map(capture_record, rows)), key=lambda row: row.primary_rank)
        for other in others:
            match = overlap_match(candidate, other, seconds=seconds, ratio=ratio)
            if match is None:
                continue
            primary, secondary = sorted((candidate, other), key=lambda row: row.primary_rank)
            if conversations_db.link_duplicate_capture(uid, primary, secondary, match):
                logger.info(
                    'cross_device_duplicate_detected overlap_seconds=%.1f overlap_ratio=%.3f',
                    match['overlap_seconds'],
                    match['overlap_ratio'],
                )
    except Exception:
        # Exception strings can carry request data; keep telemetry content-free.
        _record_degraded()


def _record_degraded() -> None:
    record_fallback(
        component='conversation_finalization',
        from_mode='duplicate_capture_check',
        to_mode='keep_both_captures',
        reason='other',
        outcome='degraded',
        log=logger,
    )
