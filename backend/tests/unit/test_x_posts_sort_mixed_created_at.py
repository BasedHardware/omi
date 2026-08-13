"""Regression test: get_x_posts(kind=...) must not crash on mixed datetime/str created_at.

database.x_posts.get_x_posts sorts the kind-filtered branch with
`docs.sort(key=lambda x: x.get('created_at') or '', reverse=True)`. Tweets are stored with a
datetime created_at while other rows store '' or omit it, so a mixed result set raises
`TypeError: '<' not supported between instances of 'datetime.datetime' and 'str'` (a 500). Line 96
of the same file already guards the identical pattern with str(); line 133 was the asymmetry.
The key now coerces to str, matching line 96.
"""

import datetime

import database.x_posts as x_posts


class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return self

    def limit(self, n):
        return self

    def stream(self):
        return iter(self._docs)


def test_kind_branch_sorts_mixed_datetime_and_missing(monkeypatch):
    dt = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)
    docs = [
        _FakeDoc({'id': 'a', 'kind': 'tweet', 'created_at': dt}),
        _FakeDoc({'id': 'b', 'kind': 'tweet'}),  # missing created_at
    ]
    monkeypatch.setattr(x_posts, '_posts_ref', lambda uid: _FakeQuery(docs))

    result = x_posts.get_x_posts('u1', kind='tweet')  # must not raise

    ids = [r['id'] for r in result]
    assert set(ids) == {'a', 'b'}
    assert result[0]['id'] == 'a'  # the datetime post sorts newest-first, ahead of the empty one
