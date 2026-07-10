from models.action_item import (
    ActionItemResponse,
    ActionItemsResponse,
    CanonicalTaskCreate,
    CanonicalTaskUpdate,
)

CANONICAL_FIELDS = {
    'goal_id': 'goal-1',
    'workstream_id': 'workstream-1',
    'owner': 'user',
    'source': 'conversation',
    'provenance': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
    'due_confidence': 0.9,
}


def test_backend_action_item_contract_preserves_canonical_fields():
    create_round_trip = CanonicalTaskCreate.model_validate(
        {'description': 'Send the budget', **CANONICAL_FIELDS}
    ).model_dump(mode='json')
    update_round_trip = CanonicalTaskUpdate.model_validate(CANONICAL_FIELDS).model_dump(mode='json')
    response = ActionItemResponse.model_validate(
        {'id': 'task-1', 'description': 'Send the budget', 'completed': False, **CANONICAL_FIELDS}
    )
    list_round_trip = ActionItemsResponse(action_items=[response]).model_dump(mode='json')['action_items'][0]

    for payload in (create_round_trip, update_round_trip, list_round_trip):
        for field, value in CANONICAL_FIELDS.items():
            if field == 'provenance':
                assert {key: payload[field][0][key] for key in value[0]} == value[0]
            else:
                assert payload.get(field) == value
