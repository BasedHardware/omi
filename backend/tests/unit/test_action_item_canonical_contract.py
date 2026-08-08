from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import database.action_items as action_items_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.action_item import (
    ActionItemCreateRequest,
    ActionItemResponse,
    ActionItemUpdateRequest,
    CanonicalTaskCreate,
    CanonicalTaskUpdate,
)
import routers.action_items as action_items_router
from tests.store_fakes import FakeDocumentStore
from utils.task_intelligence import task_links


def test_create_update_and_response_round_trip_every_canonical_field():
    payload = {
        'description': 'Send the budget',
        'status': 'active',
        'goal_id': 'goal-1',
        'owner': 'user',
        'due_at': '2026-07-10T17:00:00Z',
        'due_confidence': 0.9,
        'source': 'conversation',
        'provenance': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
        'priority': 'high',
        'sort_order': 4,
        'indent_level': 1,
        'recurrence_rule': 'weekly',
        'recurrence_parent_id': 'task-parent',
    }
    created = CanonicalTaskCreate.model_validate(payload)
    stored = {'id': 'task-1', **created.storage_payload()}
    response = ActionItemResponse.model_validate(stored).model_dump(mode='json')
    update = CanonicalTaskUpdate.model_validate(
        {
            'description': 'Send the revised budget',
            'status': 'completed',
            'goal_id': 'goal-1',
            'owner': 'user',
            'due_confidence': 1,
            'source': 'agent',
            'provenance': [{'kind': 'artifact', 'id': 'artifact-1', 'scope': 'canonical'}],
            'priority': 'medium',
            'sort_order': 5,
            'indent_level': 2,
            'recurrence_rule': 'monthly',
            'recurrence_parent_id': 'task-parent',
            'superseded_by': 'task-2',
        }
    ).storage_payload()

    assert response['task_id'] == 'task-1'
    assert response['goal_id'] == 'goal-1'
    assert response['due_confidence'] == 0.9
    assert response['provenance'][0]['id'] == 'conversation-1'
    assert response['priority'] == 'high'
    assert response['recurrence_rule'] == 'weekly'
    assert update['completed'] is True
    assert update['status'] == 'completed'
    assert update['provenance'][0]['id'] == 'artifact-1'


def test_legacy_payload_receives_explicit_compatibility_projection():
    response = ActionItemResponse.model_validate(
        {'id': 'legacy-1', 'description': 'Legacy task', 'completed': True, 'sort_order': 2}
    )

    assert response.task_id == 'legacy-1'
    assert response.status == 'completed'
    assert response.owner == 'unknown'
    assert response.source == 'legacy'
    assert response.provenance == []
    assert response.completed is True


def test_released_macos_request_shapes_remain_compatible_at_route_boundary():
    create = ActionItemCreateRequest.model_validate(
        {
            'description': 'Send the budget',
            'due_at': '2026-07-10T17:00:00.000Z',
            'source': 'desktop',
            'priority': 'high',
            'category': 'work',
            'metadata': '{"thread":"investors"}',
            'relevance_score': 900,
            'recurrence_rule': 'weekly',
            'recurrence_parent_id': 'task-parent',
        }
    )
    update = ActionItemUpdateRequest.model_validate(
        {
            'description': 'Send the revised budget',
            'due_at': None,
            'clear_due_at': True,
            'metadata': '{"thread":"investors"}',
            'relevance_score': 950,
        }
    )

    assert create.storage_payload()['description'] == 'Send the budget'
    assert 'category' not in create.storage_payload()
    assert update.storage_payload()['due_at'] is None
    assert 'clear_due_at' not in update.storage_payload()


