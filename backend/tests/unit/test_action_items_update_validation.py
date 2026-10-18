"""The codec's dirty-status ValueError maps to a 400 on the update endpoint."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.action_items as action_items_router
from models.action_item import ActionItemUpdateRequest


def test_update_endpoint_maps_codec_value_error_to_400():
    request = ActionItemUpdateRequest(description='still valid at the boundary')
    with (
        patch.object(action_items_router, '_get_valid_action_item', return_value={'id': 'ai-1'}),
        patch.object(action_items_router.task_links, 'validate_task_links'),
        patch.object(
            action_items_router.action_items_db,
            'update_action_item',
            side_effect=ValueError('completed must agree with canonical status'),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            action_items_router.update_action_item('ai-1', request, uid='user-1')
    assert exc.value.status_code == 400
    assert 'completed must agree' in exc.value.detail
