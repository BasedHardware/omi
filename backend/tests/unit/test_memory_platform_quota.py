"""Plan entitlement + metering contract for the Memory Platform API."""

import pytest
from fastapi import HTTPException

import database.memory_platform_usage as platform_usage_db
import utils.memory.platform_quota as platform_quota
from models.users import PlanType, Subscription
from utils.subscription import FREE_PLATFORM_API_REQUESTS_PER_MONTH, get_plan_limits


class _FakeRedis:
    def __init__(self, start=0, fail=False):
        self.values = {}
        self.fail = fail
        self.start = start

    def get(self, key):
        if self.fail:
            raise RuntimeError('redis down')
        return self.values.get(key, self.start)

    def incr(self, key, amount=1):
        if self.fail:
            raise RuntimeError('redis down')
        self.values[key] = self.values.get(key, self.start) + amount
        return self.values[key]

    def decr(self, key, amount=1):
        self.values[key] = self.values.get(key, self.start) - amount
        return self.values[key]

    def expire(self, key, ttl):
        return True


def _use_plan(monkeypatch, plan):
    monkeypatch.setattr(
        platform_quota,
        'users_db',
        type('_Users', (), {'get_user_valid_subscription': staticmethod(lambda _uid: Subscription(plan=plan))}),
    )


def test_basic_plan_has_a_usable_non_zero_platform_allowance():
    limit = get_plan_limits(PlanType.basic).platform_api_requests_per_month

    assert limit == FREE_PLATFORM_API_REQUESTS_PER_MONTH
    assert limit > 0


def test_existing_basic_subscriber_is_still_served(monkeypatch):
    """Legacy principal: a user already on `basic` keeps being served."""
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis())

    platform_quota.enforce_platform_quota('user-1')

    snapshot = platform_quota.get_platform_quota_snapshot('user-1')
    assert snapshot['plan_type'] == 'basic'
    assert snapshot['allowed'] is True
    assert snapshot['used'] == 1
    assert snapshot['remaining'] == FREE_PLATFORM_API_REQUESTS_PER_MONTH - 1


def test_over_quota_raises_429_naming_the_plan_and_limit(monkeypatch):
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis(start=FREE_PLATFORM_API_REQUESTS_PER_MONTH))

    with pytest.raises(HTTPException) as excinfo:
        platform_quota.enforce_platform_quota('user-1')

    assert excinfo.value.status_code == 429
    detail = excinfo.value.detail
    assert detail['error'] == 'platform_quota_exceeded'
    assert detail['plan_type'] == 'basic'
    assert detail['limit'] == FREE_PLATFORM_API_REQUESTS_PER_MONTH
    assert detail['reset_at'] > 0


def test_paid_plan_is_uncapped_and_never_metered(monkeypatch):
    _use_plan(monkeypatch, PlanType.operator)
    redis = _FakeRedis()
    monkeypatch.setattr(platform_usage_db, 'r', redis)

    platform_quota.enforce_platform_quota('user-1')

    assert redis.values == {}
    snapshot = platform_quota.get_platform_quota_snapshot('user-1')
    assert snapshot['limit'] is None
    assert snapshot['remaining'] is None
    assert snapshot['allowed'] is True


def test_counter_outage_fails_open_and_records_a_fallback(monkeypatch):
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis(fail=True))
    recorded = []
    monkeypatch.setattr(platform_usage_db, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

    platform_quota.enforce_platform_quota('user-1')

    assert len(recorded) == 1
    assert recorded[0]['component'] == 'memory_platform'
    assert recorded[0]['outcome'] == 'degraded'
