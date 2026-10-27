"""The STT breaker trip counter answers WHY a provider's breaker opened.

The ``omi_stt_provider_circuit_open`` gauge shows that a pod's Parakeet
selection breaker is open, but not what opened it: at peak on 2026-10-21
(P32) 2-10 of 40 listen pods tripped per 10m and the cause lived only in
logs. These tests pin ``omi_stt_provider_circuit_trip_total``: one count per
real closed/half-open -> open transition, labeled with the bounded cause, and
nothing counted for re-arming an already-open breaker or for unlabelled
(test) breakers.
"""

from __future__ import annotations

import pytest

from utils.metrics import OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL
from utils.stt import provider_resilience
from utils.stt import streaming
from utils.stt.provider_resilience import ProviderCircuitBreaker


class FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount: float = 1.0):
        self.parent.increments.append((self.labels, amount))


class FakeCounter:
    def __init__(self):
        self.increments: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return FakeCounterChild(self, labels)


def _breaker(**kwargs) -> ProviderCircuitBreaker:
    params: dict = {'failure_threshold': 3, 'cooldown_seconds': 30, 'provider_label': 'parakeet'}
    params.update(kwargs)
    return ProviderCircuitBreaker(**params)


def test_serve_death_trip_counts_its_cause_once(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    breaker = _breaker()
    breaker.record_serve_failure(error_class='send_failed')
    breaker.record_serve_failure(error_class='send_failed')  # re-arm, not a new trip
    assert breaker.state == 'open'
    assert counter.increments == [
        ({'provider': 'parakeet', 'kind': 'selection', 'error_class': 'send_failed', 'reason': 'connect'}, 1.0)
    ]


def test_connect_threshold_trip_counts_the_last_failure_class(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    breaker = _breaker()
    breaker.record_failure(error_class='timeout')
    breaker.record_failure(error_class='timeout')
    assert counter.increments == []  # below threshold: no trip, no count
    breaker.record_failure(error_class='timeout')
    assert breaker.state == 'open'
    assert counter.increments == [
        ({'provider': 'parakeet', 'kind': 'selection', 'error_class': 'timeout', 'reason': 'latency'}, 1.0)
    ]


def test_half_open_probe_failure_retrips_with_its_cause(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    now = [0.0]
    breaker = _breaker(cooldown_seconds=0.5, serve_error_cooldown_seconds=0.5, clock=lambda: now[0])
    breaker.record_serve_failure(error_class='connection_lost')
    now[0] = 1.0  # serve bench elapsed: the next dial is a half-open probe
    assert breaker.allow_request()
    breaker.record_failure(error_class='connection_lost')
    assert (
        counter.increments
        == [({'provider': 'parakeet', 'kind': 'selection', 'error_class': 'connection_lost', 'reason': 'connect'}, 1.0)]
        * 2
    )


def test_unbounded_or_missing_causes_count_as_untyped(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    breaker = _breaker()
    breaker.record_serve_failure()  # no cause available
    breaker.record_serve_failure(error_class='free vendor text is never a label')
    # The first death tripped as untyped; the second only re-armed the open
    # breaker and did not count again.
    assert counter.increments == [
        ({'provider': 'parakeet', 'kind': 'selection', 'error_class': 'untyped', 'reason': 'unknown'}, 1.0)
    ]


def test_account_bench_trip_is_kind_account(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    breaker = _breaker()
    breaker.record_account_rejection(error_class='quota')
    assert breaker.state == 'open'
    assert counter.increments == [
        ({'provider': 'parakeet', 'kind': 'account', 'error_class': 'quota', 'reason': 'quota'}, 1.0)
    ]


def test_unlabelled_breaker_never_touches_the_counter(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    breaker.record_serve_failure(error_class='send_failed')
    assert breaker.state == 'open'
    assert counter.increments == []


def test_serve_terminal_funnel_labels_the_trip_cause(monkeypatch):
    """The live-session terminal path (live_failure -> streaming) names its cause."""
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    streaming._parakeet_circuit.reset()
    assert streaming.open_provider_selection_circuit('parakeet', reason='send_failed') is True
    assert (
        {'provider': 'parakeet', 'kind': 'selection', 'error_class': 'send_failed', 'reason': 'connect'},
        1.0,
    ) in counter.increments
    streaming._parakeet_circuit.reset()


def test_trip_counter_zero_children_exist_from_import():
    metric = next(iter(OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL.collect()))
    samples = {(s.labels['provider'], s.labels['kind'], s.labels['error_class']) for s in metric.samples}
    for probe in (
        ('parakeet', 'selection', 'connection_lost'),
        ('parakeet', 'selection', 'send_failed'),
        ('parakeet', 'selection', 'untyped'),
        ('parakeet', 'selection', 'config_incomplete'),
        ('deepgram', 'selection', 'auth'),
        ('soniox', 'selection', 'capacity_full'),
        ('parakeet', 'account', 'quota'),
    ):
        assert probe in samples, probe


@pytest.mark.parametrize(
    ('error_class', 'reason'),
    [
        ('provider_auth_rejected', 'auth'),
        ('provider_budget_exhausted', 'quota'),
        ('provider_rate_limited', 'quota'),
        ('provider_5xx', '5xx'),
        ('modulate_serve_error', '5xx'),
        ('timeout', 'latency'),
        ('first_text_deadline', 'no_text'),
        ('empty_streak', 'no_text'),
        ('no_text', 'no_text'),
        ('connection_lost', 'connect'),
        ('capacity_full', 'capacity'),
        ('untrusted vendor payload', 'unknown'),
    ],
)
def test_trip_reason_is_bounded_and_preserves_detailed_cause(monkeypatch, error_class, reason):
    counter = FakeCounter()
    monkeypatch.setattr(provider_resilience, 'OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL', counter)
    _breaker().record_serve_failure(error_class=error_class)
    assert len(counter.increments) == 1
    labels, count = counter.increments[0]
    assert labels['reason'] == reason
    assert labels['error_class'] == ('untyped' if reason == 'unknown' else error_class)
    assert count == 1.0


def test_zero_baselines_include_the_normalized_reason():
    metric = next(iter(OMI_STT_PROVIDER_CIRCUIT_TRIP_TOTAL.collect()))
    labels = [sample.labels for sample in metric.samples]
    assert any(row['error_class'] == 'provider_5xx' and row['reason'] == '5xx' for row in labels)
    assert any(row['error_class'] == 'empty_streak' and row['reason'] == 'no_text' for row in labels)
    assert any(row['error_class'] == 'untyped' and row['reason'] == 'unknown' for row in labels)
