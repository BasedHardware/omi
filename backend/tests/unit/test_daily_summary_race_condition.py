"""
Unit tests for daily summary race condition fix (#4594).

Verifies that:
1. try_acquire_daily_summary_lock uses atomic SETNX
2. Only the first caller acquires the lock; concurrent callers are rejected
3. _send_summary_notification skips work when lock is already held
"""

import os
import sys
import types
import threading
from datetime import datetime, timedelta, timezone, tzinfo
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


_STUB_MODULE_NAMES = set()


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    _STUB_MODULE_NAMES.add(name)
    return mod


def _remove_stub_module(name: str) -> None:
    mod = sys.modules.pop(name, None)
    if "." not in name or mod is None:
        return
    parent_name, attr_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if getattr(parent, attr_name, None) is mod:
        delattr(parent, attr_name)


def _remove_empty_stub_package(name: str) -> None:
    mod = sys.modules.get(name)
    if mod is None or getattr(mod, "__file__", None):
        return
    if getattr(mod, "__path__", None) == []:
        _remove_stub_module(name)


def _clear_stale_package_tree(name: str) -> None:
    mod = sys.modules.get(name)
    if mod is not None and getattr(mod, "__file__", None):
        return
    if mod is None or getattr(mod, "__path__", None) == []:
        prefix = f"{name}."
        for module_name in list(sys.modules):
            if module_name == name or module_name.startswith(prefix):
                sys.modules.pop(module_name, None)


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

pytz_stub = types.ModuleType("pytz")
pytz_stub.utc = _UTC_TZ
pytz_stub.all_timezones = list(_PYTZ_ZONES)
pytz_stub.timezone = lambda name: _PYTZ_ZONES.get(name, _UTC_TZ)
if "pytz" not in sys.modules:
    sys.modules["pytz"] = pytz_stub
    _STUB_MODULE_NAMES.add("pytz")


# Stub database package and submodules to avoid Firestore init.
if "database" not in sys.modules:
    database_mod = _stub_module("database")
    database_mod.__path__ = []
else:
    database_mod = sys.modules["database"]

for submodule in [
    "redis_db",
    "chat",
    "conversations",
    "notifications",
    "users",
    "daily_summaries",
    "_client",
    "auth",
]:
    full_name = f"database.{submodule}"
    if full_name not in sys.modules:
        mod = _stub_module(full_name)
        setattr(database_mod, submodule, mod)

# Set up mock redis and real lock function
redis_db_mod = sys.modules["database.redis_db"]
mock_r = MagicMock()
redis_db_mod.r = mock_r


def try_acquire_daily_summary_lock(uid: str, date: str, ttl: int = 60 * 60 * 2) -> bool:
    result = mock_r.set(f'users:{uid}:daily_summary_lock:{date}', '1', ex=ttl, nx=True)
    return result is not None


redis_db_mod.try_acquire_daily_summary_lock = try_acquire_daily_summary_lock

# Set up mock auth
auth_mod = sys.modules["database.auth"]
auth_mod.get_user_name = MagicMock(return_value="Test User")

# Set up mock client
client_mod = sys.modules["database._client"]
client_mod.db = MagicMock()
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

# Stub utils modules that pull in heavy dependencies.
_clear_stale_package_tree("utils")
for package_name in ["utils", "utils.other"]:
    _remove_empty_stub_package(package_name)

for name in [
    "utils.llm.external_integrations",
    "utils.notifications",
    "utils.webhooks",
    "utils.conversations",
    "utils.conversations.factory",
]:
    if name not in sys.modules:
        mod = _stub_module(name)
        if name == "utils.conversations":
            mod.__path__ = []

# deserialize_conversation must return an object with transcript_segments and discarded attrs.
_mock_convo = MagicMock()
_mock_convo.transcript_segments = [{"text": "hello"}]
_mock_convo.discarded = False
sys.modules["utils.conversations.factory"].deserialize_conversation = MagicMock(return_value=_mock_convo)

# Add needed attrs to stubs
utils_llm_ext = sys.modules["utils.llm.external_integrations"]
utils_llm_ext.get_conversation_summary = MagicMock()
utils_llm_ext.generate_comprehensive_daily_summary = MagicMock()

utils_notifications = sys.modules["utils.notifications"]
utils_notifications.send_bulk_notification = MagicMock()
utils_notifications.send_notification = MagicMock()

utils_webhooks = sys.modules["utils.webhooks"]
utils_webhooks.day_summary_webhook = MagicMock()

# Stub models
for name in ["models.notification_message", "models.conversation"]:
    if name not in sys.modules:
        _stub_module(name)

