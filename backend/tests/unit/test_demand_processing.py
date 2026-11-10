"""Demand boundaries against the production scheduler and Redis semantics."""

import json
from unittest.mock import Mock

import fakeredis
import pytest

from config import demand_processing as config
from utils.conversations import demand_processing as demand


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('DEMAND_PROCESSING_TOOL_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(demand, 'client', lambda: redis)
    from utils import cloud_tasks

    wake = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', wake)
    return redis, wake


def schedule(uid, name, now=1000, **kwargs):
    return demand.schedule(
        uid,
        name,
        {'job_id': name, 'dispatch_generation': 1},
        dict(
            queue='conversation-finalization',
            handler='https://worker/run',
            audience='https://worker',
            invoker_sa='worker@example.invalid',
        ),
        'task-' + name,
        now=now,
        **kwargs,
    )


def report(uid, opened=True, session='phone', now=1000):
    demand.observe_surface(
        uid, session, dict(surface_open=opened, foreground=opened, transcript_visible=False), now=now
    )


@pytest.mark.parametrize(
    'last,lease,now,expected',
    [
        (None, 0, 1000, 2),
        (0, 0, 604800, 1),
        (0, 0, 604801, 2),
        (None, 1001, 1000, 0),
        (0, 1000, 1000, 1),
    ],
)
def test_tiers(last, lease, now, expected):
    assert demand.tier(last, lease, now) == expected


def test_default_off_and_owner_cohort(monkeypatch):
    monkeypatch.delenv('DEMAND_PROCESSING_ENABLED', raising=False)
    assert not config.enabled('owner')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_UID_ALLOWLIST', 'owner')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '0')
    assert config.enabled('owner') and not config.enabled('other')


@pytest.mark.parametrize('channel,stage', [('production', 'prod'), ('development', 'dev')])
def test_desktop_channel_binds_environment_without_cross_stage_keys(monkeypatch, channel, stage):
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.setenv('OMI_DESKTOP_BACKEND_RELEASE_CHANNEL', channel)
    assert demand.prefix() == stage + ':' + demand.PREFIX
    monkeypatch.setenv('OMI_DESKTOP_BACKEND_RELEASE_CHANNEL', 'unknown')
    with pytest.raises(ValueError):
        demand.prefix()


def test_surface_promotes_only_owner_and_session_leases_union(runtime):
    redis, wake = runtime
    assert schedule('owner', 'pending') and schedule('other', 'other')
    assert wake.call_args.kwargs['schedule_at'] == 1000
    report('owner')
    assert demand.user_tier('owner', now=1001) == 0
    assert json.loads(redis.get(demand.prefix() + 'pending'))['tier'] == 0
    assert json.loads(redis.get(demand.prefix() + 'other'))['tier'] == 2
    report('owner', session='mac', now=1002)
    report('owner', False, now=1003)
    assert demand.user_tier('owner', now=1004) == 0
    assert demand.user_tier('owner', now=1093) == 1
    assert demand.user_tier('owner', now=1002 + config.RECENT_SECONDS + 1) == 2


def test_ready_priority_and_ceiling_escape(runtime):
    report('active')
    report('recent', now=500)
    report('recent', False, now=501)
    schedule('dormant', 'low')
    schedule('recent', 'middle')
    schedule('active', 'high')
    # Even a ready lower tier waits for the queued higher tier.
    assert not demand.admit('middle', now=1240)
    assert demand.admit('high', now=1240)
    assert demand.admit('middle', now=1240)
    assert demand.admit('low', now=1240)
    schedule('dormant', 'starved', now=1000)
    report('new-active', now=4540)
    schedule('new-active', 'new-high', now=4540)
    # Reserving 60 seconds prevents perpetual tier-0 traffic starving old work.
    assert demand.admit('starved', now=4540)


def test_blocked_wait_backs_off_and_still_wakes_at_the_ceiling_escape(runtime):
    _, wake = runtime
    report('active')
    schedule('dormant', 'low', now=1000)
    schedule('active', 'high', now=1000)
    wake.reset_mock()
    # One named task per blocked wait, BLOCKED_WAIT_SECONDS apart, not every 5 s.
    assert not demand.admit('low', now=1240)
    assert wake.call_count == 1
    assert wake.call_args.kwargs['schedule_at'] == 1240 + config.BLOCKED_WAIT_SECONDS
    # Close to the escape, the wait lands exactly on it rather than past it.
    escape = 1000 + config.CEILING_HEADROOM_SECONDS
    assert not demand.admit('low', now=escape - 10)
    assert wake.call_args.kwargs['schedule_at'] == escape
    # Under 5 s from the escape the minimum delay wins, still inside the headroom.
    assert not demand.admit('low', now=escape - 3)
    assert wake.call_args.kwargs['schedule_at'] == escape + 2 < 1000 + config.CEILING_SECONDS
    assert demand.admit('low', now=escape)


def test_surface_open_wakes_only_the_newest_bounded_debt(runtime):
    redis, wake = runtime
    for i in range(config.OPEN_PROMOTE_LIMIT + 5):
        schedule('owner', f'debt-{i:02d}', now=1000 + i)
    wake.reset_mock()
    report('owner', now=1100)
    woken = [c.args[2] for c in wake.call_args_list if '-open-' in c.args[2]]
    assert len(woken) == config.OPEN_PROMOTE_LIMIT
    newest = {f'task-debt-{i:02d}' for i in range(5, config.OPEN_PROMOTE_LIMIT + 5)}
    assert {name.split('-open-')[0] for name in woken} == newest
    # Older debt keeps its tier (and its ceiling) instead of joining tier 0.
    assert json.loads(redis.get(demand.prefix() + 'debt-00'))['tier'] == 2


def test_ceiling_not_reset_by_revision_or_redis_repair(runtime):
    redis, _ = runtime
    schedule('owner', 'pending', now=1000)
    schedule('owner', 'pending', now=4400)
    row = json.loads(redis.get(demand.prefix() + 'pending'))
    assert row['started_at'] == 1000 and row['due_at'] == 4400
    assert redis.ttl(demand.prefix() + 'queue:2') > config.CEILING_SECONDS
    assert demand.admit('pending', now=4540)


def test_lazy_settlement_and_open_bypass(runtime):
    redis, _ = runtime
    schedule('owner', 'effects', now=1000, not_before=1600, effects_only=True)
    assert json.loads(redis.get(demand.prefix() + 'effects'))['due_at'] == 1600
    report('owner', now=1100)
    assert demand.admit('effects', now=1100)


def test_future_lazy_work_is_not_contention_for_ready_visible_work(runtime):
    report('recent', now=500)
    report('recent', False, now=501)
    schedule('recent', 'future-effects', now=1000, not_before=1600, effects_only=True)
    schedule('dormant', 'visible', now=1000)
    assert demand.admit('visible', now=1000)
    assert not demand.admit('future-effects', now=1000)


def test_tool_auth_bounds_and_progress(runtime):
    with pytest.raises(PermissionError):
        demand.process_recent('')
    for kwargs in [{'hours': 7}, {'hours': True}, {'limit': 21}, {'limit': -1}]:
        with pytest.raises(ValueError):
            demand.process_recent('owner', **kwargs)
    schedule('owner', 'pending', now=__import__('time').time())
    schedule('other', 'other', now=__import__('time').time())
    result = demand.process_recent('owner')
    assert result['promoted'] == 1 and result['ready'] is False
    assert demand.process_recent('owner')['status'] == 'rate_limited'
    assert json.loads(runtime[0].get(demand.prefix() + 'other'))['tier'] == 2


@pytest.mark.parametrize('recent', [False, True])
def test_idle_capacity_processes_every_tier_without_delay(runtime, recent):
    if recent:
        report('owner', now=500)
        report('owner', False, now=501)
    schedule('owner', 'pending', now=1000)
    assert runtime[1].call_args.kwargs['schedule_at'] == 1000
    assert demand.admit('pending', now=1000)


def test_redis_outage_is_eager_not_lost(runtime, monkeypatch):
    monkeypatch.setattr(demand, 'client', Mock(side_effect=ConnectionError()))
    assert not schedule('owner', 'pending')
    assert demand.admit('pending')


def test_stale_delivery_cannot_remove_current_priority(runtime):
    redis, _ = runtime
    schedule('owner', 'pending', now=1000)
    assert demand.admit('pending', now=1000, token=2)
    assert redis.get(demand.prefix() + 'pending')


def test_queue_age_uses_waiting_index_without_worker_start(runtime, monkeypatch):
    schedule('owner', 'pending', now=1000)
    monkeypatch.setattr(demand.time, 'time', lambda: 1200)
    assert demand.queue_age(2) == 200
    assert demand.queue_age(0) == 0


@pytest.fixture
def tool_adapters():
    from utils.retrieval.tools.demand_processing_tools import process_recent_conversations
    from utils.mcp_server.handlers import other
    from utils.mcp_server.errors import ToolExecutionError

    return process_recent_conversations, other, ToolExecutionError


def test_chat_tool_binds_injected_owner_without_uid_argument(runtime, monkeypatch, tool_adapters):
    process_recent_conversations, _, _ = tool_adapters

    assert set(process_recent_conversations.args) == {'hours', 'limit'}
    called = Mock(return_value={'ready': False, 'status': 'processing'})
    monkeypatch.setattr(demand, 'process_recent', called)
    process_recent_conversations.invoke({'hours': 2, 'limit': 3}, config={'configurable': {'user_id': 'owner'}})
    called.assert_called_once_with('owner', hours=2, limit=3)
    with pytest.raises(PermissionError):
        process_recent_conversations.invoke({})


def test_mcp_tool_rejects_an_owner_argument(runtime, tool_adapters):
    _, other, ToolExecutionError = tool_adapters

    with pytest.raises(ToolExecutionError):
        other.process_recent_conversations('owner', {'uid': 'other'})


def test_byok_enrichment_stays_in_the_request_context(runtime, monkeypatch):
    from utils import byok

    monkeypatch.setenv('DEMAND_PROCESSING_LAZY_ENABLED', 'true')
    monkeypatch.setattr(byok, 'has_byok_keys', lambda: True)
    assert not demand.lazy_enrichment_enabled('owner')
    monkeypatch.setattr(byok, 'has_byok_keys', lambda: False)
    assert demand.lazy_enrichment_enabled('owner')


@pytest.mark.parametrize('opened', [False, True])
def test_visible_sync_settle_survives_tier_zero_and_promotion(runtime, opened):
    redis, wake = runtime
    if opened:
        report('owner', now=1000)
    schedule('owner', 'sync-notes', now=1000, not_before=1600)
    row = json.loads(redis.get(demand.prefix() + 'sync-notes'))
    assert row['due_at'] == 1600
    assert wake.call_args.kwargs['schedule_at'] == 1600
    report('owner', now=1100)
    demand.promote('owner', now=1100)
    row = json.loads(redis.get(demand.prefix() + 'sync-notes'))
    assert row['tier'] == 0 and row['due_at'] == 1600
    assert wake.call_args.kwargs['schedule_at'] == 1600
    assert not demand.admit('sync-notes', now=1100)
    assert demand.admit('sync-notes', now=1600)


@pytest.mark.parametrize('surface_open', [None, 'true', 1])
def test_legacy_or_malformed_foreground_is_not_surface_intent(runtime, surface_open):
    redis, wake = runtime
    schedule('owner', 'pending')
    wake.reset_mock()
    payload = dict(foreground=True, transcript_visible=True)
    if surface_open is not None:
        payload['surface_open'] = surface_open
    demand.observe_surface('owner', 'released-phone', payload, now=1000)
    assert demand.user_tier('owner', now=1000) == 2
    assert redis.get(demand.owner_key('owner') + ':last_surface_open_at') is None
    assert json.loads(redis.get(demand.prefix() + 'pending'))['tier'] == 2
    wake.assert_not_called()
