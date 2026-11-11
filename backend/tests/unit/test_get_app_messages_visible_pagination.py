"""Visible-row pagination for app message history.

``get_app_messages`` filters reported rows in Python because legacy messages
may omit ``reported``.  A Firestore limit before that filter makes a reported
row steal a visible slot, so app-integration callers silently receive less
history than they requested.  These fakes model Firestore's limit and keyset
continuation behavior while exercising the production database function.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import database.chat as chat_db


class _FakeDocument:
    def __init__(self, document_id: str, data: dict[str, Any]):
        self.id = document_id
        self._data = dict(data)
        self.exists = True

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _FakeQuery:
    def __init__(self, collection: '_FakeMessageCollection', *, start: int = 0, limit: int | None = None):
        self._collection = collection
        self._start = start
        self._limit = limit

    def where(self, **_kwargs: Any) -> '_FakeQuery':
        return self

    def order_by(self, *_args: Any, **_kwargs: Any) -> '_FakeQuery':
        return self

    def limit(self, value: int) -> '_FakeQuery':
        return _FakeQuery(self._collection, start=self._start, limit=value)

    def start_after(self, document: _FakeDocument) -> '_FakeQuery':
        start = next(index for index, row in enumerate(self._collection.rows) if row.id == document.id) + 1
        return _FakeQuery(self._collection, start=start, limit=self._limit)

    def stream(self) -> list[_FakeDocument]:
        end = self._start + (self._limit if self._limit is not None else len(self._collection.rows))
        page = self._collection.rows[self._start : end]
        self._collection.streamed += len(page)
        return page


class _FakeMessageCollection:
    def __init__(self, rows: list[_FakeDocument]):
        self.rows = rows
        self.streamed = 0

    def where(self, **_kwargs: Any) -> _FakeQuery:
        return _FakeQuery(self)


class _FakeConversationsCollection:
    def document(self, conversation_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=conversation_id)


class _FakeDatabase:
    def __init__(self, messages: _FakeMessageCollection, conversations: dict[str, _FakeDocument] | None = None):
        self._messages = messages
        self._conversations = conversations or {}
        self.requested_conversation_ids: list[str] = []

    def collection(self, name: str) -> '_FakeDatabase':
        assert name == 'users'
        return self

    def document(self, _uid: str) -> SimpleNamespace:
        return SimpleNamespace(collection=self._user_collection)

    def _user_collection(self, name: str) -> Any:
        if name == 'messages':
            return self._messages
        assert name == 'conversations'
        return _FakeConversationsCollection()

    def get_all(self, doc_refs: list[SimpleNamespace]) -> list[_FakeDocument]:
        self.requested_conversation_ids = [ref.id for ref in doc_refs]
        return [self._conversations[ref.id] for ref in doc_refs if ref.id in self._conversations]


def _message(
    document_id: str,
    *,
    reported: bool | None = False,
    memories_id: list[str] | None = None,
) -> _FakeDocument:
    data: dict[str, Any] = {
        'id': document_id,
        'text': document_id,
        'created_at': datetime(2026, 9, 7, tzinfo=timezone.utc),
        'plugin_id': 'app-1',
        'memories_id': memories_id or [],
    }
    if reported is not None:
        data['reported'] = reported
    return _FakeDocument(
        document_id,
        data,
    )


def test_reported_middle_row_does_not_shorten_app_history_and_only_visible_rows_hydrate_conversations():
    """A hidden raw row must not consume history or trigger conversation hydration."""
    collection = _FakeMessageCollection(
        [
            _message('visible-a', memories_id=['conversation-a']),
            _message('reported', reported=True, memories_id=['conversation-hidden']),
            _message('visible-b', memories_id=['conversation-b']),
            _message('visible-c'),
        ]
    )
    database = _FakeDatabase(
        collection,
        {
            'conversation-a': _FakeDocument('conversation-a', {'id': 'conversation-a'}),
            'conversation-b': _FakeDocument('conversation-b', {'id': 'conversation-b'}),
            'conversation-hidden': _FakeDocument('conversation-hidden', {'id': 'conversation-hidden'}),
        },
    )

    with patch.object(chat_db, 'db', database):
        messages = chat_db.get_app_messages('uid-1', 'app-1', limit=2, include_conversations=True)

    assert [message['id'] for message in messages] == ['visible-a', 'visible-b']
    assert set(database.requested_conversation_ids) == {'conversation-a', 'conversation-b'}
    assert [[conversation['id'] for conversation in message['memories']] for message in messages] == [
        ['conversation-a'],
        ['conversation-b'],
    ]


def test_clean_app_history_page_streams_only_the_requested_visible_rows():
    """Slack is paid only after a reported row, not by ordinary prompt assembly."""
    collection = _FakeMessageCollection([_message(f'visible-{index}') for index in range(500)])
    database = _FakeDatabase(collection)

    with patch.object(chat_db, 'db', database):
        messages = chat_db.get_app_messages('uid-1', 'app-1', limit=5)

    assert [message['id'] for message in messages] == [f'visible-{index}' for index in range(5)]
    assert collection.streamed == 5


def test_clean_app_history_larger_than_one_firestore_batch_has_no_extra_read():
    """A 101-row clean page should not fetch a second full 100-row batch."""
    collection = _FakeMessageCollection([_message(f'visible-{index}') for index in range(500)])
    database = _FakeDatabase(collection)

    with patch.object(chat_db, 'db', database):
        messages = chat_db.get_app_messages('uid-1', 'app-1', limit=101)

    assert [message['id'] for message in messages] == [f'visible-{index}' for index in range(101)]
    assert collection.streamed == 101


def test_reported_app_history_scan_stops_at_its_bounded_slack():
    """Reported-heavy app history cannot turn one notification read into an unbounded scan."""
    collection = _FakeMessageCollection([_message(f'reported-{index}', reported=True) for index in range(5000)])
    database = _FakeDatabase(collection)

    with patch.object(chat_db, 'db', database):
        messages = chat_db.get_app_messages('uid-1', 'app-1', limit=10)

    assert messages == []
    assert collection.streamed == 10 + chat_db.CHAT_MESSAGES_VISIBLE_PAGE_SCAN_SLACK


def test_legacy_app_history_without_reported_field_remains_visible():
    """Only explicit ``reported is True`` hides a row; omitted legacy fields stay visible."""
    collection = _FakeMessageCollection(
        [
            _message('visible-a'),
            _message('legacy-visible', reported=None),
            _message('reported', reported=True),
            _message('visible-b'),
        ]
    )
    database = _FakeDatabase(collection)

    with patch.object(chat_db, 'db', database):
        messages = chat_db.get_app_messages('uid-1', 'app-1', limit=3)

    assert [message['id'] for message in messages] == ['visible-a', 'legacy-visible', 'visible-b']


def test_non_positive_app_history_limit_returns_without_a_firestore_read():
    collection = _FakeMessageCollection([_message('visible-a')])
    database = _FakeDatabase(collection)

    with patch.object(chat_db, 'db', database):
        assert chat_db.get_app_messages('uid-1', 'app-1', limit=0) == []
        assert chat_db.get_app_messages('uid-1', 'app-1', limit=-1) == []

    assert collection.streamed == 0
