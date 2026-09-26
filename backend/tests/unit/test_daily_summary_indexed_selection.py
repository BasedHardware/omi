"""Server-side daily-summary recipient selection (#13210)."""

import database.notifications as notifications_module
from database.firestore_index_registry import (
    DAILY_SUMMARY_RECIPIENTS_QUERY,
    QUERY_SPECS,
    firebase_index_manifest,
)


def _filter_tuple(field_filter):
    return (field_filter.field_path, field_filter.op_string, field_filter.value)


class _TokenDoc:
    def __init__(self, token):
        self._token = token

    def to_dict(self):
        return {'token': self._token}


class _UserDoc:
    def __init__(self, uid, data):
        self.id = uid
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, collection, filters):
        self._collection = collection
        self.filters = list(filters)

    def where(self, *, filter):
        return _Query(self._collection, self.filters + [filter])

    def stream(self):
        self._collection.completed_queries.append([_filter_tuple(item) for item in self.filters])
        zones = None
        for item in self.filters:
            if item.field_path == 'time_zone':
                zones = item.value
        if self._collection.raise_on_zones is not None and zones == self._collection.raise_on_zones:
            raise RuntimeError('index unavailable')
        return [
            _UserDoc(uid, data)
            for uid, data in self._collection.users.items()
            if data.get('time_zone') in (zones or [])
        ]


class _TokenCollection:
    def __init__(self, tokens):
        self._tokens = tokens

    def stream(self):
        return [_TokenDoc(token) for token in self._tokens]


class _UserRef:
    def __init__(self, collection, uid):
        self._collection = collection
        self._uid = uid

    def collection(self, name):
        assert name == 'fcm_tokens'
        return _TokenCollection(self._collection.tokens.get(self._uid, []))


class _UsersCollection:
    def __init__(self, users, tokens, raise_on_zones=None):
        self.users = users
        self.tokens = tokens
        self.raise_on_zones = raise_on_zones
        self.completed_queries = []

    def where(self, *, filter):
        return _Query(self, [filter])

    def document(self, uid):
        return _UserRef(self, uid)


class _FakeDb:
    def __init__(self, users, tokens=None, raise_on_zones=None):
        self.users_collection = _UsersCollection(users, tokens or {}, raise_on_zones)

    def collection(self, name):
        assert name == 'users'
        return self.users_collection


def test_indexed_selection_issues_three_filters(monkeypatch):
    fake = _FakeDb({'u1': {'time_zone': 'UTC', 'fcm_token': 'legacy'}})
    monkeypatch.setattr(notifications_module, 'db', fake)

    notifications_module.get_users_for_daily_summary_indexed(['UTC', 'America/New_York'], 22)

    assert len(fake.users_collection.completed_queries) == 1
    assert fake.users_collection.completed_queries[0] == [
        ('daily_summary_enabled', '==', True),
        ('daily_summary_hour_local', '==', 22),
        ('time_zone', 'in', ['UTC', 'America/New_York']),
    ]


def test_indexed_selection_chunks_more_than_thirty_zones(monkeypatch):
    zones = [f'Zone/{i}' for i in range(31)]
    fake = _FakeDb({})
    monkeypatch.setattr(notifications_module, 'db', fake)

    notifications_module.get_users_for_daily_summary_indexed(zones, 8)

    assert len(fake.users_collection.completed_queries) == 2
    assert fake.users_collection.completed_queries[0][2] == ('time_zone', 'in', zones[:30])
    assert fake.users_collection.completed_queries[1][2] == ('time_zone', 'in', zones[30:])


def test_indexed_selection_returns_subcollection_and_legacy_tokens(monkeypatch):
    fake = _FakeDb(
        {
            'u1': {'time_zone': 'UTC', 'fcm_token': 'legacy'},
            'u2': {'time_zone': 'UTC'},
        },
        tokens={'u1': ['sub-a', 'legacy']},
    )
    monkeypatch.setattr(notifications_module, 'db', fake)

    result = notifications_module.get_users_for_daily_summary_indexed(['UTC'], 22)

    by_uid = {uid: (tokens, zone) for uid, tokens, zone in result}
    assert by_uid['u1'] == (['sub-a', 'legacy'], 'UTC')
    assert by_uid['u2'] == ([], 'UTC')


def test_indexed_selection_keeps_tokenless_users(monkeypatch):
    fake = _FakeDb({'u1': {'time_zone': 'UTC'}})
    monkeypatch.setattr(notifications_module, 'db', fake)

    result = notifications_module.get_users_for_daily_summary_indexed(['UTC'], 22)

    assert result == [('u1', [], 'UTC')]


def test_indexed_selection_skips_a_raising_chunk(monkeypatch, caplog):
    zones_a = [f'A/{i}' for i in range(30)]
    zones_b = ['B/0']
    fake = _FakeDb(
        {'keep': {'time_zone': 'A/0'}, 'drop': {'time_zone': 'B/0'}},
        raise_on_zones=zones_b,
    )
    monkeypatch.setattr(notifications_module, 'db', fake)

    with caplog.at_level('ERROR'):
        result = notifications_module.get_users_for_daily_summary_indexed(zones_a + zones_b, 22)

    assert result == [('keep', [], 'A/0')]
    assert 'Error querying chunk for daily summary' in caplog.text


def test_daily_summary_recipients_query_is_registered():
    assert DAILY_SUMMARY_RECIPIENTS_QUERY in QUERY_SPECS
    signature = (
        'users',
        'COLLECTION',
        (
            ('daily_summary_enabled', 'ASCENDING'),
            ('daily_summary_hour_local', 'ASCENDING'),
            ('time_zone', 'ASCENDING'),
            ('__name__', 'ASCENDING'),
        ),
    )
    indexes = {
        (
            index['collectionGroup'],
            index['queryScope'],
            tuple((field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in index['fields']),
        )
        for index in firebase_index_manifest()['indexes']
    }
    assert signature in indexes
