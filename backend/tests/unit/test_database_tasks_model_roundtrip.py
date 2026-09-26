"""Exercise the task reader's output with the real caller-side Pydantic model."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import database.tasks as tasks_db
from models.task import Task, TaskAction, TaskStatus


@pytest.mark.parametrize('stored_id', [None, 'stored-task-id'])
def test_task_reader_output_validates_as_task(monkeypatch, stored_id):
    created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    payload = {
        'action': TaskAction.HUME_MERSURE_USER_EXPRESSION.value,
        'status': TaskStatus.DONE.value,
        'created_at': created_at,
        'request_id': 'req-1',
    }
    if stored_id is not None:
        payload['id'] = stored_id

    snapshot = MagicMock()
    snapshot.id = 'snapshot-task-id'
    snapshot.to_dict.return_value = payload
    fake_db = MagicMock()
    query = fake_db.collection.return_value.where.return_value
    query.where.return_value = query
    query.limit.return_value = query
    query.stream.return_value = iter([snapshot])
    monkeypatch.setattr(tasks_db, 'db', fake_db)

    result = tasks_db.get_task_by_action_request(payload['action'], 'req-1')

    assert result is not None
    task = Task(**result)
    assert task.id == (stored_id if stored_id is not None else snapshot.id)
    assert task.action == TaskAction.HUME_MERSURE_USER_EXPRESSION
    assert task.status == TaskStatus.DONE
    assert task.created_at == created_at
    assert task.request_id == 'req-1'
    assert task.executed_at is None
    assert task.updated_at is None