@pytest.mark.parametrize(
    'payload',
    [
        {'description': 'x', 'status': 'completed', 'completed': False},
        {'description': 'x', 'due_confidence': 1.1},
        {'description': 'x', 'priority': 'urgent'},
        {'description': 'x', 'provenance': [{'kind': 'local_screen', 'id': 'screen-1', 'scope': 'canonical'}]},
    ],
)
def test_canonical_task_validation_rejects_inconsistent_or_unbounded_fields(payload):
    with pytest.raises(ValidationError):
        CanonicalTaskCreate.model_validate(payload)


def test_database_write_projection_defaults_canonical_fields_without_losing_compatibility():
    prepared = action_items_db._prepare_action_item_for_write(
        {'description': 'Legacy task', 'completed': False, 'category': 'work'}
    )
    partial = action_items_db._prepare_action_item_for_write({'description': 'Edited'}, partial=True)

    assert prepared['status'] == 'active'
    assert prepared['owner'] == 'unknown'
    assert prepared['source'] == 'legacy'
    assert prepared['provenance'] == []
    assert prepared['category'] == 'work'
    assert partial == {'description': 'Edited'}


def test_apple_sync_batch_preserves_omitted_canonical_fields(monkeypatch):
    class _RecordingStore(FakeDocumentStore):
        def __init__(self):
            super().__init__()
            self.updates = []

        def update(self, path, data):
            self.updates.append((path, dict(data)))
            super().update(path, data)

    store = _RecordingStore()
    store._docs['users/user-1/action_items/task-1'] = {'description': 'existing'}
    monkeypatch.setattr(action_items_db, '_store', lambda: store)

    result = action_items_db.batch_sync_update_action_items(
        'user-1',
        [
            {
                'id': 'task-1',
                'data': {
                    'exported': True,
                    'export_platform': 'apple_reminders',
                    'apple_reminder_id': 'reminder-1',
                },
            }
        ],
    )

    assert len(store.updates) == 1
    path, patch = store.updates[0]
    assert path == 'users/user-1/action_items/task-1'
    assert isinstance(patch['updated_at'], datetime)
    assert {key: value for key, value in patch.items() if key != 'updated_at'} == {
        'exported': True,
        'export_platform': 'apple_reminders',
        'apple_reminder_id': 'reminder-1',
        'sync_requested': False,
    }, 'an Apple sync patch must not replace omitted canonical task fields with create defaults'
    # A partial update, not a full replace: the omitted field survives.
    assert store._docs['users/user-1/action_items/task-1']['description'] == 'existing'
    assert result.updated_ids == ['task-1']


def test_write_mode_reprocessing_soft_retires_removed_tasks_and_preserves_receipt_targets(monkeypatch):
    store = FakeDocumentStore()
    store._docs['users/user-1/action_items/task-active'] = {'conversation_id': 'conversation-1'}
    store._docs['users/user-1/action_items/task-removed'] = {'conversation_id': 'conversation-1'}
    monkeypatch.setattr(action_items_db, '_store', lambda: store)

    count = action_items_db.retire_action_items_for_conversation(
        'user-1',
        'conversation-1',
        active_ids=['task-active', 'task-replacement'],
        replacements={'task-removed': 'task-replacement'},
    )

    assert count == 1
    removed = store._docs['users/user-1/action_items/task-removed']
    assert removed['deleted'] is True
    assert removed['status'] == 'superseded'
    assert removed['superseded_by'] == 'task-replacement'
    # The still-active task keeps its target (never soft-retired).
    assert 'deleted' not in store._docs['users/user-1/action_items/task-active']


def test_action_item_lists_hide_soft_retired_rows_before_pagination(monkeypatch):
    store = FakeDocumentStore()
    store._docs['users/user-1/action_items/task-active'] = {
        'description': 'Active task',
        'created_at': datetime(2026, 7, 9, tzinfo=timezone.utc),
        'deleted': False,
    }
    store._docs['users/user-1/action_items/task-retired'] = {
        'description': 'Retired task',
        'created_at': datetime(2026, 7, 10, tzinfo=timezone.utc),
        'deleted': True,
    }
    monkeypatch.setattr(action_items_db, '_store', lambda: store)

    rows = action_items_db.get_action_items('user-1', limit=1)

    assert [row['id'] for row in rows] == ['task-active']


