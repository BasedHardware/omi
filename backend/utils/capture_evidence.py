"""S1 capture evidence identity and coverage; no storage or network dependencies.

Positions are integers in a declared source clock. A receipt is never inferred
from wall time, transcript text, or equality of packet boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
import uuid
from bisect import bisect_right
from typing import Iterable

from utils.committed_capture import PROOF_KIND, CommittedCaptureMap

MAX_ENVELOPE_BYTES = 4096
MAX_SOURCE_RUNS = 32


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


def parse_live_frame(payload: dict, byte_length: int) -> dict | None:
    """Validate the optional control record against its immediately following audio frame."""
    if (
        type(payload.get('version')) is not int
        or payload['version'] != 1
        or type(payload.get('byte_length')) is not int
        or payload['byte_length'] != byte_length
    ):
        return None
    try:
        root = str(uuid.UUID(payload['capture_root']))
        epoch = payload['clock_epoch']
        ordinal = payload['source_frame']
        if type(epoch) is not int or type(ordinal) is not int or epoch < 0 or ordinal < 0:
            return None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    return {'capture_root': root, 'clock_epoch': epoch, 'source_frame': ordinal}


class SourcePositionMap:
    """Bounded source-frame to decoded-sample runs for one authenticated listen socket."""

    def __init__(self, *, committed: bool = False) -> None:
        self.runs: list[dict] = []
        self.incomplete = False
        self.conflicts = 0
        self._unit_digests: dict[tuple, str] = {}
        self._committed: CommittedCaptureMap | None = CommittedCaptureMap() if committed else None

    def accept(
        self,
        claim: dict | None,
        *,
        sample_start: int,
        sample_count: int,
        rate_hz: int,
        payload: bytes,
        receipt_wall_time: float | None = None,
    ) -> None:
        if self._committed is not None:
            self._committed.accept(
                claim,
                sample_start=sample_start,
                sample_count=sample_count,
                rate_hz=rate_hz,
                receipt_wall_time=receipt_wall_time,
            )
        if claim is None or sample_count <= 0 or rate_hz <= 0:
            self.incomplete = True
            return
        identity = (claim['capture_root'], claim['clock_epoch'], claim['source_frame'])
        unit_digest = digest(payload)
        prior_digest = self._unit_digests.get(identity)
        if prior_digest is not None:
            # A repeated unit with changed bytes is never silently accepted.
            if prior_digest != unit_digest:
                self.incomplete = True
                self.conflicts += 1
        else:
            self._unit_digests[identity] = unit_digest
            if len(self._unit_digests) > 512:
                self._unit_digests.pop(next(iter(self._unit_digests)))
                self.incomplete = True
        run = {
            'capture_root': identity[0],
            'clock_epoch': identity[1],
            'source_frame_start': identity[2],
            'source_frame_end': identity[2] + 1,
            'decoded_sample_start': sample_start,
            'decoded_sample_end': sample_start + sample_count,
            'samples_per_frame': sample_count,
            'rate_hz': rate_hz,
            'channel': 'mono',
            'replay': prior_digest is not None,
        }
        if self.runs:
            tail = self.runs[-1]
            if (
                tail['capture_root'] == run['capture_root']
                and tail['clock_epoch'] == run['clock_epoch']
                and tail['source_frame_end'] == run['source_frame_start']
                and tail['decoded_sample_end'] == sample_start
                and tail['replay'] == run['replay']
                and tail['samples_per_frame'] == sample_count
                and tail['rate_hz'] == rate_hz
            ):
                tail['source_frame_end'] += 1
                tail['decoded_sample_end'] += sample_count
                return
        self.runs.append(run)
        if len(self.runs) > MAX_SOURCE_RUNS:
            self.runs.pop(0)
            self.incomplete = True

    def snapshot(self, sample_ranges: Iterable[tuple[int, int]] | None = None) -> dict:
        ranges = list(sample_ranges) if sample_ranges is not None else None
        selected: list[dict] = []
        partial = self.incomplete
        for run in self.runs:
            for start, end in (
                ranges if ranges is not None else [(run['decoded_sample_start'], run['decoded_sample_end'])]
            ):
                low = max(start, run['decoded_sample_start'])
                high = min(end, run['decoded_sample_end'])
                if high <= low:
                    continue
                stride = run['samples_per_frame']
                if (low - run['decoded_sample_start']) % stride or (high - run['decoded_sample_start']) % stride:
                    partial = True
                    continue
                first = (low - run['decoded_sample_start']) // stride
                last = (high - run['decoded_sample_start']) // stride
                selected.append(
                    {
                        **run,
                        'source_frame_start': run['source_frame_start'] + first,
                        'source_frame_end': run['source_frame_start'] + last,
                        'decoded_sample_start': low,
                        'decoded_sample_end': high,
                    }
                )
        if not selected:
            return unknown_envelope('missing_source_position', origin='live')
        result = {
            'version': 1,
            'capability': 'source_position',
            'coverage': 'incomplete' if partial else 'mapped',
            'origin': 'live',
            'conflicts': self.conflicts,
            'runs': selected,
        }
        return bounded_envelope(result)

    def remember_transcripts(self, segments: Iterable[dict]) -> None:
        if self._committed is not None:
            self._committed.remember_transcripts(segments)

    def committed_snapshot(self, conversation_id: str, segments: Iterable) -> dict | None:
        if self._committed is None or self.conflicts:
            return None
        snapshot = self._committed.committed_snapshot(conversation_id, segments)
        if snapshot is None:
            return None
        result = bounded_envelope(snapshot)
        return result if result.get('proof') == PROOF_KIND else None

    def acknowledge(self, conversation_id: str, snapshot: dict | None) -> None:
        if self._committed is not None:
            self._committed.acknowledge(conversation_id, snapshot)


def parse_sync_file_claims(value: str | None, filenames: Iterable[str]) -> dict[str, dict]:
    """Validate a bounded, versioned upload header; absent/invalid claims abstain."""
    if not value or len(value.encode()) > MAX_ENVELOPE_BYTES:
        return {}
    try:
        parsed = json.loads(value)
        if (
            type(parsed.get('version')) is not int
            or parsed['version'] != 1
            or not isinstance(parsed.get('files'), list)
        ):
            return {}
        allowed = set(filenames)
        if len(parsed['files']) > 20:
            return {}
        result = {}
        for item in parsed['files']:
            name = item['name']
            root = str(uuid.UUID(item['capture_root']))
            epoch, start, count, rate = (
                item[key] for key in ('clock_epoch', 'source_frame_start', 'frame_count', 'rate_hz')
            )
            codec = item['codec']
            if (
                name not in allowed
                or name in result
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', name)
                or any(type(n) is not int or n < 0 for n in (epoch, start, count, rate))
                or count == 0
                or rate == 0
                or codec not in {'pcm16', 'opus'}
                or item.get('channel') != 'mono'
            ):
                return {}
            result[name] = {
                'capture_root': root,
                'clock_epoch': epoch,
                'source_frame_start': start,
                'frame_count': count,
                'rate_hz': rate,
                'codec': codec,
                'channel': 'mono',
            }
        return result if len(result) == len(allowed) else {}
    except (ValueError, TypeError, KeyError, AttributeError):
        return {}


def decoded_frame_map(claim: dict, frame_samples: list[int], *, wav_rate_hz: int, wav_channels: int) -> dict | None:
    """Anchor decoded WAV samples to original frame ordinals, including a truncated prefix."""
    if (
        wav_rate_hz != claim['rate_hz']
        or wav_channels != 1
        or not frame_samples
        or len(frame_samples) > claim['frame_count']
        or any(n <= 0 for n in frame_samples)
    ):
        return None
    offsets = [0]
    for count in frame_samples:
        offsets.append(offsets[-1] + count)
    return {'claim': claim, 'offsets': offsets, 'incomplete': len(frame_samples) != claim['frame_count']}


def source_coordinate(frame_map: dict, sample: int) -> tuple[int, int] | None:
    offsets = frame_map['offsets']
    if sample < 0 or sample > offsets[-1]:
        return None
    if sample == offsets[-1]:
        return frame_map['claim']['source_frame_start'] + len(offsets) - 1, 0
    index = bisect_right(offsets, sample) - 1
    return frame_map['claim']['source_frame_start'] + index, sample - offsets[index]


def sync_segment_receipt(
    frame_map: dict, *, wav_sample_start: int, wav_sample_end: int, segment_id: str
) -> dict | None:
    """Map a derivative STT span back through VAD and decode to WAL frame offsets."""
    start = source_coordinate(frame_map, wav_sample_start)
    end = source_coordinate(frame_map, wav_sample_end)
    if start is None or end is None or end <= start:
        return None
    claim = frame_map['claim']
    return {
        'segment_id': segment_id,
        'capture_root': claim['capture_root'],
        'clock_epoch': claim['clock_epoch'],
        'channel': 'mono',
        'source_start_frame': start[0],
        'source_start_offset': start[1],
        'source_end_frame': end[0],
        'source_end_offset': end[1],
        'rate_hz': claim['rate_hz'],
        'producer_revision': 'sync_vad_stt_v1',
    }


def merge_track_receipts(existing: Iterable[object], incoming: Iterable[object]) -> dict:
    """Keep each contributor once; overflow is an explicit incomplete receipt."""
    receipts: dict[tuple, dict] = {}
    for receipt in [*existing, *incoming]:
        if not isinstance(receipt, dict):
            continue
        key = (receipt.get('segment_id'), receipt.get('capture_root'), receipt.get('clock_epoch'))
        if key in receipts and receipts[key] != receipt:
            return unknown_envelope('missing_source_position', origin='sync_conflict')
        receipts[key] = receipt
    kept: list[dict] = []
    coverage = 'mapped'
    for receipt in receipts.values():
        candidate = {
            'version': 1,
            'capability': 'source_position',
            'coverage': coverage,
            'origin': 'sync_vad',
            'receipts': [*kept, receipt],
        }
        if len(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()) > MAX_ENVELOPE_BYTES:
            coverage = 'incomplete'
            break
        kept.append(receipt)
    return (
        {'version': 1, 'capability': 'source_position', 'coverage': coverage, 'origin': 'sync_vad', 'receipts': kept}
        if kept
        else unknown_envelope('missing_source_position', origin='sync_overflow')
    )
