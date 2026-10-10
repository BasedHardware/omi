"""Tests for database.tasks resilience, document ID population, and merge writes."""

from unittest.mock import MagicMock

import pytest

import database.tasks as tasks_db


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


def test_create_task_sets_merge_true(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(tasks_db, 'db', fake_db)

    task_payload = {'id': 'task-1', 'action': 'test', 'status': 'processing'}
    tasks_db.create(task_payload)

    fake_coll.document.assert_called_once_with('task-1')
    fake_doc.set.assert_called_once_with(task_payload, merge=True)


def test_create_task_missing_id_raises_value_error(monkeypatch):
    with pytest.raises(ValueError, match="task_data must include 'id'"):
        tasks_db.create({'action': 'test'})


def test_update_task_uses_merge_write(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(tasks_db, 'db', fake_db)

    task_payload = {'status': 'done'}
    tasks_db.update('task-2', task_payload)

    fake_coll.document.assert_called_once_with('task-2')
    fake_doc.set.assert_called_once_with(task_payload, merge=True)


def test_update_task_empty_id_raises_value_error():
    with pytest.raises(ValueError, match="task_id is required"):
        tasks_db.update('', {'status': 'done'})


def test_get_task_empty_args_returns_none(monkeypatch):
    assert tasks_db.get_task_by_action_request('', 'req-1') is None
    assert tasks_db.get_task_by_action_request('action-1', '') is None


def test_get_task_handles_none_doc_snapshot(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_query = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.where.return_value = fake_query
    fake_query.where.return_value = fake_query
    fake_query.limit.return_value = fake_query

    # Firestore snapshot returns None for .to_dict()
    null_doc = _Doc('task-null', None)
    fake_query.stream.return_value = iter([null_doc])
    monkeypatch.setattr(tasks_db, 'db', fake_db)

    result = tasks_db.get_task_by_action_request('action-1', 'req-1')
    assert result is None


def test_get_task_populates_missing_id_from_snapshot(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_query = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.where.return_value = fake_query
    fake_query.where.return_value = fake_query
    fake_query.limit.return_value = fake_query

    # Firestore snapshot has data dict lacking 'id'
    doc_without_id = _Doc('task-snap-id', {'action': 'action-1', 'request_id': 'req-1', 'status': 'done'})
    fake_query.stream.return_value = iter([doc_without_id])
    monkeypatch.setattr(tasks_db, 'db', fake_db)

    result = tasks_db.get_task_by_action_request('action-1', 'req-1')
    assert result is not None
    assert result['id'] == 'task-snap-id'
    assert result['status'] == 'done'
