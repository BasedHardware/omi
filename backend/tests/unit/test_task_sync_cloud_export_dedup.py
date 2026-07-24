import asyncio
from pathlib import Path
from types import ModuleType
from typing import Any

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _stubs(store: dict[str, dict[str, Any]], create_calls: list[dict[str, Any]], *, default_app: str = 'todoist'):
    """Stub the database + integration ops so utils.task_sync loads without google.cloud.firestore.

    ``store`` maps action-item id to its persisted Firestore document. The stubbed
    ``get_action_item`` reads from it and ``update_action_item`` writes the export fields back,
    so a second auto-sync sees ``exported=True`` exactly like a retry against real Firestore.
    """

    def get_action_item(_uid: str, item_id: str):
        return store.get(item_id)

    def update_action_item(_uid: str, item_id: str, updates: dict[str, Any]) -> None:
        store.setdefault(item_id, {}).update(updates)

    async def create_task_internal(**kwargs: Any) -> dict[str, Any]:
        create_calls.append(kwargs)
        return {'success': True, 'external_task_id': f'ext-{len(create_calls)}'}

    return {
        'database.users': _module(
            'database.users',
            get_default_task_integration=lambda _uid: default_app,
            get_task_integration=lambda _uid, _app: {'connected': True},
        ),
        'database.action_items': _module(
            'database.action_items',
            get_action_item=get_action_item,
            update_action_item=update_action_item,
            batch_set_sync_requested=lambda *_a, **_k: None,
        ),
        'utils.notifications': _module(
            'utils.notifications',
            send_apple_reminders_sync_push_async=lambda **_k: None,
        ),
        'utils.task_integrations_ops': _module(
            'utils.task_integrations_ops',
            create_task_internal=create_task_internal,
        ),
    }


def test_retried_cloud_sync_does_not_create_a_second_external_task() -> None:
    store = {'task-1': {'id': 'task-1', 'description': 'Plan launch'}}
    create_calls: list[dict[str, Any]] = []

    with stub_modules(_stubs(store, create_calls)):
        task_sync = load_module_fresh('utils.task_sync', str(BACKEND_DIR / 'utils' / 'task_sync.py'))

        async def exercise():
            item = {'id': 'task-1', 'description': 'Plan launch'}
            first = await task_sync.auto_sync_action_item('user-1', item)
            # The client retried the create. The router deduped the Firestore document to the same
            # id and submitted auto-sync a second time with the same payload.
            second = await task_sync.auto_sync_action_item('user-1', item)
            return first, second

        first, second = asyncio.run(exercise())

    assert first['synced'] is True
    assert first['platform'] == 'todoist'
    # The external task is created exactly once across the retry.
    assert len(create_calls) == 1
    assert second['synced'] is True
    assert second.get('reason') == 'already_exported'
    assert store['task-1'].get('exported') is True


def test_batch_cloud_sync_skips_items_already_exported() -> None:
    store = {
        'task-a': {'id': 'task-a', 'description': 'Already done', 'exported': True},
        'task-b': {'id': 'task-b', 'description': 'Fresh'},
    }
    create_calls: list[dict[str, Any]] = []

    with stub_modules(_stubs(store, create_calls)):
        task_sync = load_module_fresh('utils.task_sync', str(BACKEND_DIR / 'utils' / 'task_sync.py'))

        items = [
            {'id': 'task-a', 'description': 'Already done'},
            {'id': 'task-b', 'description': 'Fresh'},
        ]
        results = asyncio.run(task_sync.auto_sync_action_items_batch('user-1', items))

    # Only the not-yet-exported item hits the external service.
    assert len(create_calls) == 1
    assert create_calls[0]['title'] == 'Fresh'
    assert results[0].get('reason') == 'already_exported'
    assert results[1]['synced'] is True


def test_first_cloud_sync_creates_the_external_task() -> None:
    store = {'task-9': {'id': 'task-9', 'description': 'Write notes'}}
    create_calls: list[dict[str, Any]] = []

    with stub_modules(_stubs(store, create_calls)):
        task_sync = load_module_fresh('utils.task_sync', str(BACKEND_DIR / 'utils' / 'task_sync.py'))

        item = {'id': 'task-9', 'description': 'Write notes'}
        result = asyncio.run(task_sync.auto_sync_action_item('user-1', item))

    assert result['synced'] is True
    assert len(create_calls) == 1
    assert store['task-9'].get('exported') is True
