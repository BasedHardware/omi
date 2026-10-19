"""Prepared shared-cache/client contracts; counted fake-store reads, no external IO."""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import funded_usage_session as cache, usage_units as units, usage_units_session as unit_session
from database import users as users_db
from tests.unit.fixtures.shadow_usage_firestore import Store
from utils import byok, funded_processing as funded, generated_compute as generated, ladder_v1 as ladder, subscription
from utils.storefront_copy import chat_at_cap
from utils.transcription_allowance import TranscriptionAllowance


def test_known_legacy_bypass_never_borrows_a_usage_session(monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(ladder.policy, 'entitlements', lambda subscription: None)
    borrow = Mock(side_effect=AssertionError('legacy bypass allocated a usage session'))
    monkeypatch.setattr(cache, 'budget_session', borrow)
    assert ladder.budget_snapshot('legacy', {'plan': 'plus', 'current_price_id': 'retained-legacy'}) is None
    borrow.assert_not_called()


def entitlement(budget=100000):
    return {'plan_id': 'basic', 'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': budget}}


def hour(units_used=0, *, seconds=0, identity='2026-10-17-10'):
    return {
        'id': identity,
        'year': 2026,
        'month': 10,
        'transcription_seconds': seconds,
        'speech_seconds': seconds,
        'shadow_v1': {'features': {'chat': {'funding': {'omi': {'micro_units': units_used * 1_000_000}}}}},
    }


def store(used=25000):
    return Store(
        {
            'users/u/hourly_usage/2026-10-16-09': hour(used, identity='2026-10-16-09'),
            'users/u/hourly_usage/2026-10-17-10': hour(),
        }
    )


@pytest.fixture
def clock(monkeypatch):
    value = [datetime(2026, 10, 17, 10, tzinfo=timezone.utc), 0.0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return value[0]

    for module in (funded, ladder, units, cache):
        monkeypatch.setattr(module, 'datetime', Clock)
    for module in (cache, unit_session):
        monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: value[1]))
    monkeypatch.setattr(cache, '_sessions', OrderedDict())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2026-10-01')
    monkeypatch.setattr(ladder.policy, 'entitlements', lambda subscription: entitlement())
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', Mock(return_value={'plan': 'basic'}))
    return value


def test_ladder_default_session_reads_month_once_then_open_buckets_and_reconciles(clock):
    db = store()
    first = ladder.budget_snapshot('u', firestore_client=db)
    assert first['used_units'] == 25000 and first['budget_percent'] == 25
    assert db.reads == 36  # Two hourly documents plus 17 gateway/API day pairs.
    db.docs['users/u/hourly_usage/2026-10-17-10'] = hour(3)
    db.docs['users/u/hourly_usage/2026-10-16-09'] = hour(25001, identity='2026-10-16-09')
    clock[0] += timedelta(seconds=899)
    clock[1] = 899
    before = db.reads
    warm = ladder.budget_snapshot('u', firestore_client=db)
    assert db.reads - before == 3 and warm['used_units'] == 25003
    clock[0] += timedelta(seconds=1)
    clock[1] = 900
    before = db.reads
    assert ladder.budget_snapshot('u', firestore_client=db)['used_units'] == 25004
    assert db.reads - before == 36
    assert db.writes == 0


def test_pipeline_allowance_and_unscoped_chat_budget_share_unit_session(clock):
    db = store()
    assert ladder.budget_snapshot('u', firestore_client=db)['budget_percent'] == 25
    before = db.reads
    allowance = funded.allowance('u', firestore_client=db)
    assert db.reads - before == 3
    assert allowance.managed and allowance.remaining_units == 75000 and allowance.budget_units == 100000
    users_db.get_user_valid_subscription.assert_called_with('u', provision=False, firestore_client=db)
    before = db.reads
    assert ladder.budget_snapshot('u', firestore_client=db)['budget_percent'] == 25
    assert db.reads - before == 3


