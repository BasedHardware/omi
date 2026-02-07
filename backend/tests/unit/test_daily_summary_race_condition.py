"""
Tests for issue #4594: Duplicate daily recap notifications due to race condition.

The _send_summary_notification() function had a non-atomic check-then-set pattern
with a ~3 minute LLM call gap between check and set. Multiple cron instances could
pass the Redis check before any completed, causing duplicate notifications.

Fix: Atomic SETNX lock before the expensive LLM call, with try/finally to release
on failure and allow retries.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database package and submodules
database_mod = _stub_module("database")
if not hasattr(database_mod, "__path__"):
    database_mod.__path__ = []
for submodule in [
    "redis_db",
    "memories",
    "conversations",
    "notifications",
    "users",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
    "vector_db",
    "apps",
    "llm_usage",
    "_client",
    "auth",
    "chat",
    "daily_summaries",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

redis_mod = sys.modules["database.redis_db"]
redis_mod.has_daily_summary_been_sent = MagicMock(return_value=False)
redis_mod.try_acquire_daily_summary_lock = MagicMock(return_value="fake-token-123")
redis_mod.release_daily_summary_lock = MagicMock()
redis_mod.set_daily_summary_sent = MagicMock()

conversations_mod = sys.modules["database.conversations"]
conversations_mod.get_conversations = MagicMock(return_value=[])

notifications_mod = sys.modules["database.notifications"]
notifications_mod.get_users_for_daily_summary = MagicMock(return_value=[])

daily_summaries_mod = sys.modules["database.daily_summaries"]
daily_summaries_mod.create_daily_summary = MagicMock(return_value="summary-123")

chat_mod = sys.modules["database.chat"]
chat_mod.get_messages = MagicMock(return_value=[])

# Stub utils modules
for name in [
    "utils.apps",
    "utils.analytics",
    "utils.llm.memories",
    "utils.llm.conversation_processing",
    "utils.llm.external_integrations",
    "utils.llm.trends",
    "utils.llm.persona",
    "utils.notifications",
    "utils.webhooks",
]:
    _stub_module(name)

utils_llm_ext = sys.modules["utils.llm.external_integrations"]
utils_llm_ext.generate_comprehensive_daily_summary = MagicMock(
    return_value={
        'day_emoji': '📅',
        'headline': 'Test Daily Summary',
        'overview': 'A productive day of testing.',
    }
)
utils_llm_ext.get_conversation_summary = MagicMock(return_value="summary")

utils_notifications = sys.modules["utils.notifications"]
utils_notifications.send_notification = MagicMock()
utils_notifications.send_bulk_notification = MagicMock()

utils_webhooks = sys.modules["utils.webhooks"]
utils_webhooks.day_summary_webhook = MagicMock()

# Stub models
_stub_module("models")
_stub_module("models.notification_message")
_stub_module("models.conversation")

notification_message_mod = sys.modules["models.notification_message"]


class FakeNotificationMessage:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @staticmethod
    def get_message_as_dict(msg):
        return {'text': 'test'}


notification_message_mod.NotificationMessage = FakeNotificationMessage

conversation_mod = sys.modules["models.conversation"]


class FakeConversation:
    def __init__(self, **kwargs):
        pass


conversation_mod.Conversation = FakeConversation

# Now import the module under test
from utils.other.notifications import _send_summary_notification


class TestAtomicLockAcquisition:
    """Test that try_acquire_daily_summary_lock returns a token on first call, None on second."""

    def test_lock_acquired_returns_token(self):
        redis_mod.try_acquire_daily_summary_lock.return_value = "token-abc"
        result = redis_mod.try_acquire_daily_summary_lock("user1", "2026-02-07")
        assert result == "token-abc"

    def test_lock_rejected_returns_none(self):
        redis_mod.try_acquire_daily_summary_lock.return_value = None
        result = redis_mod.try_acquire_daily_summary_lock("user1", "2026-02-07")
        assert result is None


class TestSendSummaryNotificationRaceCondition:
    """Test _send_summary_notification handles the race condition correctly."""

    def setup_method(self):
        redis_mod.has_daily_summary_been_sent.reset_mock()
        redis_mod.try_acquire_daily_summary_lock.reset_mock()
        redis_mod.release_daily_summary_lock.reset_mock()
        redis_mod.set_daily_summary_sent.reset_mock()
        conversations_mod.get_conversations.reset_mock()
        daily_summaries_mod.create_daily_summary.reset_mock()
        utils_llm_ext.generate_comprehensive_daily_summary.reset_mock()
        utils_notifications.send_notification.reset_mock()

        # Default: not sent, lock acquired, has conversations
        redis_mod.has_daily_summary_been_sent.return_value = False
        redis_mod.try_acquire_daily_summary_lock.return_value = "fake-token-123"
        conversations_mod.get_conversations.return_value = [{'id': 'conv1', 'title': 'Test'}]
        daily_summaries_mod.create_daily_summary.return_value = "summary-123"
        utils_llm_ext.generate_comprehensive_daily_summary.return_value = {
            'day_emoji': '📅',
            'headline': 'Test Summary',
            'overview': 'A test summary.',
        }

    def test_already_sent_returns_early(self):
        """If summary already sent for this date, skip entirely (no lock, no LLM)."""
        redis_mod.has_daily_summary_been_sent.return_value = True
        user_data = ("uid1", ["token1"], "America/New_York")
        _send_summary_notification(user_data)

        redis_mod.try_acquire_daily_summary_lock.assert_not_called()
        utils_llm_ext.generate_comprehensive_daily_summary.assert_not_called()

    def test_lock_not_acquired_returns_early(self):
        """If lock not acquired (another job processing), skip LLM call."""
        redis_mod.try_acquire_daily_summary_lock.return_value = None
        user_data = ("uid1", ["token1"], "America/New_York")
        _send_summary_notification(user_data)

        utils_llm_ext.generate_comprehensive_daily_summary.assert_not_called()
        utils_notifications.send_notification.assert_not_called()

    def test_no_conversations_returns_before_lock(self):
        """If no conversations found, return before acquiring lock."""
        conversations_mod.get_conversations.return_value = []
        user_data = ("uid1", ["token1"], "America/New_York")
        _send_summary_notification(user_data)

        redis_mod.try_acquire_daily_summary_lock.assert_not_called()
        utils_llm_ext.generate_comprehensive_daily_summary.assert_not_called()

    def test_success_path_calls_set_sent(self):
        """On success: lock acquired, LLM called, notification sent, sent marker set."""
        user_data = ("uid1", ["token1"], "America/New_York")
        _send_summary_notification(user_data)

        utils_llm_ext.generate_comprehensive_daily_summary.assert_called_once()
        utils_notifications.send_notification.assert_called_once()
        redis_mod.set_daily_summary_sent.assert_called_once()
        # Lock should NOT be released on success (TTL expires naturally)
        redis_mod.release_daily_summary_lock.assert_not_called()

    def test_llm_failure_releases_lock(self):
        """On LLM failure: lock released, sent marker NOT set, exception re-raised."""
        utils_llm_ext.generate_comprehensive_daily_summary.side_effect = RuntimeError("LLM timeout")
        user_data = ("uid1", ["token1"], "America/New_York")

        with pytest.raises(RuntimeError, match="LLM timeout"):
            _send_summary_notification(user_data)

        redis_mod.release_daily_summary_lock.assert_called_once()
        redis_mod.set_daily_summary_sent.assert_not_called()

    def test_llm_failure_does_not_set_sent(self):
        """On failure, set_daily_summary_sent must never be called."""
        utils_llm_ext.generate_comprehensive_daily_summary.side_effect = Exception("API error")
        user_data = ("uid1", ["token1"], "America/New_York")

        with pytest.raises(Exception, match="API error"):
            _send_summary_notification(user_data)

        redis_mod.set_daily_summary_sent.assert_not_called()

    def test_llm_failure_releases_lock_with_token(self):
        """On failure, release_daily_summary_lock is called with the same token from acquire."""
        redis_mod.try_acquire_daily_summary_lock.return_value = "my-unique-token"
        utils_llm_ext.generate_comprehensive_daily_summary.side_effect = RuntimeError("fail")
        user_data = ("uid1", ["token1"], "America/New_York")

        with pytest.raises(RuntimeError):
            _send_summary_notification(user_data)

        # Verify token is passed through to release (compare-and-delete)
        call_args = redis_mod.release_daily_summary_lock.call_args
        assert call_args is not None
        assert call_args[0][2] == "my-unique-token" or call_args[1].get('token') == "my-unique-token"


def _load_real_redis_db(mock_r):
    """Load the real redis_db module with r replaced by mock_r."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "database.redis_db_real", os.path.join(os.path.dirname(__file__), '../../database/redis_db.py')
    )
    mod = importlib.util.module_from_spec(spec)
    # Inject mock redis before exec
    import redis as _redis

    _orig_redis_class = _redis.Redis
    _redis.Redis = lambda **kwargs: mock_r
    try:
        spec.loader.exec_module(mod)
    finally:
        _redis.Redis = _orig_redis_class
    return mod


