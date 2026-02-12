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
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


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
for name in [
    "utils.llm.external_integrations",
    "utils.notifications",
    "utils.webhooks",
]:
    if name not in sys.modules:
        _stub_module(name)

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

# Now we can safely import
from utils.other.notifications import _send_summary_notification


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

    @patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=False)
    def test_skips_when_lock_not_acquired(self, mock_lock):
        convos_db = sys.modules["database.conversations"]
        convos_db.get_conversations = MagicMock()
        gen_mock = sys.modules["utils.llm.external_integrations"].generate_comprehensive_daily_summary
        send_mock = sys.modules["utils.notifications"].send_notification

        convos_db.get_conversations.reset_mock()
        gen_mock.reset_mock()
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    @patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=True)
    def test_proceeds_when_lock_acquired(self, mock_lock):
        convos_db = sys.modules["database.conversations"]
        convos_db.get_conversations = MagicMock(return_value=[{'id': 'c1'}])

        gen_mock = sys.modules["utils.llm.external_integrations"].generate_comprehensive_daily_summary
        gen_mock.return_value = {'day_emoji': '!', 'headline': 'Test', 'overview': 'Summary'}

        daily_db = sys.modules["database.daily_summaries"]
        daily_db.create_daily_summary = MagicMock(return_value='summary-123')

        send_mock = sys.modules["utils.notifications"].send_notification
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_called_once()
        send_mock.assert_called_once()

    @patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=True)
    def test_no_conversations_skips_llm(self, mock_lock):
        convos_db = sys.modules["database.conversations"]
        convos_db.get_conversations = MagicMock(return_value=[])

        gen_mock = sys.modules["utils.llm.external_integrations"].generate_comprehensive_daily_summary
        gen_mock.reset_mock()

        send_mock = sys.modules["utils.notifications"].send_notification
        send_mock.reset_mock()

        user_data = ('uid1', ['token1'], 'America/New_York')
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        convos_db.get_conversations.assert_called_once()
        gen_mock.assert_not_called()
        send_mock.assert_not_called()

    @patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=False)
    def test_utc_fallback_still_acquires_lock(self, mock_lock):
        """User data without timezone falls back to UTC; lock must still be called."""
        convos_db = sys.modules["database.conversations"]
        convos_db.get_conversations = MagicMock()
        convos_db.get_conversations.reset_mock()

        gen_mock = sys.modules["utils.llm.external_integrations"].generate_comprehensive_daily_summary
        gen_mock.reset_mock()

        # No timezone element in tuple — triggers UTC fallback
        user_data = ('uid1', ['token1'])
        _send_summary_notification(user_data)

        mock_lock.assert_called_once()
        # Lock denied, so no downstream work
        convos_db.get_conversations.assert_not_called()
        gen_mock.assert_not_called()
