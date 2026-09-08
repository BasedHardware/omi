import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@contextmanager
def _loaded_task_sync() -> Iterator[tuple[ModuleType, ModuleType, list[list[dict[str, Any]]]]]:
    users_db = _module(
        'database.users',
        get_default_task_integration=lambda _uid: 'apple_reminders',
        get_task_integration=lambda _uid, _app: {'connected': True},
    )
    action_items_db = _module(
        'database.action_items',
        batch_set_sync_requested=lambda _uid, _item_ids: None,
        update_action_item=lambda *_args, **_kwargs: None,
    )
    pushed_batches: list[list[dict[str, Any]]] = []

    async def send_apple_reminders_sync_push_async(*, user_id: str, action_items: list[dict[str, Any]]) -> bool:
        assert user_id == 'user-1'
        pushed_batches.append(action_items)
        return True

    async def create_task_internal(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError('cloud integration path must not run')

    stubs = {
        'database.users': users_db,
        'database.action_items': action_items_db,
        'utils.notifications': _module(
            'utils.notifications',
            send_apple_reminders_sync_push_async=send_apple_reminders_sync_push_async,
        ),
        'utils.task_integrations_ops': _module(
            'utils.task_integrations_ops',
            create_task_internal=create_task_internal,
        ),
    }

    with stub_modules(stubs):
        task_sync = load_module_fresh(
            'utils.task_sync',
            str(BACKEND_DIR / 'utils' / 'task_sync.py'),
        )
        yield task_sync, action_items_db, pushed_batches


async def _assert_loop_responsive_while_worker_waits(
    awaitable: Any,
    entered: asyncio.Event,
    release: threading.Event,
) -> Any:
    task = asyncio.create_task(awaitable)
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        loop_tick = asyncio.Event()
        asyncio.get_running_loop().call_soon(loop_tick.set)
        await asyncio.wait_for(loop_tick.wait(), timeout=1)
        assert not task.done()
    finally:
        release.set()
    return await asyncio.wait_for(task, timeout=2)


def test_single_apple_reminder_sync_offloads_batch_update_and_preserves_result() -> None:
    with _loaded_task_sync() as (task_sync, action_items_db, pushed_batches):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            db_calls: list[tuple[str, list[str]]] = []

            def blocking_batch_update(uid: str, item_ids: list[str]) -> None:
                db_calls.append((uid, item_ids))
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)

            action_items_db.batch_set_sync_requested = blocking_batch_update
            item = {'id': 'task-1', 'description': 'Plan launch'}

            result = await _assert_loop_responsive_while_worker_waits(
                task_sync.auto_sync_action_item('user-1', item),
                entered,
                release,
            )

            assert result == {'synced': True, 'platform': 'apple_reminders', 'pending_device': True}
            assert db_calls == [('user-1', ['task-1'])]
            assert pushed_batches == [[item]]

        asyncio.run(exercise())


def test_batch_apple_reminder_sync_offloads_batch_update_and_preserves_per_item_results() -> None:
    with _loaded_task_sync() as (task_sync, action_items_db, pushed_batches):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            db_calls: list[tuple[str, list[str]]] = []

            def blocking_batch_update(uid: str, item_ids: list[str]) -> None:
                db_calls.append((uid, item_ids))
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)

            action_items_db.batch_set_sync_requested = blocking_batch_update
            items = [
                {'id': 'task-1', 'description': 'Plan launch'},
                {'id': 'task-2', 'description': 'Write notes'},
            ]

            results = await _assert_loop_responsive_while_worker_waits(
                task_sync.auto_sync_action_items_batch('user-1', items),
                entered,
                release,
            )

            expected = {'synced': True, 'platform': 'apple_reminders', 'pending_device': True}
            assert results == [expected, expected]
            assert db_calls == [('user-1', ['task-1', 'task-2'])]
            assert pushed_batches == [items]

        asyncio.run(exercise())


def test_apple_reminder_sync_preserves_single_and_batch_error_results() -> None:
    with _loaded_task_sync() as (task_sync, action_items_db, pushed_batches):

        def fail_batch_update(_uid: str, _item_ids: list[str]) -> None:
            raise RuntimeError('firestore unavailable')

        action_items_db.batch_set_sync_requested = fail_batch_update
        item = {'id': 'task-1', 'description': 'Plan launch'}

        async def exercise() -> None:
            single = await task_sync.auto_sync_action_item('user-1', item)
            batch = await task_sync.auto_sync_action_items_batch('user-1', [item, dict(item, id='task-2')])

            assert single == {'synced': False, 'error': 'firestore unavailable'}
            assert batch == [
                {'synced': False, 'error': 'firestore unavailable'},
                {'synced': False, 'error': 'firestore unavailable'},
            ]

        asyncio.run(exercise())
        assert pushed_batches == []
