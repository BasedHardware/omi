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


def test_global_usd_and_minute_ceiling_are_shared_and_owner_lease_is_fenced(runtime):
    caps = Caps(global_daily_usd=3, global_spend_shards=1, tokens=96000, tokens_per_minute=100)
    lease = dream_store.acquire(UID, caps, now=NOW)
    assert lease
    dream_turns.reserve(UID, lease['run_id'], 60, caps, now=NOW)
    with pytest.raises(ValueError, match='dream_minute_headroom'):
        dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        dream_turns.reserve(UID, 'stale-run', 1, caps, now=NOW)
    dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW + timedelta(minutes=1))
    dream_turns.settle(UID, lease['run_id'], Turn(tokens=20, prompt_tokens=15, cached_tokens=5))
    day = lease['day']
    assert runtime.rows[('dream_users', UID, 'spend', day)]['observed_usd'] == pytest.approx(0.0002)
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] == pytest.approx(0.0002)
    runtime.rows[('users', 'other')] = {}
    runtime.rows[('dream_global_spend', day + '-0')]['reserved_usd'] = 3
    assert dream_store.acquire('other', caps, now=NOW) is None


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
