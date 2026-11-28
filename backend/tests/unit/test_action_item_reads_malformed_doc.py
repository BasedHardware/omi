"""A partial stored action item must not 500 the single-item and shared-task reads.

The list endpoints already skip a record that fails `ActionItemResponse` validation
(`_safe_action_item_responses`), but two reads of the same record did not:

  * `GET /v1/action-items/{id}` built `ActionItemResponse(**item)` directly, so an item
    stored with a null or missing `description` raised `ValidationError`;
  * the public `GET /v1/action-items/shared/{token}` preview used
    `item.get('description', '')`, which keeps an explicit `None`, so response
    validation of `SharedActionItemPreview.description: str` failed. Accepting the same
    share copied that `None` into the recipient's new task.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database.action_items import prepare_action_item_for_read
from routers import action_items as action_items_router

SHARE = {'uid': 'sender', 'display_name': 'Sender', 'task_ids': ['t1']}


def _get_single(stored):
    with patch.object(
        action_items_router.action_items_db,
        'get_action_item',
        return_value=prepare_action_item_for_read(dict(stored)),
    ):
        return action_items_router.get_action_item('a1', uid='owner')


def test_a_single_item_without_a_description_is_not_found_rather_than_a_500():
    with pytest.raises(HTTPException) as raised:
        _get_single({'id': 'a1', 'completed': False})

    assert raised.value.status_code == 404


def test_a_single_item_with_a_null_description_is_not_found_rather_than_a_500():
    with pytest.raises(HTTPException) as raised:
        _get_single({'id': 'a1', 'description': None, 'completed': False})

    assert raised.value.status_code == 404


def test_a_valid_single_item_is_still_returned():
    item = _get_single({'id': 'a1', 'description': 'Ship it', 'completed': False})

    assert item.id == 'a1' and item.description == 'Ship it'


def _shared_preview(stored):
    app = FastAPI()
    app.include_router(action_items_router.router)
    with patch.object(action_items_router.redis_db, 'get_task_share', return_value=dict(SHARE)), patch.object(
        action_items_router.action_items_db, 'get_action_item', return_value=dict(stored)
    ):
        return TestClient(app, raise_server_exceptions=False).get('/v1/action-items/shared/token')


def test_the_shared_preview_renders_a_null_description_as_empty():
    response = _shared_preview({'id': 't1', 'description': None, 'completed': False})

    assert response.status_code == 200
    assert response.json()['tasks'] == [{'description': '', 'due_at': None}]


def test_accepting_a_share_does_not_copy_a_null_description():
    request = action_items_router.AcceptSharedTasksRequest(token='token')
    with patch.object(action_items_router.redis_db, 'get_task_share', return_value=dict(SHARE)), patch.object(
        action_items_router.redis_db, 'try_accept_task_share', return_value=True
    ), patch.object(
        action_items_router.action_items_db, 'get_action_item', return_value={'id': 't1', 'description': None}
    ), patch.object(
        action_items_router.action_items_db, 'create_action_items_batch', return_value=['new-t1']
    ) as create_batch, patch.object(
        action_items_router, '_wake_task_changes'
    ), patch.object(
        action_items_router, 'upsert_action_item_vector'
    ):
        action_items_router.accept_shared_action_items(request, uid='recipient')

    assert create_batch.call_args[0][1][0]['description'] == ''