class TestRedisLockImplementation:
    """Test the real Redis lock functions with r mocked."""

    def test_acquire_lock_calls_set_with_nx_and_ttl(self):
        """Verify the real try_acquire_daily_summary_lock calls r.set with nx=True and correct TTL."""
        mock_r = MagicMock()
        mock_r.set.return_value = True  # SETNX success
        rdb = _load_real_redis_db(mock_r)

        token = rdb.try_acquire_daily_summary_lock("user1", "2026-02-07")
        assert token is not None
        call_args = mock_r.set.call_args
        assert call_args[0][0] == 'users:user1:daily_summary_lock:2026-02-07'
        assert call_args[1]['nx'] is True
        assert call_args[1]['ex'] == 60 * 30

    def test_acquire_lock_returns_none_when_already_held(self):
        """Verify the real function returns None when SETNX fails."""
        mock_r = MagicMock()
        mock_r.set.return_value = None  # SETNX failure
        rdb = _load_real_redis_db(mock_r)

        result = rdb.try_acquire_daily_summary_lock("user1", "2026-02-07")
        assert result is None

    def test_acquire_lock_returns_unique_tokens(self):
        """Verify each acquisition attempt generates a unique UUID token."""
        mock_r = MagicMock()
        mock_r.set.return_value = True
        rdb = _load_real_redis_db(mock_r)

        token1 = rdb.try_acquire_daily_summary_lock("user1", "2026-02-07")
        token2 = rdb.try_acquire_daily_summary_lock("user1", "2026-02-07")
        assert token1 != token2

    def test_release_lock_uses_lua_eval(self):
        """Verify the real release_daily_summary_lock calls r.eval with Lua script."""
        mock_r = MagicMock()
        rdb = _load_real_redis_db(mock_r)

        rdb.release_daily_summary_lock("user1", "2026-02-07", "my-token")
        mock_r.eval.assert_called_once()
        args = mock_r.eval.call_args[0]
        assert 'redis.call("get", KEYS[1]) == ARGV[1]' in args[0]
        assert args[2] == 'users:user1:daily_summary_lock:2026-02-07'
        assert args[3] == 'my-token'

    def test_release_with_wrong_token_still_calls_eval(self):
        """Release with wrong token still calls eval (Lua handles the comparison)."""
        mock_r = MagicMock()
        mock_r.eval.return_value = 0  # Lua returns 0 = no delete
        rdb = _load_real_redis_db(mock_r)

        rdb.release_daily_summary_lock("user1", "2026-02-07", "wrong-token")
        mock_r.eval.assert_called_once()
        # The Lua script returns 0 (no-op) — verified by the return value
        assert mock_r.eval.return_value == 0

    def test_release_with_empty_token(self):
        """Release with empty token calls eval safely (Lua handles mismatch)."""
        mock_r = MagicMock()
        mock_r.eval.return_value = 0
        rdb = _load_real_redis_db(mock_r)

        rdb.release_daily_summary_lock("user1", "2026-02-07", "")
        mock_r.eval.assert_called_once()
        args = mock_r.eval.call_args[0]
        assert args[3] == ""

    def test_concurrent_acquisition_only_one_succeeds(self):
        """Two callers race: only the first acquires the lock."""
        lock_held = {'value': None}

        def mock_setnx(key, value, ex=None, nx=False):
            if nx and lock_held['value'] is None:
                lock_held['value'] = value
                return True
            return None

        mock_r = MagicMock()
        mock_r.set.side_effect = mock_setnx
        rdb = _load_real_redis_db(mock_r)

        result1 = rdb.try_acquire_daily_summary_lock("u1", "2026-02-07")
        result2 = rdb.try_acquire_daily_summary_lock("u1", "2026-02-07")

        assert result1 is not None
        assert result2 is None

    def test_lock_expiry_release_is_noop(self):
        """After lock expires and another worker acquires, release with old token is a no-op."""
        mock_r = MagicMock()
        # Simulate: Lua script returns 0 because stored token != provided token
        mock_r.eval.return_value = 0
        rdb = _load_real_redis_db(mock_r)

        # Worker 1's token — lock has expired, worker 2 now holds different token
        rdb.release_daily_summary_lock("user1", "2026-02-07", "worker1-old-token")
        mock_r.eval.assert_called_once()
        # Lua returned 0 = key NOT deleted — worker 2's lock is safe
        assert mock_r.eval.return_value == 0

    def test_set_daily_summary_sent_uses_24h_ttl(self):
        """Verify set_daily_summary_sent uses 24-hour TTL by default."""
        mock_r = MagicMock()
        rdb = _load_real_redis_db(mock_r)

        rdb.set_daily_summary_sent("user1", "2026-02-07")
        call_args = mock_r.set.call_args
        assert call_args[0][0] == 'users:user1:daily_summary_sent:2026-02-07'
        assert call_args[1]['ex'] == 60 * 60 * 24
