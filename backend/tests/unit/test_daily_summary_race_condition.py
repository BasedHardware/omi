"""
Unit tests for daily summary race condition fix (#4594).

Verifies that:
1. try_acquire_daily_summary_lock uses atomic SETNX
2. Only the first caller acquires the lock; concurrent callers are rejected
3. _send_summary_notification skips work when lock is already held
"""

import threading
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _PytzFixedTimezone(tzinfo):
    def __init__(self, offset: timedelta, name: str):
        self._offset = offset
        self._zone = timezone(offset, name)

    def utcoffset(self, dt):
        return self._offset

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return self._zone.tzname(dt)

    def fromutc(self, value):
        return (value + self._offset).replace(tzinfo=self)

    def localize(self, value):
        return value.replace(tzinfo=self)


class _PytzEasternTimezone(tzinfo):
    _standard_offset = timedelta(hours=-5)
    _daylight_offset = timedelta(hours=-4)

    @staticmethod
    def _first_sunday_on_or_after(year: int, month: int, day: int) -> datetime:
        value = datetime(year, month, day)
        return value + timedelta(days=(6 - value.weekday()) % 7)

    @classmethod
    def _dst_local_bounds(cls, year: int) -> tuple[datetime, datetime]:
        start = cls._first_sunday_on_or_after(year, 3, 8).replace(hour=2)
        end = cls._first_sunday_on_or_after(year, 11, 1).replace(hour=2)
        return start, end

    @classmethod
    def _is_dst_local(cls, value: datetime) -> bool:
        start, end = cls._dst_local_bounds(value.year)
        return start <= value.replace(tzinfo=None) < end

    @classmethod
    def _is_dst_utc(cls, value: datetime) -> bool:
        start_local, end_local = cls._dst_local_bounds(value.year)
        start_utc = start_local - cls._standard_offset
        end_utc = end_local - cls._daylight_offset
        return start_utc <= value.replace(tzinfo=None) < end_utc

    def utcoffset(self, dt):
        if dt is None:
            return self._standard_offset
        return self._daylight_offset if self._is_dst_local(dt) else self._standard_offset

    def dst(self, dt):
        return self.utcoffset(dt) - self._standard_offset

    def tzname(self, dt):
        return "EDT" if self.dst(dt) else "EST"

    def fromutc(self, value):
        offset = self._daylight_offset if self._is_dst_utc(value) else self._standard_offset
        return (value + offset).replace(tzinfo=self)

    def localize(self, value):
        return value.replace(tzinfo=self)


_UTC_TZ = _PytzFixedTimezone(timedelta(0), "UTC")
_NY_TZ = _PytzEasternTimezone()
_PYTZ_ZONES = {"UTC": _UTC_TZ, "America/New_York": _NY_TZ}

pytz_stub = ModuleType("pytz")
pytz_stub.utc = _UTC_TZ
pytz_stub.all_timezones = list(_PYTZ_ZONES)
pytz_stub.timezone = lambda name: _PYTZ_ZONES.get(name, _UTC_TZ)

# Set up mock redis and real lock function
mock_r = MagicMock()


def try_acquire_daily_summary_lock(uid: str, date: str, ttl: int = 60 * 60 * 2) -> bool:
    result = mock_r.set(f'users:{uid}:daily_summary_lock:{date}', '1', ex=ttl, nx=True)
    return result is not None


@pytest.fixture
def notification_harness() -> Iterator[SimpleNamespace]:
    conversations_db = _module('database.conversations', get_conversations=MagicMock())
    notification_db = _module('database.notifications')
    daily_summaries_db = _module(
        'database.daily_summaries',
        get_daily_summary_by_date=MagicMock(return_value=None),
        create_daily_summary=MagicMock(return_value='summary-123'),
    )
    redis_db = _module(
        'database.redis_db',
        try_acquire_daily_summary_lock=try_acquire_daily_summary_lock,
    )

    mock_conversation = MagicMock()
    mock_conversation.transcript_segments = [{'text': 'hello'}]
    mock_conversation.discarded = False
    conversation_factory = _module(
        'utils.conversations.factory',
        deserialize_conversation=MagicMock(return_value=mock_conversation),
    )
    generate_summary = MagicMock()
    external_integrations = _module(
        'utils.llm.external_integrations',
        generate_comprehensive_daily_summary=generate_summary,
    )
    send_notification = MagicMock()
    notifications = _module(
        'utils.notifications',
        send_bulk_notification=MagicMock(),
        send_notification=send_notification,
    )
    notification_message = MagicMock()
    notification_message.get_message_as_dict = MagicMock(return_value={})
    executors = _module(
        'utils.executors',
        db_executor=MagicMock(),
        postprocess_executor=MagicMock(),
        run_blocking=MagicMock(),
    )

    stubs = {
        'pytz': pytz_stub,
        'database.conversations': conversations_db,
        'database.notifications': notification_db,
        'database.redis_db': redis_db,
        'database.daily_summaries': daily_summaries_db,
        'models.notification_message': _module(
            'models.notification_message',
            NotificationMessage=notification_message,
        ),
        'utils.conversations.factory': conversation_factory,
        'utils.llm.external_integrations': external_integrations,
        'utils.notifications': notifications,
        'utils.webhooks': _module('utils.webhooks', day_summary_webhook=MagicMock()),
        'utils.executors': executors,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            'utils.other.notifications',
            str(BACKEND_DIR / 'utils' / 'other' / 'notifications.py'),
        )
        yield SimpleNamespace(
            module=module,
            send_summary=module._send_summary_notification,
            conversations_db=conversations_db,
            daily_summaries_db=daily_summaries_db,
            generate_summary=generate_summary,
            send_notification=send_notification,
        )


