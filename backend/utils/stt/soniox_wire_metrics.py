# LIFECYCLE: permanent
"""Bounded ON-only Soniox wire-ledger correctness cohorts."""

import threading
from typing import NamedTuple

from prometheus_client import Counter, Gauge


class SonioxWireMetrics(NamedTuple):
    checkpoints: Counter
    holes: Counter
    hole_samples: Counter
    intervals: Counter


class SonioxGateMetrics(NamedTuple):
    controls: Counter
    association_lost: Counter
    sockets: Gauge
    recoveries: Counter


_metrics: SonioxWireMetrics | None = None
_lock = threading.Lock()
_ordered_metrics: Counter | None = None
_gate_metrics: SonioxGateMetrics | None = None


def finalize_gate_metrics() -> SonioxGateMetrics:
    """Successful controls and active socket occupancy; fixed label sets only."""
    global _gate_metrics
    with _lock:
        if _gate_metrics is None:
            _gate_metrics = SonioxGateMetrics(
                Counter(
                    'omi_soniox_wire_ledger_controls_total',
                    'Successful finalize writes and their per-control settlements',
                    ['mode', 'outcome'],
                ),
                Counter(
                    'omi_soniox_wire_ledger_association_lost_total',
                    'Sockets permanently losing finalize acknowledgment association',
                    ['mode'],
                ),
                Gauge(
                    'omi_soniox_wire_ledger_sockets',
                    'Active clocks by capture admission state; pending, uncertain and lost are refusal occupancy',
                    ['mode', 'state'],
                ),
                Counter(
                    'omi_soniox_wire_ledger_recoveries_total',
                    'Clocks leaving pending or uncertain state with acknowledgment association still intact',
                    ['mode'],
                ),
            )
            for mode in ('reported', 'ordered'):
                for outcome in ('sent', 'verified', 'mismatch', 'unverified'):
                    _gate_metrics.controls.labels(mode=mode, outcome=outcome)
                for state in ('placeable', 'pending', 'uncertain', 'association_lost'):
                    _gate_metrics.sockets.labels(mode=mode, state=state)
                _gate_metrics.association_lost.labels(mode=mode)
                _gate_metrics.recoveries.labels(mode=mode)
    return _gate_metrics


def ordered_finalize_metrics() -> Counter:
    """One bounded family, registered only by the new enabled clock."""
    global _ordered_metrics
    with _lock:
        if _ordered_metrics is None:
            _ordered_metrics = Counter(
                'omi_soniox_ordered_finalize_checkpoints_total',
                'FIFO finalize predictions verified, mismatched or left unverified',
                ['outcome'],
            )
            for outcome in ('verified', 'mismatch', 'unverified'):
                _ordered_metrics.labels(outcome=outcome)
    return _ordered_metrics


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
