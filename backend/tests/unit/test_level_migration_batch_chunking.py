"""Firestore rejects a batch with more than 500 mutations; the level-batch migrations built one
batch from the whole id list.

`migrate_chats_level_batch` (database/chat.py) and `migrate_memories_level_batch`
(database/memories.py) are reached with client-controlled id groups from
`POST /v1/users/migration/batch-requests` (the request models carry no length bound), and each
put every update into a single `WriteBatch`. More than 500 ids of one type therefore raise
"A maximum of 500 operations are allowed on a commit" and nothing is migrated.

The sibling `migrate_memories` was chunked at `BATCH_LIMIT` (#15152) and
`migrate_conversations_level_batch` chunks its writes, so the two level-batch functions are the
missed ones. These tests pin the chunking with a Firestore-like batch that refuses a 501st write.
"""

import os
from contextlib import nullcontext
from types import SimpleNamespace

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.chat as chat_db
import database.memories as memories_db


class _CappedBatch:
    """Firestore-like batch: commit is rejected above 500 pending operations."""

    def __init__(self, commits):
        self._commits = commits
        self.pending = 0

    def update(self, ref, data):
        self.pending += 1
        if self.pending > 500:
            raise ValueError('A maximum of 500 operations are allowed on a commit')

    def commit(self):
        self._commits.append(self.pending)
        self.pending = 0


def _documents(prefix, count):
    docs = []
    for index in range(count):
        doc_id = f'{prefix}{index}'
        docs.append(
            SimpleNamespace(
                id=doc_id,
                exists=True,
                reference=SimpleNamespace(id=doc_id),
                to_dict=lambda: {'data_protection_level': 'standard', 'text': 'hello', 'content': 'hello'},
            )
        )
    return docs


def _fake_client(commits, docs):
    return SimpleNamespace(
        batch=lambda: _CappedBatch(commits),
        get_all=lambda refs: docs,
        collection=lambda name: SimpleNamespace(
            document=lambda uid: SimpleNamespace(
                collection=lambda coll: SimpleNamespace(document=lambda doc_id: SimpleNamespace(id=doc_id))
            )
        ),
    )


def test_chat_level_migration_chunks_past_500(monkeypatch):
    docs = _documents('c', 1201)
    commits = []
    monkeypatch.setattr(chat_db, 'db', _fake_client(commits, docs))
    monkeypatch.setattr(chat_db, '_prepare_message_for_read', lambda data, uid: data)
    monkeypatch.setattr(chat_db.encryption, 'encrypt', lambda text, uid: text)

    chat_db.migrate_chats_level_batch('u1', [doc.id for doc in docs], 'enhanced')

    assert commits == [500, 500, 201]
    assert sum(commits) == 1201


def test_chat_level_migration_with_nothing_to_migrate_commits_nothing(monkeypatch):
    commits = []
    monkeypatch.setattr(chat_db, 'db', _fake_client(commits, []))

    chat_db.migrate_chats_level_batch('u1', [], 'enhanced')

    assert commits == []


def test_memories_level_migration_chunks_past_500(monkeypatch):
    docs = _documents('m', 1201)
    commits = []
    monkeypatch.setattr(memories_db, 'external_write_fence', lambda uid, **kwargs: nullcontext())
    monkeypatch.setattr(memories_db, '_prepare_memory_for_read', lambda data, uid: data)
    monkeypatch.setattr(memories_db.encryption, 'encrypt', lambda text, uid: text)

    memories_db.migrate_memories_level_batch(
        'u1', [doc.id for doc in docs], 'enhanced', firestore_client=_fake_client(commits, docs)
    )

    assert commits == [500, 500, 201]
    assert sum(commits) == 1201
