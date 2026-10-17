"""All-user rotation, work/hunt eligibility and reserved minute admission."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from config.dream_agent import Caps, eligible
from database import dream_scheduler, dream_store, dream_turns
from tests.support.dream_firestore import DreamFirestore
from tests.unit.test_dream_harness_runtime import runtime, store, UID
from utils.llm.shaped_agent import Turn

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def test_due_queue_orders_backlog_and_staleness_independently_of_discovery(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    db = DreamFirestore()
    seen = []
    monkeypatch.setattr(dream_scheduler, 'discover', lambda database, now: seen.append(database))

    class Query:
        def where(self, *, filter):
            assert filter.field_path == 'due_at' and filter.op_string == '<='
            return self

        def order_by(self, field):
            assert field == 'due_at'
            return self

        def limit(self, count):
            assert count == 5000
            return self

        def stream(self, **kwargs):
            return [SimpleNamespace(id='old-backlog'), SimpleNamespace(id='due-hunt')]

    original = db.collection
    monkeypatch.setattr(db, 'collection', lambda name: Query() if name == 'dream_due' else original(name))
    page = dream_scheduler.candidates(limit=5000, now=NOW, firestore_client=db)
    assert page == ['old-backlog', 'due-hunt'] and seen == [db]
    assert not db.rows  # Unattempted work is retained by the queue, never cursor-skipped.


def test_staleness_and_backlog_priority_are_bounded():
    old = {'last_pass_at': NOW - timedelta(days=2), 'score': 1}
    fresh = {'last_pass_at': NOW, 'score': 500}
    assert dream_scheduler.priority(old, NOW) > dream_scheduler.priority(fresh, NOW)
    assert dream_scheduler.priority({'score': 500}, NOW)[0] == dream_scheduler.priority({'score': 500000}, NOW)[0]


@pytest.mark.parametrize('policy,allowed', [('all', True), ('paid', False), ('allowlist', False), ('unknown', False)])
def test_eligibility_defaults_and_optional_restrictions(monkeypatch, policy, allowed):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', policy)
    monkeypatch.delenv('DREAM_AGENT_UID_ALLOWLIST', raising=False)
    assert eligible('synthetic', {}) is allowed
    assert not eligible('dream-canary-synthetic', {})
    assert not eligible('synthetic', {'deleted': True})


def test_minute_ceiling_is_shared_and_owner_daily_usd_is_not_global(runtime):
    caps = Caps(tokens=96000, tokens_per_minute=100, daily_usd=0.0003)
    lease = dream_store.acquire(UID, caps, now=NOW)
    assert lease
    dream_turns.reserve(UID, lease['run_id'], 60, caps, now=NOW)
    with pytest.raises(ValueError, match='dream_minute_headroom'):
        dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        dream_turns.reserve(UID, 'stale-run', 1, caps, now=NOW)
    dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW + timedelta(minutes=1))
    settled = Turn(tokens=20, prompt_tokens=15, cached_tokens=5)
    settled.cost_status = 'priced'
    settled.cost_micro_usd = 200
    dream_turns.settle(UID, lease['run_id'], settled)
    day = lease['day']
    assert runtime.rows[('dream_users', UID, 'spend', day)]['observed_usd'] == pytest.approx(0.0002)
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] == pytest.approx(0.0002)
    runtime.rows[('users', 'other')] = {}
    runtime.rows[('dream_users', 'other')] = {'score': 1}
    runtime.rows[('dream_users', 'other', 'dirty', dream_store.dirty_id('conversations', 'synthetic'))] = {
        'collection': 'conversations',
        'id': 'synthetic',
        'version': 'synthetic-version',
        'last_changed_at': NOW,
    }
    runtime.rows[('dream_global_spend', day + '-0')] = {'reserved_usd': 3}
    assert dream_store.acquire('other', caps, now=NOW) is not None
    dream_store.finish(UID, lease, {'tokens': 20, 'usage_unknown': True}, success=True, now=NOW)
    runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] = caps.daily_usd
    assert dream_store.acquire(UID, caps, now=NOW + timedelta(seconds=1)) is None


def test_empty_backlog_hunt_is_daily_and_stale_lease_reclaim_is_1740_seconds(runtime):
    lease = dream_store.acquire(UID, Caps(tokens=96000), now=NOW)
    assert lease and lease['hunt']
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1740)) is None
    replacement = dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1741))
    assert replacement and replacement['run_id'] != lease['run_id']
    dream_store.finish(UID, replacement, {'tokens': 10, 'usage_unknown': False}, success=True, now=NOW)
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(hours=2)) is None


def test_dirty_priority_orders_backlog_and_staleness_not_user_document_id(runtime):
    old = {'last_pass_at': NOW - timedelta(days=2), 'score': 1}
    new = {'last_pass_at': NOW - timedelta(days=1), 'score': 1}
    busy = {'last_pass_at': NOW - timedelta(days=1), 'score': 20}
    assert dream_scheduler.due_time(old, NOW) < dream_scheduler.due_time(new, NOW)
    assert dream_scheduler.due_time(busy, NOW) < dream_scheduler.due_time(new, NOW)


@pytest.mark.parametrize(
    'raw,bucket,hours',
    [
        ('', 'light', 24),
        ('', 'heavy', 6),
        ('2', 'light', 2),
        ('2', 'heavy', 2),
        ('48', 'light', 24),
        ('0', 'light', 24),
        ('x', 'heavy', 6),
    ],
)
def test_hunt_interval_override_only_shortens(monkeypatch, raw, bucket, hours):
    from config.dream_agent import hunt_interval

    monkeypatch.setenv('DREAM_AGENT_HUNT_INTERVAL_HOURS', raw)
    assert hunt_interval(bucket) == timedelta(hours=hours)
    assert dream_scheduler.due_time({'last_pass_at': NOW, 'size_bucket': bucket}, NOW) == NOW + timedelta(hours=hours)


def test_short_hunt_interval_and_high_pass_cap_admit_repeat_hunts(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_HUNT_INTERVAL_HOURS', '1')
    caps = Caps(tokens=96000, passes=48)
    for hour in range(4):
        lease = dream_store.acquire(UID, caps, now=NOW + timedelta(hours=hour))
        assert lease and lease['hunt']
        dream_store.finish(
            UID, lease, {'tokens': 10, 'usage_unknown': False}, success=True, now=NOW + timedelta(hours=hour)
        )
    assert dream_store.acquire(UID, caps, now=NOW + timedelta(hours=3, minutes=30)) is None


def test_allowlist_discovery_reads_only_listed_owners(monkeypatch):
    store = DreamFirestore()
    store.collection('users').document('listed-owner').set({'plan': 'free'})
    store.collection('users').document('other-owner').set({'plan': 'free'})
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', 'listed-owner,missing-owner')
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)

    def scan(**kwargs):
        raise AssertionError('allowlist discovery must not scan users')

    monkeypatch.setattr(dream_scheduler, 'candidate_page', scan)
    dream_scheduler.discover(store, NOW)
    assert store.collection('dream_due').document('listed-owner').get().exists
    assert not store.collection('dream_due').document('other-owner').get().exists
    assert not store.collection('dream_due').document('missing-owner').get().exists
    assert not store.collection('dream_scheduler').document('discovery').get().exists
