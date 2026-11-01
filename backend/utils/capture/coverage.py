"""Committed source-frame coverage authority; admission never reserves audio.

Only durable conversation writes may call record. Concurrent uncommitted
transcriptions are still fenced/deduplicated by the assignment transaction.
"""

from __future__ import annotations

from utils.observability.reasons import ReasonFamily, reason_label, CaptureCoverageOutcome

from config import refactor_modes
from database import capture_coverage as store
from models.capture_coverage import (
    AdmitResult,
    CaptureKey,
    CoverageOrigin,
    CoverageRecord,
    FrameRange,
    CaptureCommittedEvent,
)
from utils.capture_evidence import Span, coverage_union, novel_coverage
from utils.capture.coverage_metrics import ADMIT

FLAG = 'CAPTURE_COVERAGE_MODE'
# Shadow measures on a uid sample; the serve cohort always keeps a complete ledger.
SHADOW_SAMPLE_PERCENT = 5.0
MAX_QUERY_RANGES = 32
MAX_QUERY_FRAMES = 360_000


def normalized(ranges: list[FrameRange]) -> tuple[Span, ...]:
    if len(ranges) > MAX_QUERY_RANGES:
        raise ValueError('too many capture coverage ranges')
    spans = coverage_union(Span(r.start, r.end) for r in ranges)
    if sum(s.end - s.start for s in spans) > MAX_QUERY_FRAMES:
        raise ValueError('capture coverage range exceeds frame bound')
    return spans


def _ranges(spans) -> list[FrameRange]:
    return [FrameRange(start=s.start, end=s.end) for s in spans]


def decide(ranges: list[FrameRange], records: list[CoverageRecord]) -> AdmitResult:
    incoming = normalized(ranges)
    committed = coverage_union(Span(r.start, r.end) for rec in records for r in rec.ranges)
    uncovered = coverage_union(part for span in incoming for part in novel_coverage(span, committed))
    covered = coverage_union(part for span in incoming for part in novel_coverage(span, uncovered))
    owners = {
        rec.conversation_id
        for rec in records
        if any(max(r.start, s.start) < min(r.end, s.end) for r in rec.ranges for s in incoming)
    }
    return AdmitResult(
        uncovered=_ranges(uncovered),
        covered=_ranges(covered),
        basis='frames',
        covering_conversation_id=next(iter(owners)) if len(owners) == 1 else None,
    )


def query(uid: str, key: CaptureKey, ranges: list[FrameRange]) -> AdmitResult:
    incoming = normalized(ranges)
    store.key_payload(key)
    if not refactor_modes.shadow_sampled(FLAG, uid, SHADOW_SAMPLE_PERCENT):
        return AdmitResult(uncovered=_ranges(incoming))
    records = store.read(uid, key)
    if refactor_modes.serving_for(FLAG, uid):
        shared = store.read_shared(uid, key)
        if shared:
            # The same secondary already has its own durable receipt. Replace
            # only the proven shared interiors so the answer names the primary.
            aliases = coverage_union(Span(r.start, r.end) for rec in shared for r in rec.ranges)
            records = [
                rec.model_copy(
                    update={
                        'ranges': _ranges(
                            coverage_union(
                                part for r in rec.ranges for part in novel_coverage(Span(r.start, r.end), aliases)
                            )
                        )
                    }
                )
                for rec in records
            ]
            records.extend(shared)
    return decide(ranges, records)


def admit(uid: str, key: CaptureKey, ranges: list[FrameRange], *, origin: CoverageOrigin) -> AdmitResult:
    result = query(uid, key, ranges)
    outcome = 'covered' if result.covered and not result.uncovered else 'partial' if result.covered else 'uncovered'
    ADMIT.labels(
        origin=origin,
        basis=result.basis,
        outcome=reason_label(ReasonFamily.HELD_CONTENT, outcome, CaptureCoverageOutcome),
    ).inc()
    return result


def record(uid: str, key: CaptureKey, rec: CoverageRecord) -> None:
    if refactor_modes.shadow_sampled(FLAG, uid, SHADOW_SAMPLE_PERCENT):
        normalized(rec.ranges)
        store.record(uid, key, rec)


def committed_events(uid: str, key: CaptureKey, ranges: list[FrameRange]) -> list[CaptureCommittedEvent]:
    """Custody receipts for exact secondary frames, naming the confirmed primary.

    Consumers emit these only after a durable reconciliation, never on wall
    overlap or an uncommitted candidate. No receipt escapes shadow or off.
    """
    if not refactor_modes.serving_for(FLAG, uid):
        return []
    result = query(uid, key, ranges)
    if not result.covering_conversation_id:
        return []
    return [
        CaptureCommittedEvent(
            conversation_id=result.covering_conversation_id,
            capture_root=key.capture_root,
            channel=key.channel,
            clock_epoch=key.clock_epoch,
            recording_session_id=key.recording_session_id,
            source_start=r.start,
            source_end=r.end,
        )
        for r in result.covered
    ]