models_notif = sys.modules["models.notification_message"]
mock_notification_message = MagicMock()
mock_notification_message.get_message_as_dict = MagicMock(return_value={})
models_notif.NotificationMessage = mock_notification_message

models_convo = sys.modules["models.conversation"]
models_convo.Conversation = MagicMock()

# utils.executors / utils.subscription are imported by notifications.py and pull firebase_admin
# transitively; stub them (neither is used by _send_summary_notification).
exec_mod = _stub_module("utils.executors")
exec_mod.postprocess_executor = MagicMock()
exec_mod.run_blocking = MagicMock()
sub_mod = _stub_module("utils.subscription")
sub_mod.is_trial_paywalled = MagicMock(return_value=False)

# Now we can safely import the real module while keeping handles to its stubbed collaborators.
import utils.other.notifications as notifications_module

_send_summary_notification = notifications_module._send_summary_notification
_CONVERSATIONS_DB = notifications_module.conversations_db
_DAILY_SUMMARIES_DB = notifications_module.daily_summaries_db
_GENERATE_COMPREHENSIVE_DAILY_SUMMARY = notifications_module.generate_comprehensive_daily_summary
_SEND_NOTIFICATION = notifications_module.send_notification

for stub_name in sorted(_STUB_MODULE_NAMES, key=lambda item: item.count("."), reverse=True):
    _remove_stub_module(stub_name)
_remove_stub_module("utils.other.notifications")


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

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=False)
    def test_skips_when_lock_not_acquired(self, mock_lock):
        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock()
        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        send_mock = _SEND_NOTIFICATION

        convos_db.get_conversations.reset_mock()
        gen_mock.reset_mock()
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=True)
    def test_proceeds_when_lock_acquired(self, mock_lock):
        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock(return_value=[{'id': 'c1'}])

        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        gen_mock.return_value = {'day_emoji': '!', 'headline': 'Test', 'overview': 'Summary'}

        daily_db = _DAILY_SUMMARIES_DB
        daily_db.get_daily_summary_by_date = MagicMock(return_value=None)
        daily_db.create_daily_summary = MagicMock(return_value='summary-123')

        send_mock = _SEND_NOTIFICATION
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_called_once()
        send_mock.assert_called_once()

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=True)
    def test_skips_when_summary_already_exists(self, mock_lock):
        """#4608: if a summary already exists for the date (lock lost on a later tick), skip before
        spending LLM tokens or sending — do not create a duplicate doc."""
        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        gen_mock.reset_mock()

        daily_db = _DAILY_SUMMARIES_DB
        daily_db.get_daily_summary_by_date = MagicMock(return_value={'id': 'existing-1'})
        daily_db.create_daily_summary = MagicMock()

        send_mock = _SEND_NOTIFICATION
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        daily_db.get_daily_summary_by_date.assert_called_once()
        # An existing summary short-circuits everything: no fetch, no LLM, no create, no send.
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
        daily_db.create_daily_summary.assert_not_called()
        send_mock.assert_not_called()

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=True)
    def test_summary_lookup_error_propagates_no_duplicate(self, mock_lock):
        """#4608: a transient Firestore error during the by-date lookup must propagate (skip this
        tick, retry next) rather than being swallowed into a duplicate-creating path."""
        daily_db = _DAILY_SUMMARIES_DB
        daily_db.get_daily_summary_by_date = MagicMock(side_effect=Exception("Firestore unavailable"))
        daily_db.create_daily_summary = MagicMock()

        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        gen_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        try:
            _send_summary_notification(user_data)
            assert False, "Expected the Firestore error to propagate"
        except Exception as e:
            assert "Firestore unavailable" in str(e)

        # Error surfaced (logged + retried next tick by the outer gather), no duplicate created.
        daily_db.create_daily_summary.assert_not_called()
        gen_mock.assert_not_called()
        convos_db.get_conversations.assert_not_called()

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=True)
    def test_no_conversations_skips_llm(self, mock_lock):
        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock(return_value=[])
        daily_db = _DAILY_SUMMARIES_DB
        daily_db.get_daily_summary_by_date = MagicMock(return_value=None)

        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        gen_mock.reset_mock()

        send_mock = _SEND_NOTIFICATION
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    @patch.object(notifications_module, 'try_acquire_daily_summary_lock', return_value=False)
    def test_utc_fallback_still_acquires_lock(self, mock_lock):
        """User data without timezone falls back to UTC; lock must still be called."""
        convos_db = _CONVERSATIONS_DB
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = _GENERATE_COMPREHENSIVE_DAILY_SUMMARY
        gen_mock.reset_mock()

        # No timezone element in tuple — triggers UTC fallback
        user_data = ('uid1', ['token1'])
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        # Lock denied, so no downstream work
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
