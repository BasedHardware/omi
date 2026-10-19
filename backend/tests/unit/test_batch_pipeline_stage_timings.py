"""Profiling must retain failed work, remain content-free, and preserve draining."""

import asyncio

from prometheus_client import CollectorRegistry
import pytest

from tests.unit.test_batch_pipeline_pump import setup
from tests.unit.test_batch_pipeline_worker import setup_worker, item
from utils.batch_pipeline import stage_timings as module
from utils.batch_pipeline.stage_timings import StageTimings


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
    assert registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': 'ordered_merge'}) >= 1
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


def test_broken_telemetry_does_not_lose_persisted_result(monkeypatch):
    timings = StageTimings(CollectorRegistry())

    def broken(*args):
        raise RuntimeError('telemetry unavailable')

    monkeypatch.setattr(timings.duration, 'labels', broken)
    worker, _, saved, _, _, failures = setup_worker(timings=timings)
    assert worker.process_batch([item()])[0].segment_id == 'a'
    assert saved and not failures
