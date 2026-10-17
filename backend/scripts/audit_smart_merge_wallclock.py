#!/usr/bin/env python3
"""Summarize an exported Cloud Logging JSON array on stdin; emit no IDs or text."""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter

# Whitelist bounded decision fields; never copy a log entry into output/errors.
FIELDS = re.compile(r'\b(would|reason|p_same|gap_wall_s|gap_legacy_s)=([^\s]+)')


def summarize(entries: list[dict]) -> dict:
    counts: Counter[str] = Counter()
    scores = []
    gaps = []
    for entry in entries:
        message = entry.get('textPayload', '')
        if not isinstance(message, str) or 'event=smart_merge_wallclock_shadow ' not in message:
            continue
        fields = dict(FIELDS.findall(message))
        would, reason = fields.get('would'), fields.get('reason')
        if would not in {'merge', 'kept', 'skip'} or reason not in {
            'jev_same',
            'jev_different',
            'jev_unavailable',
            'wallclock_gap_negative',
            'wallclock_time_invalid',
            'gap_out_of_window',
            'too_few_words',
            'span_cap',
            'segment_cap',
            'fragment_cap',
        }:
            counts['unrecognized'] += 1
            continue
        counts[f'{would}:{reason}'] += 1
        for key, values in [('p_same', scores), ('gap_wall_s', gaps)]:
            try:
                number = float(fields.get(key, ''))
            except ValueError:
                continue
            if math.isfinite(number):
                values.append(number)
    return {
        'decisions': dict(sorted(counts.items())),
        'score_count': len(scores),
        'scores_near_cutoff_030_040': sum(0.30 <= score <= 0.40 for score in scores),
        'wall_gap_count': len(gaps),
        'wall_gap_min_seconds': min(gaps, default=None),
        'wall_gap_max_seconds': max(gaps, default=None),
        'note': 'Counts describe proposals, not reviewed same-call labels or calibrated probabilities.',
    }


def main() -> int:
    try:
        entries = json.load(sys.stdin)
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise ValueError()
        result = summarize(entries)
    except (ValueError, TypeError):
        print('Expected a Cloud Logging JSON array; input omitted.', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
