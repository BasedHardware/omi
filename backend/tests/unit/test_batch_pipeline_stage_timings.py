"""Profiling must retain failed work, stay content-free, honor its flag, and drain."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import asyncio
import threading

from prometheus_client import CollectorRegistry
import pytest

from config.batch_pipeline import stage_profiling_enabled
from tests.unit.test_batch_pipeline_pump import setup
from tests.unit.test_batch_pipeline_worker import setup_worker, item
from utils.batch_pipeline import stage_timings as module
from utils.batch_pipeline.stage_timings import StageTimings


@pytest.fixture(autouse=True)
def _profiling_enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', 'true')


@pytest.mark.parametrize(
    'flag,stage,expected',
    [
        (None, 'dev', True),
        (None, 'prod', False),
        (None, None, False),
        (None, 'local', False),
        (None, 'offline', False),
        ('true', 'prod', True),
        ('TRUE', 'prod', True),
        ('1', None, True),
        ('on', 'local', True),
        ('false', 'dev', False),
        ('0', 'dev', False),
        ('off', 'offline', False),
        ('no', 'prod', False),
        ('garbage', 'dev', True),
        ('garbage', 'prod', False),
    ],
)
def test_flag_defaults_to_dev_stage_with_explicit_override(monkeypatch, flag, stage, expected):
    monkeypatch.delenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', raising=False)
    if flag is not None:
        monkeypatch.setenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', flag)
    if stage is None:
        monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    else:
        monkeypatch.setenv('OMI_ENV_STAGE', stage)
    assert stage_profiling_enabled() is expected
    registry = CollectorRegistry()
    assert (StageTimings(registry).duration is not None) is expected
    assert ('omi_batch_pipeline_stage_seconds' in [metric.name for metric in registry.collect()]) is expected


def test_disabled_timings_process_work_without_any_samples(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', 'false')
    registry = CollectorRegistry()
    timings = StageTimings(registry)
    worker, _, saved, _, _, failures = setup_worker(timings=timings)
    assert worker.process_batch([item()])[0].segment_id == 'a'
    assert saved and not failures
    assert not list(registry.collect())


def test_failed_stage_is_observed_without_error_text_or_dynamic_labels(monkeypatch):
    registry = CollectorRegistry()
    timings = StageTimings(registry)
    clock = iter([10.0, 12.5])
    monkeypatch.setattr(module.time, 'perf_counter', lambda: next(clock))
    with pytest.raises(RuntimeError, match='synthetic-private'):
        with timings.measure('fetch_decode'):
            raise RuntimeError('synthetic-private')
    assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_sum', {'stage': 'fetch_decode'}) == 2.5
    for metric in registry.collect():
        for sample in metric.samples:
            assert set(sample.labels) <= {'stage', 'le'}
            assert 'synthetic-private' not in str(sample)
    with pytest.raises(ValueError):
        with timings.measure('synthetic-owner'):
            pass


def test_cancelled_stage_keeps_cancellation_and_observes_partial_time():
    registry = CollectorRegistry()
    timings = StageTimings(registry)
    with pytest.raises(asyncio.CancelledError):
        with timings.measure('vad'):
            raise asyncio.CancelledError()
    assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': 'vad'}) == 1


def test_background_thread_stages_are_observed_where_they_run():
    registry = CollectorRegistry()
    timings = StageTimings(registry)
    off_main_thread = []

    def io_work():
        off_main_thread.append(threading.current_thread() is not threading.main_thread())
        timings.call('persist', lambda: 'uri')

    runner = threading.Thread(target=io_work)
    runner.start()
    runner.join()
    assert off_main_thread == [True]
    assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': 'persist'}) == 1


@pytest.mark.asyncio
async def test_real_pump_and_worker_export_one_cycle_with_nested_leaf_stages():
    registry = CollectorRegistry()
    timings = StageTimings(registry)
    worker, _, _, _, _, _ = setup_worker(timings=timings)
    store, _, pump = setup(worker, timings=timings)
    assert await pump.run_once() == 1
    assert store.rows['jobs', 'first']['state'] == 'committed'
    for stage in [
        'pump_cycle',
        'pull',
        'worker_flight',
        'fetch_decode',
        'vad',
        'windows',
        'asr',
        'diarize',
        'persist',
        'publication',
    ]:
        assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': stage}) == 1
    for stage in ['ordered_merge', 'maintenance']:
        assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': stage}) >= 1
    for absent in ['asr_recovery', 'cuda_sync', 'flight_segment', 'flight_diarize']:
        assert not registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': absent})
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


def test_broken_telemetry_does_not_lose_persisted_result(monkeypatch):
    timings = StageTimings(CollectorRegistry())

    def broken(*args):
        raise RuntimeError('telemetry unavailable')

    monkeypatch.setattr(timings.duration, 'labels', broken)
    worker, _, saved, _, _, failures = setup_worker(timings=timings)
    assert worker.process_batch([item()])[0].segment_id == 'a'
    assert saved and not failures


def test_broken_start_clock_preserves_the_operation_and_its_exception(monkeypatch):
    timings = StageTimings(CollectorRegistry())

    def broken():
        raise RuntimeError('clock failed')

    monkeypatch.setattr(module.time, 'perf_counter', broken)
    assert timings.call('asr', lambda: 7) == 7
    failure = ValueError('model failed')
    with pytest.raises(ValueError) as raised:
        with timings.measure('asr'):
            raise failure
    assert raised.value is failure