class TestTryAcquireDailySummaryLock:
    """Tests for the atomic SETNX lock function."""

    def test_lock_acquired_returns_true(self):
        mock_r.set.return_value = True
        assert try_acquire_daily_summary_lock('uid1', '2026-02-07') is True
        mock_r.set.assert_called_with('users:uid1:daily_summary_lock:2026-02-07', '1', ex=7200, nx=True)

    def test_lock_already_held_returns_false(self):
        mock_r.set.return_value = None  # SETNX returns None when key exists
        assert try_acquire_daily_summary_lock('uid1', '2026-02-07') is False

    def test_custom_ttl(self):
        mock_r.set.return_value = True
        try_acquire_daily_summary_lock('uid1', '2026-02-07', ttl=3600)
        mock_r.set.assert_called_with('users:uid1:daily_summary_lock:2026-02-07', '1', ex=3600, nx=True)

    def test_different_users_get_separate_locks(self):
        mock_r.set.return_value = True
        try_acquire_daily_summary_lock('uid1', '2026-02-07')
        try_acquire_daily_summary_lock('uid2', '2026-02-07')
        calls = mock_r.set.call_args_list[-2:]
        assert calls[0][0][0] == 'users:uid1:daily_summary_lock:2026-02-07'
        assert calls[1][0][0] == 'users:uid2:daily_summary_lock:2026-02-07'

    def test_different_dates_get_separate_locks(self):
        mock_r.set.return_value = True
        try_acquire_daily_summary_lock('uid1', '2026-02-06')
        try_acquire_daily_summary_lock('uid1', '2026-02-07')
        calls = mock_r.set.call_args_list[-2:]
        assert calls[0][0][0] == 'users:uid1:daily_summary_lock:2026-02-06'
        assert calls[1][0][0] == 'users:uid1:daily_summary_lock:2026-02-07'


