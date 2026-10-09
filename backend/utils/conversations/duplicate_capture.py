"""Non-destructive cross-source overlap hints and capture groups at finalization (#3244).

Overlap is evidence of a possible shared meeting, not proof of identical speech.
Keep both transcripts, discard state, and derived work independent. Longer wall
windows are primary; equal windows use the document ID for stable ordering.

A window match is only a proposal. When both captures also share speech
(``shared_speech``), they join one capture group (``database.capture_groups``),
which clients present as one event. Grouping is metadata only.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from database import capture_groups as capture_groups_db
from database import conversations as conversations_db
from utils.conversations.capture_containment import (
    capture_group_containment_mode,
    measure_capture_containment,
    record_capture_containment,
)
from utils.conversations.shared_speech import measure_shared_speech
from utils.conversations.capture_jev_shadow import submit_resummary, submit_same_scene
from utils.observability.fallback import record_fallback
from utils.product_metrics import record_product_event

logger = logging.getLogger(__name__)
MIN_OVERLAP_SECONDS = 60.0
MIN_WINDOW_COVERAGE = 0.5
CANDIDATE_PAGE_LIMIT = 100
# Each confirmation re-reads one decrypted transcript; bound the work per finalization.
MAX_CONTENT_CHECKS = 6


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
        matches = []
        for other in others:
            match = overlap_match(candidate, other, seconds=seconds, ratio=ratio)
            if match is None:
                continue
            matches.append(other)
            primary, secondary = sorted((candidate, other), key=lambda row: row.primary_rank)
            if conversations_db.link_duplicate_capture(uid, primary, secondary, match):
                record_product_event('duplicate_capture_detected')
                logger.info(
                    'cross_device_duplicate_detected overlap_seconds=%.1f overlap_ratio=%.3f',
                    match['overlap_seconds'],
                    match['overlap_ratio'],
                )
    except Exception:
        # Exception strings can carry request data; keep telemetry content-free.
        _record_degraded()
        return
    _group_confirmed_captures(uid, conversation, candidate, matches[:MAX_CONTENT_CHECKS])
    # The shadow sees overlapping candidates even when source, window threshold,
    # or content threshold kept the shipped rule from grouping them.
    shadow_candidates = 0
    for other in others:
        if other.conversation_id == candidate.conversation_id:
            continue
        overlap = (
            min(candidate.finished_at, other.finished_at) - max(candidate.started_at, other.started_at)
        ).total_seconds()
        if overlap > 0:
            submit_same_scene(uid, candidate.conversation_id, other.conversation_id)
            shadow_candidates += 1
            if shadow_candidates >= MAX_CONTENT_CHECKS:
                break


def _segments_of(record: Any):
    return (
        record.get('transcript_segments')
        if isinstance(record, Mapping)
        else getattr(record, 'transcript_segments', None)
    )


def _group_confirmed_captures(uid: str, conversation: Any, candidate: CaptureRecord, matches: list) -> None:
    """Group window matches that also share speech; never block finalization.

    Both transcripts are re-read fresh (the in-memory conversation may predate a
    later edit) together with a fingerprint the join transaction re-checks.
    """
    if not matches:
        return
    try:
        own_row, own_fingerprint = conversations_db.get_conversation_for_capture_check(uid, candidate.conversation_id)
    except Exception:
        _record_degraded(to_mode='separate_captures')
        return
    own_segments = _segments_of(own_row or {})
    containment_mode = capture_group_containment_mode()
    for other in matches:
        try:
            other_row, other_fingerprint = conversations_db.get_conversation_for_capture_check(
                uid, other.conversation_id
            )
            shared = measure_shared_speech(own_segments, _segments_of(other_row or {}))
            containment = None
            if containment_mode != 'off':
                try:
                    containment = measure_capture_containment(own_row or {}, other_row or {}, mode=containment_mode)
                    record_capture_containment(containment, mode=containment_mode, phase='rule')
                except Exception:
                    logger.warning('capture_group_containment detector failed')
                    _record_degraded(to_mode='separate_captures')
                    containment = None
            if shared.confirms():
                evidence = shared.evidence()
            elif (
                containment_mode == 'on'
                and containment is not None
                and containment.would_join
                and containment.basis == 'full'
            ):
                evidence = containment.evidence()
            else:
                record_product_event('capture_group_joined', outcome='none')
                continue
            group_id = capture_groups_db.join_capture_group(
                uid,
                candidate.conversation_id,
                other.conversation_id,
                evidence,
                expected_windows={
                    record.conversation_id: (record.started_at, record.finished_at) for record in (candidate, other)
                },
                expected_fingerprints={
                    candidate.conversation_id: own_fingerprint,
                    other.conversation_id: other_fingerprint,
                },
            )
            record_product_event('capture_group_joined', outcome='applied' if group_id else 'conflict')
            own_group = (
                own_row.get('capture_group')
                if isinstance(own_row, Mapping)
                else getattr(own_row, 'capture_group', None)
            ) or {}
            other_group = (
                other_row.get('capture_group')
                if isinstance(other_row, Mapping)
                else getattr(other_row, 'capture_group', None)
            ) or {}
            if group_id and own_group.get('id') != other_group.get('id'):
                if own_group.get('id') == group_id:
                    submit_resummary(
                        uid, own_group.get('primary_id') or candidate.conversation_id, other.conversation_id
                    )
                elif other_group.get('id') == group_id:
                    submit_resummary(
                        uid, other_group.get('primary_id') or other.conversation_id, candidate.conversation_id
                    )
            if group_id and isinstance(own_row, dict):
                primary = min((candidate, other), key=lambda row: row.primary_rank)
                own_row['capture_group'] = {'id': group_id, 'primary_id': primary.conversation_id}
            logger.info(
                'capture_group_join outcome=%s containment=%.3f shared_trigrams=%d',
                'applied' if group_id else 'conflict',
                shared.containment,
                shared.shared_trigrams,
            )
        except Exception:
            _record_degraded(to_mode='separate_captures')


def _record_degraded(to_mode: str = 'keep_both_captures') -> None:
    record_fallback(
        component='conversation_finalization',
        from_mode='duplicate_capture_check',
        to_mode=to_mode,
        reason='other',
        outcome='degraded',
        log=logger,
    )
