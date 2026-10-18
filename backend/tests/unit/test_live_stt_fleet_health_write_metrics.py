"""Low-cardinality accounting for fleet-health Redis write attempts."""

import asyncio

import pytest

from utils.stt import live_health as live_health_module
from utils.stt.live_health import FleetHealth
from utils.stt.live_metrics import (
    FLEET_HEALTH_WRITE_ATTEMPTED,
    FLEET_HEALTH_WRITE_DROPPED,
    FLEET_HEALTH_WRITE_WRITTEN,
)


def _value(counter, **labels):
    return counter.labels(**labels)._value.get()


def _capture_background_tasks(monkeypatch):
    tasks = []

    def start(coroutine, *, name):
        task = asyncio.create_task(coroutine, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(live_health_module, 'start_background_task', start)
    return tasks


def test_transcript_schedule_without_a_loop_records_bounded_drop_reason(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    labels = {'write_path': 'transcript_result', 'kind': 'result'}
    before_attempted = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    dropped_labels = {**labels, 'reason': 'loop_unavailable'}
    before_dropped = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)

    async def pending_write():
        return None

    health.schedule(pending_write(), **labels)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == before_attempted + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == before_dropped + 1


def test_raising_write_counters_do_not_break_record_or_schedule(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')

    def raise_counter_error(**_labels):
        raise RuntimeError('synthetic metrics failure')

    monkeypatch.setattr(FLEET_HEALTH_WRITE_ATTEMPTED, 'labels', raise_counter_error)
    monkeypatch.setattr(FLEET_HEALTH_WRITE_DROPPED, 'labels', raise_counter_error)
    monkeypatch.setattr(FLEET_HEALTH_WRITE_WRITTEN, 'labels', raise_counter_error)
    health = FleetHealth(clock=lambda: 1000.0)

    # Without a running loop record() takes the ordinary bounded drop path.
    health.record('soniox', 'en', 'text')


@pytest.mark.asyncio
async def test_raising_attempt_counter_does_not_block_background_schedule(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')

    def raise_counter_error(**_labels):
        raise RuntimeError('synthetic metrics failure')

    monkeypatch.setattr(FLEET_HEALTH_WRITE_ATTEMPTED, 'labels', raise_counter_error)
    health = FleetHealth(clock=lambda: 1000.0)
    tasks = _capture_background_tasks(monkeypatch)
    completed = []

    async def pending_write():
        completed.append(True)

    health.schedule(pending_write(), write_path='transcript_result', kind='result')
    await asyncio.gather(*tasks)

    assert completed == [True]


@pytest.mark.asyncio
async def test_transcript_written_counter_increments_only_after_pipeline_commit(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    labels = {'write_path': 'transcript_result', 'kind': 'result'}
    attempted_before = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)

    class Pipeline:
        def incr(self, _key):
            return self

        def expire(self, _key, _seconds):
            return self

        async def execute(self):
            assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before
            return [1, 1]

    class Redis:
        def pipeline(self, *, transaction):
            assert transaction is False
            return Pipeline()

    health = FleetHealth(clock=lambda: 1000.0, redis_client=Redis())
    monkeypatch.setattr(health, '_check_identity', lambda: 'stable')
    monkeypatch.setattr(health, '_score_keys', lambda *_args: ('text-score', 'no-text-score'))

    async def bounded(operation):
        return await operation

    monkeypatch.setattr(health, '_bounded', bounded)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_result('soniox', 'en', 'no_text', expected_identity='stable'),
        **labels,
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == attempted_before + 1
    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1


@pytest.mark.asyncio
async def test_transcript_post_commit_cleanup_error_stays_written_only(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    labels = {'write_path': 'transcript_result', 'kind': 'result'}
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)
    dropped_labels = {**labels, 'reason': 'redis_error'}
    dropped_before = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)

    class Pipeline:
        def incr(self, _key):
            return self

        def expire(self, _key, _seconds):
            return self

        async def execute(self):
            return [1, 1]

    class Redis:
        async def mget(self, _keys):
            return ['selection:999', None]

        def pipeline(self, *, transaction):
            assert transaction is False
            return Pipeline()

        async def eval(self, *_args):
            raise ConnectionError('synthetic post-commit cleanup failure')

    health = FleetHealth(clock=lambda: 1000.0, redis_client=Redis())
    monkeypatch.setattr(health, '_check_identity', lambda: 'stable')
    monkeypatch.setattr(health, '_score_keys', lambda *_args: ('text-score', 'no-text-score'))

    async def bounded(operation):
        return await operation

    monkeypatch.setattr(health, '_bounded', bounded)
    await health._write_result('soniox', 'en', 'text', expected_identity='stable')

    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == dropped_before
    assert health._redis_retry_at == 0.0


@pytest.mark.asyncio
async def test_cost_result_backoff_does_not_slide_or_mark_local_state_unreconciled(monkeypatch):
    from utils.stt.live_gate import GateState

    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    health._redis_retry_at = 1005.0
    health._cost_local[('soniox', 'all')] = GateState(stage=0)
    labels = {'write_path': 'cost_routing_result', 'kind': 'result'}
    backoff_labels = {**labels, 'reason': 'redis_backoff'}
    redis_error_labels = {**labels, 'reason': 'redis_error'}
    backoff_before = _value(FLEET_HEALTH_WRITE_DROPPED, **backoff_labels)
    redis_error_before = _value(FLEET_HEALTH_WRITE_DROPPED, **redis_error_labels)
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)

    await health._write_cost_result('soniox', 'en', True, None, 'a' * 16)

    assert _value(FLEET_HEALTH_WRITE_DROPPED, **backoff_labels) == backoff_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **redis_error_labels) == redis_error_before
    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before
    assert health._redis_retry_at == 1005.0
    assert not health._cost_unreconciled


