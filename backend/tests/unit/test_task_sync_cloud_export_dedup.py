import asyncio
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _Harness:
    """Per-test stub state, swapped without re-importing ``utils.task_sync``.

    Each test used to run its own ``stub_modules`` + ``load_module_fresh`` pair, and
    the block teardown evicts every module imported inside it (httpx and friends),
    so all four tests re-paid the full transitive import in the duration-guard's
    measured call phase: 0.5-1.0s CPU per test on CI runners, past the 1.0s
    fast-unit fail budget whenever the file-isolated runner saturated the machine.
    One module-scoped import pays that cost once, in the first test's setup phase,
    which the guard deliberately does not charge.
    """

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.fail_on: set[str] = set()

    def seed(self, store: dict[str, dict[str, Any]], *, fail_on: set[str] | None = None) -> None:
        self.store = store
        self.create_calls = []
        self.fail_on = fail_on or set()


def _stubs(harness: _Harness, *, default_app: str = 'todoist'):
    """Stub the database + integration ops so utils.task_sync loads without google.cloud.firestore.

    The stubbed functions dispatch through ``harness`` so the single module-scoped
    import serves every test; each test seeds its own store first.
    ``harness.store`` maps action-item id to its persisted Firestore document, and the
    stubbed ``get_action_item`` reads from it while ``update_action_item`` writes the
    export fields back, so a second auto-sync sees ``exported=True`` exactly like a
    retry against real Firestore. ``harness.fail_on`` raises inside
    ``create_task_internal`` for the given action-item titles, simulating a transient
    per-item failure such as an OAuth preflight error.
    """

    def get_action_item(_uid: str, item_id: str):
        return harness.store.get(item_id)

    def update_action_item(_uid: str, item_id: str, updates: dict[str, Any]) -> None:
        harness.store.setdefault(item_id, {}).update(updates)

    async def create_task_internal(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get('title') in harness.fail_on:
            raise RuntimeError(f"token refresh failed for {kwargs.get('title')}")
        harness.create_calls.append(kwargs)
        return {'success': True, 'external_task_id': f'ext-{len(harness.create_calls)}'}

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


@pytest.fixture(scope='module')
def task_sync():
    harness = _Harness()
    with stub_modules(_stubs(harness)):
        yield load_module_fresh('utils.task_sync', str(BACKEND_DIR / 'utils' / 'task_sync.py')), harness


def test_retried_cloud_sync_does_not_create_a_second_external_task(task_sync) -> None:
    module, harness = task_sync
    harness.seed({'task-1': {'id': 'task-1', 'description': 'Plan launch'}})

    async def exercise():
        item = {'id': 'task-1', 'description': 'Plan launch'}
        first = await module.auto_sync_action_item('user-1', item)
        # The client retried the create. The router deduped the Firestore document to the same
        # id and submitted auto-sync a second time with the same payload.
        second = await module.auto_sync_action_item('user-1', item)
        return first, second

    first, second = asyncio.run(exercise())

    assert first['synced'] is True
    assert first['platform'] == 'todoist'
    # The external task is created exactly once across the retry.
    assert len(harness.create_calls) == 1
    assert second['synced'] is True
    assert second.get('reason') == 'already_exported'
    assert harness.store['task-1'].get('exported') is True


def test_batch_cloud_sync_skips_items_already_exported(task_sync) -> None:
    module, harness = task_sync
    harness.seed(
        {
            'task-a': {'id': 'task-a', 'description': 'Already done', 'exported': True},
            'task-b': {'id': 'task-b', 'description': 'Fresh'},
        }
    )

    items = [
        {'id': 'task-a', 'description': 'Already done'},
        {'id': 'task-b', 'description': 'Fresh'},
    ]
    results = asyncio.run(module.auto_sync_action_items_batch('user-1', items))

    # Only the not-yet-exported item hits the external service.
    assert len(harness.create_calls) == 1
    assert harness.create_calls[0]['title'] == 'Fresh'
    assert results[0].get('reason') == 'already_exported'
    assert results[1]['synced'] is True


def test_first_cloud_sync_creates_the_external_task(task_sync) -> None:
    module, harness = task_sync
    harness.seed({'task-9': {'id': 'task-9', 'description': 'Write notes'}})

    item = {'id': 'task-9', 'description': 'Write notes'}
    result = asyncio.run(module.auto_sync_action_item('user-1', item))

    assert result['synced'] is True
    assert len(harness.create_calls) == 1
    assert harness.store['task-9'].get('exported') is True


def test_batch_cloud_sync_isolates_a_failing_item_from_the_rest(task_sync) -> None:
    module, harness = task_sync
    harness.seed(
        {
            'task-0': {'id': 'task-0', 'description': 'First'},
            'task-1': {'id': 'task-1', 'description': 'Second'},
            'task-2': {'id': 'task-2', 'description': 'Third'},
        },
        fail_on={'Second'},
    )

    items = [
        {'id': 'task-0', 'description': 'First'},
        {'id': 'task-1', 'description': 'Second'},
        {'id': 'task-2', 'description': 'Third'},
    ]
    results = asyncio.run(module.auto_sync_action_items_batch('user-1', items))

    # Item 0 (before the failure) and item 2 (after it) both still get attempted and succeed;
    # only the failing item itself reports an error.
    assert results[0]['synced'] is True
    assert harness.store['task-0'].get('exported') is True
    assert results[1]['synced'] is False
    assert 'error' in results[1]
    assert results[2]['synced'] is True
    assert harness.store['task-2'].get('exported') is True
    assert len(harness.create_calls) == 2