def test_same_uid_clients_are_isolated_with_fresh_dispatch_reads(clock):
    first, second = store(25000), store(100000)
    assert funded.processing_allowed('u', firestore_client=first)
    assert not funded.processing_allowed('u', firestore_client=second)
    reads = first.reads + second.reads
    assert funded.processing_allowed('u', firestore_client=first)
    assert not funded.processing_allowed('u', firestore_client=second)
    assert first.reads + second.reads == reads + 6
    assert first.reads == second.reads == 39
    assert len(cache._sessions) == 2
    assert all(entry.firestore_client is not None for entry in cache._sessions.values())


def test_explicit_unit_session_is_honored_without_allocating_shared_entry(clock):
    db = store()
    session = unit_session.UsageUnitsSession()
    assert ladder.budget_snapshot('u', firestore_client=db, session_cache=session)['used_units'] == 25000
    before = db.reads
    assert ladder.budget_snapshot('u', firestore_client=db, session_cache=session)['used_units'] == 25000
    assert db.reads - before == 3
    assert not cache._sessions


def test_default_client_seam_omits_none_keyword_and_never_provisions(clock, monkeypatch):
    db = store()
    monkeypatch.setattr(units, 'get_customer_firestore_client', lambda: db)
    assert funded.allowance('u').managed
    users_db.get_user_valid_subscription.assert_called_once_with('u', provision=False)
    assert db.writes == 0
    before = db.reads
    ladder.budget_snapshot('u')
    assert db.reads - before == 3
    users_db.get_user_valid_subscription.assert_called_with('u', provision=False)


def test_cache_is_lru_bounded_and_uses_identity_for_unhashable_equal_clients(clock):
    class EqualClient:
        __hash__ = None

        def __eq__(self, other):
            return True

    first, second = EqualClient(), EqualClient()
    with cache.budget_session('u', firestore_client=first) as original:
        pass
    with cache.budget_session('u', firestore_client=second) as other:
        assert other is not original
    for i in range(cache.MAX_BUDGET_SESSIONS - 2):
        with cache.budget_session(str(i)):
            pass
    with cache.budget_session('u', firestore_client=first) as touched:
        assert touched is original
    with cache.budget_session('overflow'):
        pass
    assert len(cache._sessions) == 1024
    assert ('u', id(first)) in cache._sessions and ('u', id(second)) not in cache._sessions
    assert original.firestore_client is first  # Strong reference prevents identity reuse.


def test_ladder_chat_402_body_exactly_matches_existing_copy_and_warm_reads(clock):
    db = store(100000)
    app = FastAPI()

    @app.post('/chat')
    def route():
        ladder.enforce_chat_budget('u', firestore_client=db)
        raise AssertionError('chat provider must never start')

    with TestClient(app) as client:
        first = client.post('/chat')
        before = db.reads
        second = client.post('/chat')
    reset = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())
    expected = {
        'detail': {
            'error': 'usage_budget_exhausted',
            'trigger': 'usage_budget',
            'chat_at_cap': chat_at_cap('basic', reset),
        }
    }
    assert first.status_code == second.status_code == 402
    assert first.json() == expected and first.content == second.content
    assert db.reads - before == 3 and db.writes == 0


