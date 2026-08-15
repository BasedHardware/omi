"""Regression test: GET /v1/dev/user/goals must honour `limit` when include_inactive=true.

routers.developer.get_goals clamps `limit` to [1, 1000] and then branches. The default branch
calls goals_db.get_user_goals(uid, limit=limit), which is bounded. The include_inactive=True
branch called goals_db.get_all_goals(uid, include_inactive=True), which had no limit parameter
and streamed the whole goals collection, so the clamp was dead code on that branch and the
endpoint returned every goal the user had ever created -- ignoring its own documented
"**limit**: Maximum number of goals to return".

The clamp is now passed down and applied after the in-Python newest-first sort. The bound is
deliberately not pushed into the Firestore query: order_by('created_at') excludes documents
missing the field, and legacy goals can lack created_at, so a query-level bound would silently
drop them. These tests assert the bounded page is the NEWEST goals, that dateless legacy goals
survive bounding (sorting last), and that the bounded path is taken by the route.

get_all_goals stays fetch-everything by default for its other callers
(/v1/dev/user/goals/{goal_id}, routers/goals.py::get_all_goals, and the MCP goal reads); the
limit is opt-in and only this route passes it.
"""

import pytest

import database.goals as goals_db_module
import routers.developer as developer


def _fake_goals(count):
    return [{'id': f'g{index}', 'title': f'goal {index}'} for index in range(count)]


# --- router: the clamp reaches the helper -----------------------------------------------


def test_include_inactive_passes_the_clamp_down_to_the_query(monkeypatch):
    captured = {}

    def get_all_goals(uid, include_inactive=False, *, limit=None):
        captured.update(uid=uid, include_inactive=include_inactive, limit=limit)
        return _fake_goals(min(limit, 25))

    monkeypatch.setattr(developer.goals_db, 'get_all_goals', get_all_goals)

    result = developer.get_goals(uid='u1', limit=5, include_inactive=True)

    # The bound is delegated, not applied after the fact.
    assert captured == {'uid': 'u1', 'include_inactive': True, 'limit': 5}
    assert len(result) == 5


def test_include_inactive_delegates_the_clamp_ceiling(monkeypatch):
    captured = {}

    def get_all_goals(uid, include_inactive=False, *, limit=None):
        captured.update(limit=limit)
        return _fake_goals(limit)

    monkeypatch.setattr(developer.goals_db, 'get_all_goals', get_all_goals)

    result = developer.get_goals(uid='u1', limit=99999, include_inactive=True)

    assert captured == {'limit': 1000}
    assert len(result) == 1000


def test_active_only_branch_still_delegates_the_limit(monkeypatch):
    captured = {}

    def get_user_goals(uid, limit):
        captured.update(uid=uid, limit=limit)
        return _fake_goals(3)

    monkeypatch.setattr(developer.goals_db, 'get_user_goals', get_user_goals)

    result = developer.get_goals(uid='u1', limit=3, include_inactive=False)

    assert captured == {'uid': 'u1', 'limit': 3}
    assert len(result) == 3


# --- database: the page is the newest goals and legacy goals survive ---------------------


class _FakeDoc:
    def __init__(self, doc_id, payload):
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeCollection:
    """Streams the given docs; records whether a query-level order/limit was pushed down
    (it must NOT be — that is the legacy-goal-dropping shape this fix avoids)."""

    def __init__(self, docs, calls):
        self._docs = docs
        self.calls = calls

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def where(self, **kwargs):
        self.calls.append(('where', kwargs))
        return self

    def order_by(self, field, direction=None):
        self.calls.append(('order_by', field, direction))
        return self

    def limit(self, count):
        self.calls.append(('limit', count))
        return self

    def stream(self):
        return iter(self._docs)


def _docs(count):
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        _FakeDoc(
            f'g{index}',
            {'created_at': base + timedelta(days=index), 'is_active': True, 'status': 'background'},
        )
        for index in range(count)
    ]


def test_get_all_goals_bounded_page_is_the_newest_goals():
    calls = []
    client = _FakeCollection(_docs(50), calls)

    result = goals_db_module.get_all_goals('u1', include_inactive=True, limit=5, firestore_client=client)

    # Newest first: the docs were streamed oldest-first, so the page must be the LAST five
    # ids in reverse creation order — proving the sort ran before the slice.
    assert [g['id'] for g in result] == ['g49', 'g48', 'g47', 'g46', 'g45']
    # And the bound was never pushed into the query, where order_by('created_at') would
    # exclude legacy goals lacking the field.
    assert not any(call[0] in ('order_by', 'limit') for call in calls)


def test_get_all_goals_keeps_legacy_goals_without_created_at():
    calls = []
    dated = _docs(3)
    legacy = _FakeDoc('legacy', {'is_active': True, 'status': 'background'})  # no created_at
    client = _FakeCollection(dated + [legacy], calls)

    result = goals_db_module.get_all_goals('u1', include_inactive=True, limit=10, firestore_client=client)

    # The dateless legacy goal is retained (a query-level order_by would have dropped it)
    # and sorts deterministically last.
    assert [g['id'] for g in result] == ['g2', 'g1', 'g0', 'legacy']


def test_get_all_goals_bounds_still_apply_over_legacy_goals():
    client = _FakeCollection(_docs(2) + [_FakeDoc('legacy', {'is_active': True, 'status': 'background'})], [])

    result = goals_db_module.get_all_goals('u1', include_inactive=True, limit=2, firestore_client=client)

    # Dated goals fill the page first; the dateless one only appears when room remains.
    assert [g['id'] for g in result] == ['g1', 'g0']


def test_get_all_goals_stays_unbounded_for_existing_callers():
    calls = []
    client = _FakeCollection(_docs(50), calls)

    result = goals_db_module.get_all_goals('u1', include_inactive=True, firestore_client=client)

    assert not any(call[0] in ('limit', 'order_by') for call in calls)
    assert len(result) == 50
