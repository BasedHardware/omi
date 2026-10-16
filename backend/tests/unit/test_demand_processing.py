"""Demand boundaries against the production scheduler and Redis semantics."""

import json
from unittest.mock import Mock

import fakeredis
import pytest

from config import demand_processing as config
from utils.conversations import demand_processing as demand
from utils.conversations.day_merge_pass import engaged, shadow_day


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('DEMAND_PROCESSING_TOOL_ENABLED', 'true')
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
        **kwargs
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


def test_surface_promotes_only_owner_and_session_leases_union(runtime):
    redis, wake = runtime
    assert schedule('owner', 'pending') and schedule('other', 'other')
    assert wake.call_args.kwargs['schedule_at'] == 4540
    report('owner')
    assert demand.user_tier('owner', now=1001) == 0
    assert json.loads(redis.get(demand.PREFIX + 'pending'))['tier'] == 0
    assert json.loads(redis.get(demand.PREFIX + 'other'))['tier'] == 2
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
    assert not demand.admit('low', now=4539)
    report('new-active', now=4540)
    schedule('new-active', 'new-high', now=4540)
    # Reserving 60 seconds prevents perpetual tier-0 traffic starving old work.
    assert demand.admit('low', now=4540)


def test_ceiling_not_reset_by_revision_or_redis_repair(runtime):
    redis, _ = runtime
    schedule('owner', 'pending', now=1000)
    schedule('owner', 'pending', now=4400)
    row = json.loads(redis.get(demand.PREFIX + 'pending'))
    assert row['started_at'] == 1000 and row['due_at'] == 4540
    assert demand.admit('pending', now=4540)


def test_lazy_settlement_and_open_bypass(runtime):
    redis, _ = runtime
    schedule('owner', 'effects', now=1000, not_before=1600, effects_only=True)
    assert json.loads(redis.get(demand.PREFIX + 'effects'))['due_at'] == 1600
    report('owner', now=1100)
    assert demand.admit('effects', now=1100)


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
    assert json.loads(runtime[0].get(demand.PREFIX + 'other'))['tier'] == 2


def test_merge_pass_is_shadow_and_unknown_engagement_protected(monkeypatch, caplog):
    for key in ['opened_at', 'edited_at', 'shared_at', 'acted_at']:
        assert engaged({'engagement_unobserved': True, key: 'receipt'})
    assert engaged({})
    monkeypatch.setenv('DEMAND_PROCESSING_DAY_MERGE_SHADOW_ENABLED', 'true')
    rows = [{'id': 'opaque', 'summary': 'PRIVATE'}, {'engagement_unobserved': True}]
    with caplog.at_level('INFO'):
        assert shadow_day(rows) == {'link_only': 1, 'candidate': 1}
    assert 'PRIVATE' not in caplog.text and 'opaque' not in caplog.text


def test_redis_outage_is_eager_not_lost(runtime, monkeypatch):
    monkeypatch.setattr(demand, 'client', Mock(side_effect=ConnectionError()))
    assert not schedule('owner', 'pending')
    assert demand.admit('pending')


def test_stale_delivery_cannot_remove_current_priority(runtime):
    redis, _ = runtime
    schedule('owner', 'pending', now=1000)
    assert demand.admit('pending', now=1000, token=2)
    assert redis.get(demand.PREFIX + 'pending')


def test_queue_age_uses_waiting_index_without_worker_start(runtime, monkeypatch):
    schedule('owner', 'pending', now=1000)
    monkeypatch.setattr(demand.time, 'time', lambda: 1200)
    assert demand.queue_age(2) == 200
    assert demand.queue_age(0) == 0
