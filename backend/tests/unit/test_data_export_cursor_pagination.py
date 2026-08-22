from database import chat as chat_db
from database import conversations as conversations_db


class _Doc:
    def __init__(self, doc_id):
        self.id = doc_id

    def to_dict(self):
        return {'id': self.id}


class _Query:
    def __init__(self, docs, tracker, *, cursor=None, page_limit=None):
        self.docs = docs
        self.tracker = tracker
        self.cursor = cursor
        self.page_limit = page_limit

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.tracker['limits'].append(value)
        return _Query(self.docs, self.tracker, cursor=self.cursor, page_limit=value)

    def start_after(self, cursor):
        self.tracker['cursors'].append(cursor.id)
        return _Query(self.docs, self.tracker, cursor=cursor, page_limit=self.page_limit)

    def stream(self):
        docs = self.docs
        if self.cursor is not None:
            cursor_index = next(index for index, doc in enumerate(docs) if doc.id == self.cursor.id)
            docs = docs[cursor_index + 1 :]
        page = docs[: self.page_limit]
        self.tracker['page_sizes'].append(len(page))
        return page


class _Firestore:
    def __init__(self, count):
        self.tracker = {'limits': [], 'cursors': [], 'page_sizes': []}
        self.query = _Query([_Doc(f'doc-{index}') for index in range(count)], self.tracker)

    def collection(self, _name):
        return self

    def document(self, _doc_id):
        return self

    def order_by(self, *_args, **_kwargs):
        return self.query


def test_iter_all_conversations_uses_snapshot_cursor_pages(monkeypatch):
    client = _Firestore(5)
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, '_prepare_conversation_for_read', lambda data, _uid: data)

    rows = list(conversations_db.iter_all_conversations('uid', batch_size=2))

    assert [row['id'] for row in rows] == [f'doc-{index}' for index in range(5)]
    assert client.tracker == {
        'limits': [2, 2, 2],
        'cursors': ['doc-1', 'doc-3'],
        'page_sizes': [2, 2, 1],
    }


def test_iter_all_messages_uses_snapshot_cursor_pages(monkeypatch):
    client = _Firestore(5)
    monkeypatch.setattr(chat_db, 'db', client)
    monkeypatch.setattr(chat_db, '_prepare_message_for_read', lambda data, _uid: data)

    rows = list(chat_db.iter_all_messages('uid', batch_size=2))

    assert [row['id'] for row in rows] == [f'doc-{index}' for index in range(5)]
    assert client.tracker == {
        'limits': [2, 2, 2],
        'cursors': ['doc-1', 'doc-3'],
        'page_sizes': [2, 2, 1],
    }
