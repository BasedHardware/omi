"""Offline, content-free mentor score/outcome readout; never connects to an account store."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from typing import Any, Iterable


def utc(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise ValueError('timestamps must be timezone-aware')
    return result.astimezone(timezone.utc)


def auc(rows: list[tuple[float, bool, bool]], label: int) -> float | None:
    """Pairwise ranking probability, giving ties half credit, in O(n log n)."""
    positives = sum(row[label] for row in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return None
    wins = 0.0
    below = 0
    for _, group in groupby(sorted(rows), key=lambda row: row[0]):
        tied = list(group)
        positive = sum(row[label] for row in tied)
        negative = len(tied) - positive
        wins += positive * (below + 0.5 * negative)
        below += negative
    return wins / (positives * negatives)


def rates(rows: list[tuple[float, bool, bool]]) -> dict[str, Any]:
    total = len(rows)
    acted = sum(row[1] for row in rows)
    negative = sum(row[2] for row in rows)
    return dict(
        deliveries=total,
        acted=acted,
        negative=negative,
        acted_rate=acted / total if total else None,
        negative_rate=negative / total if total else None,
    )


def report(
    items: Iterable[dict[str, Any]],
    *,
    cohort_start: datetime,
    cohort_end: datetime,
    now: datetime,
    producer_version: int = 1,
    thresholds: Iterable[float] = (0.25, 0.5, 0.75),
) -> dict[str, Any]:
    start, end, now = utc(cohort_start), utc(cohort_end), utc(now)
    if start >= end or end > now - timedelta(hours=48):
        raise ValueError('use a creation cohort ending at least 48 hours ago')
    scored = []
    missing = 0
    for item in items:
        if item.get('producer') != 'conversation_mentor_v2' or item.get('producer_version') != producer_version:
            continue
        if item.get('delivered') is not True or not start <= utc(item['created_at']) < end:
            continue
        if utc(item['delivered_at']) + timedelta(hours=24) > now:
            continue
        score = item.get('usefulness_score')
        if type(score) not in {int, float} or not math.isfinite(score) or not 0 <= score <= 1:
            missing += 1
            continue
        if type(item['acted_24h']) is not bool or type(item['negative']) is not bool:
            raise ValueError('outcomes must be canonical booleans')
        scored.append((float(score), item['acted_24h'], item['negative']))
    by_threshold = []
    for threshold in thresholds:
        if type(threshold) not in {int, float} or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('invalid threshold')
        by_threshold.append(
            dict(
                threshold=threshold,
                kept=rates([row for row in scored if row[0] >= threshold]),
                dropped=rates([row for row in scored if row[0] < threshold]),
            )
        )
    return dict(
        producer_version=producer_version,
        cohort_start=start.isoformat(),
        cohort_end=end.isoformat(),
        mature_deliveries=len(scored) + missing,
        missing_score_deliveries=missing,
        scored=rates(scored),
        acted_auc=auc(scored, 1),
        negative_auc=auc(scored, 2),
        by_threshold=by_threshold,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON array of content-free canonical ledger projections')
    parser.add_argument('--cohort-start', type=utc, required=True)
    parser.add_argument('--cohort-end', type=utc, required=True)
    parser.add_argument('--now', type=utc, default=datetime.now(timezone.utc))
    parser.add_argument('--producer-version', type=int, default=1)
    parser.add_argument('--threshold', type=float, action='append')
    args = parser.parse_args()
    rows = json.loads(args.input.read_text())
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        parser.error('input must be a JSON array of ledger projections')
    result = report(
        rows,
        cohort_start=args.cohort_start,
        cohort_end=args.cohort_end,
        now=args.now,
        producer_version=args.producer_version,
        thresholds=args.threshold if args.threshold is not None else (0.25, 0.5, 0.75),
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
