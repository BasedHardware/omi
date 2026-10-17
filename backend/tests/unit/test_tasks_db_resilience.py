"""Hermetic unit tests for tasks database TOCTOU guard, validation, and error handling."""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from unittest.mock import MagicMock
import pytest

import database.tasks as tasks_db


def test_update_task_success(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(tasks_db.db, "collection", lambda name: mock_col)

    res = tasks_db.update("task-123", {"status": "completed"})
    assert res is True
    mock_doc.update.assert_called_once_with({"status": "completed"})


def test_update_task_not_found(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(tasks_db.db, "collection", lambda name: mock_col)

    res = tasks_db.update("task-missing", {"status": "completed"})
    assert res is False


def test_update_task_toctou_race_guard(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = Exception("NotFound: Concurrent deletion")
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(tasks_db.db, "collection", lambda name: mock_col)

    res = tasks_db.update("task-raced", {"status": "failed"})
    assert res is False


def test_update_task_empty_id():
    res = tasks_db.update("   ", {"status": "failed"})
    assert res is False


def test_create_task_success(monkeypatch):
    mock_doc = MagicMock()
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(tasks_db.db, "collection", lambda name: mock_col)

    tasks_db.create({"id": "task-abc", "action": "test"})
    mock_col.document.assert_called_once_with("task-abc")
    mock_doc.set.assert_called_once_with({"id": "task-abc", "action": "test"})


def test_create_task_validation():
    with pytest.raises(ValueError, match="task_data must contain an 'id' field"):
        tasks_db.create({})
