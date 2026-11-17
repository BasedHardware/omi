"""Original upload clocks and closed entitlement labels; no customer identifiers."""

import math

from prometheus_client import Counter, Histogram

CLASSES = frozenset({'paid', 'trial', 'free', 'unknown'})
CREATED = Counter('omi_batch_pipeline_created_units_total', 'First durable unit admissions', ['entitlement'])
DELIVERED = Histogram(
    'omi_batch_pipeline_upload_to_transcript_seconds',
    'Original upload request arrival to authoritative transcript publication; not client receipt or notes',
    ['entitlement'],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 86400),
)
COLLECTORS = (CREATED, DELIVERED)
for _class in sorted(CLASSES):
    CREATED.labels(_class)
    DELIVERED.labels(_class)


def bounded_class(value):
    return value if isinstance(value, str) and value in CLASSES else 'unknown'


def clock_fields(arrived_at, entitlement):
    if type(arrived_at) not in (int, float) or not math.isfinite(arrived_at) or arrived_at < 0:
        return {}
    return {'upload_arrived_at': arrived_at, 'upload_entitlement': bounded_class(entitlement)}


def observe_delivery(row, now):
    """Called only after a first authoritative non-deletion completion commits."""
    arrived = row.get('upload_arrived_at')
    if type(arrived) in (int, float) and math.isfinite(arrived) and 0 <= arrived <= now:
        DELIVERED.labels(bounded_class(row.get('upload_entitlement'))).observe(now - arrived)


def observe_completion(original, members, *, merged, changed, result, now):
    if result is None or result.get('reason_code') == 'source_deleted':
        return
    for member in members:
        # Members are ONLY the original receipts this transaction first completed.
        observe_delivery(member, now)
    if changed and not merged:
        observe_delivery(original, now)
