import pytest

from routers.action_items import (
    ActionItemResponse,
    ActionItemsResponse,
    CreateActionItemRequest,
    UpdateActionItemRequest,
)

CANONICAL_FIELDS = {
    'goal_id': 'goal-1',
    'workstream_id': 'workstream-1',
    'owner': 'user',
    'source': 'conversation',
    'provenance': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
    'due_confidence': 0.9,
}


@pytest.mark.xfail(strict=True, reason='#9352 Ticket 02 removes the backend canonical round-trip gap')
def test_backend_action_item_contract_currently_drops_canonical_fields():
    create_round_trip = CreateActionItemRequest.model_validate(
        {'description': 'Send the budget', **CANONICAL_FIELDS}
    ).model_dump(mode='json')
    update_round_trip = UpdateActionItemRequest.model_validate(CANONICAL_FIELDS).model_dump(mode='json')
    response = ActionItemResponse.model_validate(
        {'id': 'task-1', 'description': 'Send the budget', 'completed': False, **CANONICAL_FIELDS}
    )
    list_round_trip = ActionItemsResponse(action_items=[response]).model_dump(mode='json')['action_items'][0]

    for payload in (create_round_trip, update_round_trip, list_round_trip):
        assert all(payload.get(field) == value for field, value in CANONICAL_FIELDS.items())
