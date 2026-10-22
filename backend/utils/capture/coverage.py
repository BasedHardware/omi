"""Committed source-frame coverage authority; admission never reserves audio.

Only durable conversation writes may call record. Concurrent uncommitted
transcriptions are still fenced/deduplicated by the assignment transaction.
"""

from __future__ import annotations

from utils.observability.reasons import ReasonFamily, reason_label, CaptureCoverageOutcome

from config import refactor_modes
from database import capture_coverage as store
from models.capture_coverage import AdmitResult, CaptureKey, CoverageOrigin, CoverageRecord, FrameRange
from utils.capture_evidence import Span, coverage_union, novel_coverage
from utils.capture.coverage_metrics import ADMIT

FLAG = 'CAPTURE_COVERAGE_MODE'
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
    if not refactor_modes.shadow_or_serve(FLAG):
        return AdmitResult(uncovered=_ranges(incoming))
    return decide(ranges, store.read(uid, key))


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
    if refactor_modes.shadow_or_serve(FLAG):
        normalized(rec.ranges)
        store.record(uid, key, rec)
