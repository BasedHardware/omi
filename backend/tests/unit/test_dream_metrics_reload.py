"""Prometheus collectors outlive temporary imports and keep their recorded values."""

from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge

from database import dream_metrics
from utils import dream_metrics as pass_metrics
from testing.import_isolation import load_module_fresh, stub_modules


def test_reimport_reuses_both_counters_and_preserves_counts():
    passes = dream_metrics.PASSES
    abandoned = dream_metrics.ABANDONED
    failed = passes.labels('failed', 'LeaseAbandoned')
    bounded = abandoned.labels('bounded')
    before = (failed._value.get(), bounded._value.get())
    path = Path(dream_metrics.__file__)
    for _ in range(2):
        with stub_modules({}):
            fresh = load_module_fresh('database.dream_metrics', str(path))
            assert fresh.PASSES is passes is pass_metrics.PASSES
            assert fresh.ABANDONED is abandoned
            fresh.record_reclaimed(301, 'bounded')
    assert (failed._value.get(), bounded._value.get()) == (before[0] + 2, before[1] + 2)


@pytest.mark.parametrize('factory,labels', [(Counter, ['different']), (Gauge, ['status', 'error_type'])])
def test_reimport_rejects_incompatible_metric_shape(monkeypatch, factory, labels):
    registry = CollectorRegistry()
    factory('synthetic_dream_reload_total', 'Synthetic', labels, registry=registry)
    monkeypatch.setattr(dream_metrics, 'REGISTRY', registry)
    with pytest.raises(ValueError, match='already registered with a different shape'):
        dream_metrics._counter('synthetic_dream_reload_total', 'Synthetic', ['status', 'error_type'])


def test_reimport_does_not_hide_an_unrelated_registration_error(monkeypatch):
    registry = CollectorRegistry()
    monkeypatch.setattr(dream_metrics, 'REGISTRY', registry)

    def fail(*args, **kwargs):
        raise ValueError('synthetic registration failure')

    monkeypatch.setattr(dream_metrics, 'Counter', fail)
    with pytest.raises(ValueError, match='synthetic registration failure'):
        dream_metrics._counter('synthetic_dream_reload_total', 'Synthetic', ['status', 'error_type'])