def test_flags_off_real_http_bytes_and_no_new_reads(clock, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    lookup = users_db.get_user_valid_subscription
    db = store(100000)
    app = FastAPI()

    @app.get('/chat')
    def route():
        assert ladder.budget_snapshot('u', firestore_client=db) is None
        assert funded.processing_allowed('u', firestore_client=db)
        generated.require_generated_compute('u', 'chat_agent', firestore_client=db)
        return {'status': 'unchanged'}

    with TestClient(app) as client:
        response = client.get('/chat')
    assert response.status_code == 200 and response.content == b'{"status":"unchanged"}'
    lookup.assert_not_called()
    assert db.reads == db.writes == 0 and not cache._sessions


def test_legacy_cache_forwards_client_reads_current_hour_then_reconciles(clock, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    db = Store(
        {
            'users/u/hourly_usage/2026-10-16-09': hour(seconds=20, identity='2026-10-16-09'),
            'users/u/hourly_usage/2026-10-17-10': hour(seconds=30),
        }
    )
    resolver = Mock(
        side_effect=lambda uid, **kwargs: TranscriptionAllowance(
            'managed', 100 - kwargs['usage']['transcription_seconds'], 'remaining', limit_seconds=100
        )
    )
    monkeypatch.setattr(subscription, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(
        cache, 'get_customer_firestore_client', Mock(side_effect=AssertionError('explicit client lost'))
    )
    assert funded.allowance('u', firestore_client=db).remaining_seconds == 50
    assert db.reads == 2
    db.docs['users/u/hourly_usage/2026-10-17-10'] = hour(seconds=40)
    before = db.reads
    assert funded.allowance('u', firestore_client=db).remaining_seconds == 40
    assert db.reads - before == 1
    clock[0] += timedelta(minutes=15)
    clock[1] = 900
    before = db.reads
    assert funded.allowance('u', firestore_client=db).remaining_seconds == 40
    assert db.reads - before == 2
    users_db.get_user_valid_subscription.assert_called_with('u', provision=False, firestore_client=db)
    assert resolver.call_args.kwargs['usage']['transcription_seconds'] == 60
    assert db.writes == 0


def test_subscription_failure_fails_closed_without_provision_or_ledger_reads(clock):
    db = store()
    users_db.get_user_valid_subscription.side_effect = RuntimeError('synthetic unavailable')
    result = funded.allowance('u', firestore_client=db)
    assert not result.managed and result.reason == 'allowance_unavailable'
    assert db.reads == db.writes == 0


def test_legacy_direct_session_does_not_reuse_totals_for_another_client(clock, monkeypatch):
    launch = datetime(2026, 10, 1, tzinfo=timezone.utc)
    first = Store({'users/u/hourly_usage/2026-10-17-10': hour(seconds=20)})
    second = Store({'users/u/hourly_usage/2026-10-17-10': hour(seconds=80)})
    session = cache.LegacyUsageSession()
    assert session.read('u', launch, firestore_client=first)['speech_seconds'] == 20
    assert session.read('u', launch, firestore_client=second)['speech_seconds'] == 80
    assert first.reads == second.reads == 1


def test_chat_quota_forwards_explicit_client_through_adapter_without_provision(clock, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(byok, 'has_validated_byok_keys', lambda: False)
    db = Store({'users/u/hourly_usage/2026-10-17-10': hour(seconds=100)})
    monkeypatch.setattr(
        subscription,
        'resolve_transcription_allowance',
        Mock(return_value=TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted', limit_seconds=100)),
    )
    with pytest.raises(HTTPException) as error:
        subscription.enforce_chat_quota('u', firestore_client=db, provision=False)
    assert error.value.status_code == 402 and error.value.detail['error'] == 'usage_budget_exhausted'
    users_db.get_user_valid_subscription.assert_called_once_with('u', provision=False, firestore_client=db)
    assert db.reads == 1 and db.writes == 0


def test_shared_session_serializes_snapshot_reads_for_one_client(clock, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    db = store()
    started, projected = Event(), Event()
    original = units.get_usage_units

    def projection(*args, **kwargs):
        projected.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(units, 'get_usage_units', projection)

    def read():
        started.set()
        return ladder.budget_snapshot('u', firestore_client=db)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with cache.budget_session('u', firestore_client=db):
            future = executor.submit(read)
            assert started.wait(2)
            assert not projected.wait(0.05)  # It must not mutate the borrowed unit session yet.
        assert future.result(timeout=2)['used_units'] == 25000
    assert projected.is_set() and db.reads == 36
