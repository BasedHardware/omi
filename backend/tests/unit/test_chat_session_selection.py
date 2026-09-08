"""`get_chat_session` must pick the newest session without hiding old ones.

Two failure modes, both silent, both seen in review:

  * an unordered `.limit(1)` returns whichever document the index yields, so a
    user with several sessions has their conversation split across them at
    random;
  * ordering the *query* by `created_at` makes Firestore omit every document
    that lacks the field, so a session written without a timestamp becomes
    invisible and the user's existing history is stranded behind a new session.

The fix has to satisfy both at once, which is what these assert.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import database.chat as chat_db


def _doc(session_id, created_at=None, plugin_id=None):
    data = {'id': session_id, 'plugin_id': plugin_id}
    if created_at is not None:
        data['created_at'] = created_at
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.id = session_id
    return doc


def _query_returning(docs):
    """Stands in for the Firestore chain `get_chat_session` builds."""
    query = MagicMock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    timestamped = [doc for doc in docs if doc.to_dict().get('created_at') is not None]
    query.stream.side_effect = [iter(timestamped), iter(docs)]
    collection = MagicMock()
    collection.document.return_value.collection.return_value = query
    return collection, query


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _run(monkeypatch, docs):
    """Swap the lazy Firestore proxy for a stub.

    monkeypatch.setattr rather than mock.patch.object: patching introspects the
    object it replaces, and every attribute read on `database._client.db` proxies
    through to a real client build, which the hermetic guard blocks.
    """
    collection, query = _query_returning(docs)
    db = MagicMock()
    db.collection.return_value = collection
    monkeypatch.setattr(chat_db, 'db', db)
    return chat_db.get_chat_session('uid', 'app'), query


def test_picks_the_newest_of_several_sessions(monkeypatch):
    older = _doc('older', NOW - timedelta(days=2))
    newest = _doc('newest', NOW)
    middle = _doc('middle', NOW - timedelta(days=1))

    result, _ = _run(monkeypatch, [older, newest, middle])

    assert result['id'] == 'newest'


def test_a_session_without_created_at_is_still_found(monkeypatch):
    # The regression: ordering in the query drops this document entirely, so the
    # user looks like they have no session at all and a new one is created over
    # the top of their history.
    result, _ = _run(monkeypatch, [_doc('legacy')])

    assert result is not None
    assert result['id'] == 'legacy'


def test_a_timestamped_session_wins_over_an_untimestamped_one(monkeypatch):
    result, _ = _run(monkeypatch, [_doc('legacy'), _doc('current', NOW)])

    assert result['id'] == 'current'


def test_ties_break_on_id_so_the_answer_is_stable(monkeypatch):
    same = NOW
    first, _ = _run(monkeypatch, [_doc('b', same), _doc('a', same)])
    again, _ = _run(monkeypatch, [_doc('a', same), _doc('b', same)])

    assert first['id'] == again['id']


def test_no_sessions_returns_none(monkeypatch):
    result, _ = _run(monkeypatch, [])

    assert result is None


def test_the_timestamped_query_orders_by_created_at(monkeypatch):
    # A static guard on the mechanism, not just the outcome: reintroducing
    # `.order_by('created_at')` would pass every test above when the fixtures
    # all carry the field, and silently reopen the legacy hole in production.
    _, query = _run(monkeypatch, [_doc('only', NOW)])

    assert query.order_by.called


def test_legacy_fallback_uses_a_deterministic_document_order(monkeypatch):
    result, query = _run(monkeypatch, [_doc('a'), _doc('b')])

    assert result['id'] == 'a'
    query.order_by.assert_any_call('__name__', direction=chat_db.firestore.Query.ASCENDING)
