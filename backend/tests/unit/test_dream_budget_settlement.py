"""Per-user admission and atomic known/unknown-usage settlement contracts."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from config.dream_agent import Caps
from database import dream_store
from tests.support.dream_firestore import DreamFirestore

UID = 'synthetic-budget-owner'
OTHER = 'synthetic-budget-other'
NOW = datetime(2026, 10, 14, 23, 59, tzinfo=timezone.utc)
RATE = 0.00001


@pytest.fixture
def db(monkeypatch):
    database = DreamFirestore()
    for uid in (UID, OTHER):
        database.rows[('users', uid)] = {}
        database.rows[('dream_users', uid)] = {'score': 1}
        database.rows[('dream_users', uid, 'dirty', dream_store.dirty_id('conversations', 'synthetic'))] = {
            'collection': 'conversations',
            'id': 'synthetic',
            'version': 'synthetic-version',
            'last_changed_at': NOW,
        }
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID + ',' + OTHER)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store._review_store(), 'encode_doc', lambda uid, value: value)
    return database


def caps():
    return Caps(tokens=432768, passes=24, daily_usd=250)


def priced(tokens):
    micro = int(round(tokens * RATE * 1000000))
    return {
        'tokens': tokens,
        'usage_unknown': False,
        'usage_complete': True,
        'cost_status': 'priced',
        'cost_micro_usd': micro,
        'cost_usd': tokens * RATE,
    }


def ledger(db, uid=UID, day=None):
    return db.rows[('dream_users', uid, 'spend', day or NOW.date().isoformat())]['reserved_usd']


def finish(db, lease, tokens=820000, **kwargs):
    report = priced(tokens)
    dream_store.finish(UID, lease, report, success=kwargs.pop('success', True), firestore_client=db, **kwargs)
    return report


def test_known_cost_and_lease_finish_share_one_transaction(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    assert ledger(db) == pytest.approx(0)
    report = finish(db, lease)
    assert ledger(db) == pytest.approx(8.2)
    assert report['cost_usd'] == report['budget_charge_usd'] == pytest.approx(8.2)
    assert db.rows[('dream_users', UID)]['lease'] is None
    run_path = ('users', UID, 'dream_runs', lease['run_id'])
    assert db.rows[run_path]['cost_usd'] == pytest.approx(8.2)
    tx = db.transactions[-1]
    assert {path for path, _ in tx.sets} == {
        run_path,
        ('dream_users', UID, 'spend', lease['day']),
        ('dream_due', UID),
    }
    assert ('dream_users', UID) in {path for path, _ in tx.updates}
    before = deepcopy(db.rows)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        finish(db, lease)
    assert db.rows == before


def test_full_24_hour_cadence_under_250(db):
    for index in range(24):
        lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
        assert lease is not None
        assert ledger(db) == pytest.approx(index * 8.2)
        finish(db, lease)
    assert ledger(db) == pytest.approx(196.8)
    assert dream_store.acquire(UID, caps(), now=NOW, firestore_client=db) is None


def test_users_have_independent_admission_and_no_legacy_global_reads(db):
    db.rows[('dream_spend', NOW.date().isoformat())] = {'reserved_usd': 9999}
    db.rows[('dream_users', UID, 'spend', NOW.date().isoformat())] = {'reserved_usd': 250}
    assert dream_store.acquire(UID, caps(), now=NOW, firestore_client=db) is None
    lease = dream_store.acquire(OTHER, caps(), now=NOW, firestore_client=db)
    assert lease and ledger(db, OTHER) == pytest.approx(0)
    assert ledger(db) == 250
    assert ('dream_spend', NOW.date().isoformat()) not in db.reads


@pytest.mark.parametrize(
    'flags',
    [
        {'usage_unknown': True},
        {},
        {'usage_complete': False},
        {'usage_unknown': True, 'usage_complete': True},
    ],
)
def test_unknown_or_missing_usage_retains_full_reservation(db, flags):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    db.rows[('dream_users', UID)]['lease']['reservation_usd'] = 1.2
    db.rows[('dream_users', UID)]['lease']['budget_charge_usd'] = 1.2
    db.rows[('dream_users', UID, 'spend', lease['day'])]['reserved_usd'] = 1.2
    report = {'tokens': 400000, 'cost_usd': 4, 'cost_status': 'priced', 'cost_micro_usd': 4000000, **flags}
    dream_store.finish(UID, lease, report, success=True, firestore_client=db)
    assert ledger(db) == pytest.approx(1.2)
    assert report['budget_charge_usd'] == pytest.approx(1.2)


def test_unknown_usage_cannot_be_refunded(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    db.rows[('dream_users', UID)]['lease']['reservation_usd'] = 1.2
    db.rows[('dream_users', UID)]['lease']['budget_charge_usd'] = 1.2
    db.rows[('dream_users', UID, 'spend', lease['day'])]['reserved_usd'] = 1.2
    dream_store.finish(
        UID, lease, {'tokens': 0, 'usage_unknown': True}, success=False, refund=True, firestore_client=db
    )
    assert ledger(db) == pytest.approx(1.2)
    assert db.rows[('dream_users', UID)]['passes'] == 1


def test_known_billable_failure_includes_retries_and_samples(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    report = finish(db, lease, tokens=1640000, success=False)
    assert ledger(db) == report['cost_usd'] == pytest.approx(16.4)
    assert db.rows[('dream_users', UID)]['passes'] == 1


def test_priced_settlement_keeps_prior_charges(db, monkeypatch):
    db.rows[('dream_users', UID, 'spend', NOW.date().isoformat())] = {'reserved_usd': 10}
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    monkeypatch.setenv('DREAM_AGENT_MAX_USD_PER_TOKEN', '1')
    finish(db, lease)
    assert ledger(db) == pytest.approx(18.2)


def test_midnight_settles_admission_day_only(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    tomorrow = (NOW + timedelta(days=1)).date().isoformat()
    db.rows[('dream_users', UID, 'spend', tomorrow)] = {'reserved_usd': 11}
    finish(db, lease, now=NOW + timedelta(minutes=2))
    assert ledger(db) == pytest.approx(8.2) and ledger(db, day=tomorrow) == 11


def test_retained_lease_settlement_and_zero_refund_are_idempotent(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    finish(db, lease, release=False)
    finish(db, lease, release=False)
    assert ledger(db) == pytest.approx(8.2)
    finish(db, lease)
    assert ledger(db) == pytest.approx(8.2)
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    for _ in range(2):
        dream_store.finish(UID, lease, {'tokens': 0}, success=False, refund=True, release=False, firestore_client=db)
    assert ledger(db) == pytest.approx(8.2)
    assert db.rows[('dream_users', UID)]['passes'] == 1


def test_failed_report_encoding_does_not_change_spend_or_lease(db, monkeypatch):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    before = deepcopy(db.rows)

    def fail(*args):
        raise RuntimeError('synthetic encoding failure')

    monkeypatch.setattr(dream_store._review_store(), 'encode_doc', fail)
    with pytest.raises(RuntimeError):
        finish(db, lease)
    assert db.rows == before
    assert not db.transactions[-1].has_written


def test_legacy_inflight_lease_keeps_its_original_shared_ledger(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    lease['reservation_usd'] = 1.2
    for key in ('spend_scope', 'budget_charge_usd'):
        lease.pop(key, None)
    db.rows[('dream_users', UID)]['lease'] = deepcopy(lease)
    user_path = ('dream_users', UID, 'spend', lease['day'])
    db.rows[('dream_spend', lease['day'])] = db.rows.pop(user_path)
    db.rows[('dream_spend', lease['day'])]['reserved_usd'] = 1.2
    dream_store.finish(
        UID,
        lease,
        {'tokens': 10, 'usage_unknown': True},
        success=True,
        firestore_client=db,
    )
    assert db.rows[('dream_spend', lease['day'])]['reserved_usd'] == pytest.approx(1.2)
    assert user_path not in db.rows


def test_known_actual_usage_is_not_clamped_to_the_reservation(db):
    lease = dream_store.acquire(UID, caps(), now=NOW, firestore_client=db)
    finish(db, lease, tokens=3000000)
    assert ledger(db) == pytest.approx(30)


def test_non_utc_admission_uses_the_utc_day(db):
    local = NOW.astimezone(timezone(timedelta(hours=7)))
    lease = dream_store.acquire(UID, caps(), now=local, firestore_client=db)
    assert lease['day'] == NOW.date().isoformat()
    assert lease['started_at'].tzinfo == timezone.utc
