"""Stale admission settlement never consumes dirty work or steals a live lease."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from config.dream_agent import Caps, DRAIN_TIMEOUT_SECONDS, LEASE_RECLAIM_MARGIN_SECONDS
from database import dream_store
from tests.support.dream_firestore import DreamFirestore

UID = 'synthetic-abandoned-owner'
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
DIRTY = ('dream_users', UID, 'dirty', dream_store.dirty_id('conversations', 'synthetic'))


@pytest.fixture
def db(monkeypatch):
    database = DreamFirestore()
    database.rows[('users', UID)] = {}
    database.rows[('dream_users', UID)] = {'score': 1}
    database.rows[DIRTY] = {
        'collection': 'conversations',
        'id': 'synthetic',
        'version': 'pending-version',
        'last_changed_at': NOW,
        'failed_passes': 2,
    }
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store._review_store(), 'encode_doc', lambda uid, value: value)
    return database


def caps(context='bounded', **kw):
    return Caps(tokens=24000, passes=24, daily_usd=250, **kw)


def acquire(db, at=NOW, context='bounded', **kw):
    return dream_store.acquire(UID, caps(context), now=at, firestore_client=db, **kw)


def deadline(context):
    return DRAIN_TIMEOUT_SECONDS + LEASE_RECLAIM_MARGIN_SECONDS


@pytest.mark.parametrize('context', ['bounded', 'full'])
@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_only_strictly_older_leases_are_reclaimed(db, context, offset):
    old = acquire(db, context=context)
    before = deepcopy(db.rows)
    new = acquire(db, NOW + timedelta(seconds=deadline(context) + offset), context=context)
    if offset <= 0:
        assert new is None
        state = ('dream_users', UID)
        assert db.rows[state]['lease'] == before[state]['lease']
        assert db.rows[DIRTY] == before[DIRTY]
        for path, row in before.items():
            if path != state:
                assert db.rows[path] == row
        assert db.rows[('dream_due', UID)]['due_at'] == old['started_at'] + timedelta(seconds=1741)
    else:
        assert new['run_id'] != old['run_id']
        assert db.rows[('dream_users', UID)]['lease'] == new
        assert db.rows[DIRTY] == before[DIRTY]
        assert db.rows[('dream_users', UID)]['abandoned_passes'] == 1
        assert db.rows[('dream_users', UID, 'spend', old['day'])]['reserved_usd'] == pytest.approx(0)
        # One transaction contains the old report, charge and replacement lease.
        paths = {path for path, _ in db.transactions[-1].sets}
        assert paths == {
            ('users', UID, 'dream_runs', old['run_id']),
            ('dream_users', UID),
            ('dream_users', UID, 'spend', old['day']),
        }
        assert not any('dirty' in path or 'reviews' in path for path in paths)


def test_legacy_short_context_cannot_shorten_the_v2_reclaim_fence(db):
    old = acquire(db)
    db.rows[('dream_users', UID)]['lease']['context_mode'] = 'bounded'
    assert acquire(db, NOW + timedelta(seconds=301)) is None
    assert db.rows[('dream_users', UID)]['lease']['run_id'] == old['run_id']
    assert acquire(db, NOW + timedelta(seconds=1741)) is not None


@pytest.mark.parametrize('scope', ['user', 'legacy'])
@pytest.mark.parametrize('previous_charge', [None, 0.08, 0.0])
def test_unknown_usage_restores_full_reservation_only_on_original_day_ledger(db, scope, previous_charge):
    old = acquire(db)
    current = db.rows[('dream_users', UID)]['lease']
    old_path = ('dream_users', UID, 'spend', old['day'])
    if scope == 'legacy':
        current.pop('spend_scope')
        legacy_path = ('dream_spend', old['day'])
        db.rows[legacy_path] = db.rows.pop(old_path)
        old_path = legacy_path
    if previous_charge is not None:
        current['budget_charge_usd'] = previous_charge
        current['admission_refunded'] = previous_charge == 0
        db.rows[old_path]['reserved_usd'] = 7 + previous_charge
    else:
        current.pop('budget_charge_usd')
        db.rows[old_path]['reserved_usd'] = 7 + old['reservation_usd']
    original_dirty = deepcopy(db.rows[DIRTY])
    later = NOW + timedelta(days=1)
    today_path = ('dream_users', UID, 'spend', later.date().isoformat())
    db.rows[today_path] = {'reserved_usd': 11}
    new = acquire(db, later)
    assert new['day'] != old['day']
    assert db.rows[old_path]['reserved_usd'] == pytest.approx(7 + old['reservation_usd'])
    assert db.rows[today_path]['reserved_usd'] == pytest.approx(11)
    assert db.rows[DIRTY] == original_dirty
    run = db.rows[('users', UID, 'dream_runs', old['run_id'])]
    assert run['success'] is False and run['records_queued_after'] == 1
    assert run['tokens'] == 0 and run['cost_status'] == 'unpriced' and 'cost_usd' not in run
    assert run['source'] == {
        'status': 'failed',
        'reason': 'abandoned',
        'usage_unknown': True,
        'size_bucket': 'light',
        'abandoned': 1,
        'tokens': 0,
        'records_queued_after': 1,
        'budget_charge_usd': old['reservation_usd'] if previous_charge is None else previous_charge,
        'cost_status': 'unpriced',
    }
    if scope == 'legacy':
        assert ('dream_users', UID, 'spend', old['day']) not in db.rows


def test_abandoned_run_omits_cost_when_one_settled_turn_is_unpriced(db):
    old = acquire(db)
    lease = db.rows[('dream_users', UID)]['lease']
    lease['turn_receipts'] = [
        {
            'tokens': 100,
            'accounted_tokens': 100,
            'cached_tokens': 0,
            'cost_status': 'priced',
            'cost_micro_usd': 500000,
        },
        {'tokens': 40, 'accounted_tokens': 40, 'cached_tokens': 0, 'cost_status': 'unpriced'},
    ]
    lease['budget_charge_usd'] = 1.25
    lease['reservation_usd'] = 1.25
    assert acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1)) is not None
    run = db.rows[('users', UID, 'dream_runs', old['run_id'])]
    assert run['tokens'] == 140 and run['cost_status'] == 'unpriced' and 'cost_usd' not in run
    assert run['source']['tokens'] == 140
    assert run['source']['usage_unknown'] is True
    assert run['source']['cost_status'] == 'unpriced'
    assert 'cost_usd' not in run['source']
    assert run['source']['budget_charge_usd'] == pytest.approx(1.25)


def test_abandoned_run_includes_cost_when_every_receipt_is_priced(db):
    old = acquire(db)
    lease = db.rows[('dream_users', UID)]['lease']
    lease['turn_receipts'] = [
        {
            'tokens': 80,
            'accounted_tokens': 80,
            'cached_tokens': 10,
            'cost_status': 'priced',
            'cost_micro_usd': 250000,
        },
        {
            'tokens': 20,
            'accounted_tokens': 20,
            'cached_tokens': 0,
            'cost_status': 'priced',
            'cost_micro_usd': 750000,
        },
    ]
    lease['budget_charge_usd'] = 1.0
    lease['reservation_usd'] = 1.0
    assert acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1)) is not None
    run = db.rows[('users', UID, 'dream_runs', old['run_id'])]
    assert run['tokens'] == 100 and run['cost_status'] == 'priced'
    assert run['cost_usd'] == pytest.approx(1.0)
    assert run['source']['usage_unknown'] is False
    assert run['source']['cost_usd'] == pytest.approx(1.0)
    assert run['source']['budget_charge_usd'] == pytest.approx(1.0)


def test_late_finish_cannot_clobber_new_lease_spend_report_or_dirty_versions(db):
    old = acquire(db)
    new = acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1))
    before = deepcopy(db.rows)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        dream_store.finish(
            UID,
            old,
            {'tokens': 1, 'usage_unknown': False},
            success=True,
            consumed=[db.rows[DIRTY]],
            refund=True,
            firestore_client=db,
        )
    assert db.rows == before
    assert db.rows[('dream_users', UID)]['lease']['run_id'] == new['run_id']
    assert not db.transactions[-1].has_written


@pytest.mark.parametrize('trigger,reason', [('schedule', None), ('manual', 'dream_manual_limit')])
def test_reclamation_commits_even_when_new_admission_is_denied(db, trigger, reason):
    old = acquire(db)
    db.rows[('dream_users', UID)].update(passes=24, manual_runs=3)
    at = NOW + timedelta(seconds=deadline('bounded') + 1)
    if reason:
        with pytest.raises(dream_store.AdmissionDenied, match=reason):
            acquire(db, at, trigger=trigger)
    else:
        assert acquire(db, at, trigger=trigger) is None
    state = db.rows[('dream_users', UID)]
    assert state['lease'] is None and state['abandoned_passes'] == 1
    assert state['passes'] == 24 and state['manual_runs'] == 3
    assert db.rows[('dream_users', UID, 'spend', old['day'])]['reserved_usd'] == old['reservation_usd']
    assert db.rows[DIRTY]['failed_passes'] == 2


def test_reclamation_recharges_same_day_before_applying_daily_cap(db):
    old = acquire(db)
    db.rows[('dream_users', UID)]['lease']['reservation_usd'] = 1.0
    db.rows[('dream_users', UID)]['lease']['budget_charge_usd'] = 0
    db.rows[('dream_users', UID, 'spend', old['day'])]['reserved_usd'] = 249.5
    assert acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1)) is None
    assert db.rows[('dream_users', UID, 'spend', old['day'])]['reserved_usd'] == pytest.approx(250.5)
    assert db.rows[('dream_users', UID)]['lease'] is None


def test_idle_reclamation_preserves_watermark_and_score(db):
    old = acquire(db)
    del db.rows[DIRTY]
    db.rows[('dream_users', UID)]['score'] = 0
    before = deepcopy(db.rows[('dream_users', UID)])
    replacement = acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1))
    assert replacement and replacement['hunt']
    state = db.rows[('dream_users', UID)]
    assert state['lease']['run_id'] == replacement['run_id'] and state['score'] == 0
    assert state.get('watermark') == before.get('watermark')
    assert old['run_id'] in {path[-1] for path in db.rows if 'dream_runs' in path}


def test_reclaim_details_return_only_for_the_committed_claim(db):
    acquire(db)
    reclaimed = {}
    acquire(db, NOW + timedelta(seconds=deadline('bounded') + 1), reclaim_sink=reclaimed)
    assert reclaimed == {'age_s': 1741, 'size_bucket': 'light'}
    next_reclaimed = {}
    assert acquire(db, NOW + timedelta(seconds=deadline('bounded') + 2), reclaim_sink=next_reclaimed) is None
    assert next_reclaimed == {}


def test_reclaim_details_return_even_when_manual_admission_is_denied(db):
    acquire(db, trigger='manual')
    state = db.rows[('dream_users', UID)]
    state['manual_runs'] = caps().manual_runs
    reclaimed = {}
    with pytest.raises(dream_store.AdmissionDenied):
        acquire(db, NOW + timedelta(seconds=1741), trigger='manual', reclaim_sink=reclaimed)
    assert reclaimed == {'age_s': 1741, 'size_bucket': 'light'}
    assert db.rows[('dream_users', UID)]['lease'] is None


def test_failed_commit_does_not_publish_reclaim_details(db, monkeypatch):
    acquire(db)
    reclaimed = {}

    def fail_commit(fn):
        def claim_then_fail(transaction):
            fn(transaction)
            raise RuntimeError('synthetic commit failure')

        return claim_then_fail

    monkeypatch.setattr(dream_store.firestore, 'transactional', fail_commit)
    with pytest.raises(RuntimeError, match='synthetic commit failure'):
        acquire(db, NOW + timedelta(seconds=1741), reclaim_sink=reclaimed)
    assert reclaimed == {}
