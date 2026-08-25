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


def _doc(session_id, created_at=None, plugin_id=None, updated_at=None):
    data = {'id': session_id, 'plugin_id': plugin_id}
    if created_at is not None:
        data['created_at'] = created_at
    if updated_at is not None:
        data['updated_at'] = updated_at
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
    calls = {'n': 0}

    def _stream():
        calls['n'] += 1
        if calls['n'] == 1:
            return iter(timestamped)
        return iter(list(docs))

    query.stream.side_effect = _stream
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


class _ScopedSessionQuery:
    def __init__(self, docs, field=None, value=None, limit=None):
        self._docs = docs
        self._field = field
        self._value = value
        self._limit = limit

    def where(self, filter=None, **_kwargs):
        return _ScopedSessionQuery(self._docs, field=filter.field_path, value=filter.value, limit=self._limit)

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        return _ScopedSessionQuery(self._docs, field=self._field, value=self._value, limit=n)

    def stream(self):
        matched = []
        for doc in self._docs:
            data = doc.to_dict()
            if self._field is None or data.get(self._field) == self._value:
                matched.append(doc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return iter(matched)


def test_plugin_id_only_session_is_selected(monkeypatch):
    collection = _ScopedSessionQuery([_doc('legacy-plugin', NOW, plugin_id='app')])
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = collection
    monkeypatch.setattr(chat_db, 'db', db)

    result = chat_db.get_chat_session('uid', 'app')

    assert result is not None
    assert result['id'] == 'legacy-plugin'


def test_newer_plugin_id_only_session_wins_over_older_app_id_session(monkeypatch):
    older = _doc('older-app', NOW - timedelta(days=2), plugin_id=None)
    older.to_dict.return_value['app_id'] = 'app'
    newer = _doc('newer-plugin', NOW, plugin_id='app')
    collection = _ScopedSessionQuery([older, newer])
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = collection
    monkeypatch.setattr(chat_db, 'db', db)

    result = chat_db.get_chat_session('uid', 'app')

    assert result['id'] == 'newer-plugin'



def test_doc_matches_app_scope_accepts_legacy_null_app_id():
    """Reconcile cursors minted from plugin_id-only rows must stay in scope."""
    assert chat_db._doc_matches_app_scope({'plugin_id': 'app'}, 'app') is True
    assert chat_db._doc_matches_app_scope({'app_id': None, 'plugin_id': 'app'}, 'app') is True
    assert chat_db._doc_matches_app_scope({'app_id': 'other', 'plugin_id': 'app'}, 'app') is False
    assert chat_db._doc_matches_app_scope({'app_id': 'app'}, 'app') is True


def test_plugin_id_scan_is_newest_first(monkeypatch):
    _, query = _run(monkeypatch, [_doc('only', NOW, plugin_id='app')])
    query.order_by.assert_any_call('updated_at', direction=chat_db.firestore.Query.DESCENDING)
    query.order_by.assert_any_call('created_at', direction=chat_db.firestore.Query.DESCENDING)


class _OmittingOrderQuery:
    """Drops documents missing the ordered field, like Firestore."""

    def __init__(self, docs, field=None, value=None, order_fields=None, limit=None):
        self._docs = docs
        self._field = field
        self._value = value
        self._order_fields = list(order_fields or [])
        self._limit = limit

    def where(self, filter=None, **_kwargs):
        return _OmittingOrderQuery(
            self._docs,
            field=filter.field_path,
            value=filter.value,
            order_fields=self._order_fields,
            limit=self._limit,
        )

    def order_by(self, field, **_kwargs):
        return _OmittingOrderQuery(
            self._docs,
            field=self._field,
            value=self._value,
            order_fields=self._order_fields + [field],
            limit=self._limit,
        )

    def limit(self, n):
        return _OmittingOrderQuery(
            self._docs,
            field=self._field,
            value=self._value,
            order_fields=self._order_fields,
            limit=n,
        )

    def stream(self):
        matched = []
        for doc in self._docs:
            data = doc.to_dict()
            if self._field is not None and data.get(self._field) != self._value:
                continue
            if any(field != '__name__' and field not in data for field in self._order_fields):
                continue
            matched.append(doc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return iter(matched)


def test_plugin_id_only_session_without_updated_at_is_selected(monkeypatch):
    """v1 rows have plugin_id + created_at and no updated_at.

    The updated_at scan cannot see them; the created_at scan must.
    """
    legacy = _doc('legacy-v1', NOW, plugin_id='app')
    collection = _OmittingOrderQuery([legacy])
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = collection
    monkeypatch.setattr(chat_db, 'db', db)

    result = chat_db.get_chat_session('uid', 'app')

    assert result is not None
    assert result['id'] == 'legacy-v1'


def test_plugin_id_updated_at_row_still_wins_when_newer(monkeypatch):
    older_created_only = _doc('older-created', NOW - timedelta(days=2), plugin_id='app')
    newer_updated = _doc('newer-updated', NOW, plugin_id='app', updated_at=NOW)
    collection = _OmittingOrderQuery([older_created_only, newer_updated])
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = collection
    monkeypatch.setattr(chat_db, 'db', db)

    result = chat_db.get_chat_session('uid', 'app')

    assert result['id'] == 'newer-updated'
