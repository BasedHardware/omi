"""Summarize saved speaker_id_decision logs without emitting customer identifiers.

Usage: python backend/scripts/analyze_speaker_decisions.py /path/to/decisions.txt
Reports each Cloud Run service separately as well as the complete file. Legacy
clip_seconds is longest segment duration, not actual embedded audio duration.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    accepted = sum(row['accepted'] == 'True' for row in rows)
    compared = [row for row in rows if row.get('best') not in ('None', None)]
    rejected = [row for row in compared if row['accepted'] != 'True']
    bins = []
    for lower, upper in ((0, 2), (2, 5), (5, 10), (10, float('inf'))):
        bucket = [row for row in compared if lower <= float(row['clip_seconds']) < upper]
        bins.append(
            {
                'clip_seconds': f'{lower}-{upper}',
                'n': len(bucket),
                'accepted': sum(row['accepted'] == 'True' for row in bucket),
                'median_best_distance': median(float(row['best_distance']) for row in bucket) if bucket else None,
            }
        )
    return {
        'decisions': len(rows),
        'users': len({row.get('uid') for row in rows}),
        'accepted': accepted,
        'rejected': len(rows) - accepted,
        'accept_rate': accepted / len(rows) if rows else None,
        'compared': len(compared),
        'below_5_seconds': sum(float(row['clip_seconds']) < 5 for row in compared),
        'accepts_below_5_seconds': sum(
            float(row['clip_seconds']) < 5 and row['accepted'] == 'True' for row in compared
        ),
        'rejected_above_065': sum(float(row['best_distance']) > 0.65 for row in rejected),
        'rejected_above_065_through_075': sum(0.65 < float(row['best_distance']) <= 0.75 for row in rejected),
        'rejected_065_to_075_inclusive': sum(0.65 <= float(row['best_distance']) <= 0.75 for row in rejected),
        'bins': bins,
        'outcomes': {
            outcome: sum(row.get('outcome', 'legacy') == outcome for row in rows)
            for outcome in sorted({row.get('outcome', 'legacy') for row in rows})
        },
        'pooled_evidence': {
            field: {'n': len(values), 'median': median(values) if values else None}
            for field in ('segments', 'clips', 'evidence_seconds', 'available_seconds', 'failed_clips')
            for values in [[float(row[field]) for row in rows if field in row]]
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    services: dict[str, list[dict[str, str]]] = defaultdict(list)
    all_rows: list[dict[str, str]] = []
    malformed = 0
    timestamps = []
    for line in args.path.read_text().splitlines():
        if 'speaker_id_decision surface=sync' not in line:
            continue
        row = dict(re.findall(r'(\w+)=([^\s]+)', line))
        try:
            for field in ('clip_seconds', 'best_distance', 'runner_up_distance'):
                float(row[field])
            if row['accepted'] not in ('True', 'False'):
                raise ValueError('invalid boolean')
        except (KeyError, ValueError):
            malformed += 1
            continue
        parts = line.split('\t')
        service = parts[1] if len(parts) >= 3 and parts[1] in ('backend-sync', 'backend-sync-backfill') else 'unknown'
        if len(parts) >= 3:
            timestamps.append(parts[0])
        services[service].append(row)
        all_rows.append(row)
    print(
        json.dumps(
            {
                'malformed': malformed,
                'time_range': [min(timestamps), max(timestamps)] if timestamps else [],
                'all': summarize(all_rows),
                'finite_runner_up': summarize(
                    [row for row in all_rows if math.isfinite(float(row['runner_up_distance']))]
                ),
                'services': {name: summarize(rows) for name, rows in sorted(services.items())},
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
