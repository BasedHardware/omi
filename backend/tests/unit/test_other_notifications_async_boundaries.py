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
def _loaded_other_notifications() -> Iterator[tuple[ModuleType, ModuleType]]:
    async def no_async_work(*_args: Any, **_kwargs: Any) -> None:
        return None

    def no_db_work(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    notification_db = _module(
        'database.notifications',
        get_users_for_daily_summary=no_db_work,
        get_users_token_in_timezones=no_db_work,
    )
    notification_message = type(
        'NotificationMessage',
        (),
        {
            '__init__': lambda self, **kwargs: self.__dict__.update(kwargs),
            'get_message_as_dict': staticmethod(lambda message: dict(message.__dict__)),
        },
    )
    stubs = {
        'database.conversations': _module('database.conversations', get_conversations=lambda *_args, **_kwargs: []),
        'database.notifications': notification_db,
        'database.redis_db': _module('database.redis_db', try_acquire_daily_summary_lock=lambda *_args: True),
        'models.notification_message': _module(
            'models.notification_message',
            NotificationMessage=notification_message,
        ),
        'utils.conversations.factory': _module(
            'utils.conversations.factory',
            deserialize_conversation=lambda value: value,
        ),
        'utils.llm.external_integrations': _module(
            'utils.llm.external_integrations',
            generate_comprehensive_daily_summary=lambda *_args: {},
        ),
        'utils.notifications': _module(
            'utils.notifications',
            send_bulk_notification=no_async_work,
            send_notification=lambda *_args, **_kwargs: None,
        ),
        'utils.webhooks': _module('utils.webhooks', day_summary_webhook=no_async_work),
        'database.daily_summaries': _module(
            'database.daily_summaries',
            get_daily_summary_by_date=lambda *_args: None,
            create_daily_summary=lambda *_args: 'summary-id',
        ),
    }

    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.other.notifications',
            str(BACKEND_DIR / 'utils' / 'other' / 'notifications.py'),
        )
        yield notifications, notification_db


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


def test_daily_summary_user_read_runs_off_loop_and_preserves_empty_result() -> None:
    with _loaded_other_notifications() as (notifications, notification_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            calls: list[tuple[list[str], int]] = []

            def blocking_read(timezones: list[str], target_hour: int) -> list[Any]:
                calls.append((timezones, target_hour))
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return []

            notifications._get_timezones_grouped_by_hour = lambda: {8: ['UTC']}
            notification_db.get_users_for_daily_summary = blocking_read

            result = await _assert_loop_responsive_while_worker_waits(
                notifications.send_daily_summary_notification(),
                entered,
                release,
            )
            assert result is None
            assert calls == [(['UTC'], 8)]

        asyncio.run(exercise())


def test_timezone_token_read_runs_off_loop_and_returns_tokens() -> None:
    with _loaded_other_notifications() as (notifications, notification_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            calls: list[list[str]] = []

            def blocking_read(timezones: list[str]) -> list[str]:
                calls.append(timezones)
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return ['token-a', 'token-b']

            notifications._get_timezones_at_time = lambda _target: ['Asia/Kolkata']
            notification_db.get_users_token_in_timezones = blocking_read

            result = await _assert_loop_responsive_while_worker_waits(
                notifications._get_users_in_timezone('08:00'),
                entered,
                release,
            )
            assert result == ['token-a', 'token-b']
            assert calls == [['Asia/Kolkata']]

        asyncio.run(exercise())


def test_daily_summary_db_failure_remains_fail_soft() -> None:
    with _loaded_other_notifications() as (notifications, notification_db):
        notifications._get_timezones_grouped_by_hour = lambda: {8: ['UTC']}

        def fail_read(_timezones: list[str], _target_hour: int) -> list[Any]:
            raise RuntimeError('firestore unavailable')

        notification_db.get_users_for_daily_summary = fail_read

        assert asyncio.run(notifications.send_daily_summary_notification()) is None
