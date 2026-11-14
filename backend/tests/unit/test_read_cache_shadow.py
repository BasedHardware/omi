"""Shadow outcomes, sampling, admission, and isolation from a slow/failing read."""

import threading
from unittest.mock import Mock

import pytest

from utils import executors, read_cache_shadow as shadow


@pytest.fixture
def queued(monkeypatch):
    pending = []
    monkeypatch.setenv('OMI_READ_CACHE_SHADOW_RATE', '1')
    monkeypatch.setattr(executors, 'submit_with_context', lambda pool, fn: pending.append(fn))
    metric = Mock()
    monkeypatch.setattr(shadow, 'SHADOW', metric)
    return pending, metric


def totals(value=0):
    return dict.fromkeys(shadow.USAGE_FIELDS, value)


@pytest.mark.parametrize(
    'cache,cached,fresh,result',
    [
        ('usage_month', totals(1), totals(1.0), 'match'),
        ('usage_month', totals(1), {**totals(1), 'speech_seconds': 2}, 'mismatch'),
        ('episode_members', {'b': {}, 'a': {}}, {'a': {'title': 'changed'}, 'b': {}}, 'match'),
        ('episode_members', {'a': {}}, {}, 'mismatch'),
        ('usage_month', totals(), {}, 'error'),
    ],
)
def test_comparison(queued, cache, cached, fresh, result):
    pending, metric = queued
    fetch = Mock(return_value=fresh)
    shadow.compare_hit(cache, cached, fetch, sample=lambda: 0)
    fetch.assert_not_called()
    pending.pop()()
    fetch.assert_called_once_with(5.0)
    metric.labels.assert_called_once_with(cache=cache, result=result)
    metric.labels.return_value.inc.assert_called_once_with()


def test_error_never_escapes_or_logs_values(queued, caplog):
    pending, metric = queued
    shadow.compare_hit('usage_month', totals(), Mock(side_effect=RuntimeError('sensitive')), sample=lambda: 0)
    pending.pop()()
    metric.labels.assert_called_once_with(cache='usage_month', result='error')
    assert 'sensitive' not in caplog.text


@pytest.mark.parametrize('rate', ['0', '-1', 'nan', 'inf', 'abc', '', '1%'])
def test_disabled(queued, monkeypatch, rate):
    monkeypatch.setenv('OMI_READ_CACHE_SHADOW_RATE', rate)
    sample = Mock(side_effect=AssertionError('must not sample'))
    shadow.compare_hit('usage_month', totals(), Mock(), sample=sample)
    assert not queued[0]
    sample.assert_not_called()
    queued[1].labels.assert_not_called()


def test_default_sampling_boundary_is_injectable(queued, monkeypatch):
    monkeypatch.delenv('OMI_READ_CACHE_SHADOW_RATE')
    shadow.compare_hit('usage_month', totals(), Mock(), sample=lambda: 0.01)
    assert not queued[0]
    shadow.compare_hit('usage_month', totals(), Mock(), sample=lambda: 0.0099)
    assert len(queued[0]) == 1


@pytest.mark.parametrize('cache,cached', [('usage_month', totals(1)), ('episode_members', {'b': {}, 'a': {}})])
def test_canonicalization_runs_only_in_worker_with_raw_snapshot(queued, monkeypatch, cache, cached):
    canonical = Mock(wraps=shadow._canonical)
    monkeypatch.setattr(shadow, '_canonical', canonical)
    shadow.compare_hit(cache, cached, lambda timeout: cached, sample=lambda: 0)
    canonical.assert_not_called()
    queued[0].pop()()
    assert canonical.call_count == 2
    assert canonical.call_args_list[0].args[1] is cached
    queued[1].labels.assert_called_once_with(cache=cache, result='match')


def test_admission_and_metric_errors_never_escape(queued, monkeypatch):
    monkeypatch.setattr(executors, 'submit_with_context', Mock(side_effect=RuntimeError('shutdown')))
    queued[1].labels.side_effect = RuntimeError('metrics down')
    shadow.compare_hit('usage_month', totals(), Mock(), sample=lambda: 0)


def test_incomplete_read_is_skipped(queued):
    shadow.compare_hit('usage_month', totals(), Mock(side_effect=shadow.ShadowSkipped()), sample=lambda: 0)
    queued[0].pop()()
    queued[1].labels.assert_called_once_with(cache='usage_month', result='skipped')


def test_real_executor_is_bounded_and_does_not_wait(monkeypatch, caplog):
    monkeypatch.setenv('OMI_READ_CACHE_SHADOW_RATE', '1')
    entered = threading.Barrier(3)
    release = threading.Event()
    completed = []
    metric = Mock()
    monkeypatch.setattr(shadow, 'SHADOW', metric)
    submit = executors.submit_with_context

    def track(pool, fn):
        future = submit(pool, fn)
        completed.append(future)
        return future

    monkeypatch.setattr(executors, 'submit_with_context', track)

    def blocking_read(timeout):
        entered.wait(timeout=2)
        assert release.wait(timeout=2)
        return totals()

    try:
        shadow.compare_hit('usage_month', totals(), blocking_read, sample=lambda: 0)
        shadow.compare_hit('usage_month', totals(), blocking_read, sample=lambda: 0)
        entered.wait(timeout=2)
        third = Mock()
        shadow.compare_hit('usage_month', totals(), third, sample=lambda: 0)
        third.assert_not_called()
        assert len(completed) == 2
        metric.labels.assert_called_with(cache='usage_month', result='skipped')
        assert 'executor_saturated' not in caplog.text
    finally:
        release.set()
        for future in completed:
            future.result(timeout=3)
