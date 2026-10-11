"""A failed cloud export must not discard other items' attempts or outcomes."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from utils import task_integrations_ops, task_sync


@pytest.fixture
def cloud_batch(monkeypatch):
    items = [{'id': f'task-{i}', 'description': f'Task {i}'} for i in range(3)]
    state = SimpleNamespace(
        items=items,
        stored={item['id']: dict(item) for item in items},
        reads=[],
        creates=[],
        writes=[],
        fault=None,
        rejected_title=None,
    )

    def read(_uid, item_id):
        state.reads.append(item_id)
        if state.fault == ('read', item_id):
            raise RuntimeError('private database exception')
        return dict(state.stored[item_id])

    def write(_uid, item_id, updates):
        state.writes.append(item_id)
        if state.fault == ('write', item_id):
            raise RuntimeError('private database exception')
        state.stored[item_id].update(updates)

    def provider(request):
        body = json.loads(request.content)
        if request.url == 'https://api.todoist.com/api/v1/tasks':
            title = body['content']
            response_body = {'id': f'external-{title}'}
        else:
            assert request.url == 'https://app.asana.com/api/1.0/tasks'
            title = body['data']['name']
            response_body = {'data': {'gid': f'external-{title}'}}
        state.creates.append(title)
        if title == state.rejected_title:
            return httpx.Response(503)
        return httpx.Response(201, json=response_body)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        task_sync.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(provider), **kwargs)
    )
    monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda _uid: 'todoist')
    monkeypatch.setattr(
        task_sync.users_db, 'get_task_integration', lambda *_args: {'connected': True, 'access_token': 'test-token'}
    )
    monkeypatch.setattr(task_sync.action_items_db, 'get_action_item', read)
    monkeypatch.setattr(task_sync.action_items_db, 'update_action_item', write)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_index', [0, 1, 2])
@pytest.mark.parametrize('stage', ['read', 'write'])
async def test_database_failure_only_fails_its_item(cloud_batch, caplog, stage, failed_index):
    batch = cloud_batch
    batch.fault = (stage, f'task-{failed_index}')

    results = await task_sync.auto_sync_action_items_batch('test-user', batch.items)

    assert [result['synced'] for result in results] == [i != failed_index for i in range(3)]
    assert batch.reads == ['task-0', 'task-1', 'task-2']
    expected_creates = [f'Task {i}' for i in range(3) if stage == 'write' or i != failed_index]
    assert batch.creates == expected_creates
    assert [bool(batch.stored[f'task-{i}'].get('exported')) for i in range(3)] == [i != failed_index for i in range(3)]
    assert results[failed_index] == {'synced': False, 'platform': 'todoist', 'error': 'Auto-sync failed'}
    assert 'private database exception' not in caplog.text
    assert 'RuntimeError' in caplog.text
    assert caplog.text.count('omi_fallback_event') == 1


@pytest.mark.asyncio
async def test_refresh_exception_preserves_previous_success_and_attempts_tail(cloud_batch, monkeypatch):
    batch = cloud_batch
    # This check runs before create_task_internal's provider-error handler, so a
    # transient OAuth refresh failure reaches the batch boundary as an exception.
    integration = {'connected': True, 'access_token': 'test-token', 'workspace_gid': 'test-workspace'}
    refresh = AsyncMock(side_effect=[integration, RuntimeError('refresh unavailable'), integration])
    monkeypatch.setattr(task_integrations_ops, 'ensure_valid_oauth_token', refresh)
    monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda _uid: 'asana')
    results = await task_sync.auto_sync_action_items_batch('test-user', batch.items)

    assert refresh.await_count == 3
    assert [result['synced'] for result in results] == [True, False, True]
    assert results[1] == {'synced': False, 'platform': 'asana', 'error': 'Auto-sync failed'}
    assert batch.creates == ['Task 0', 'Task 2']
    assert batch.writes == ['task-0', 'task-2']


@pytest.mark.asyncio
async def test_provider_rejection_and_export_dedup_preserve_order(cloud_batch):
    batch = cloud_batch
    batch.stored['task-0']['exported'] = True
    batch.rejected_title = 'Task 1'

    results = await task_sync.auto_sync_action_items_batch('test-user', batch.items)

    assert results[0] == {'synced': True, 'platform': 'todoist', 'reason': 'already_exported'}
    assert results[1] == {'synced': False, 'platform': 'todoist', 'error': 'Todoist API error: 503'}
    assert results[2] == {'synced': True, 'platform': 'todoist', 'external_task_id': 'external-Task 2'}
    assert batch.creates == ['Task 1', 'Task 2']


@pytest.mark.asyncio
async def test_cancellation_still_propagates_without_attempting_tail(cloud_batch, monkeypatch):
    create = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(task_sync, 'create_task_internal', create)

    with pytest.raises(asyncio.CancelledError):
        await task_sync.auto_sync_action_items_batch('test-user', cloud_batch.items)

    assert create.await_count == 1
    assert cloud_batch.reads == ['task-0']
    assert cloud_batch.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize('connected', [None, False])
async def test_shared_configuration_failure_prevents_all_exports(cloud_batch, monkeypatch, connected):
    integration = None if connected is None else {'connected': False}
    monkeypatch.setattr(task_sync.users_db, 'get_task_integration', lambda *_args: integration)

    results = await task_sync.auto_sync_action_items_batch('test-user', cloud_batch.items)

    reason = 'integration_not_found' if connected is None else 'integration_not_connected'
    assert results == [{'synced': False, 'reason': reason}] * 3
    assert cloud_batch.reads == cloud_batch.creates == cloud_batch.writes == []