@pytest.mark.asyncio
async def test_transcript_redis_backoff_uses_reason_label(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    health._redis_retry_at = 1001.0
    labels = {'write_path': 'transcript_result', 'kind': 'result', 'reason': 'redis_backoff'}
    before = _value(FLEET_HEALTH_WRITE_DROPPED, **labels)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_result('soniox', 'en', 'no_text', expected_identity='stable'),
        write_path='transcript_result',
        kind='result',
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_DROPPED, **labels) == before + 1


@pytest.mark.asyncio
async def test_cost_result_identity_change_is_counted_with_its_write_path(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    monkeypatch.setattr(health, '_check_identity', lambda: 'current')
    labels = {'write_path': 'cost_routing_result', 'kind': 'result'}
    attempted_before = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    dropped_labels = {**labels, 'reason': 'identity_changed'}
    dropped_before = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_cost_result('soniox', 'en', True, None, 'a' * 16, expected_identity='old'),
        **labels,
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == attempted_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == dropped_before + 1


@pytest.mark.asyncio
async def test_cost_result_written_counter_increments_after_a_cas_commit(monkeypatch):
    from utils.stt.live_gate import GateState

    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    monkeypatch.setattr(health, '_check_identity', lambda: 'stable')

    async def server_now(_identity):
        return 1000.0

    monkeypatch.setattr(health, '_server_now', server_now)
    labels = {'write_path': 'cost_routing_result', 'kind': 'result'}
    attempted_before = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)

    async def commit(*_args, on_commit=None, **_kwargs):
        assert on_commit is not None
        assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before
        on_commit()
        assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1
        return GateState()

    monkeypatch.setattr(health, '_cost_update', commit)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_cost_result('soniox', 'en', True, None, 'a' * 16, expected_identity='stable'),
        **labels,
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == attempted_before + 1
    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1


@pytest.mark.asyncio
async def test_cost_bench_redis_error_uses_bounded_path_and_reason_labels(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    monkeypatch.setattr(health, '_check_identity', lambda: 'stable')

    async def fail_server_time(_identity):
        raise ConnectionError('synthetic Redis failure')

    monkeypatch.setattr(health, '_server_now', fail_server_time)
    labels = {'write_path': 'cost_bench', 'kind': 'bench'}
    attempted_before = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    dropped_labels = {**labels, 'reason': 'redis_error'}
    dropped_before = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_cost_quarantine('soniox', lambda state: state, expected_identity='stable'),
        **labels,
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == attempted_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == dropped_before + 1


@pytest.mark.asyncio
async def test_cost_bench_commit_then_identity_change_records_commit_and_drop(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    health = FleetHealth(clock=lambda: 1000.0)
    monkeypatch.setattr(health, '_check_identity', lambda: 'stable')

    async def server_now(_identity):
        return 1000.0

    monkeypatch.setattr(health, '_server_now', server_now)
    labels = {'write_path': 'cost_bench', 'kind': 'bench'}
    attempted_before = _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels)
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)
    dropped_labels = {**labels, 'reason': 'identity_changed_after_commit'}
    dropped_before = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)

    async def commit_then_change_identity(*_args, on_commit=None, on_identity_changed=None, **_kwargs):
        assert on_commit is not None
        assert on_identity_changed is not None
        assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before
        on_commit()
        assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1
        on_identity_changed('identity_changed_after_commit')

    monkeypatch.setattr(health, '_cost_update', commit_then_change_identity)
    tasks = _capture_background_tasks(monkeypatch)
    health.schedule(
        health._write_cost_quarantine('soniox', lambda state: state, expected_identity='stable'),
        **labels,
    )
    await asyncio.gather(*tasks)

    assert _value(FLEET_HEALTH_WRITE_ATTEMPTED, **labels) == attempted_before + 1
    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == dropped_before + 1


@pytest.mark.asyncio
async def test_cost_bench_post_commit_identity_check_error_is_not_a_drop(monkeypatch):
    from dataclasses import replace

    from utils.stt.live_gate import GateState

    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')

    class Redis:
        async def time(self):
            return (1000, 0)

        async def get(self, _key):
            return None

        async def eval(self, *_args):
            return 1

    health = FleetHealth(clock=lambda: 1000.0, redis_client=Redis())
    health._identity = 'stable'
    checks = {'count': 0}

    def check_identity():
        checks['count'] += 1
        if checks['count'] == 5:
            raise RuntimeError('synthetic post-commit identity read failure')
        return 'stable'

    monkeypatch.setattr(health, '_check_identity', check_identity)
    labels = {'write_path': 'cost_bench', 'kind': 'bench'}
    written_before = _value(FLEET_HEALTH_WRITE_WRITTEN, **labels)
    dropped_labels = {**labels, 'reason': 'identity_changed_after_commit'}
    dropped_before = _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels)
    retry_at = health._redis_retry_at

    await health._write_cost_quarantine(
        'modulate-velma-2',
        lambda state: replace(state, stage=0, until=2000.0, generation=1),
        expected_identity='stable',
    )

    assert _value(FLEET_HEALTH_WRITE_WRITTEN, **labels) == written_before + 1
    assert _value(FLEET_HEALTH_WRITE_DROPPED, **dropped_labels) == dropped_before
    assert health._redis_retry_at == retry_at
