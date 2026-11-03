"""Real budget projection with counted Firestore reads and a session-owned cache."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest
from database import usage_units as units
from database.usage_units_session import UsageUnitsSession
from tests.unit.fixtures.shadow_usage_firestore import Store
from utils import ladder_v1 as ladder, stt_cap_dispatch as cap


@pytest.fixture
def billing():
    from utils import subscription

    return subscription


@pytest.fixture
def clock(monkeypatch, billing):

    value = [datetime(2026, 10, 17, 23, tzinfo=timezone.utc), 0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return value[0]

    monkeypatch.setattr(units, 'datetime', Clock)
    monkeypatch.setattr(ladder, 'datetime', Clock)
    monkeypatch.setattr(cap.time, 'monotonic', lambda: value[1])
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')

    def advance(seconds):
        value[0] += timedelta(seconds=seconds)
        value[1] += seconds

    return value, advance


def entitlement(budget=100000):
    return {'plan_id': 'basic', 'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': budget}}


def hourly(micro=0):
    return {
        'year': 2026,
        'month': 10,
        'shadow_v1': {'features': {'transcription': {'funding': {'omi': {'micro_units': micro}}}}},
    }


def gateway(micro):
    return {'shadow_v1': {'hours': {'23': {'features': {'chat': {'funding': {'omi': {'micro_units': micro}}}}}}}}


def paths(now):
    return (
        'users/u/hourly_usage/' + now.strftime('%Y-%m-%d-%H'),
        'llm_gateway_user_days/' + now.date().isoformat() + '_' + sha256(b'u').hexdigest()[:16],
        'users/u/ladder_v1_api_days/' + now.date().isoformat(),
    )


def month_store(percent=95):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    docs = {
        'users/u/hourly_usage/' + (start + timedelta(hours=i)).strftime('%Y-%m-%d-%H'): hourly() for i in range(408)
    }
    docs['users/u/hourly_usage/2026-10-01-00'] = hourly(percent * 1000 * 1_000_000)
    return Store(docs)


def read(store, clock, cache):
    return units.get_usage_units(
        'u', clock[0][0], firestore_client=store, entitlements=entitlement(), session_cache=cache
    )


def test_minute_reads_only_open_buckets_and_reconciles_backdated_writes(clock):
    store, cache = month_store(), UsageUnitsSession()
    assert read(store, clock, cache)['used_units'] == 95000
    assert store.reads == 408 + 34
    hour, day, api = paths(clock[0][0])
    store.docs[hour] = hourly(2_000_000)
    store.docs[day] = gateway(3_000_000)
    store.docs[api] = {'micro_units': 4_000_000, 'requests': 1}
    store.docs['users/u/hourly_usage/2026-10-01-00'] = hourly(95001_000_000)
    clock[1](60)
    before = store.reads
    snapshot = read(store, clock, cache)
    assert store.reads - before == 3
    assert snapshot['used_units'] == 95009  # Closed-hour late write stays cached.
    for _ in range(13):
        clock[1](60)
        before = store.reads
        assert read(store, clock, cache) == snapshot
        assert store.reads - before == 3
    clock[1](60)
    before = store.reads
    assert read(store, clock, cache)['used_units'] == 95010
    assert store.reads - before == 442
    assert not hasattr(cache, 'documents')  # The session holds sums, not a monthly document list.


@pytest.mark.parametrize('boundary', ['hour', 'day', 'month'])
def test_rollover_closes_old_buckets_once_and_matches_a_fresh_scan(clock, boundary):
    clock[0][0] = (
        datetime(2026, 10, 17, 22, 59, tzinfo=timezone.utc)
        if boundary == 'hour'
        else datetime(2026, 10, 17, 23, 59, tzinfo=timezone.utc)
    )
    if boundary == 'month':
        clock[0][0] = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
    old_hour, old_day, old_api = paths(clock[0][0])
    store = Store({old_hour: hourly(1_000_000), old_day: gateway(2_000_000), old_api: {'micro_units': 3_000_000}})
    cache = UsageUnitsSession()
    read(store, clock, cache)
    store.docs[old_hour] = hourly(2_000_000)  # Last-minute writes must not be lost at closure.
    store.docs[old_day] = gateway(3_000_000)
    store.docs[old_api] = {'micro_units': 4_000_000}
    clock[1](60)
    new_hour, new_day, new_api = paths(clock[0][0])
    h = hourly(5_000_000)
    h.update(year=clock[0][0].year, month=clock[0][0].month)
    store.docs[new_hour] = h
    if boundary != 'hour':
        store.docs[new_day], store.docs[new_api] = gateway(6_000_000), {'micro_units': 7_000_000}
    result = read(store, clock, cache)
    expected = units.get_usage_units('u', clock[0][0], firestore_client=Store(store.docs), entitlements=entitlement())
    assert result == expected
    clock[1](60)
    before = store.reads
    assert read(store, clock, cache) == result
    assert store.reads - before == 3


def test_failed_refresh_does_not_commit_partial_cache_and_invalidation_rescans(clock, monkeypatch):
    store, cache = month_store(), UsageUnitsSession()
    initial = read(store, clock, cache)
    clock[1](60)
    with monkeypatch.context() as patch:
        patch.setattr(store, 'get_all', Mock(side_effect=RuntimeError('synthetic read failure')))
        with pytest.raises(RuntimeError):
            read(store, clock, cache)
    assert cache.full_at == 0
    assert read(store, clock, cache) == initial
    cache.invalidate()
    before = store.reads
    assert read(store, clock, cache) == initial
    assert store.reads - before == 442


@pytest.mark.parametrize('dispatch', [False, True])
@pytest.mark.parametrize('percent,cadence', [(0, 900), (50, 900), (95, 60)])
async def test_real_live_admission_read_counts_and_local_debit(clock, monkeypatch, billing, dispatch, percent, cadence):
    store = month_store(percent)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setattr(ladder, 'account', lambda *a, **k: entitlement())
    monkeypatch.setattr(units, 'get_customer_firestore_client', lambda: store)
    subscription = billing

    monkeypatch.setattr(subscription, 'is_marketplace_reviewer', lambda _: False)
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *a, **k: False)

    async def run(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('u')
    await state.refresh(subscription={'plan': 'basic'})
    assert store.reads == 442
    remaining = state.remaining_units
    raw = Mock(send=Mock(return_value=True))
    for second in range(1, cadence):
        clock[1](1)
        state.send(raw, b'\0' * 32000, 'modulate', 16000)
        await state.refresh(force=False, subscription={'plan': 'basic'})
    assert store.reads == 442
    assert state.remaining_units < remaining
    clock[1](1)
    await state.refresh(force=False, subscription={'plan': 'basic'})
    assert store.reads == 442 + (3 if percent == 95 else 442)
    before = store.reads
    await state.refresh(force=True, subscription={'plan': 'basic'})
    assert store.reads - before == 442


async def test_unavailable_snapshot_uses_bounded_exponential_retry_and_resets(clock, monkeypatch):
    from utils.transcription_allowance import TranscriptionAllowance

    resolver = Mock(return_value=TranscriptionAllowance('on_device', 0, 'allowance_unavailable'))
    monkeypatch.setattr(cap, 'funded_allowance', resolver)

    async def run(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('u')
    await state.refresh()
    for delay in [60, 120, 240, 480, 900, 900]:
        count = resolver.call_count
        clock[1](delay - 1)
        await state.refresh(force=False)
        assert resolver.call_count == count
        clock[1](1)
        await state.refresh(force=False)
        assert resolver.call_count == count + 1
    await state.refresh(force=True)  # Invalidation always bypasses backoff.
    resolver.return_value = TranscriptionAllowance(
        'managed', None, 'usage_budget_available', remaining_units=5000, budget_units=100000
    )
    await state.refresh(force=True)
    assert state.failures == 0 and state.managed
    clock[1](59)
    assert not state.refresh_due()
    clock[1](1)
    assert state.refresh_due()


async def test_membership_change_drops_old_full_scan_deadline(clock, monkeypatch):
    from utils.transcription_allowance import TranscriptionAllowance

    resolver = Mock(return_value=TranscriptionAllowance('managed', None, 'legacy_dispatch_disabled'))
    monkeypatch.setattr(cap, 'funded_allowance', resolver)

    async def run(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('u')
    state.refreshed_at = state.usage_cache.full_at = 0
    state.remaining_units, state.budget_units = 100000, 100000
    clock[1](900)
    await state.refresh(force=False)
    assert state.usage_cache.full_at is None
    for delay in [60, 60, 779]:
        clock[1](delay)
        await state.refresh(force=False)
    assert resolver.call_count == 1
    clock[1](1)
    await state.refresh(force=False)
    assert resolver.call_count == 2
