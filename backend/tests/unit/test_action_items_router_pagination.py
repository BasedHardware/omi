"""Router pagination uses one database call with a one-row lookahead."""

from unittest.mock import patch

import pytest

import routers.action_items as action_items_router


def _item(item_id: str, *, locked: bool = False, description: str = 'Do a thing') -> dict:
    return {
        'id': item_id,
        'description': description,
        'completed': False,
        'is_locked': locked,
    }


def _call(*, limit: int = 2, offset: int = 0):
    return action_items_router.get_action_items(
        limit=limit,
        offset=offset,
        completed=None,
        conversation_id=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
        uid='user-1',
    )


@pytest.mark.parametrize(
    ('rows', 'expected_ids', 'expected_has_more'),
    [
        ([_item('one'), _item('two'), _item('three')], ['one', 'two'], True),
        ([_item('one'), _item('two')], ['one', 'two'], False),
        ([_item('one')], ['one'], False),
    ],
)
def test_page_uses_one_row_lookahead(rows, expected_ids, expected_has_more):
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=rows) as get_items:
        response = _call(limit=2, offset=7)

    get_items.assert_called_once_with(
        uid='user-1',
        conversation_id=None,
        completed=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
        limit=3,
        offset=7,
    )
    assert [item.id for item in response['action_items']] == expected_ids
    assert response['has_more'] is expected_has_more


def test_lookahead_row_is_trimmed_before_locked_item_redaction():
    extra_description = 'x' * 80
    rows = [_item('one'), _item('two'), _item('lookahead', locked=True, description=extra_description)]

    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=rows):
        response = _call(limit=2)

    assert [item.id for item in response['action_items']] == ['one', 'two']
    assert response['has_more'] is True
    assert rows[2]['description'] == extra_description
