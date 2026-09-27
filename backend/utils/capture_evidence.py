"""S1 capture evidence identity and coverage; no storage or network dependencies.

Positions are integers in a declared source clock. A receipt is never inferred
from wall time, transcript text, or equality of packet boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable

MAX_ENVELOPE_BYTES = 4096


class Capability(str, Enum):
    source_position = 'source_position'
    stable_artifact = 'stable_artifact'
    unknown = 'unknown'


@dataclass(frozen=True)
class Surface:
    source_id: str
    installation_epoch: str
    uploader_id: str | None = None


@dataclass(frozen=True)
class CaptureRoot:
    uid: str
    root_id: str
    surface: Surface


@dataclass(frozen=True)
class Track:
    root: CaptureRoot
    channel_id: str
    clock_epoch: str
    rate_hz: int
    clock_domain: str

    def __post_init__(self) -> None:
        if self.rate_hz <= 0:
            raise ValueError('rate_hz must be positive')


@dataclass(frozen=True, order=True)
class Span:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError('expected a nonempty half-open range')


@dataclass(frozen=True)
class EvidenceUnit:
    track: Track
    unit_id: str
    kind: str
    producer_revision: str
    source_span: Span
    payload_digest: str

    def __post_init__(self) -> None:
        if not self.unit_id or not self.producer_revision or not self.kind:
            raise ValueError('unit identity requires id, kind and producer revision')
        if len(self.payload_digest) != 64 or any(c not in '0123456789abcdef' for c in self.payload_digest):
            raise ValueError('payload digest must be lowercase SHA-256 hex')

    @property
    def identity(self) -> tuple[str, ...]:
        t = self.track
        return (
            t.root.uid,
            t.root.root_id,
            t.root.surface.source_id,
            t.root.surface.installation_epoch,
            t.channel_id,
            t.clock_epoch,
            self.unit_id,
            self.kind,
            self.producer_revision,
        )


def digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def coverage_union(spans: Iterable[Span]) -> tuple[Span, ...]:
    merged: list[Span] = []
    for span in sorted(spans):
        if merged and span.start <= merged[-1].end:
            merged[-1] = Span(merged[-1].start, max(span.end, merged[-1].end))
        else:
            merged.append(span)
    return tuple(merged)


def novel_coverage(incoming: Span, existing: Iterable[Span]) -> tuple[Span, ...]:
    remaining = [incoming]
    for covered in coverage_union(existing):
        next_remaining: list[Span] = []
        for part in remaining:
            if covered.end <= part.start or covered.start >= part.end:
                next_remaining.append(part)
                continue
            if covered.start > part.start:
                next_remaining.append(Span(part.start, covered.start))
            if covered.end < part.end:
                next_remaining.append(Span(covered.end, part.end))
        remaining = next_remaining
    return tuple(remaining)


class DeliveryVerdict(str, Enum):
    novel = 'novel'
    overlap = 'overlap'
    replay = 'replay'
    conflict = 'conflict'


def classify_delivery(
    incoming: EvidenceUnit, existing: Iterable[EvidenceUnit]
) -> tuple[DeliveryVerdict, tuple[Span, ...]]:
    """Identity handles replay/conflict; spans separately account for novel media.

    Callers must only compare units within the same track. Alternative transcript
    renditions can share a source span without being delivery duplicates.
    """
    same_track: list[EvidenceUnit] = []
    for unit in existing:
        # Transport uploader is provenance, not source identity. Compare the
        # declared track key before comparing rates or packet boundaries.
        if unit.identity[:6] != incoming.identity[:6]:
            continue
        if unit.track.rate_hz != incoming.track.rate_hz or unit.track.clock_domain != incoming.track.clock_domain:
            return DeliveryVerdict.conflict, ()
        same_track.append(unit)
        if unit.identity == incoming.identity:
            if unit.payload_digest == incoming.payload_digest and unit.source_span == incoming.source_span:
                return DeliveryVerdict.replay, ()
            return DeliveryVerdict.conflict, ()
    media = [unit.source_span for unit in same_track if unit.kind == incoming.kind == 'audio']
    novel = novel_coverage(incoming.source_span, media)
    if media and sum(s.end - s.start for s in novel) < incoming.source_span.end - incoming.source_span.start:
        return DeliveryVerdict.overlap, novel
    return DeliveryVerdict.novel, novel


def envelope(unit: EvidenceUnit, *, capability: Capability = Capability.source_position) -> dict:
    t = unit.track
    return {
        'version': 1,
        'capability': capability.value,
        'source': t.root.surface.source_id,
        'installation_epoch': t.root.surface.installation_epoch,
        'uploader': t.root.surface.uploader_id,
        'capture_root': t.root.root_id,
        'channel': t.channel_id,
        'clock_epoch': t.clock_epoch,
        'rate_hz': t.rate_hz,
        'clock_domain': t.clock_domain,
        'unit_id': unit.unit_id,
        'kind': unit.kind,
        'producer_revision': unit.producer_revision,
        'source_start': unit.source_span.start,
        'source_end': unit.source_span.end,
        'digest': unit.payload_digest,
    }


def bounded_envelope(payload: dict) -> dict:
    """Never claim complete coverage when the piggyback write exceeds S1's cap."""
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    if len(encoded) <= MAX_ENVELOPE_BYTES:
        return payload
    return {'version': 1, 'capability': 'unknown', 'coverage': 'incomplete', 'reason': 'overflow'}


def unknown_envelope(reason: str, *, origin: str) -> dict:
    if reason not in {'missing_source_position', 'untrusted_clock', 'multichannel_mix', 'compacted_lineage', 'legacy'}:
        raise ValueError('unbounded unknown reason')
    return {'version': 1, 'capability': 'unknown', 'coverage': 'unknown', 'origin': origin, 'reason': reason}
