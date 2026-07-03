"""GET /v1/goals/completed returns the user's inactive (completed/archived) goals.

The active-goal endpoints (/v1/goals, /v1/goals/all) only ever return active goals, so
once a goal is ended or bumped out of the active set it can no longer be queried and the
user's goal history becomes invisible. The endpoint filters get_all_goals(include_inactive=True)
down to the inactive goals, newest first, and serializes their datetimes.

Test isolation: routers.goals imports cleanly, so we monkeypatch the import-cheap goals_db
attribute and call the handler directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timezone  # noqa: E402

from routers import goals as goals_mod  # noqa: E402


def _goal(gid, is_active, **extra):
    g = {'id': gid, 'title': gid, 'is_active': is_active}
    g.update(extra)
    return g


def test_completed_goals_returns_only_inactive_preserving_order(monkeypatch):
    dt = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    # get_all_goals(include_inactive=True) returns active + inactive, newest first.
    all_goals = [
        _goal('active_now', True, created_at=dt),
        _goal('done_new', False, created_at=dt, updated_at=dt, ended_at=dt),
        _goal('done_old', False, created_at=dt),
    ]
    captured = {}

    def fake_get_all_goals(uid, include_inactive=False):
        captured['uid'] = uid
        captured['include_inactive'] = include_inactive
        return all_goals

    monkeypatch.setattr(goals_mod.goals_db, 'get_all_goals', fake_get_all_goals)

    result = goals_mod.get_completed_goals(uid='u1')

    # Only the inactive goals, order preserved (newest first).
    assert [g['id'] for g in result] == ['done_new', 'done_old']
    # Queried with include_inactive so the DB returns the full set.
    assert captured == {'uid': 'u1', 'include_inactive': True}
    # Datetime fields serialized to ISO strings, including ended_at.
    assert result[0]['created_at'] == '2026-05-01T12:00:00+00:00'
    assert result[0]['ended_at'] == '2026-05-01T12:00:00+00:00'


def test_completed_goals_empty_when_all_active(monkeypatch):
    monkeypatch.setattr(
        goals_mod.goals_db,
        'get_all_goals',
        lambda uid, include_inactive=False: [{'id': 'g1', 'is_active': True}],
    )
    assert goals_mod.get_completed_goals(uid='u1') == []


def test_completed_goals_treats_missing_is_active_as_inactive(monkeypatch):
    # A legacy goal with no is_active field is not returned by the active-only endpoints,
    # so it belongs in the completed/archive view rather than being lost entirely.
    monkeypatch.setattr(
        goals_mod.goals_db,
        'get_all_goals',
        lambda uid, include_inactive=False: [{'id': 'legacy'}],
    )
    assert [g['id'] for g in goals_mod.get_completed_goals(uid='u1')] == ['legacy']
