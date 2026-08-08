"""Regression test: get_x_posts(kind=...) must sort before truncating, not after.

database.x_posts.get_x_posts's kind-filtered branch fetches every matching
document (a kind filter + order_by would need a new composite index, so the
module deliberately sorts in Python instead -- see the function's own
docstring), sorts by created_at descending, and only then slices to ``limit``.

An earlier bug pre-limited the query to ``limit * 3`` matches BEFORE the Python
sort. Once an account has more than ``limit * 3`` posts of a kind, the true
newest posts can fall outside that arbitrary pre-sort window and never reach the
Python sort at all. GET /v1/x/posts (routers/x_connector.py, docstring: "newest
first") and the MCP tool get_x_posts then silently return stale posts instead of
the newest ones, with no error.

Migrated to the neutral storage port (WP2, ADR-0002/0022): the module now issues
``_store().query(coll, filters=[('kind','==',kind)])`` with no limit, so every
matching document is sorted before the final ``limit`` slice. This test seeds a
FakeDocumentStore (whose ``query`` returns matches unordered, like Firestore
absent an order_by) and asserts the true-newest posts come back.
"""

from datetime import datetime, timedelta, timezone

import database.x_posts as x_posts
from tests.store_fakes import FakeDocumentStore


def _make_store(monkeypatch, num_docs):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    store = FakeDocumentStore()
    # id '0' is oldest, id '{num_docs-1}' is newest. Seeded in ascending order so
    # the fake's query (which preserves insertion order, no ordering guarantee --
    # like Firestore absent an order_by) hands the module oldest-first.
    for i in range(num_docs):
        store.set(
            f'users/u1/x_posts/{i}',
            {'id': str(i), 'kind': 'tweet', 'created_at': base + timedelta(days=i)},
        )
    monkeypatch.setattr(x_posts, '_store', lambda: store)
    return store


def test_kind_filter_returns_true_newest_beyond_prelimit_window(monkeypatch):
    """10 tweets exist; limit=2 (an old pre-sort window would be 2*3=6) must still return the 2 newest."""
    _make_store(monkeypatch, num_docs=10)

    result = x_posts.get_x_posts('u1', limit=2, kind='tweet')

    # True newest two tweets are ids '9' and '8'.
    assert [r['id'] for r in result] == ['9', '8']


def test_kind_filter_within_prelimit_window_still_correct(monkeypatch):
    """Sanity check: when matches fit inside the old *3 window, order is fine either way."""
    _make_store(monkeypatch, num_docs=4)  # 4 <= limit*3 (2*3=6)

    result = x_posts.get_x_posts('u1', limit=2, kind='tweet')

    assert [r['id'] for r in result] == ['3', '2']
