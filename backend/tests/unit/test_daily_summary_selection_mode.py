"""Selection-mode dispatch and notifications-job run lock (#13210).

``utils.other.notifications`` pulls heavy deps at import, so this file loads it
through the sanctioned ``stub_modules`` + ``load_module_fresh`` seam (same
fixture approach as ``test_daily_summary_job_resilience.py``). Selectors are
stubbed on the ``notification_db`` module object; ``get_users_for_daily_summary_indexed``
is called by attribute name and does not have to exist on the real database module.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, List, Tuple

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

# Imported for its cost, not its API. The job imports learned_today, which builds
# pydantic models at import; paying that here keeps the fast-unit CPU duration
# guard measuring the tests rather than a one-time import.
import utils.memory.learned_today  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parents[2]

UserRow = Tuple[str, List[str], str]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


async def _fake_run_blocking(_executor: Any, fn: Any, *args: Any) -> Any:
    return fn(*args)


@contextmanager
def _loaded_notifications() -> Iterator[Tuple[ModuleType, ModuleType, ModuleType]]:
    async def no_async_work(*_args: Any, **_kwargs: Any) -> None:
        return None

    def no_db_work(*_args: Any, **_kwargs: Any) -> List[Any]:
        return []

    notification_db = _module(
        'database.notifications',
        get_users_for_daily_summary=no_db_work,
        get_users_for_daily_summary_indexed=no_db_work,
        get_users_token_in_timezones=no_db_work,
        get_users_id_in_timezones=no_db_work,
    )
    redis_db = _module(
        'database.redis_db',
        try_acquire_daily_summary_lock=lambda *_args: True,
        release_daily_summary_lock=lambda *_args: None,
        try_acquire_notifications_job_run_lock=lambda *_args, **_kwargs: True,
        try_acquire_daily_wear_lock=lambda *_args, **_kwargs: True,
        release_notifications_job_run_lock=lambda *_args, **_kwargs: None,
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
        'database._client': AutoMockModule('database._client'),
        'database.conversations': _module('database.conversations', get_conversations=lambda *_a, **_k: []),
        'database.notifications': notification_db,
        'database.redis_db': redis_db,
        'models.notification_message': _module(
            'models.notification_message',
            NotificationMessage=notification_message,
        ),
        'utils.conversations.factory': _module('utils.conversations.factory', deserialize_conversation=lambda v: v),
        'utils.executors': _module(
            'utils.executors',
            db_executor=object(),
            postprocess_executor=object(),
            run_blocking=_fake_run_blocking,
        ),
        'utils.llm.external_integrations': _module(
            'utils.llm.external_integrations',
            generate_comprehensive_daily_summary=lambda *_a, **_k: {},
        ),
        'utils.notifications': _module(
            'utils.notifications',
            send_bulk_notification=no_async_work,
            send_notification=lambda *_a, **_k: None,
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
        yield notifications, notification_db, redis_db


def _rows(*uids: str) -> List[UserRow]:
    return [(uid, [f'token-{uid}'], 'UTC') for uid in uids]


def _recording_selector(label: str, rows_by_chunk0: dict[str, List[UserRow]], calls: list) -> Any:
    def selector(chunk: List[str], hour: int) -> List[UserRow]:
        calls.append((label, tuple(chunk), hour))
        return list(rows_by_chunk0.get(chunk[0], []))

    return selector


# --------------------------------------------------------------- env mode


def test_selection_mode_unset_defaults_to_legacy(monkeypatch) -> None:
    with _loaded_notifications() as (notifications, _db, _redis):
        monkeypatch.delenv('DAILY_SUMMARY_SELECTION_MODE', raising=False)
        assert notifications._selection_mode_from_env() == 'legacy'


def test_selection_mode_normalizes_indexed(monkeypatch) -> None:
    with _loaded_notifications() as (notifications, _db, _redis):
        monkeypatch.setenv('DAILY_SUMMARY_SELECTION_MODE', 'INDEXED')
        assert notifications._selection_mode_from_env() == 'indexed'
        monkeypatch.setenv('DAILY_SUMMARY_SELECTION_MODE', ' indexed ')
        assert notifications._selection_mode_from_env() == 'indexed'


def test_selection_mode_shadow(monkeypatch) -> None:
    with _loaded_notifications() as (notifications, _db, _redis):
        monkeypatch.setenv('DAILY_SUMMARY_SELECTION_MODE', 'shadow')
        assert notifications._selection_mode_from_env() == 'shadow'


def test_selection_mode_garbage_falls_back_to_legacy_with_warning(monkeypatch, caplog) -> None:
    with _loaded_notifications() as (notifications, _db, _redis):
        monkeypatch.setenv('DAILY_SUMMARY_SELECTION_MODE', 'not-a-mode')
        with caplog.at_level(logging.WARNING):
            assert notifications._selection_mode_from_env() == 'legacy'
        assert 'daily_summary_selection_mode_unknown' in caplog.text
        assert 'not-a-mode' in caplog.text


# --------------------------------------------------------------- selector dispatch


def test_legacy_mode_calls_only_legacy_selector() -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'legacy'
        calls: list = []
        indexed_calls: list = []

        def indexed(_chunk: List[str], _hour: int) -> List[UserRow]:
            indexed_calls.append(_chunk)
            raise AssertionError('indexed selector must not run in legacy mode')

        notification_db.get_users_for_daily_summary = _recording_selector('legacy', {'UTC': _rows('uid-legacy')}, calls)
        notification_db.get_users_for_daily_summary_indexed = indexed

        users, error, every = asyncio.run(notifications._get_users_for_daily_summary(['UTC'], 22))

        assert users == _rows('uid-legacy')
        assert error is None
        assert every is True
        assert calls == [('legacy', ('UTC',), 22)]
        assert indexed_calls == []


def test_indexed_mode_calls_only_indexed_selector() -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'indexed'
        calls: list = []
        legacy_calls: list = []

        def legacy(_chunk: List[str], _hour: int) -> List[UserRow]:
            legacy_calls.append(_chunk)
            raise AssertionError('legacy selector must not run in indexed mode')

        notification_db.get_users_for_daily_summary = legacy
        notification_db.get_users_for_daily_summary_indexed = _recording_selector(
            'indexed', {'UTC': _rows('uid-indexed')}, calls
        )

        users, error, every = asyncio.run(notifications._get_users_for_daily_summary(['UTC'], 22))

        assert users == _rows('uid-indexed')
        assert error is None
        assert every is True
        assert calls == [('indexed', ('UTC',), 22)]
        assert legacy_calls == []


def test_shadow_mode_returns_legacy_and_logs_set_diff(caplog) -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'shadow'
        calls: list = []
        notification_db.get_users_for_daily_summary = _recording_selector(
            'legacy', {'UTC': _rows('uid-a', 'uid-b', 'uid-c')}, calls
        )
        notification_db.get_users_for_daily_summary_indexed = _recording_selector(
            'indexed', {'UTC': _rows('uid-b', 'uid-c', 'uid-d')}, calls
        )

        with caplog.at_level(logging.INFO):
            users, error, every = asyncio.run(notifications._get_users_for_daily_summary(['UTC'], 22))

        assert users == _rows('uid-a', 'uid-b', 'uid-c')
        assert error is None
        assert every is True
        assert [label for label, _chunk, _hour in calls] == ['legacy', 'indexed']
        assert 'daily_summary_selection_shadow hour=22 legacy=3 indexed=3 only_legacy=1 only_indexed=1' in caplog.text
        assert "sample_only_legacy=['uid-a']" in caplog.text
        assert "sample_only_indexed=['uid-d']" in caplog.text


def test_shadow_mode_indexed_exception_does_not_change_legacy_result(caplog) -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'shadow'
        legacy_rows = _rows('uid-legacy')

        notification_db.get_users_for_daily_summary = lambda _chunk, _hour: list(legacy_rows)

        def indexed(_chunk: List[str], _hour: int) -> List[UserRow]:
            raise RuntimeError('indexed down')

        notification_db.get_users_for_daily_summary_indexed = indexed

        with caplog.at_level(logging.WARNING):
            users, error, every = asyncio.run(notifications._get_users_for_daily_summary(['UTC'], 22))

        assert users == legacy_rows
        assert error is None
        assert every is True
        assert 'daily_summary_selection_shadow_failed hour=22' in caplog.text
        assert 'indexed down' in caplog.text
        assert 'daily_summary_selection_shadow hour=' not in caplog.text


def test_partial_read_reports_first_error_in_legacy_mode() -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'legacy'
        zones = [f'tz{i:02d}' for i in range(31)]

        def legacy(chunk: List[str], _hour: int) -> List[UserRow]:
            if 'tz30' in chunk:
                raise RuntimeError('legacy chunk failed')
            return _rows('uid-ok')

        def indexed(_chunk: List[str], _hour: int) -> List[UserRow]:
            raise AssertionError('indexed selector must not run in legacy mode')

        notification_db.get_users_for_daily_summary = legacy
        notification_db.get_users_for_daily_summary_indexed = indexed

        users, error, every = asyncio.run(notifications._get_users_for_daily_summary(zones, 22))

        assert users == _rows('uid-ok')
        assert every is False
        assert isinstance(error, RuntimeError)
        assert str(error) == 'legacy chunk failed'


def test_partial_read_reports_first_error_in_indexed_mode() -> None:
    with _loaded_notifications() as (notifications, notification_db, _redis):
        notifications.DAILY_SUMMARY_SELECTION_MODE = 'indexed'
        zones = [f'tz{i:02d}' for i in range(31)]

        def indexed(chunk: List[str], _hour: int) -> List[UserRow]:
            if 'tz30' in chunk:
                raise RuntimeError('indexed chunk failed')
            return _rows('uid-ok')

        def legacy(_chunk: List[str], _hour: int) -> List[UserRow]:
            raise AssertionError('legacy selector must not run in indexed mode')

        notification_db.get_users_for_daily_summary = legacy
        notification_db.get_users_for_daily_summary_indexed = indexed

        users, error, every = asyncio.run(notifications._get_users_for_daily_summary(zones, 22))

        assert users == _rows('uid-ok')
        assert every is False
        assert isinstance(error, RuntimeError)
        assert str(error) == 'indexed chunk failed'


# --------------------------------------------------------------- start_cron_job lock


def _install_send_spies(notifications: ModuleType) -> list[str]:
    calls: list[str] = []

    async def fake_daily() -> None:
        calls.append('daily')

    async def fake_summary() -> Any:
        calls.append('summary')
        return notifications.DailySummaryCronOutcome(ok=True)

    notifications.send_daily_notification = fake_daily
    notifications.send_daily_summary_notification = fake_summary
    return calls


def test_start_cron_job_skips_when_lock_held(caplog) -> None:
    with _loaded_notifications() as (notifications, _db, redis_db):
        redis_db.try_acquire_notifications_job_run_lock = lambda *_a, **_k: False
        released: list[str] = []
        redis_db.release_notifications_job_run_lock = lambda token: released.append(token)
        calls = _install_send_spies(notifications)

        with caplog.at_level(logging.WARNING):
            asyncio.run(notifications.start_cron_job())

        assert calls == []
        assert released == []
        assert 'notifications_job_run_skipped reason=overlap' in caplog.text


def test_start_cron_job_runs_and_releases_same_token() -> None:
    with _loaded_notifications() as (notifications, _db, redis_db):
        acquired: list[str] = []
        released: list[str] = []

        def acquire(token: str, ttl: int = 55 * 60) -> bool:
            acquired.append(token)
            assert ttl == 55 * 60
            return True

        redis_db.try_acquire_notifications_job_run_lock = acquire
        redis_db.release_notifications_job_run_lock = lambda token: released.append(token)
        calls = _install_send_spies(notifications)

        asyncio.run(notifications.start_cron_job())

        assert calls == ['daily', 'summary']
        assert acquired == released
        assert len(acquired) == 1
        assert acquired[0]


def test_start_cron_job_fails_open_when_acquire_raises(caplog) -> None:
    with _loaded_notifications() as (notifications, _db, redis_db):

        def acquire(_token: str, ttl: int = 55 * 60) -> bool:
            raise RuntimeError('redis down')

        released: list[str] = []
        redis_db.try_acquire_notifications_job_run_lock = acquire
        redis_db.release_notifications_job_run_lock = lambda token: released.append(token)
        calls = _install_send_spies(notifications)

        with caplog.at_level(logging.WARNING):
            asyncio.run(notifications.start_cron_job())

        assert calls == ['summary']
        assert released == []
        assert 'notifications_job_run_lock_acquire_failed' in caplog.text
        assert 'redis down' in caplog.text


def test_send_daily_wear_disabled_does_not_bulk_send() -> None:
    with _loaded_notifications() as (notifications, _db, _redis):
        sent: list[object] = []

        async def fake_bulk(*_a: Any, **_k: Any) -> None:
            sent.append(1)

        notifications.send_bulk_notification = fake_bulk
        asyncio.run(notifications.send_daily_notification())
        assert sent == []


def test_send_daily_wear_caps_one_send_per_uid(caplog) -> None:
    with _loaded_notifications() as (notifications, db, redis_db):
        notifications.should_send_wear_device_reminder = lambda: True
        notifications._get_timezones_at_time = lambda _t: ['America/New_York']
        db.get_users_id_in_timezones = lambda _chunk: [
            ('u1', ['t1'], 'America/New_York'),
            ('u2', [], 'America/New_York'),
            ('u3', ['t3a', 't3b'], 'America/New_York'),
        ]
        held: list[str] = []

        def wear_lock(uid: str, _date: str, ttl: int = 60 * 60 * 24) -> bool:
            assert ttl == 60 * 60 * 24
            if uid in held:
                return False
            held.append(uid)
            return True

        redis_db.try_acquire_daily_wear_lock = wear_lock
        sent: list[list[str]] = []

        async def fake_bulk(tokens: list[str], title: str, body: str) -> None:
            sent.append(list(tokens))
            assert title == 'omi says'

        notifications.send_bulk_notification = fake_bulk

        with caplog.at_level(logging.INFO):
            asyncio.run(notifications.send_daily_notification())
            asyncio.run(notifications.send_daily_notification())

        assert sent == [['t1', 't3a', 't3b']]
        assert held == ['u1', 'u3']
        assert 'notification_blast kind=wear users=2 tokens=3' in caplog.text