def test_task_workstream_goal_invariant_fails_closed_until_ticket04_resolver():
    task_links.clear_workstream_goal_resolver()
    with pytest.raises(task_links.TaskLinkResolverUnavailableError):
        task_links.validate_task_links('user-1', goal_id='goal-1', workstream_id='workstream-1')

    task_links.register_workstream_goal_resolver(lambda uid, workstream_id: 'goal-1')
    task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')
    task_links.validate_task_links('user-1', goal_id='goal-1', workstream_id='workstream-1')
    with pytest.raises(task_links.TaskLinkValidationError):
        task_links.validate_task_links('user-1', goal_id='goal-2', workstream_id='workstream-1')
    task_links.clear_workstream_goal_resolver()


def test_task_goal_only_link_requires_an_existing_goal():
    task_links.clear_workstream_goal_resolver()
    task_links.register_workstream_goal_resolver(lambda uid, workstream_id: None)
    task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')

    task_links.validate_task_links('user-1', goal_id='goal-1', workstream_id=None)
    with pytest.raises(task_links.TaskLinkValidationError):
        task_links.validate_task_links('user-1', goal_id='missing-goal', workstream_id=None)
    task_links.clear_workstream_goal_resolver()


def test_action_item_router_writes_shared_contract_and_preserves_old_response(monkeypatch):
    written = {}
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')
    monkeypatch.setattr(action_items_router, 'upsert_action_item_vector', lambda *args: None)
    monkeypatch.setattr(action_items_router, 'submit_with_context', lambda *args: None)
    monkeypatch.setattr(action_items_router, 'send_action_item_data_message', lambda **kwargs: None)
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'create_action_item',
        lambda uid, data, idempotency_key=None: written.update(data) or 'task-1',
    )
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'created_at': now, **written},
    )
    request = CanonicalTaskCreate.model_validate(
        {
            'description': 'Send the budget',
            'goal_id': 'goal-1',
            'source': 'manual',
            'provenance': [{'kind': 'external', 'id': 'manual-1', 'scope': 'canonical'}],
        }
    )

    response = action_items_router.create_action_item(request, uid='user-1')

    assert response.id == 'task-1'
    assert response.task_id == 'task-1'
    assert written['goal_id'] == 'goal-1'
    assert written['provenance'][0]['id'] == 'manual-1'


def test_action_item_router_rejects_unverifiable_workstream_link_before_write(monkeypatch):
    task_links.clear_workstream_goal_resolver()
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'create_action_item',
        lambda *args, **kwargs: pytest.fail('must reject before write'),
    )
    request = CanonicalTaskCreate(description='x', goal_id='goal-1', workstream_id='workstream-1')

    with pytest.raises(HTTPException) as error:
        action_items_router.create_action_item(request, uid='user-1')

    assert error.value.status_code == 409


def test_action_item_router_maps_exhausted_contention_to_retryable_503(monkeypatch):
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'create_action_item',
        MagicMock(side_effect=FirestoreContentionExhausted('contention')),
    )

    with pytest.raises(HTTPException) as error:
        action_items_router.create_action_item(ActionItemCreateRequest(description='Retry me'), uid='user-1')

    assert error.value.status_code == 503
    assert error.value.detail == 'Service temporarily unavailable'


def test_action_item_batch_router_maps_exhausted_contention_to_retryable_503(monkeypatch):
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'create_action_items_batch',
        MagicMock(side_effect=FirestoreContentionExhausted('contention')),
    )

    with pytest.raises(HTTPException) as error:
        action_items_router.create_action_items_batch(
            [ActionItemCreateRequest(description='Retry me')],
            uid='user-1',
        )

    assert error.value.status_code == 503
    assert error.value.detail == 'Service temporarily unavailable'
