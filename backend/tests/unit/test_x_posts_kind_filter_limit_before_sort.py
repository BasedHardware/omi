"""Regression test: get_x_posts(kind=...) must sort before truncating, not after.

database.x_posts.get_x_posts's kind-filtered branch runs:

    coll.where(filter=FieldFilter('kind', '==', kind)).limit(limit * 3).stream()

with no ``order_by`` (a kind filter + order_by would need a new composite
index, so the module deliberately sorts in Python instead -- see the
function's own docstring). But ``.limit()`` without a matching ``order_by``
returns an ARBITRARY ``limit * 3`` matching documents, not the newest ones --
Firestore is free to return matches in any order (in practice, often
insertion/document-id order, and these documents are keyed by tweet
snowflake id, which increases over time, i.e. oldest-first). Once an account
has more than ``limit * 3`` posts of a kind, the true newest posts can fall
outside that arbitrary pre-sort window and never reach the Python sort at
all. GET /v1/x/posts (routers/x_connector.py, docstring: "newest first") and
the MCP tool get_x_posts then silently return stale posts instead of the
newest ones, with no error.

The fix drops the premature ``.limit(limit * 3)`` so every matching document
is sorted before the final ``limit`` slice -- matching the sibling
(non-kind-filtered) branch two lines down, which already orders at the
Firestore level before limiting.
"""

from datetime import datetime, timedelta, timezone

import database.x_posts as x_posts


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class _FakeKindQuery:
    """Mimics coll.where(kind==X)[.limit(n)].stream() with no order_by.

    Firestore gives no ordering guarantee absent an explicit order_by. This
    fake models that by streaming matches in insertion order (oldest tweet
    id first) and genuinely truncating on `.limit(n)` -- exactly like
    Firestore truncates before any Python-side sort ever gets a chance to
    run. It records the calls made so the test can assert what was actually
    asked of "Firestore", not just what came back.
    """

    def __init__(self, docs):
        self._docs = docs
        self.limit_calls = []
        self._limit = None

    def where(self, **kwargs):
        return self

    def limit(self, n):
        self.limit_calls.append(n)
        self._limit = n
        return self

    def stream(self):
        docs = self._docs if self._limit is None else self._docs[: self._limit]
        return iter(docs)


def _make_fake(monkeypatch, num_docs):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # id '0' is oldest, id '{num_docs-1}' is newest -- streamed oldest-first,
    # the order Firestore returns absent an order_by on these doc-id-keyed,
    # monotonically-increasing-over-time records.
    docs = [
        _FakeDoc(str(i), {'id': str(i), 'kind': 'tweet', 'created_at': base + timedelta(days=i)})
        for i in range(num_docs)
    ]
    fake = _FakeKindQuery(docs)
    monkeypatch.setattr(x_posts, '_posts_ref', lambda uid: fake)
    return fake


def test_kind_filter_returns_true_newest_beyond_prelimit_window(monkeypatch):
    """10 tweets exist; limit=2 (pre-sort window would be 2*3=6) must still return the 2 newest."""
    fake = _make_fake(monkeypatch, num_docs=10)

    result = x_posts.get_x_posts('u1', limit=2, kind='tweet')

    # True newest two tweets are ids '9' and '8'. The bug's pre-sort
    # `.limit(2*3=6)` keeps only ids '0'..'5' (the SIX OLDEST out of 10), so
    # the "newest" the Python sort can find among them tops out at id '5'.
    assert [r['id'] for r in result] == ['9', '8']


def test_kind_filter_within_prelimit_window_still_correct(monkeypatch):
    """Sibling/normal-path sanity check: when matches fit inside the old *3 window, order is fine
    either way -- this must pass both before and after the fix, proving the fix doesn't regress
    the common case."""
    fake = _make_fake(monkeypatch, num_docs=4)  # 4 <= limit*3 (2*3=6), fits in the old window too

    result = x_posts.get_x_posts('u1', limit=2, kind='tweet')

    assert [r['id'] for r in result] == ['3', '2']
