import os
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import pytest

import routers.action_items as action_items_router
from routers.action_items import SyncBatchItem, SyncBatchRequest, sync_batch_update


@pytest.fixture(autouse=True)
def _quiet_side_effects(monkeypatch):
    monkeypatch.setattr(action_items_router, 'run_task_changed_wake', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items_router, 'upsert_action_item_vectors_batch', lambda *_args, **_kwargs: None)


@pytest.fixture
def reminders(monkeypatch):
    calls = []
    monkeypatch.setattr(action_items_router, 'sync_action_item_reminder', lambda **kwargs: calls.append(kwargs))
    return calls


def _batch_result(updated_ids):
    result = types.SimpleNamespace(
        updated_ids=updated_ids,
        missing_ids=[],
        noop_ids=[],
        updated_count=len(updated_ids),
    )
    result.model = lambda: {
        'updated_count': len(updated_ids),
        'updated_ids': updated_ids,
        'missing_ids': [],
        'noop_ids': [],
    }
    return result


def test_completing_a_task_through_the_sync_batch_cancels_its_reminder(reminders):
    due_at = datetime.now(timezone.utc) + timedelta(days=1)
    with patch('routers.action_items.action_items_db') as mock_db:
        mock_db.get_action_item.return_value = {
            'id': 't1',
            'description': 'Pay the bill',
            'due_at': due_at,
            'completed': False,
        }
        mock_db.batch_sync_update_action_items = MagicMock(return_value=_batch_result(['t1']))

        sync_batch_update(SyncBatchRequest(items=[SyncBatchItem(id='t1', completed=True)]), uid='u1')

    assert reminders == [
        {
            'user_id': 'u1',
            'action_item_id': 't1',
            'description': 'Pay the bill',
            'completed': True,
            'due_at': due_at,
        }
    ]


def test_moving_a_due_date_through_the_sync_batch_reschedules_the_reminder(reminders):
    new_due_at = datetime.now(timezone.utc) + timedelta(days=2)
    with patch('routers.action_items.action_items_db') as mock_db:
        mock_db.get_action_item.return_value = {'id': 't1', 'description': 'Call back', 'completed': False}
        mock_db.batch_sync_update_action_items = MagicMock(return_value=_batch_result(['t1']))

        sync_batch_update(SyncBatchRequest(items=[SyncBatchItem(id='t1', due_at=new_due_at)]), uid='u1')

    assert [(call['completed'], call['due_at']) for call in reminders] == [(False, new_due_at)]


def test_an_export_only_sync_leaves_the_reminder_alone(reminders):
    with patch('routers.action_items.action_items_db') as mock_db:
        mock_db.get_action_item.return_value = {'id': 't1', 'description': 'Call back', 'completed': False}
        mock_db.batch_sync_update_action_items = MagicMock(return_value=_batch_result(['t1']))

        sync_batch_update(
            SyncBatchRequest(items=[SyncBatchItem(id='t1', exported=True, export_platform='apple_reminders')]),
            uid='u1',
        )

    assert reminders == []
