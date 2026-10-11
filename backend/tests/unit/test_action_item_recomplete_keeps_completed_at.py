"""Completing an already-completed task keeps its original ``completed_at``.

``PATCH /v1/action-items/{id}`` with ``completed: true``, ``PATCH .../completed?completed=true``
and a sync-batch entry with ``completed: true`` all stamped ``completed_at`` with "now" even
when the item was already completed, so a duplicated tap, a client resending the whole
object, or a sync replay moved the completion time. Completion is idempotent: the first
completion stamps, a repeat keeps, un-completing clears.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import routers.action_items as action_items_router
from models.action_item import ActionItemUpdateRequest
from routers.action_items import SyncBatchItem, SyncBatchRequest

ORIGINAL = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)


def _done():
    return {'id': 't1', 'description': 'd', 'completed': True, 'status': 'completed', 'completed_at': ORIGINAL}


def _open():
    return {'id': 't1', 'description': 'd', 'completed': False, 'status': 'active', 'completed_at': None}


@pytest.fixture
def router_db():
    with patch.object(action_items_router, 'action_items_db') as db, patch.object(
        action_items_router.task_links, 'validate_task_links'
    ), patch.object(action_items_router, 'sync_action_item_reminder'), patch.object(
        action_items_router, 'record_product_event'
    ):
        db.update_action_item.return_value = True
        db.mark_action_item_completed.return_value = True
        db.batch_sync_update_action_items.return_value = MagicMock(updated_ids=['t1'], missing_ids=[])
        yield db


def test_patch_recomplete_keeps_original_completed_at(router_db):
    router_db.get_action_item.return_value = _done()

    action_items_router.update_action_item('t1', ActionItemUpdateRequest(completed=True), uid='u1', http_request=None)

    update_data = router_db.update_action_item.call_args.args[2]
    assert update_data['completed'] is True
    assert update_data['completed_at'] == ORIGINAL


def test_patch_first_completion_stamps_now_and_uncomplete_clears(router_db):
    router_db.get_action_item.return_value = _open()
    action_items_router.update_action_item('t1', ActionItemUpdateRequest(completed=True), uid='u1', http_request=None)
    stamped = router_db.update_action_item.call_args.args[2]['completed_at']
    assert stamped is not None and stamped != ORIGINAL

    router_db.get_action_item.return_value = _done()
    action_items_router.update_action_item('t1', ActionItemUpdateRequest(completed=False), uid='u1', http_request=None)
    assert router_db.update_action_item.call_args.args[2]['completed_at'] is None


def test_toggle_route_recomplete_does_not_rewrite_the_completion(router_db):
    router_db.get_action_item.return_value = _done()

    response = action_items_router.toggle_action_item_completion('t1', completed=True, uid='u1', http_request=None)

    router_db.mark_action_item_completed.assert_not_called()
    assert response.completed_at == ORIGINAL


def test_toggle_route_first_completion_and_uncomplete_still_write(router_db):
    router_db.get_action_item.return_value = _open()
    action_items_router.toggle_action_item_completion('t1', completed=True, uid='u1', http_request=None)
    router_db.mark_action_item_completed.assert_called_once_with('u1', 't1', True)

    router_db.get_action_item.return_value = _done()
    action_items_router.toggle_action_item_completion('t1', completed=False, uid='u1', http_request=None)
    assert router_db.mark_action_item_completed.call_args.args == ('u1', 't1', False)


def test_sync_batch_recomplete_keeps_original_completed_at(router_db):
    router_db.get_action_item.return_value = _done()

    action_items_router.sync_batch_update(SyncBatchRequest(items=[SyncBatchItem(id='t1', completed=True)]), uid='u1')

    (updates,) = router_db.batch_sync_update_action_items.call_args.args[1:]
    assert updates[0]['data']['completed_at'] == ORIGINAL
