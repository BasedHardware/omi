"""Regression test: GET /v1/dev/user/goals must honour `limit` when include_inactive=true.

routers.developer.get_goals clamps `limit` to [1, 1000] and then branches. The default branch
calls goals_db.get_user_goals(uid, limit=limit), which is bounded. The include_inactive=True
branch called goals_db.get_all_goals(uid, include_inactive=True), which has no limit parameter
and streams the whole goals collection, so the clamp was dead code on that branch and the
endpoint returned every goal the user had ever created -- ignoring its own documented
"**limit**: Maximum number of goals to return". The limit is now applied to that result.

get_all_goals is deliberately unbounded (it is also the "fetch everything" helper behind
/v1/dev/user/goals/{goal_id}, routers/goals.py::get_all_goals and the MCP goal reads), so the
bound belongs at this call site rather than in the shared helper.
"""

import routers.developer as developer


def _fake_goals(count):
    return [{'id': f'g{index}', 'title': f'goal {index}'} for index in range(count)]


def test_include_inactive_honours_limit(monkeypatch):
    monkeypatch.setattr(developer.goals_db, 'get_all_goals', lambda uid, include_inactive=False: _fake_goals(25))

    result = developer.get_goals(uid='u1', limit=5, include_inactive=True)

    assert len(result) == 5
    assert [goal['id'] for goal in result] == ['g0', 'g1', 'g2', 'g3', 'g4']


def test_include_inactive_applies_the_clamp_ceiling(monkeypatch):
    monkeypatch.setattr(developer.goals_db, 'get_all_goals', lambda uid, include_inactive=False: _fake_goals(1500))

    result = developer.get_goals(uid='u1', limit=99999, include_inactive=True)

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
