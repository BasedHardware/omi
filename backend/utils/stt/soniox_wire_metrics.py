# LIFECYCLE: permanent
"""Bounded ON-only Soniox wire-ledger correctness cohorts."""

import threading
from typing import NamedTuple

from prometheus_client import Counter


class SonioxWireMetrics(NamedTuple):
    checkpoints: Counter
    holes: Counter
    hole_samples: Counter
    intervals: Counter


_metrics: SonioxWireMetrics | None = None
_lock = threading.Lock()


def wire_metrics() -> SonioxWireMetrics:
    """Register only on an ON clock or bound wire epoch; OFF has no new series."""
    global _metrics
    with _lock:
        if _metrics is None:
            _metrics = SonioxWireMetrics(
                Counter(
                    'omi_soniox_wire_ledger_finalize_checkpoints_total',
                    'Wire finalize controls settled by acknowledgment or receive-loop termination',
                    ['outcome'],
                ),
                Counter('omi_soniox_wire_ledger_provider_holes_total', 'Positive provider-only holes registered'),
                Counter('omi_soniox_wire_ledger_provider_hole_samples_total', 'Registered provider-only hole samples'),
                Counter(
                    'omi_soniox_wire_ledger_intervals_total',
                    'Wire-ledger translator candidates granted or refused before persistence merging',
                    ['outcome'],
                ),
            )
            for outcome in ('clean', 'raced', 'missing_ack'):
                _metrics.checkpoints.labels(outcome=outcome)
            for outcome in ('known', 'unplaceable_by_race', 'other_refused'):
                _metrics.intervals.labels(outcome=outcome)
    return _metrics