class TestRaceConditionPrevention:
    """Simulate concurrent calls to verify only one wins the lock."""

    def test_concurrent_lock_attempts_only_one_wins(self):
        call_count = 0

        def setnx_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First caller wins, rest get None
            return True if call_count == 1 else None

        mock_r.set.side_effect = setnx_side_effect

        results = []
        barrier = threading.Barrier(5)

        def attempt_lock():
            barrier.wait()
            result = try_acquire_daily_summary_lock('uid1', '2026-02-07')
            results.append(result)

        threads = [threading.Thread(target=attempt_lock) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1
        assert results.count(False) == 4

        # Reset side_effect
        mock_r.set.side_effect = None

    def test_redis_error_propagates_no_silent_swallow(self):
        """Transient Redis failure must propagate — no state mutation should happen."""
        mock_r.set.side_effect = ConnectionError("Redis unavailable")

        try:
            try_acquire_daily_summary_lock('uid1', '2026-02-07')
            assert False, "Expected ConnectionError to propagate"
        except ConnectionError:
            pass  # Expected: error propagates, no silent swallow

        mock_r.set.side_effect = None


class TestSendSummaryNotificationLockIntegration:
    """Verify _send_summary_notification respects the lock."""

    def test_skips_when_lock_not_acquired(self, notification_harness):
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock()
        gen_mock = notification_harness.generate_summary
        send_mock = notification_harness.send_notification

        convos_db.get_conversations.reset_mock()
        gen_mock.reset_mock()
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=False
        ) as mock_lock:
            notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    def test_proceeds_when_lock_acquired(self, notification_harness):
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock(return_value=[{'id': 'c1'}])

        gen_mock = notification_harness.generate_summary
        gen_mock.return_value = {'day_emoji': '!', 'headline': 'Test', 'overview': 'Summary'}

        daily_db = notification_harness.daily_summaries_db
        daily_db.get_daily_summary_by_date = MagicMock(return_value=None)
        daily_db.create_daily_summary = MagicMock(return_value='summary-123')

        send_mock = notification_harness.send_notification
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=True
        ) as mock_lock:
            notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_called_once()
        send_mock.assert_called_once()

    def test_skips_when_summary_already_exists(self, notification_harness):
        """#4608: if a summary already exists for the date (lock lost on a later tick), skip before
        spending LLM tokens or sending — do not create a duplicate doc."""
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = notification_harness.generate_summary
        gen_mock.reset_mock()

        daily_db = notification_harness.daily_summaries_db
        daily_db.get_daily_summary_by_date = MagicMock(return_value={'id': 'existing-1'})
        daily_db.create_daily_summary = MagicMock()

        send_mock = notification_harness.send_notification
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=True
        ) as mock_lock:
            notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()
        daily_db.get_daily_summary_by_date.assert_called_once()
        # An existing summary short-circuits everything: no fetch, no LLM, no create, no send.
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
        daily_db.create_daily_summary.assert_not_called()
        send_mock.assert_not_called()

    def test_summary_lookup_error_propagates_no_duplicate(self, notification_harness):
        """#4608: a transient Firestore error during the by-date lookup must propagate (skip this
        tick, retry next) rather than being swallowed into a duplicate-creating path."""
        daily_db = notification_harness.daily_summaries_db
        daily_db.get_daily_summary_by_date = MagicMock(side_effect=Exception("Firestore unavailable"))
        daily_db.create_daily_summary = MagicMock()

        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = notification_harness.generate_summary
        gen_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=True
        ) as mock_lock:
            with pytest.raises(Exception, match='Firestore unavailable'):
                notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()

        # Error surfaced (logged + retried next tick by the outer gather), no duplicate created.
        daily_db.create_daily_summary.assert_not_called()
        gen_mock.assert_not_called()
        convos_db.get_conversations.assert_not_called()

    def test_no_conversations_skips_llm(self, notification_harness):
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock(return_value=[])
        daily_db = notification_harness.daily_summaries_db
        daily_db.get_daily_summary_by_date = MagicMock(return_value=None)

        gen_mock = notification_harness.generate_summary
        gen_mock.reset_mock()

        send_mock = notification_harness.send_notification
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=True
        ) as mock_lock:
            notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    def test_utc_fallback_still_acquires_lock(self, notification_harness):
        """User data without timezone falls back to UTC; lock must still be called."""
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = notification_harness.generate_summary
        gen_mock.reset_mock()

        # No timezone element in tuple — triggers UTC fallback
        user_data = ('uid1', ['token1'])
        with patch.object(
            notification_harness.module, 'try_acquire_daily_summary_lock', return_value=False
        ) as mock_lock:
            notification_harness.send_summary(user_data)

        mock_lock.assert_called_once()
        # Lock denied, so no downstream work
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()


class TestDailyRecapNotDesktopPaywalled:
    """#9357: the daily recap is a cross-platform, server-initiated cron that does not know the
    originating platform. It must NOT be gated on the *desktop* trial paywall — doing so (via a
    hardcoded 'macos' platform) suppressed the recap on mobile/web for any trial-expired user."""

    def test_send_summary_does_not_gate_on_trial_paywall(self, notification_harness):
        import inspect

        # Ignore comments (the fix documents *why* the gate was removed); only executable code counts.
        code_lines = [
            line
            for line in inspect.getsource(notification_harness.send_summary).splitlines()
            if not line.strip().startswith('#')
        ]
        assert not any(
            'is_trial_paywalled' in line for line in code_lines
        ), "daily recap must not gate on the desktop trial paywall (regressed #9357)"

    def test_module_no_longer_imports_desktop_paywall(self, notification_harness):
        # The import was removed with the gate; re-adding it would signal the gate is back.
        assert not hasattr(notification_harness.module, 'is_trial_paywalled')

    def test_trial_expired_user_still_gets_recap(self, notification_harness):
        convos_db = notification_harness.conversations_db
        convos_db.get_conversations = MagicMock(return_value=[{'id': 'c1'}])

        gen_mock = notification_harness.generate_summary
        gen_mock.return_value = {'day_emoji': '!', 'headline': 'Test', 'overview': 'Summary'}

        daily_db = notification_harness.daily_summaries_db
        daily_db.get_daily_summary_by_date = MagicMock(return_value=None)
        daily_db.create_daily_summary = MagicMock(return_value='summary-123')

        send_mock = notification_harness.send_notification
        send_mock.reset_mock()

        # Even if this user's desktop trial has expired, the recap must still be generated + sent.
        user_data = ('uid1', ['token1'], 'America/New_York')
        with patch.object(notification_harness.module, 'try_acquire_daily_summary_lock', return_value=True):
            notification_harness.send_summary(user_data)

        gen_mock.assert_called_once()
        daily_db.create_daily_summary.assert_called_once()
        send_mock.assert_called_once()
