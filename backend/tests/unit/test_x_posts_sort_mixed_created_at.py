"""Regression test: get_x_posts(kind=...) must not crash on mixed datetime/str created_at.

database.x_posts.get_x_posts sorts the kind-filtered branch with
`docs.sort(key=lambda x: str(x.get('created_at') or ''), reverse=True)`. Tweets are stored with a
datetime created_at while other rows store '' or omit it. Without the `str()` coercion a mixed
result set would raise
`TypeError: '<' not supported between instances of 'datetime.datetime' and 'str'` (a 500).

Migrated to the neutral storage port (WP2, ADR-0002/0022): the module reads through
``_store().query(...)``; this test seeds a FakeDocumentStore with a datetime post and a
created_at-less post and asserts the sort does not raise and orders newest-first.
"""

import datetime

import database.x_posts as x_posts
from tests.store_fakes import FakeDocumentStore


def test_kind_branch_sorts_mixed_datetime_and_missing(monkeypatch):
    dt = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)
    store = FakeDocumentStore()
    store.set('users/u1/x_posts/a', {'id': 'a', 'kind': 'tweet', 'created_at': dt})
    store.set('users/u1/x_posts/b', {'id': 'b', 'kind': 'tweet'})  # missing created_at
    monkeypatch.setattr(x_posts, '_store', lambda: store)

    result = x_posts.get_x_posts('u1', kind='tweet')  # must not raise

    ids = [r['id'] for r in result]
    assert set(ids) == {'a', 'b'}
    assert result[0]['id'] == 'a'  # the datetime post sorts newest-first, ahead of the empty one
