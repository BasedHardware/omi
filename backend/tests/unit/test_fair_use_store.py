"""Behavioral tests for ``database.fair_use`` over the neutral storage port (WP2).

Before the storage-port migration this module talked to the raw Firestore client, so no unit test
exercised its real read/write logic (the fair-use suites stub the whole ``database.fair_use``
module). These tests drive the *real* functions through a ``FakeDocumentStore`` injected at the
``_store`` seam, asserting on returned values and stored state — including the two cross-parent
``query_group`` (collection-group) paths that the port gained for this migration.
"""

from datetime import datetime, timedelta, timezone

import pytest

import database.fair_use as fair_use_db
from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(fair_use_db, '_store', lambda: fake)
    return fake


class TestFairUseState:
    def test_get_missing_returns_empty_dict(self, store):
        assert fair_use_db.get_fair_use_state('u1') == {}

    def test_update_then_get_roundtrip(self, store):
        fair_use_db.update_fair_use_state('u1', {'stage': 'warning'})
        state = fair_use_db.get_fair_use_state('u1')
        assert state['stage'] == 'warning'
        # update stamps updated_at and persists at the exact user-scoped path
        assert isinstance(state['updated_at'], datetime)
        assert 'users/u1/fair_use_state/current' in store._docs

    def test_update_merges_not_replaces(self, store):
        fair_use_db.update_fair_use_state('u1', {'stage': 'warning', 'a': 1})
        fair_use_db.update_fair_use_state('u1', {'stage': 'throttle'})
        state = fair_use_db.get_fair_use_state('u1')
        assert state['stage'] == 'throttle'
        assert state['a'] == 1  # earlier field survives the merge

    def test_set_stage_and_reset(self, store):
        fair_use_db.set_fair_use_stage('u1', 'restrict', last_classifier_score=0.9)
        assert fair_use_db.get_fair_use_state('u1')['stage'] == 'restrict'
        fair_use_db.reset_fair_use_state('u1', admin_uid='admin1')
        state = fair_use_db.get_fair_use_state('u1')
        assert state['stage'] == 'none'
        assert state['reset_by'] == 'admin1'
        assert state['violation_count_7d'] == 0


class TestFairUseEvents:
    def test_create_event_returns_id_and_stamps_fields(self, store):
        event_id = fair_use_db.create_fair_use_event('u1', {'reason': 'x'})
        assert isinstance(event_id, str) and event_id
        stored = store.get(f'users/u1/fair_use_events/{event_id}').to_dict()
        assert stored['reason'] == 'x'
        assert isinstance(stored['created_at'], datetime)
        assert stored['case_ref'].startswith('FU-')

    def test_get_events_newest_first_and_carry_id(self, store):
        now = datetime.now(timezone.utc)
        store.set('users/u1/fair_use_events/old', {'created_at': now - timedelta(days=2)})
        store.set('users/u1/fair_use_events/new', {'created_at': now})
        events = fair_use_db.get_fair_use_events('u1')
        assert [e['id'] for e in events] == ['new', 'old']

    def test_get_events_respects_limit(self, store):
        now = datetime.now(timezone.utc)
        for i in range(5):
            store.set(f'users/u1/fair_use_events/e{i}', {'created_at': now - timedelta(minutes=i)})
        assert len(fair_use_db.get_fair_use_events('u1', limit=3)) == 3

    def test_violation_counts_7d_and_30d(self, store):
        now = datetime.now(timezone.utc)
        store.set('users/u1/fair_use_events/a', {'created_at': now - timedelta(days=1)})
        store.set('users/u1/fair_use_events/b', {'created_at': now - timedelta(days=10)})
        store.set('users/u1/fair_use_events/c', {'created_at': now - timedelta(days=40)})  # outside 30d
        counts = fair_use_db.get_violation_counts('u1')
        assert counts == {'violation_count_7d': 1, 'violation_count_30d': 2}

    def test_resolve_event_updates_in_place(self, store):
        store.set('users/u1/fair_use_events/e1', {'reason': 'x'})
        fair_use_db.resolve_fair_use_event('u1', 'e1', 'admin1', notes='ok')
        stored = store.get('users/u1/fair_use_events/e1').to_dict()
        assert stored['resolved'] is True
        assert stored['resolved_by'] == 'admin1'
        assert stored['admin_notes'] == 'ok'
        assert stored['reason'] == 'x'  # original field preserved


class TestAdminGroupQueries:
    """The two collection-group (query_group) paths: scan across all users' subcollections."""

    def test_flagged_users_default_filters_and_uid_extraction(self, store):
        now = datetime.now(timezone.utc)
        store.set('users/u1/fair_use_state/current', {'stage': 'warning', 'updated_at': now - timedelta(hours=2)})
        store.set('users/u2/fair_use_state/current', {'stage': 'restrict', 'updated_at': now})
        store.set('users/u3/fair_use_state/current', {'stage': 'none', 'updated_at': now})  # excluded

        flagged = fair_use_db.get_flagged_users()
        # newest updated_at first, 'none' excluded, uid recovered from the logical path
        assert [f['uid'] for f in flagged] == ['u2', 'u1']
        assert flagged[0]['stage'] == 'restrict'
        assert flagged[0]['id'] == 'current'

    def test_flagged_users_stage_filter(self, store):
        now = datetime.now(timezone.utc)
        store.set('users/u1/fair_use_state/current', {'stage': 'warning', 'updated_at': now})
        store.set('users/u2/fair_use_state/current', {'stage': 'restrict', 'updated_at': now})
        flagged = fair_use_db.get_flagged_users(stage_filter='restrict')
        assert [f['uid'] for f in flagged] == ['u2']

    def test_flagged_users_respects_limit(self, store):
        now = datetime.now(timezone.utc)
        for i in range(4):
            store.set(f'users/u{i}/fair_use_state/current', {'stage': 'warning', 'updated_at': now})
        assert len(fair_use_db.get_flagged_users(limit=2)) == 2

    def test_lookup_by_case_ref_found(self, store):
        store.set('users/u7/fair_use_events/evt', {'case_ref': 'FU-ABC123', 'reason': 'x'})
        found = fair_use_db.lookup_fair_use_event_by_case_ref('FU-ABC123')
        assert found is not None
        assert found['uid'] == 'u7'
        assert found['event_id'] == 'evt'
        assert found['reason'] == 'x'

    def test_lookup_by_case_ref_not_found(self, store):
        store.set('users/u7/fair_use_events/evt', {'case_ref': 'FU-ABC123'})
        assert fair_use_db.lookup_fair_use_event_by_case_ref('FU-NOPE') is None
