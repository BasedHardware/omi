import os
from datetime import datetime, timezone

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import database.action_items as action_items_db
import database.notifications as notifications_db
import routers.scores as scores_router


class _Filter:
    def __init__(self, field_path, op_string, value):
        self.field_path, self.op_string, self.value = field_path, op_string, value


class _Doc:
    def __init__(self, doc_id, data):
        self.id, self._data = doc_id, data

    def to_dict(self):
        return self._data


class _Query:
    def __init__(self, docs, filters=()):
        self.docs, self.filters = docs, filters

    def where(self, *, filter):
        return _Query(self.docs, self.filters + ((filter.field_path, filter.op_string, filter.value),))

    def order_by(self, *_a, **_k):
        return self

    def limit(self, _value):
        return self

    def start_after(self, _cursor):
        return _Query([], self.filters)

    def _matching(self):
        docs = self.docs
        for field, op, value in self.filters:
            if op == '==':
                docs = [d for d in docs if d._data.get(field) == value]
            elif op == '>=':
                docs = [d for d in docs if d._data.get(field) is not None and d._data[field] >= value]
            elif op == '<':
                docs = [d for d in docs if d._data.get(field) is not None and d._data[field] < value]
        return docs

    def count(self):
        query = self

        class _Agg:
            def get(self):
                return [[type('C', (), {'value': len(query._matching())})()]]

        return _Agg()

    def stream(self):
        return self._matching()


class _Client:
    def __init__(self, rows):
        self.query = _Query([_Doc(f't{i}', row) for i, row in enumerate(rows)])

    def collection(self, name):
        return self.query if name == action_items_db.action_items_collection else self

    def document(self, _doc_id):
        return self


EVENING_IN_LOS_ANGELES = datetime(2025, 1, 15, 6, tzinfo=timezone.utc)


def _scores(monkeypatch, time_zone, date):
    monkeypatch.setattr(action_items_db, 'FieldFilter', _Filter)
    client = _Client([{'completed': True, 'due_at': EVENING_IN_LOS_ANGELES, 'created_at': EVENING_IN_LOS_ANGELES}])
    monkeypatch.setattr(action_items_db, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(notifications_db, 'get_user_time_zone', lambda uid: time_zone)
    return scores_router.get_scores(date=date, uid='uid')


def test_scores_count_a_task_on_the_users_local_day(monkeypatch):
    assert _scores(monkeypatch, 'America/Los_Angeles', '2025-01-14')['daily']['total_tasks'] == 1
    assert _scores(monkeypatch, 'America/Los_Angeles', '2025-01-15')['daily']['total_tasks'] == 0


def test_scores_without_a_stored_time_zone_keep_the_utc_day(monkeypatch):
    assert _scores(monkeypatch, None, '2025-01-14')['daily']['total_tasks'] == 0
    assert _scores(monkeypatch, None, '2025-01-15')['daily']['total_tasks'] == 1


def test_daily_score_counts_a_task_on_the_users_local_day(monkeypatch):
    monkeypatch.setattr(action_items_db, 'FieldFilter', _Filter)
    monkeypatch.setattr(
        action_items_db,
        'db',
        _Client([{'completed': True, 'due_at': EVENING_IN_LOS_ANGELES, 'created_at': EVENING_IN_LOS_ANGELES}]),
    )
    monkeypatch.setattr(notifications_db, 'get_user_time_zone', lambda uid: 'America/Los_Angeles')

    assert scores_router.get_daily_score(date='2025-01-14', uid='uid')['total_tasks'] == 1
