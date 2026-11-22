"""Shared billing holds: strict read ordering and idempotency, not a contention fake."""

from datetime import datetime, timedelta, timezone

import pytest

from database import free_allowance_leases as ledger, monthly_usage_totals as totals
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, ReadAfterWriteError

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
MONTH = ('users', 'u', 'monthly_usage_totals', '2026-11')
HOLDS = ('users', 'u', 'free_allowance_months', '2026-11')


@pytest.fixture
def store():
    return StrictFirestore(
        {
            ('users', 'u'): {},
            MONTH: {
                'schema_version': 1,
                'epoch': 'v1',
                'ready': True,
                'totals': {'transcription_seconds': 90},
                'days': {},
            },
        }
    )


def reserve(store, operation='first', seconds=6, **kwargs):
    return ledger.reserve('u', operation, seconds, 100, now=NOW, firestore_client=store, **kwargs)


def settle(store, leases, seconds, **kwargs):
    user = store.collection('users').document('u')
    transaction = store.transaction()
    with totals.publication_fence(user, transaction, firestore_client=store):
        queue = ledger.prepare_settlement(transaction, user, leases, seconds, now=NOW, **kwargs)
        # Simulate the SAME committed billing write. No transform fake is used.
        data = totals.month_ref(user, NOW).get(transaction=transaction).to_dict()
        data['totals']['transcription_seconds'] += seconds if not kwargs.get('daily_ptt') else 0
        transaction.set(totals.month_ref(user, NOW), data)
        queue()


def test_two_independent_callers_cannot_reuse_one_balance(store):
    first = reserve(store)
    assert first.reason == 'reserved' and first.remaining == 4
    assert reserve(store, 'second').reason == 'allowance_exhausted'
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 96


def test_retry_and_renewal_reserve_once_and_do_not_shrink_exposure(store):
    first = reserve(store).lease
    again = reserve(store, seconds=1).lease
    assert first is not None and again is not None and first.key == again.key
    assert again.seconds == 6
    assert len(store.rows[HOLDS]['holds']) == 1


def test_expired_lease_retains_uncertain_spend_and_cannot_be_resurrected(store):
    first = reserve(store).lease
    assert first is not None
    result = ledger.reserve('u', 'first', 6, 100, now=NOW + timedelta(seconds=31), firestore_client=store)
    assert result.reason == 'lease_expired'
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 96
    ledger.settle_billed([first], 0, now=NOW, firestore_client=store)
    receipt = store.rows[('users', 'u', 'free_allowance_receipts', f'{first.month}_{first.key}')]
    assert receipt['decision'] == 'unobserved'
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 90


def test_exhaustion_is_the_durable_allowance_refusal_reason(store):
    decision = reserve(store, seconds=11)
    assert decision.reason == 'allowance_exhausted'
    ref = ledger.reference('u', 'first', NOW)
    ledger.settle_billed([ref], 0, now=NOW, firestore_client=store)
    receipt = store.rows[('users', 'u', 'free_allowance_receipts', f'{ref.month}_{ref.key}')]
    assert receipt['decision'] == 'would_refuse'


def test_actual_billing_and_release_are_queued_without_read_after_write(store):
    lease = reserve(store).lease
    assert lease is not None
    settle(store, [lease], 3)
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 93
    assert reserve(store).reason == 'already_settled'
    assert reserve(store, 'second').remaining == 1


def test_unrelated_billing_cannot_discharge_an_inflight_hold(store):
    reserve(store)
    store.rows[MONTH]['totals']['transcription_seconds'] += 4
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 100
    assert reserve(store, 'second', 1).reason == 'allowance_exhausted'


def test_settling_an_expired_hold_is_safe_after_successful_billing(store):
    lease = reserve(store).lease
    assert lease is not None
    store.rows[HOLDS]['holds'][lease.key]['expires_at'] = NOW.timestamp() - 1
    settle(store, [lease], 4)
    assert store.rows[HOLDS]['holds'] == {}
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 94


def test_ptt_uses_accepted_daily_units_once_without_changing_monthly_billing(store):
    lease = reserve(store).lease
    assert lease is not None
    ledger.settle_daily_ptt(lease, 3.125, now=NOW, firestore_client=store)
    ledger.settle_daily_ptt(lease, 3.125, now=NOW, firestore_client=store)
    assert store.rows[MONTH]['totals']['transcription_seconds'] == 90
    assert ledger.chargeable_seconds('u', NOW, firestore_client=store) == 93.125


def test_last_live_window_can_be_partial(store):
    result = reserve(store, seconds=30, partial=True)
    assert result.lease is not None and result.lease.seconds == 10
    assert reserve(store, 'other', 1).reason == 'allowance_exhausted'


@pytest.mark.parametrize('value', [None, {}, {'ready': False}, {'totals': {'transcription_seconds': float('nan')}}])
def test_missing_or_corrupt_billing_never_synthesizes_zero(store, value):
    if value is None:
        store.rows.pop(MONTH)
    else:
        store.rows[MONTH] = value
    with pytest.raises(ValueError):
        reserve(store)
    assert HOLDS not in store.rows


@pytest.mark.parametrize('seconds', [float('nan'), float('inf'), -1, True, 0])
def test_invalid_duration_cannot_authorize_or_publish(store, seconds):
    with pytest.raises(ValueError):
        reserve(store, seconds=seconds)
    assert HOLDS not in store.rows


def test_month_boundary_clamps_lease_and_old_hold_does_not_charge_new_month(store):
    now = datetime(2026, 11, 30, 23, 59, 50, tzinfo=timezone.utc)
    result = ledger.reserve('u', 'first', 6, 100, now=now, firestore_client=store)
    assert result.lease is not None and result.lease.expires_at == now.timestamp() + 10
    store.rows[('users', 'u', 'monthly_usage_totals', '2026-12')] = {
        **store.rows[MONTH],
        'totals': {'transcription_seconds': 0},
    }
    assert ledger.chargeable_seconds('u', now + timedelta(seconds=11), firestore_client=store) == 0


def test_settlement_cannot_read_after_billing_or_cross_an_account(store):
    lease = reserve(store).lease
    assert lease is not None
    tx = store.transaction()
    user = store.collection('users').document('u')
    tx.set(totals.month_ref(user, NOW), store.rows[MONTH])
    with pytest.raises(ReadAfterWriteError):
        ledger.prepare_settlement(tx, user, [lease], 3, now=NOW)
    with pytest.raises(ValueError, match='owner'):
        ledger.prepare_settlement(store.transaction(), store.collection('users').document('other'), [lease], 3, now=NOW)


def test_no_flags_on_atomic_reservation(store, monkeypatch):
    monkeypatch.setenv('STT_FREE_ALLOWANCE_WATCH_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.delenv('SUBSCRIPTION_LAUNCH_DATE', raising=False)
    assert reserve(store).lease is not None


def test_partial_live_renewal_cannot_extend_the_last_funded_seconds(store):
    first = reserve(store, seconds=30, partial=True).lease
    assert first is not None and first.expires_at == NOW.timestamp() + 10
    renewed = ledger.reserve(
        'u', 'first', 35, 100, now=NOW + timedelta(seconds=5), partial=True, elapsed_seconds=5, firestore_client=store
    ).lease
    assert renewed is not None and renewed.expires_at == first.expires_at
