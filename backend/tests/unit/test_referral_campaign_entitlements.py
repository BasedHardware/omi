from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import fsr_read_cache, usage_units, users
from models.users import PlanType, Subscription
from tests.unit.fixtures.shadow_usage_firestore import Store
from utils.referral_campaign import CAMPAIGN_ID, GRANT_FIELD
from utils import fair_use, screen_vector_entitlements


@pytest.fixture
def active_grant(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    now = datetime.now(timezone.utc)
    return {
        'campaign_id': CAMPAIGN_ID,
        'status': 'active',
        'starts_at': int((now - timedelta(seconds=10)).timestamp()),
        'ends_at': int((now + timedelta(days=60)).timestamp()),
    }


def test_actual_admission_resolver_projects_grant_but_commercial_reader_stays_raw(monkeypatch, active_grant):
    basic = Subscription(plan=PlanType.basic, status='active')
    monkeypatch.setattr(users, 'get_existing_user_subscription', lambda *a, **k: basic)
    monkeypatch.setattr(users, 'user_snapshot', lambda *a: SimpleNamespace(to_dict=lambda: {GRANT_FIELD: active_grant}))
    projected = users.get_user_valid_subscription('owner', provision=False)
    assert projected.plan == PlanType.unlimited_v2
    assert projected.stripe_subscription_id is None
    assert users.get_existing_user_subscription('owner').plan == PlanType.basic
    active_grant['ends_at'] = 1
    assert users.get_user_valid_subscription('owner', provision=False).plan == PlanType.basic


def test_paid_historical_price_version_survives_grant_projection(monkeypatch, active_grant):
    paid = Subscription(
        plan=PlanType.operator,
        status='active',
        current_price_id='historical-price',
        stripe_subscription_id='paid-sub',
        current_period_end=active_grant['ends_at'],
    )
    monkeypatch.setattr(users, 'get_existing_user_subscription', lambda *a, **k: paid)
    monkeypatch.setattr(users, 'user_snapshot', lambda *a: SimpleNamespace(to_dict=lambda: {GRANT_FIELD: active_grant}))
    projected = users.get_user_valid_subscription('owner', provision=False)
    assert projected is paid
    assert projected.current_price_id == 'historical-price'
    assert projected.stripe_subscription_id == 'paid-sub'


def test_raw_budget_admission_uses_same_grant_projection(monkeypatch, active_grant):
    client = Store({'users/owner': {'subscription': {'plan': 'basic'}, GRANT_FIELD: active_grant}})
    resolved = []
    monkeypatch.setattr(usage_units, 'read_usage_month', lambda c, p, db, ent: (resolved.append(ent) or [], []))
    usage_units.get_usage_units('owner', datetime.now(timezone.utc), firestore_client=client)
    assert resolved[0]['plan_id'] == 'unlimited_v2'
    client.docs['users/owner'][GRANT_FIELD]['ends_at'] = 1
    usage_units.get_usage_units('owner', datetime.now(timezone.utc), firestore_client=client)
    assert resolved[-1]['plan_id'] == 'basic'


def test_fair_use_and_screen_vector_read_effective_authority(monkeypatch, active_grant):
    paid = Subscription(plan=PlanType.unlimited_v2, status='active', current_period_end=active_grant['ends_at'])
    calls = []

    def valid(uid, **kwargs):
        calls.append(kwargs)
        return paid

    monkeypatch.setattr(users, 'get_user_valid_subscription', valid)
    monkeypatch.setattr(
        fair_use.users_db, 'get_existing_user_subscription', lambda *a: pytest.fail('raw admission bypass')
    )
    assert fair_use.fair_use_caps_for_user('owner') == fair_use.fair_use_caps_for_plan(paid.plan)
    monkeypatch.setattr(screen_vector_entitlements, 'get_customer_firestore_client', lambda: 'customer')
    assert screen_vector_entitlements.read_subscription('owner') is paid
    assert all(c['provision'] is False for c in calls)


def test_request_dedupe_projection_includes_grant(monkeypatch, active_grant):
    reads = []

    class Client:
        def collection(self, name):
            return self

        def document(self, uid):
            return self

        def get(self, fields):
            reads.append(fields)
            return SimpleNamespace(to_dict=lambda: {GRANT_FIELD: active_grant})

    monkeypatch.setattr(fsr_read_cache, 'lever_enabled', lambda *a: True)
    holder = fsr_read_cache.RequestReads()
    token = fsr_read_cache._request.set(holder)
    try:
        client = Client()
        fsr_read_cache.user_snapshot('owner', client, ['subscription'])
        assert fsr_read_cache.user_snapshot('owner', client, [GRANT_FIELD]).to_dict()[GRANT_FIELD] == active_grant
        assert len(reads) == 1 and GRANT_FIELD in reads[0]
    finally:
        fsr_read_cache._request.reset(token)
