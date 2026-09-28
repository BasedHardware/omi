"""Firestore rejects a batch with more than 500 mutations; the chat-file multi-writers built one
batch from the whole list.

`add_multi_files` / `delete_multi_files` (`database/chat.py`) put every write into a single
`WriteBatch`. A file upload request with >500 files raises "A maximum of 500 operations are allowed
on a commit" (500 on the upload route, after the OpenAI objects were already uploaded), and a chat
session that accumulated >500 attachments then hits clear-chat: the router catches the `ValueError`
and silently leaves the Firestore file docs behind after deleting the provider objects.

The sibling writers in this module are chunked at `BATCH_LIMIT` (500); these two were the remaining
unchunked batch boundaries here (same class as #19493 for the level migrations).
"""

import os
from types import SimpleNamespace

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.chat as chat_db


class _CappedBatch:
    """Firestore-like batch: a commit is rejected above 500 pending operations."""

    def __init__(self, commits):
        self._commits = commits
        self.pending = 0

    def set(self, ref, data):
        self.pending += 1
        if self.pending > 500:
            raise ValueError('A maximum of 500 operations are allowed on a commit')

    def delete(self, ref):
        self.pending += 1
        if self.pending > 500:
            raise ValueError('A maximum of 500 operations are allowed on a commit')

    def commit(self):
        self._commits.append(self.pending)
        self.pending = 0


def _fake_db(commits):
    return SimpleNamespace(
        batch=lambda: _CappedBatch(commits),
        collection=lambda name: SimpleNamespace(
            document=lambda uid: SimpleNamespace(
                collection=lambda coll: SimpleNamespace(document=lambda doc_id: SimpleNamespace(id=doc_id))
            )
        ),
    )


def _files(count):
    return [{'id': f'f{i}'} for i in range(count)]


def test_add_multi_files_chunks_past_500(monkeypatch):
    commits = []
    monkeypatch.setattr(chat_db, 'db', _fake_db(commits))

    chat_db.add_multi_files('u1', _files(1201))

    assert commits == [500, 500, 201]
    assert sum(commits) == 1201


def test_delete_multi_files_chunks_past_500(monkeypatch):
    commits = []
    monkeypatch.setattr(chat_db, 'db', _fake_db(commits))

    chat_db.delete_multi_files('u1', _files(1201))

    assert commits == [500, 500, 201]
    assert sum(commits) == 1201


def test_empty_lists_commit_nothing(monkeypatch):
    commits = []
    monkeypatch.setattr(chat_db, 'db', _fake_db(commits))

    chat_db.add_multi_files('u1', [])
    chat_db.delete_multi_files('u1', [])

    assert commits == []
