"""Non-destructive cross-source overlap hints and capture groups at finalization (#3244).

Overlap is evidence of a possible shared meeting, not proof of identical speech.
Keep both transcripts, discard state, and derived work independent. Longer wall
windows are primary; equal windows use the document ID for stable ordering.

A window match is only a proposal. When both captures also share speech
(``shared_speech``), they join one capture group (``database.capture_groups``),
which records their shared event identity. Grouping is metadata only.
The default-off desktop-call path accepts complementary speech under its
meeting-role and window contract, and pins the desktop primary.
"""

from __future__ import annotations

import logging
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from config.capture_shared_speech import shared_speech_mode
from config.refactor_modes import serving_for
from utils.capture.coverage_crossdevice import reconcile as reconcile_cross_device
from utils.conversations.lifecycle_clocks import speech_clock, utc
from database import capture_groups as capture_groups_db
from database import conversations as conversations_db
from database.capture_speech import get_shared_speech_snapshot
from utils.conversations.capture_containment import (
    capture_group_containment_mode,
    measure_capture_containment,
    record_capture_containment,
)
from utils.conversations.shared_speech import measure_shared_speech
from utils.conversations.overlap_shared_speech import (
    measure_overlap_shared_speech,
    pair_category,
    shared_speech_group_guard,
    VERSION,
)
from utils.observability.fallback import record_fallback
from utils.product_metrics import record_product_event

logger = logging.getLogger(__name__)
MIN_OVERLAP_SECONDS = 60.0
MIN_WINDOW_COVERAGE = 0.5
CANDIDATE_PAGE_LIMIT = 100
# Each confirmation re-reads one decrypted transcript; bound the work per finalization.
MAX_CONTENT_CHECKS = 6
MAX_SHARED_SPEECH_CHECKS = 12


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


def capture_record(record: Any, uid: str | None = None) -> CaptureRecord | None:
    def field(name):
        return record.get(name) if isinstance(record, Mapping) else getattr(record, name, None)

    if field('discarded') or field('status') != 'completed':
        return None
    normalize = uid is not None and serving_for('LIFECYCLE_V2_MODE', uid)
    start = utc(field('started_at')) if normalize else field('started_at')
    finish = (
        speech_clock(uid, {'finished_at': field('finished_at'), 'last_speech_at': field('last_speech_at')})
        if normalize and uid is not None
        else field('finished_at')
    )
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
    candidate = capture_record(conversation, uid)
    if candidate is None:
        return
    speech_mode = shared_speech_mode(uid)
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
        others = sorted(filter(None, map(lambda row: capture_record(row, uid), rows)), key=lambda row: row.primary_rank)
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
    if reconcile_cross_device(
        uid,
        candidate.conversation_id,
        [
            other.conversation_id
            for other in others
            if other.conversation_id != candidate.conversation_id
            and min(candidate.finished_at, other.finished_at) > max(candidate.started_at, other.started_at)
        ],
    ):
        return
    # refactor: superseded by utils.capture.coverage_crossdevice when CAPTURE_COVERAGE_MODE=serve
    if speech_mode != 'on':
        _group_confirmed_captures(uid, conversation, candidate, matches[:MAX_CONTENT_CHECKS])
    if speech_mode != 'off':
        overlapping = [
            other
            for other in others
            if other.conversation_id != candidate.conversation_id
            and min(candidate.finished_at, other.finished_at) > max(candidate.started_at, other.started_at)
        ]
        _group_with_overlap_speech(
            uid,
            candidate,
            overlapping[:MAX_CONTENT_CHECKS],
            mode=speech_mode,
            legacy_ids={other.conversation_id for other in matches[:MAX_CONTENT_CHECKS]},
        )


def _segments_of(record: Any):
    return (
        record.get('transcript_segments')
        if isinstance(record, Mapping)
        else getattr(record, 'transcript_segments', None)
    )


