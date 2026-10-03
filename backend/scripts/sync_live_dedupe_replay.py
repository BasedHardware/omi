"""Offline production-dedupe replay; input segment start/end are absolute seconds."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.sync.capture_repeat_evidence import capture_covered_indices
from utils.sync.live_speech_dedupe import drop_covered_repeats, drop_proven_exact_retries


def _segments(payload: dict, name: str) -> list[dict]:
    rows = payload.get(name)
    if not isinstance(rows, list):
        raise ValueError(f'{name} must be a list')
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get('text'), str):
            raise ValueError(f'{name}[{index}] must contain text, start and end')
        start, end = row.get('start'), row.get('end')
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
        ):
            raise ValueError(f'{name}[{index}] start/end must be finite numbers')
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end) or end <= start or not math.isfinite(end - start):
            raise ValueError(f'{name}[{index}] requires a finite positive absolute interval')
        result.append(dict(row, start=start, end=end))
    return result


def replay(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('input must be an object containing live_segments and sync_segments')
    live = _segments(payload, 'live_segments')
    sync = _segments(payload, 'sync_segments')
    incoming = [dict(row, timestamp=row['start'], start=0.0, end=row['end'] - row['start']) for row in sync]
    verified = capture_covered_indices(
        incoming, payload.get('sync_capture_evidence'), payload.get('live_capture_evidence')
    )
    lexical_kept, report = drop_covered_repeats(
        incoming, live, live_origin=0.0, live_pinned=False, verified_capture_indices=verified
    )
    existing = [dict(row, timestamp=row['start']) for row in live]
    lexical_ids = {id(row) for row in lexical_kept}
    kept, _, _ = drop_proven_exact_retries(
        [(index, row) for index, row in enumerate(incoming) if id(row) in lexical_ids],
        existing,
        verified_indices=verified,
    )
    kept_ids = {id(row) for row in kept}
    methods = iter(report['methods'])
    decisions = []
    kept_durations = []
    dropped_durations = []
    for index, (original, segment) in enumerate(zip(sync, incoming)):
        duration = original['end'] - original['start']
        if id(segment) not in lexical_ids:
            reason = 'lexical_repeat:' + next(methods)
        elif id(segment) not in kept_ids:
            reason = 'exact_retry'
        else:
            reason = 'not_covered_or_outside_bounds'
        retained = id(segment) in kept_ids
        (kept_durations if retained else dropped_durations).append(duration)
        decisions.append(
            {
                'index': index,
                'start': original['start'],
                'end': original['end'],
                'decision': 'kept' if retained else 'dropped',
                'reason': reason,
            }
        )
    return {
        'segments': decisions,
        'totals': {
            'kept_segments': len(kept_durations),
            'dropped_segments': len(dropped_durations),
            'kept_seconds': math.fsum(kept_durations),
            'dropped_seconds': math.fsum(dropped_durations),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Local JSON file; each start/end is an absolute timestamp in seconds')
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding='utf-8'))
        result = replay(payload)
    except (OSError, ValueError, OverflowError):
        parser.exit(2, 'Replay input must be readable JSON with valid text and finite positive absolute intervals.\n')
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
