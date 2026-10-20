"""get_user_goals must not truncate before it filters and sorts.

The query has no order_by, so ``.limit(limit)`` returns the first ``limit``
active rows in document-id order. The ended-goal filter and the oldest-first
sort both run in Python, so a limit pushed into the query drops active goals
whose document ids sort later, and an ended row inside the first page comes
back as a short page. Mentor notifications and deep daily recaps call this
with ``limit=3``.
"""

from datetime import datetime, timezone

import database.goals as goals_db

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Goals:
    """Streams documents in document-id order and honours ``limit``, like Firestore."""

    def __init__(self, goals):
        self._goals = goals
        self._limit = None

    def where(self, *args, **kwargs):
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        docs = [_Doc(doc_id, self._goals[doc_id]) for doc_id in sorted(self._goals)]
        return docs if self._limit is None else docs[: self._limit]


class _UserDoc:
    def __init__(self, goals):
        self._goals = goals

    def collection(self, _name):
        return _Goals(self._goals)


class _Users:
    def __init__(self, goals):
        self._goals = goals

    def document(self, _doc_id):
        return _UserDoc(self._goals)


class _Db:
    def __init__(self, goals):
        self._goals = goals

    def collection(self, _name):
        return _Users(self._goals)


def _goal(day, *, status='background'):
    return {
        'title': f'goal day {day}',
        'status': status,
        'is_active': True,
        'created_at': BASE.replace(day=day),
    }


def test_limit_three_keeps_the_oldest_active_goals_past_the_first_document_ids(monkeypatch):
    """The three oldest goals have the latest document ids, so a query limit drops them."""
    goals = {
        'goal_a': _goal(6),
        'goal_b': _goal(5),
        'goal_c': _goal(4),
        'goal_d': _goal(1),
        'goal_e': _goal(2),
        'goal_f': _goal(3),
    }
    monkeypatch.setattr(goals_db, '_get_db', lambda firestore_client=None: _Db(goals))

    result = goals_db.get_user_goals('u1', limit=3)

    assert [goal['id'] for goal in result] == ['goal_d', 'goal_e', 'goal_f']


def test_ended_rows_inside_the_first_page_do_not_shorten_the_result(monkeypatch):
    goals = {
        'goal_a': _goal(1, status='achieved'),
        'goal_b': _goal(2, status='abandoned'),
        'goal_c': _goal(3, status='achieved'),
        'goal_d': _goal(4),
        'goal_e': _goal(5),
        'goal_f': _goal(6),
    }
    monkeypatch.setattr(goals_db, '_get_db', lambda firestore_client=None: _Db(goals))

    result = goals_db.get_user_goals('u1', limit=3)

    assert [goal['id'] for goal in result] == ['goal_d', 'goal_e', 'goal_f']
