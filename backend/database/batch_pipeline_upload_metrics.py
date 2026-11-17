"""Original-upload metrics with closed labels; no customer identifiers or storage calls."""

import math

from prometheus_client import Counter, Histogram

from config.request_clock import CLASSES, bounded_class

CREATED = Counter('omi_batch_pipeline_created_units_total', 'First durable unit admissions', ['entitlement'])
DELIVERED = Histogram(
    'omi_batch_pipeline_upload_to_transcript_seconds',
    'Original upload request arrival to authoritative transcript publication; not client receipt or notes',
    ['entitlement'],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 86400),
)
INTER_UPLOAD_GAP = Histogram(
    'omi_batch_pipeline_inter_upload_gap_seconds',
    'Request-arrival gaps between accepted originals on the same coalescing owner/session/key; '
    'excludes bypasses, replays, invalid clocks and terminal right-censored pauses',
    ['entitlement', 'freshness', 'boundary'],
    buckets=(1, 5, 10, 20, 30, 45, 55, 60, 65, 70, 75, 90, 120, 180, 240, 300, 600, 1800, 7200, 86400),
)
COLLECTORS = (CREATED, DELIVERED, INTER_UPLOAD_GAP)
for _class in sorted(CLASSES):
    CREATED.labels(_class)
    DELIVERED.labels(_class)
    for _freshness in ('fresh', 'backlog'):
        for _boundary in ('within_group', 'between_groups'):
            INTER_UPLOAD_GAP.labels(_class, _freshness, _boundary)


def observe_delivery(row, now):
    """Called only after a first authoritative non-deletion completion commits."""
    arrived = row.get('upload_arrived_at')
    if type(arrived) in (int, float) and math.isfinite(arrived) and 0 <= arrived <= now:
        DELIVERED.labels(bounded_class(row.get('upload_entitlement'))).observe(now - arrived)


def inter_upload_gap(member, predecessors):
    """Already-read compatible originals only; never bridge an unknown clock."""
    clocks = [row.get('upload_arrived_at') for row in [*predecessors, member]]
    if len(clocks) < 2 or any(
        type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 for stamp in clocks
    ):
        return None
    gap = clocks[-1] - max(clocks[:-1])
    return gap if gap > 0 else None  # Concurrent/reordered arrivals cannot invent cadence.


def observe_gap(member, gap, boundary):
    if gap is not None:
        freshness = (
            'backlog'
            if member.get('lane') == 'backfill' or (member.get('item') or {}).get('priority', 0) != 0
            else 'fresh'
        )
        INTER_UPLOAD_GAP.labels(bounded_class(member.get('upload_entitlement')), freshness, boundary).observe(gap)


def observe_completion(original, members, *, merged, changed, result, now):
    if result is None or result.get('reason_code') == 'source_deleted':
        return
    for member in members:
        # Members are ONLY the original receipts this transaction first completed.
        observe_delivery(member, now)
    if changed and not merged:
        observe_delivery(original, now)
