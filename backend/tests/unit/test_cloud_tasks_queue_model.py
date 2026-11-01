"""F1 Cloud Tasks throttle model and the fast-500 stall scenarios (swarm lane 4, contract (d))."""

import pytest

from testing.fakes import cloud_tasks_queue as ctq


def _queue(status=200, latency=0.1, config=ctq.QueueConfig(10.0, 50, 5, 3, 1.0, 4.0)):
    return ctq.CloudTasksQueue(lambda task, now: (status, latency), config)


def test_token_bucket_caps_dispatch_rate():
    q = _queue()
    for i in range(200):
        q.create_task(f't{i}', 'sync')
    q.run_until(5.0)
    assert 45 <= q.stats.dispatched <= 56  # 10/s for 5 s plus a 5-token burst


def test_named_task_dedupe():
    q = _queue()
    assert q.create_task('same', 'sync') and not q.create_task('same', 'sync')
    assert q.stats.created == 1 and q.stats.already_exists == 1


def test_retry_backoff_and_max_attempts():
    q = _queue(status=409, config=ctq.QueueConfig(10.0, 50, 5, 3, 1.0, 4.0))
    q.tick_s = 0.5
    q.create_task('x', 'enrichment')
    q.run_until(1.0)
    assert q.tasks['x'].attempts == 1 and q.tasks['x'].schedule_at == pytest.approx(1.5, abs=0.51)
    q.run_until(20.0)
    assert q.tasks['x'].attempts == 3 and q.tasks['x'].dropped and q.stats.dropped == 1


def test_409_never_trips_the_system_throttle():
    q = _queue(status=409)
    for i in range(300):
        q.create_task(f't{i}', 'enrichment')
    q.run_until(60.0)
    assert q.effective_rate == 10.0


def test_fast_500s_collapse_rate_and_a_config_patch_does_not_reset_it():
    q = _queue(status=500, latency=0.3)
    for i in range(300):
        q.create_task(f't{i}', 'enrichment')
    q.run_until(120.0)
    assert q.effective_rate == pytest.approx(0.1)
    q.update_config(ctq.QueueConfig(1.0, 10, 10, 3, 1.0, 4.0))  # sol-queue-stall's bounded probe
    assert q.effective_rate == pytest.approx(0.1)


def test_slow_500s_do_not_count_as_fast_failures():
    q = _queue(status=500, latency=30.0)
    for i in range(100):
        q.create_task(f't{i}', 'sync')
    q.run_until(60.0)
    assert q.effective_rate == 10.0


@pytest.mark.parametrize('scenario', [ctq.scenario_enrichment_fast_500_throttle, ctq.scenario_sync_backfill_0452])
def test_stall_reproduces_with_500_and_clears_with_409(scenario):
    stalled = scenario(500, duration_s=600.0)
    assert not stalled.passed and stalled.min_rate <= 0.2
    assert stalled.sync_pending > 0.5 * stalled.sync_created
    healthy = scenario(409, duration_s=600.0)
    assert healthy.passed, healthy.reason


@pytest.fixture(scope='module')
def route_status():
    # Importing the real router is the expensive part; do it in setup, not the timed call.
    return ctq.enrichment_route_status()


def test_enrichment_fast_500_throttle_passes_on_current_route_code(route_status):
    """Behavioural proof for contract (d): the real enrichment route's answer to an expected
    first-summary wait keeps the shared queue healthy. FAILS before #22371 (500), passes after (409)."""
    status = route_status
    result = ctq.scenario_enrichment_fast_500_throttle(status, duration_s=600.0)
    assert status == 409 and result.passed, result.summary()
