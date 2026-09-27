"""Firestore rejects a batch with more than 500 mutations. delete_action_items_for_conversation,
retire_action_items_for_conversation, and batch_set_sync_requested built one WriteBatch per
call with no chunking, so a conversation or sync request with more than ~500 action items
would crash with "A maximum of 500 operations are allowed on a commit" instead of completing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import database.action_items as action_items_db

UID = "user-chunking"


class _RecordingBatch:
    def __init__(self, commits, writes):
        self._commits = commits
        self._writes = writes

    def delete(self, ref):
        self._writes.append(ref.id)

    def update(self, ref, data):
        self._writes.append(ref.id)

    def commit(self):
        self._commits.append(len(self._writes))


def _install_fake_db(monkeypatch, docs=None, query_docs=None):
    commits = []
    writes = []

    items_collection = MagicMock()
    if query_docs is not None:
        query = MagicMock()
        query.where.return_value = query
        query.stream.return_value = iter(query_docs)
        items_collection.where.return_value = query
    items_collection.document.side_effect = lambda doc_id: SimpleNamespace(id=doc_id)

    user_doc = MagicMock()
    user_doc.collection.return_value = items_collection
    users = MagicMock()
    users.document.return_value = user_doc

    fake_db = MagicMock()
    fake_db.collection.return_value = users
    fake_db.batch.side_effect = lambda: _RecordingBatch(commits, writes)

    monkeypatch.setattr(action_items_db, "db", fake_db)
    monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
    return commits, writes


def _docs(n):
    return [SimpleNamespace(id=f"a{i}", reference=SimpleNamespace(id=f"a{i}")) for i in range(n)]


def test_delete_action_items_for_conversation_chunks_past_499(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch, query_docs=_docs(1200))

    deleted = action_items_db.delete_action_items_for_conversation(UID, "conv-1")

    assert deleted == 1200
    assert len(writes) == 1200
    # 1200 deletes chunked at 499 -> commits after 499, 998, and the trailing 202.
    assert commits == [499, 998, 1200]


def test_delete_action_items_for_conversation_under_limit_single_commit(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch, query_docs=_docs(10))

    deleted = action_items_db.delete_action_items_for_conversation(UID, "conv-1")

    assert deleted == 10
    assert len(writes) == 10
    assert commits == [10]


def test_retire_action_items_for_conversation_chunks_past_499(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch, query_docs=_docs(1200))

    retired = action_items_db.retire_action_items_for_conversation(UID, "conv-1", active_ids=[])

    assert retired == 1200
    assert len(writes) == 1200
    assert commits == [499, 998, 1200]


def test_batch_set_sync_requested_chunks_past_499(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch)

    item_ids = [f"a{i}" for i in range(1200)]
    action_items_db.batch_set_sync_requested(UID, item_ids)

    assert len(writes) == 1200
    assert commits == [499, 998, 1200]
