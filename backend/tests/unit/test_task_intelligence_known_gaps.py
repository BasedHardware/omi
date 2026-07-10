import json
from pathlib import Path

from models.action_item import (
    ActionItemCreateRequest,
    ActionItemResponse,
    ActionItemUpdateRequest,
    ActionItemsResponse,
    CanonicalTaskCreate,
    CanonicalTaskUpdate,
)
from models.workstream import Workstream

FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'task_intelligence' / 'canonical_round_trip_v1.json'

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


def test_shared_client_round_trip_fixture_matches_backend_create_list_update_contracts():
    fixture = json.loads(FIXTURE_PATH.read_text())

    created = ActionItemCreateRequest.model_validate(fixture['create_request']).storage_payload()
    updated = ActionItemUpdateRequest.model_validate(fixture['update_request']).storage_payload()
    create_response = ActionItemResponse.model_validate(fixture['create_response']).model_dump(mode='json')
    update_response = ActionItemResponse.model_validate(fixture['update_response']).model_dump(mode='json')
    listed = ActionItemsResponse.model_validate(fixture['list_response']).model_dump(mode='json')['action_items'][0]
    legacy = ActionItemResponse.model_validate(fixture['legacy_response'])
    workstream = Workstream.model_validate(fixture['linked_workstream'])

    for field in CANONICAL_FIELDS:
        assert created[field] == fixture['create_request'][field]
        if field == 'provenance':
            for index, evidence in enumerate(fixture['create_response'][field]):
                assert {key: listed[field][index][key] for key in evidence} == evidence
        else:
            assert listed[field] == fixture['create_response'][field]
    assert updated['status'] == 'completed'
    assert update_response['completed_at'] == '2026-07-09T13:00:00Z'
    assert legacy.task_id == 'legacy-task-1'
    assert legacy.owner == 'unknown'
    assert workstream.workstream_id == create_response['workstream_id']
    assert workstream.status.value == 'open'
