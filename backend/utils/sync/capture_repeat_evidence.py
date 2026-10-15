"""Independent capture-proof helper for lexical WAL repeat drops.

A lexical repeat drop additionally requires full source-frame coverage proof:
each incoming sync segment's own ``sync_vad`` receipt must uniquely identify a
nonempty half-open frame span, and the canonical live row's ``origin=live`` S1
snapshot must positively prove every touched frame for the same capture root,
clock epoch, mono channel and rate. Missing, malformed, conflicting, partial or
mismatched evidence yields no proof; the segment is simply a normal candidate.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping
from typing import Any

from utils.sync.audio_coverage import validated_live_ranges

MAX_INCOMING_SEGMENTS = 64
MAX_RECEIPTS = 64


def _is_int(value: object) -> bool:
    return type(value) is int


def _valid_capture_root(root: object) -> bool:
    if not isinstance(root, str):
        return False
    try:
        uuid.UUID(root)
    except (ValueError, AttributeError):
        return False
    return True


def _incoming_receipts(envelope: Any) -> list | None:
    """Return the bounded receipt list of a well-formed sync_vad envelope."""
    if not isinstance(envelope, Mapping):
        return None
    if not _is_int(envelope.get('version')) or envelope['version'] != 1:
        return None
    if envelope.get('capability') != 'source_position' or envelope.get('origin') != 'sync_vad':
        return None
    if envelope.get('coverage') not in ('mapped', 'incomplete'):
        return None
    receipts = envelope.get('receipts')
    if not isinstance(receipts, list) or len(receipts) > MAX_RECEIPTS:
        return None
    return receipts


def _receipt_span(receipt: Any) -> tuple[dict, int, int, int] | None:
    """(claim, start_frame, end_frame_exclusive, end_offset) or None.

    The touched source-frame domain is ``[source_start_frame, source_end_frame +
    (source_end_offset > 0))``: a zero end offset is an exclusive boundary, any
    positive end offset touches one more frame.
    """
    if not isinstance(receipt, Mapping):
        return None
    if not _valid_capture_root(receipt.get('capture_root')):
        return None
    epoch: Any = receipt.get('clock_epoch')
    start_frame: Any = receipt.get('source_start_frame')
    end_frame: Any = receipt.get('source_end_frame')
    start_offset: Any = receipt.get('source_start_offset')
    end_offset: Any = receipt.get('source_end_offset')
    rate: Any = receipt.get('rate_hz')
    if not all(_is_int(v) for v in (epoch, start_frame, end_frame, start_offset, end_offset, rate)):
        return None
    if epoch < 0 or rate <= 0 or start_frame < 0 or end_frame < start_frame:
        return None
    if end_frame == start_frame and end_offset <= start_offset:
        return None
    if start_offset < 0 or end_offset < 0:
        return None
    if receipt.get('channel') != 'mono':
        return None
    end_exclusive = end_frame + (1 if end_offset > 0 else 0)
    claim = {
        'capture_root': receipt['capture_root'],
        'clock_epoch': epoch,
        'source_frame_start': start_frame,
        'frame_count': end_exclusive - start_frame,
        'rate_hz': rate,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    return claim, start_frame, end_exclusive, end_offset


def _run_covers(run: Any, claim: Mapping, frame: int) -> int | None:
    """Return the matching positive run's samples_per_frame, else None."""
    if not isinstance(run, Mapping):
        return None
    if run.get('capture_root') != claim['capture_root'] or run.get('clock_epoch') != claim['clock_epoch']:
        return None
    if run.get('channel') != 'mono' or run.get('rate_hz') != claim['rate_hz']:
        return None
    first: Any = run.get('source_frame_start')
    last: Any = run.get('source_frame_end')
    spf: Any = run.get('samples_per_frame')
    if not all(_is_int(v) for v in (first, last, spf)) or spf <= 0:
        return None
    if first <= frame < last:
        return spf
    return None


def _offsets_fit(receipt: Mapping, live_evidence: Any, claim: Mapping, end_frame: int, end_offset: int) -> bool:
    """Start/end receipt offsets must fit the corresponding positive run's frame size."""
    runs = live_evidence.get('runs') if isinstance(live_evidence, Mapping) else None
    if not isinstance(runs, list):
        return False
    start_spf = None
    end_spf = None
    for run in runs:
        if start_spf is None:
            start_spf = _run_covers(run, claim, receipt['source_start_frame'])
        if end_offset > 0 and end_spf is None:
            end_spf = _run_covers(run, claim, end_frame)
    if start_spf is None or not (0 <= receipt['source_start_offset'] < start_spf):
        return False
    if end_offset > 0 and (end_spf is None or end_offset > end_spf):
        return False
    return True


def _fully_covered(ranges: tuple[tuple[int, int], ...], start: int, end: int) -> bool:
    """The merged positive union must cover [start, end) contiguously."""
    cursor = start
    for low, high in ranges:
        if low > cursor:
            return False
        cursor = max(cursor, high)
        if cursor >= end:
            return True
    return False


def capture_covered_indices(
    incoming_segments: list[dict], incoming_evidence: object, live_evidence: object
) -> frozenset[int]:
    """Indices of incoming segments with independently proven full frame capture.

    A segment index is returned only when its nonempty ``id`` uniquely matches
    one well-formed ``sync_vad`` receipt, the id is unique across this intake,
    and the live envelope's validated positive ranges cover every frame that
    receipt touches. Anything else — absent receipts, id collisions, malformed
    matching evidence, conflicting live runs, partial coverage — leaves the
    segment unproven and kept by the caller's normal rules.
    """
    receipts = _incoming_receipts(incoming_evidence)
    if receipts is None or not isinstance(live_evidence, Mapping):
        return frozenset()
    if len(incoming_segments) > MAX_INCOMING_SEGMENTS:
        return frozenset()
    id_counts = Counter(
        segment.get('id') for segment in incoming_segments if isinstance(segment.get('id'), str) and segment.get('id')
    )
    proven: set[int] = set()
    for index, segment in enumerate(incoming_segments):
        segment_id = segment.get('id')
        if not isinstance(segment_id, str) or not segment_id or id_counts[segment_id] != 1:
            continue
        matching = [r for r in receipts if isinstance(r, Mapping) and r.get('segment_id') == segment_id]
        if len(matching) != 1:
            continue
        receipt = matching[0]
        span = _receipt_span(receipt)
        if span is None:
            continue
        claim, start_frame, end_exclusive, end_offset = span
        ranges = validated_live_ranges(claim, [live_evidence])
        if ranges is None or not ranges:
            continue
        if not _offsets_fit(receipt, live_evidence, claim, receipt['source_end_frame'], end_offset):
            continue
        if not _fully_covered(ranges, start_frame, end_exclusive):
            continue
        proven.add(index)
    return frozenset(proven)
