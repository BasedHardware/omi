"""Closed-vocabulary custody answers and durable, phone-independent backlog."""

import math
import time

from prometheus_client import Counter, Gauge

from database.record_wal_handoff import pending_sample
from database.record_wal_capacity import sample as capacity_sample

_fresh_until = 0.0


class _SampleGauge(Gauge):
    def collect(self):
        if time.monotonic() < _fresh_until:
            yield from super().collect()


def deactivate():
    global _fresh_until
    _fresh_until = 0.0


answers = Counter('omi_record_wal_handoff_answers_total', 'WAL custody answers', ['outcome'])
pending = _SampleGauge('omi_record_wal_handoff_pending_files', 'Reserved/unsettled WAL originals; capped at 10001')
pending_bytes = _SampleGauge('omi_record_wal_handoff_pending_bytes', 'Reserved WAL bytes including crash orphans')
capacity_refusals = Counter(
    'omi_record_wal_handoff_capacity_refusals_total', 'WAL admission stopped by pending quota', ['scope']
)
age = _SampleGauge('omi_record_wal_handoff_oldest_age_seconds', 'Age of oldest unsettled original')
sampled_at = Gauge('omi_record_wal_handoff_sampled_at_seconds', 'Last successful durable backlog sample')
sample_errors = Counter('omi_record_wal_handoff_sample_errors_total', 'Unavailable durable backlog samples')


def refresh(store, now, *, expires_at=None):
    global _fresh_until
    try:
        count, oldest = pending_sample(store.client, store.namespace)
        volume = capacity_sample(store.client)
        pending.set(count)
        pending_bytes.set(volume['bytes'])
        age.set(max(0, now - oldest) if oldest is not None else 0)
        sampled_at.set(now)
        _fresh_until = expires_at if expires_at is not None else time.monotonic() + 120
    except Exception:
        deactivate()
        pending.set(math.nan)
        pending_bytes.set(math.nan)
        age.set(math.nan)
        sample_errors.inc()
