"""MCP daily rollup: Redis accumulation matches the raw-stream cadence statistics (SCA-3665)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import fakeredis
import pytest

from utils import mcp_analytics as analytics
from utils import mcp_daily_rollup as rollup

DAY = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
T0 = int(DAY.timestamp())


@pytest.fixture
def redis(monkeypatch):
    server = fakeredis.FakeRedis()
    monkeypatch.setattr(rollup, '_ensure_sweeper', lambda: None)
    monkeypatch.delenv(rollup.ENABLED_ENV, raising=False)
    return server


def record(redis, at, *, uid='u1', client='codex', tool='get_memories', initiator='user'):
    return rollup.record_success(
        uid=uid, client=client, tool=tool, initiator=initiator, now=DAY, redis=redis, clock_s=T0 + at
    )


def raw_stats(calls):
    """The wall-mcp SQL definitions over raw eligible calls (seconds, tool)."""
    calls = sorted(calls)
    gaps = [b[0] - a[0] for a, b in zip(calls, calls[1:])]
    positive = [g for g in gaps if g > 0]
    tools = {}
    for _, tool in calls:
        tools[tool] = tools.get(tool, 0) + 1
    return {
        'calls': len(calls),
        'positive_gaps': len(positive),
        'sum_gap_s': sum(positive),
        'sum_gap_sq_s': sum(g * g for g in positive),
        'span_s': calls[-1][0] - calls[0][0],
        'dominant_tool_calls': max(tools.values()),
    }


def flush(redis, now):
    emit = Mock(return_value=True)
    count = rollup.flush_due(emit, now=now, redis=redis)
    return count, [call.kwargs for call in emit.call_args_list]


def test_snapshot_matches_raw_cadence_definitions(redis):
    calls = [
        (0, 'get_memories'),
        (60, 'get_memories'),
        (60, 'search_memories'),
        (185, 'get_memories'),
        (4000, 'get_goals'),
    ]
    for at, tool in calls:
        assert record(redis, at, tool=tool)
    record(redis, 5000, initiator='scheduled_agent')
    count, emitted = flush(redis, DAY + timedelta(days=1))
    assert count == 1
    props = emitted[0]['properties']
    assert emitted[0]['uid'] == 'u1' and emitted[0]['event'] == 'MCP Daily Activity'
    assert {k: props[k] for k in raw_stats(calls)} == raw_stats(calls)
    assert props['raw_calls'] == 6
    assert props['utc_day'] == '2026-11-23' and props['client'] == 'codex'
    assert props['$process_person_profile'] is False


def test_snapshots_are_throttled_per_key_and_cumulative(redis):
    record(redis, 0)
    record(redis, 100)
    assert flush(redis, DAY)[0] == 0  # not due before the flush delay
    count, first = flush(redis, DAY + timedelta(seconds=rollup.FLUSH_DELAY_SECONDS + 1))
    assert count == 1 and first[0]['properties']['calls'] == 2
    assert flush(redis, DAY + timedelta(seconds=rollup.FLUSH_DELAY_SECONDS + 2))[0] == 0  # claimed once
    record(redis, 200)
    count, settled = flush(redis, DAY + timedelta(days=1))  # day over: flush regardless of due time
    assert count == 1 and settled[0]['properties']['calls'] == 3


def test_keys_are_per_uid_client_and_day(redis):
    record(redis, 0, uid='a')
    record(redis, 0, uid='b')
    record(redis, 0, uid='a', client='cursor')
    count, emitted = flush(redis, DAY + timedelta(days=1))
    assert count == 3
    assert sorted((e['uid'], e['properties']['client']) for e in emitted) == [
        ('a', 'codex'),
        ('a', 'cursor'),
        ('b', 'codex'),
    ]
    ttl = redis.ttl(rollup.stats_key('20261123', 'a', 'codex'))
    assert 0 < ttl <= rollup.KEY_TTL_SECONDS


def test_kill_switch_and_redis_failure_fail_open(redis, monkeypatch):
    monkeypatch.setenv(rollup.ENABLED_ENV, 'off')
    assert not record(redis, 0)
    assert redis.keys('*') == []
    monkeypatch.delenv(rollup.ENABLED_ENV)
    broken = Mock()
    broken.eval.side_effect = ConnectionError('down')
    assert not rollup.record_success(uid='u', client='codex', tool='get_memories', initiator='user', redis=broken)


def test_success_path_queues_rollup_without_blocking_raw_event(monkeypatch):
    capture = Mock(return_value=True)
    queued = []
    monkeypatch.setattr(analytics, 'emit_product_event', capture)
    monkeypatch.setattr(analytics, 'submit_with_context', lambda executor, fn, **kw: queued.append((fn, kw)))
    monkeypatch.delenv(rollup.ENABLED_ENV, raising=False)
    analytics.schedule_mcp_tool_use_succeeded(uid='u', tool_name='get_memories', client_name='codex', initiator='user')
    assert capture.call_args.kwargs['event'] == 'MCP Tool Use Succeeded'
    assert len(queued) == 1
    fn, kwargs = queued[0]
    occurred_at = capture.call_args.kwargs['timestamp']
    assert fn is rollup.record_success
    assert kwargs == {'uid': 'u', 'client': 'codex', 'tool': 'get_memories', 'initiator': 'user', 'now': kwargs['now']}
    # The UTC day comes from the success time, not from when the queued task runs.
    assert kwargs['now'].tzinfo is not None and kwargs['now'] == occurred_at
    monkeypatch.setenv(rollup.ENABLED_ENV, 'false')
    queued.clear()
    analytics.schedule_mcp_tool_use_succeeded(uid='u', tool_name='get_memories', client_name='codex', initiator='user')
    assert queued == [] and capture.call_count == 2


def test_day_bucket_follows_the_success_time_not_the_worker_clock(redis):
    late = datetime(2026, 11, 23, 23, 59, 59, tzinfo=timezone.utc)
    rollup.record_success(
        uid='u1',
        client='codex',
        tool='get_memories',
        initiator='user',
        now=late,
        redis=redis,
        clock_s=int(late.timestamp()) + 5,
    )  # the worker runs after midnight
    assert redis.exists(rollup.stats_key('20261123', 'u1', 'codex'))
    assert not redis.exists(rollup.stats_key('20261124', 'u1', 'codex'))


def test_refused_snapshot_is_requeued_and_retried(redis):
    record(redis, 0)
    refused = Mock(return_value=False)
    assert rollup.flush_due(refused, now=DAY + timedelta(days=1), redis=redis) == 0
    assert refused.call_count == 1
    count, emitted = flush(redis, DAY + timedelta(days=1, minutes=2))
    assert count == 1 and emitted[0]['properties']['calls'] == 1
