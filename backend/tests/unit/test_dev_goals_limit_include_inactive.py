"""Regression test: GET /v1/dev/user/goals must honour `limit` when include_inactive=true.

routers.developer.get_goals clamps `limit` to [1, 1000] and then branches. The default branch
calls goals_db.get_user_goals(uid, limit=limit), which is bounded. The include_inactive=True
branch called goals_db.get_all_goals(uid, include_inactive=True), which had no limit parameter
and streamed the whole goals collection, so the clamp was dead code on that branch and the
endpoint returned every goal the user had ever created -- ignoring its own documented
"**limit**: Maximum number of goals to return".

The clamp is now passed down to the query rather than applied to the result. Slicing the
returned list would fix the payload length but still stream every historical goal first, which
is exactly the cost the clamp's own comment says it prevents ("an oversized limit cannot stream
the whole collection"). So these tests assert the bounded path is *taken*, not only that the
final list is short.

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


# --- database: the query itself is bounded ----------------------------------------------


class _FakeDoc:
    def __init__(self, doc_id, payload):
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeQuery:
    """Records the query builder calls so the test can assert what Firestore was asked for."""

    def __init__(self, docs, calls):
        self._docs = docs
        self.calls = calls

    def where(self, **kwargs):
        self.calls.append(('where', kwargs))
        return self

    def order_by(self, field, direction=None):
        self.calls.append(('order_by', field, direction))
        return self

    def limit(self, count):
        self.calls.append(('limit', count))
        return _FakeQuery(self._docs[:count], self.calls)

    def stream(self):
        return iter(self._docs)


class _FakeClient:
    def __init__(self, docs, calls):
        self._docs = docs
        self._calls = calls

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def where(self, **kwargs):
        return _FakeQuery(self._docs, self._calls).where(**kwargs)

    def order_by(self, field, direction=None):
        return _FakeQuery(self._docs, self._calls).order_by(field, direction)

    def limit(self, count):
        return _FakeQuery(self._docs, self._calls).limit(count)

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


def test_get_all_goals_bounds_the_query_when_limit_is_given():
    calls = []
    client = _FakeClient(_docs(50), calls)

    result = goals_db_module.get_all_goals('u1', include_inactive=True, limit=5, firestore_client=client)

    # The read itself is bounded, and ordered so the bounded page is the newest goals rather
    # than an arbitrary slice that only looks sorted after the in-Python sort.
    assert ('limit', 5) in calls
    assert any(call[0] == 'order_by' and call[1] == 'created_at' for call in calls)
    assert len(result) == 5


def test_get_all_goals_stays_unbounded_for_existing_callers():
    calls = []
    client = _FakeClient(_docs(50), calls)

    result = goals_db_module.get_all_goals('u1', include_inactive=True, firestore_client=client)

    # No limit and no ordering pushed into the query: the other callers still fetch everything.
    assert not any(call[0] == 'limit' for call in calls)
    assert not any(call[0] == 'order_by' for call in calls)
    assert len(result) == 50


def test_get_all_goals_rejects_a_limit_it_cannot_serve():
    # A limit alongside the is_active filter would need a composite index this project does not
    # declare, and Firestore answers a missing composite index with an opaque 500. Fail loudly
    # here instead.
    with pytest.raises(ValueError):
        goals_db_module.get_all_goals('u1', include_inactive=False, limit=5, firestore_client=_FakeClient([], []))
