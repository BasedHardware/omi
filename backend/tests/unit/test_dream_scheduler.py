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


def test_all_users_rotation_reaches_never_dirty_owners_and_wraps(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    db = DreamFirestore()
    rows = [SimpleNamespace(id=f'owner-{i:03}', to_dict=lambda: {}) for i in range(205)]

    def page(after=None, limit=100, **kwargs):
        start = next((i + 1 for i, row in enumerate(rows) if row.id == after), 0)
        return rows[start : start + limit]

    monkeypatch.setattr(dream_scheduler, 'candidate_page', page)
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    seen = []
    for _ in range(3):
        result = dream_scheduler.candidates(now=NOW, firestore_client=db)
        seen.extend(result)
        dream_scheduler.advance(result, set(result), firestore_client=db)
    assert seen == [row.id for row in rows]
    assert dream_scheduler.candidates(now=NOW, firestore_client=db)[0] == rows[0].id


def test_skipped_ineligible_owners_advance_but_unattempted_work_does_not(monkeypatch):
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    db = DreamFirestore()
    page = dream_scheduler.CandidatePage(['b', 'c'], ordered=['a', 'b', 'c'], after=None, skipped=['a'])
    dream_scheduler.advance(page, {'b'}, firestore_client=db)
    assert db.rows[('dream_scheduler', 'rotation')]['after'] == 'b'
    stale = dream_scheduler.CandidatePage(['c'], ordered=['c'], after=None)
    dream_scheduler.advance(stale, {'c'}, firestore_client=db)
    assert db.rows[('dream_scheduler', 'rotation')]['after'] == 'b'


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
    caps = Caps(global_daily_usd=3, tokens=96000, tokens_per_minute=100)
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
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] == pytest.approx(0.96)
    runtime.rows[('users', 'other')] = {}
    runtime.rows[('dream_global_spend', day)]['reserved_usd'] = 3
    assert dream_store.acquire('other', caps, now=NOW) is None


def test_empty_backlog_hunt_is_daily_and_stale_lease_reclaim_is_1740_seconds(runtime):
    lease = dream_store.acquire(UID, Caps(tokens=96000), now=NOW)
    assert lease and lease['hunt']
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1740)) is None
    replacement = dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1741))
    assert replacement and replacement['run_id'] != lease['run_id']
    dream_store.finish(UID, replacement, {'tokens': 10, 'usage_unknown': False}, success=True, now=NOW)
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(hours=2)) is None