def _group_with_overlap_speech(
    uid: str, candidate: CaptureRecord, matches: list[CaptureRecord], *, mode: str, legacy_ids: set[str]
) -> None:
    """Observe or apply bounded same-sentence decisions through the fenced writer.

    Shadow adds at most seven decrypted reads, no new writes. On replaces all
    automatic grouping policies for the cohort and keeps existing groups intact.
    """
    if not matches:
        return
    snapshots = {}

    def load(cid):
        if cid not in snapshots:
            if len(snapshots) >= MAX_CONTENT_CHECKS + 1:
                return None, None
            snapshots[cid] = get_shared_speech_snapshot(uid, cid)
        return snapshots[cid]

    remaining_checks = MAX_SHARED_SPEECH_CHECKS

    def confirms(first, second):
        nonlocal remaining_checks
        if remaining_checks <= 0:
            return None
        remaining_checks -= 1
        return measure_overlap_shared_speech(first, second)

    try:
        own, own_fingerprint = load(candidate.conversation_id)
    except Exception:
        _record_degraded(to_mode='separate_captures')
        return
    for other in matches:
        try:
            row, fingerprint = load(other.conversation_id)
            if not row:
                break  # exhausted read budget or absent snapshot; never infer a fold
            started = time.perf_counter()
            decision = confirms(own, row)
            if decision is None:
                break
            elapsed_ms = (time.perf_counter() - started) * 1000
            incumbent = False
            if other.conversation_id in legacy_ids:
                if any(
                    record.get('has_transcript_corrections')
                    or record.get('transcript_correction_overlay') is not None
                    or record.get('_shared_speech_rejection')
                    for record in (own or {}, row)
                ):
                    incumbent = None  # no mutable overlay reads to simulate the incumbent
                else:
                    incumbent = measure_shared_speech(_segments_of(own), _segments_of(row)).confirms()
                    if not incumbent and capture_group_containment_mode() == 'on':
                        containment = measure_capture_containment(own, row, mode='on')
                        incumbent = containment.would_join and containment.basis == 'full'
            own_group = (own or {}).get('capture_group') or {}
            other_group = (row or {}).get('capture_group') or {}
            already_grouped = bool(own_group.get('id') and own_group.get('id') == other_group.get('id'))
            windows = {r.conversation_id: (r.started_at, r.finished_at) for r in (candidate, other)}
            fingerprints = {candidate.conversation_id: own_fingerprint, other.conversation_id: fingerprint}
            existing = own_group if own_group.get('id') else other_group
            expected_revision = int(existing.get('revision') or 0)
            would_join, reason = decision.would_join, decision.reason
            if would_join and not already_grouped:
                # Shared speech is not transitive: a long A containing scenes B
                # and C must not fold B and C through A. Confirm the new entrant
                # against every existing member, within the same read/CPU budget.
                if own_group.get('id') and other_group.get('id'):
                    would_join, reason = False, 'different_groups'
                else:
                    entrant = row if own_group.get('id') else own
                    for member in existing.get('members') or []:
                        cid = member['id']
                        if cid in fingerprints:
                            continue
                        member_row, member_fingerprint = load(cid)
                        record = capture_record(member_row, uid)
                        if record is None:
                            would_join, reason = False, 'group_unconfirmed'
                            break
                        confirmation = confirms(entrant, member_row)
                        if confirmation is None or not confirmation.would_join:
                            would_join, reason = False, 'group_unconfirmed'
                            break
                        windows[cid] = (record.started_at, record.finished_at)
                        fingerprints[cid] = member_fingerprint
            outcome = 'shadow' if mode == 'shadow' else 'none'
            if mode == 'on' and would_join:
                group_id = capture_groups_db.join_capture_group(
                    uid,
                    candidate.conversation_id,
                    other.conversation_id,
                    decision.evidence(),
                    expected_windows=windows,
                    expected_fingerprints=fingerprints,
                    expected_group_revision=expected_revision,
                    join_guard=shared_speech_group_guard,
                )
                outcome = 'applied' if group_id else 'conflict'
                record_product_event('capture_group_joined', outcome=outcome)
            logger.info(
                'capture_shared_speech %s',
                json.dumps(
                    {
                        'event': 'capture_shared_speech',
                        'version': VERSION,
                        'mode': mode,
                        'uid': uid,
                        'first_id': candidate.conversation_id,
                        'second_id': other.conversation_id,
                        'category': pair_category(own, row),
                        'current_would_join': incumbent,
                        'already_grouped': already_grouped,
                        'would_join': would_join,
                        'reason': reason,
                        'pair_would_join': decision.would_join,
                        'outcome': outcome,
                        'matcher_ms': round(elapsed_ms, 3),
                        **decision.evidence(),
                    },
                    sort_keys=True,
                    separators=(',', ':'),
                ),
            )
        except Exception:
            logger.warning('event=capture_shared_speech outcome=error')
            _record_degraded(to_mode='separate_captures')


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
                    record_capture_containment(containment, mode=containment_mode)
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
