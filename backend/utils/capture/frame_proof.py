"""Committed S1 frame coverage shared by sync, batch and bridge dedupe.

Only committed transcript evidence suppresses speech. Full source-frame unions
use the established S1 interval algebra; partial receipt edges contribute only
when their exact source position matches the incoming edge.
"""

from collections import Counter
from collections.abc import Mapping, Sequence

from utils.capture.identity import compatible_keys
from utils.capture_evidence import Span, novel_coverage
from utils.sync.capture_repeat_evidence import incoming_receipts, offsets_fit, receipt_span
from utils.sync.committed_coverage import validated_committed_runs
from utils.sync.live_overlap import compatible_capture

MAX_ROWS = 128


def _same_track(left: Mapping, right: Mapping) -> bool:
    return all(left.get(key) == right.get(key) for key in ('capture_root', 'clock_epoch', 'rate_hz', 'channel'))


def _stored_receipt_ranges(row: Mapping, incoming: Mapping, claim: Mapping) -> tuple[list[Span], bool]:
    receipts = incoming_receipts(row.get('capture_evidence'))
    if receipts is None:
        return [], False
    ids = Counter(segment.get('id') for segment in row.get('transcript_segments') or [] if segment.get('id'))
    receipt_ids = Counter(receipt.get('segment_id') for receipt in receipts if isinstance(receipt, Mapping))
    ranges, positioned = [], False
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            continue
        segment_id = receipt.get('segment_id')
        if not segment_id or ids[segment_id] != 1 or receipt_ids[segment_id] != 1:
            continue
        parsed = receipt_span(receipt)
        if parsed is None or not _same_track(parsed[0], claim):
            continue
        positioned = True
        start, end = receipt['source_start_frame'], receipt['source_end_frame']
        # A partial boundary alone cannot prove that entire source frame.
        full_start = start + int(receipt['source_start_offset'] > 0)
        if end > full_start:
            ranges.append(Span(full_start, end))
        start_matches = (start, receipt['source_start_offset']) == (
            incoming['source_start_frame'],
            incoming['source_start_offset'],
        )
        end_matches = (end, receipt['source_end_offset']) == (
            incoming['source_end_frame'],
            incoming['source_end_offset'],
        )
        if start_matches and (end > start or end_matches):
            ranges.append(Span(start, start + 1))
        if receipt['source_end_offset'] > 0 and end_matches and (start < end or start_matches):
            ranges.append(Span(end, end + 1))
    return ranges, positioned


def evaluate(
    incoming: list[dict], incoming_row: dict, reference_rows: Sequence[dict]
) -> tuple[frozenset[int], frozenset[int]]:
    receipts = incoming_receipts(incoming_row.get('capture_evidence'))
    if receipts is None or len(reference_rows) > MAX_ROWS:
        return frozenset(), frozenset()
    ids = Counter(segment.get('id') for segment in incoming if segment.get('id'))
    matches = Counter(receipt.get('segment_id') for receipt in receipts if isinstance(receipt, Mapping))
    proven, positioned = set(), set()
    for index, segment in enumerate(incoming):
        segment_id = segment.get('id')
        if not segment_id or ids[segment_id] != 1 or matches[segment_id] != 1:
            continue
        receipt = next(r for r in receipts if isinstance(r, Mapping) and r.get('segment_id') == segment_id)
        parsed = receipt_span(receipt)
        if parsed is None:
            continue
        claim, start, end, end_offset = parsed
        ranges = []
        for row in reference_rows:
            if not compatible_capture(row, incoming_row) or not compatible_keys(row, incoming_row):
                continue
            evidence = row.get('capture_evidence') or {}
            runs = validated_committed_runs(claim, [evidence])
            if runs:
                positioned.add(index)
            if runs and offsets_fit(receipt, evidence, claim, receipt['source_end_frame'], end_offset):
                ranges.extend(Span(run['source_frame_start'], run['source_frame_end']) for run in runs)
            receipt_ranges, has_positions = _stored_receipt_ranges(row, receipt, claim)
            if has_positions:
                positioned.add(index)
            ranges.extend(receipt_ranges)
        if not novel_coverage(Span(start, end), ranges):
            proven.add(index)
    return frozenset(proven), frozenset(positioned)


def covered_indices(incoming: list[dict], incoming_row: dict, reference_rows: Sequence[dict]) -> frozenset[int]:
    return evaluate(incoming, incoming_row, reference_rows)[0]
