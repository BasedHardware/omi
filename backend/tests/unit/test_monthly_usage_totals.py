"""Serving equivalence and read/write budgets; contention lives in emulator tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from database import monthly_usage_totals as totals, user_usage
from database.firestore_read_origin import current_read_origin
from tests.unit.fixtures.shadow_usage_firestore import Store
from models.users import PlanType, Subscription, SubscriptionStatus
from utils import subscription

NOW = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)


def seeded_month():
    rows, days = {'users/u': {'synthetic': True}}, {}
    counts = dict.fromkeys(totals.FIELDS, 0)
    for hour in range(31 * 24):
        stamp = NOW.replace(day=1, hour=0) + timedelta(hours=hour)
        identity = stamp.strftime('%Y-%m-%d-%H')
        values = {key: hour + i for i, key in enumerate(totals.FIELDS)}
        rows[f'users/u/hourly_usage/{identity}'] = dict(id=identity, year=2026, month=10, **values)
        day = days.setdefault(f'{stamp.day:02d}', dict.fromkeys(totals.FIELDS, 0))
        for key in counts:
            counts[key] += values[key]
            day[key] += values[key]
    rows['users/u/monthly_usage_totals/2026-10'] = {
        'schema_version': 1,
        'epoch': 'v1',
        'ready': True,
        'totals': counts,
        'days': days,
    }
    return Store(rows)


@pytest.mark.parametrize(
    'start', [None, datetime(2026, 9, 30), datetime(2026, 10, 1), datetime(2026, 10, 23, 19, 30), datetime(2026, 11, 1)]
)
def test_one_read_replaces_month_scan_with_identical_result(monkeypatch, start):
    store = seeded_month()
    monkeypatch.setattr(user_usage, 'db', store)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')  # no Redis wrapper in either leg
    reader = user_usage.get_monthly_usage_stats if start is None else user_usage.get_monthly_usage_stats_since
    args = ('u', NOW) if start is None else ('u', NOW, start)
    legacy = reader(*args)
    legacy_reads = store.reads
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    store.reads = 0
    assert reader(*args) == legacy
    assert store.reads == 1
    if start is None or start.month == 9 or start.day == 1 and start.month == 10:
        assert legacy_reads == 744
    elif start.month == 10:
        assert legacy_reads == 9 * 24


def test_disabled_or_bad_epoch_never_reads_projection(monkeypatch):
    client = Mock()
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    assert totals.read_monthly_totals('u', NOW, firestore_client=client) is None
    client.collection.assert_not_called()
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    monkeypatch.setenv('FSR_USAGE_MONTH_TOTAL_EPOCH', '')
    assert totals.read_monthly_totals('u', NOW, firestore_client=client) is None
    client.collection.assert_not_called()


def test_hour_writer_adds_one_atomic_write_and_three_authority_reads(monkeypatch):
    store = seeded_month()
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'free')
    before = store.docs['users/u/monthly_usage_totals/2026-10']['totals'].copy()
    user_usage.update_hourly_usage(
        'u', NOW, {'transcription_seconds': 30, 'speech_seconds': 20}, firestore_client=store
    )
    assert store.reads == 3 and store.writes == 2
    row = store.docs['users/u/monthly_usage_totals/2026-10']
    assert row['totals']['transcription_seconds'] == before['transcription_seconds'] + 30
    assert row['totals']['speech_seconds'] == before['speech_seconds'] + 20
    assert row['ready'] is True
    # No plan/entitlement branching in the total: Free source accounting matches too.
    assert store.docs['users/u/hourly_usage/2026-10-23-15']['plan_usage']['free']['transcription_seconds'] == 30


def test_reader_origins_are_static_and_restore_callers_context(monkeypatch):
    store = seeded_month()
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    seen = []
    original = store.collection('users').document('u').__class__.get

    def capture(ref, *args, **kwargs):
        seen.append(current_read_origin())
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(store.collection('users').document('u').__class__, 'get', capture)
    assert totals.read_monthly_totals('u', NOW, firestore_client=store)
    assert seen == ['job:usage_month_total_read']
    assert current_read_origin() == 'unset'


def test_unavailable_projection_uses_original_authoritative_query(monkeypatch):
    store = seeded_month()
    monkeypatch.setattr(user_usage, 'db', store)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    monkeypatch.setattr(totals, '_rebuild', Mock(side_effect=RuntimeError('offline')))
    store.docs['users/u/monthly_usage_totals/2026-10']['ready'] = False
    assert user_usage.get_monthly_usage_stats('u', NOW)['transcription_seconds'] == sum(range(744))
    assert store.reads == 745


def test_databases_cannot_share_totals(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    first, second = seeded_month(), seeded_month()
    second.docs['users/u/monthly_usage_totals/2026-10']['totals']['speech_seconds'] = 123
    assert totals.read_monthly_totals('u', NOW, firestore_client=second)['speech_seconds'] == 123
    assert totals.read_monthly_totals('u', NOW, firestore_client=first)['speech_seconds'] != 123


@pytest.mark.parametrize('plan', [PlanType.basic, PlanType.plus])
@pytest.mark.parametrize('used', [9, 1_000_000])
def test_free_and_paid_allowance_remain_identical_through_real_resolver(monkeypatch, plan, used):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    stats = {key: used if key == 'transcription_seconds' else 0 for key in totals.FIELDS}
    store = Store(
        {
            'users/u/hourly_usage/2026-10-23-15': dict(id='2026-10-23-15', year=2026, month=10, **stats),
            'users/u/monthly_usage_totals/2026-10': {
                'schema_version': 1,
                'epoch': 'v1',
                'ready': True,
                'totals': stats,
                'days': {'23': stats},
            },
        }
    )
    monkeypatch.setattr(user_usage, 'db', store)
    monkeypatch.setattr(subscription, 'datetime', Clock)
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2026-10-01')
    monkeypatch.setattr(subscription, 'is_marketplace_reviewer', lambda uid: False)
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *a, **k: False)
    monkeypatch.setattr(subscription.ladder_v1, 'budget_snapshot', lambda *a, **k: None)
    member = Subscription(plan=plan, status=SubscriptionStatus.active)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    before = subscription.resolve_transcription_allowance('u', subscription=member, byok_active=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    after = subscription.resolve_transcription_allowance('u', subscription=member, byok_active=False)
    assert after.as_dict() == before.as_dict()
    assert after.reason in {'plan_within_allowance', 'plan_allowance_exhausted'}


@pytest.mark.parametrize('once', [False, True])
@pytest.mark.parametrize('authority', ['missing_root', 'pending', 'completed', 'destructive_gate'])
def test_record_usage_refusal_is_nonfatal_and_emits_bounded_counter(monkeypatch, caplog, once, authority):
    from database import legal_holds
    from utils import analytics
    from utils.metrics import OMI_FALLBACK_TOTAL

    store = Store({'users/u': {'synthetic': True}})
    if authority == 'missing_root':
        del store.docs['users/u']
    elif authority == 'destructive_gate':
        store.docs['legal_hold_deletion_gates/u'] = {
            'schema_version': legal_holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
            'uid': 'u',
            'kind': 'explicit_memory_deletion',
            'token': 'test-gate',
            'state': 'running',
            'started_at': datetime.now(timezone.utc),
        }
    else:
        store.docs['account_deletions/u'] = {'wipe_status': authority}
    monkeypatch.setattr(user_usage, 'db', store)
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'free')
    reason = 'usage_root_missing' if authority == 'missing_root' else 'usage_fence_blocked'
    counter = OMI_FALLBACK_TOTAL.labels(
        component='usage_publication', from_mode='publish', to_mode='skip', reason=reason, outcome='degraded'
    )
    before_count, before_writes = counter._value.get(), store.writes
    before_docs = dict(store.docs)

    analytics.record_usage('u', speech_seconds=5, transcription_seconds=5, idempotency_key='capture' if once else None)

    assert store.writes == before_writes
    assert store.docs == before_docs  # no hourly/monthly doc or committed usage receipt
    assert counter._value.get() == before_count + 1
    event = next(
        record.getMessage() for record in caplog.records if 'component=usage_publication' in record.getMessage()
    )
    assert event == (
        'omi_fallback_event component=usage_publication from=publish to=skip ' f'reason={reason} outcome=degraded'
    )


@pytest.mark.parametrize('once', [False, True])
def test_record_usage_does_not_swallow_unrelated_write_errors(monkeypatch, once):
    from utils import analytics

    writer = 'update_hourly_usage_once' if once else 'update_hourly_usage'
    monkeypatch.setattr(user_usage, writer, Mock(side_effect=RuntimeError('synthetic write failure')))
    with pytest.raises(RuntimeError, match='synthetic write failure'):
        analytics.record_usage('u', speech_seconds=5, idempotency_key='capture' if once else None)
