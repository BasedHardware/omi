"""Regression tests for #19449: Firestore batch boundary overflow and document contention in action_items."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

import database.action_items as action_items_db
import database.vector_db as vector_db

UID = "user-batch-boundary"


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


def _install_fake_db(monkeypatch, get_all_returns=None):
    commits = []
    writes = []
    get_all_chunks = []

    items_collection = MagicMock()
    items_collection.document.side_effect = lambda doc_id: SimpleNamespace(id=doc_id)

    user_doc = MagicMock()
    user_doc.collection.return_value = items_collection
    users = MagicMock()
    users.document.return_value = user_doc

    fake_db = MagicMock()
    fake_db.collection.return_value = users
    fake_db.batch.side_effect = lambda: _RecordingBatch(commits, writes)

    def _fake_get_all(refs):
        get_all_chunks.append(len(refs))
        if get_all_returns is not None:
            return get_all_returns(refs)
        return [
            SimpleNamespace(exists=True, id=ref.id, to_dict=lambda: {'description': f'desc-{ref.id}'}) for ref in refs
        ]

    fake_db.get_all.side_effect = _fake_get_all

    monkeypatch.setattr(action_items_db, "db", fake_db)
    monkeypatch.setattr(action_items_db, "_purge_proactivity_source", lambda uid, item_id: None)
    monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
    return commits, writes, get_all_chunks


def test_delete_action_items_batch_deduplicates_and_avoids_contention(monkeypatch):
    commits, writes, _ = _install_fake_db(monkeypatch)

    input_ids = ['a1', 'a2', 'a1', '  ', 'a3', 'a2', 'a4']
    deleted = action_items_db.delete_action_items_batch(UID, input_ids)

    assert deleted == ['a1', 'a2', 'a3', 'a4']
    assert writes == ['a1', 'a2', 'a3', 'a4']
    assert commits == [4]


def test_delete_action_items_batch_chunks_over_499(monkeypatch):
    commits, writes, _ = _install_fake_db(monkeypatch)

    input_ids = [f'item-{i}' for i in range(1200)]
    deleted = action_items_db.delete_action_items_batch(UID, input_ids)

    assert len(deleted) == 1200
    assert len(writes) == 1200
    assert commits == [499, 998, 1200]


def test_batch_set_sync_requested_deduplicates_and_avoids_contention(monkeypatch):
    commits, writes, _ = _install_fake_db(monkeypatch)

    input_ids = ['a1', 'a1', 'a2', '  ', 'a3', 'a2']
    action_items_db.batch_set_sync_requested(UID, input_ids)

    assert writes == ['a1', 'a2', 'a3']
    assert commits == [3]


def test_get_action_items_by_ids_chunks_and_preserves_order(monkeypatch):
    commits, writes, get_all_chunks = _install_fake_db(monkeypatch)

    # 1000 IDs with duplicates
    unique_ids = [f'item-{i}' for i in range(1000)]
    input_ids = unique_ids + ['item-0', 'item-1']

    results = action_items_db.get_action_items_by_ids(UID, input_ids)

    # Output matches length of input (preserving repeats if desired by caller)
    assert len(results) == len(input_ids)
    assert results[0]['id'] == 'item-0'
    assert results[-1]['id'] == 'item-1'
    # get_all was called in chunks of 499 (499, 499, 2)
    assert get_all_chunks == [499, 499, 2]


def test_empty_or_whitespace_uid_handled_safely(monkeypatch):
    commits, writes, _ = _install_fake_db(monkeypatch)

    assert action_items_db.delete_action_items_batch('', ['a1']) == []
    assert action_items_db.delete_action_items_batch('   ', ['a1']) == []
    assert action_items_db.get_action_items_by_ids('', ['a1']) == []
    action_items_db.batch_set_sync_requested('', ['a1'])
    assert len(writes) == 0


def test_delete_action_item_vectors_batch_handles_pinecone_failure(monkeypatch):
    mock_index = MagicMock()
    mock_index.delete.side_effect = RuntimeError("Pinecone timeout or connection error")
    monkeypatch.setattr(vector_db, "index", mock_index)

    # Must not raise an exception
    vector_db.delete_action_item_vectors_batch(UID, ['a1', 'a2'])
    assert mock_index.delete.called
