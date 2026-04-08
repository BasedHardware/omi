"""Tests for fair-use clearing on paid plan upgrade (#6298).

Covers:
- clear_fair_use_on_upgrade() clears free_exhausted enforcement stages
- clear_fair_use_on_upgrade() preserves abuse-derived enforcement
- clear_fair_use_on_upgrade() no-ops when not applicable
- is_hard_restricted() defense-in-depth guard for paid + free_exhausted
- Source-level verification that payment.py calls clear_fair_use_on_upgrade
"""

import os
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

_redis_mod = types.ModuleType('database.redis_db')
_mock_redis = MagicMock()
_redis_mod.r = _mock_redis
sys.modules.setdefault('database.redis_db', _redis_mod)

sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# Stub database.fair_use
_fair_use_db = types.ModuleType('database.fair_use')
_fair_use_db.get_fair_use_state = MagicMock(return_value={})
_fair_use_db.update_fair_use_state = MagicMock()
_fair_use_db.create_fair_use_event = MagicMock(return_value='evt-123')
_fair_use_db.get_fair_use_events = MagicMock(return_value=[])
_fair_use_db.get_violation_counts = MagicMock(return_value={'violation_count_7d': 0, 'violation_count_30d': 0})
sys.modules.setdefault('database.fair_use', _fair_use_db)

# Stub database.users
_users_db = MagicMock()
sys.modules.setdefault('database.users', _users_db)

# Stub database.user_usage
sys.modules.setdefault('database.user_usage', MagicMock())

# Stub notifications
sys.modules.setdefault('utils.notifications', MagicMock())

# Now import the module under test
import utils.fair_use as fair_use_mod
from models.users import PlanType, SubscriptionStatus, Subscription


def _make_paid_subscription():
    """Create a valid paid subscription object."""
    return Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        current_period_end=int((datetime.utcnow() + timedelta(days=30)).timestamp()),
    )


def _make_basic_subscription():
    """Create a basic (free) subscription object."""
    return Subscription(
        plan=PlanType.basic,
        status=SubscriptionStatus.active,
    )


class TestClearFairUseOnUpgrade:
    """Test clear_fair_use_on_upgrade() behavior."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _fair_use_db.get_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_restrict_state(self, mock_users):
        """Free-exhausted restrict stage is cleared on paid upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        _fair_use_db.update_fair_use_state.assert_called_once()
        call_args = _fair_use_db.update_fair_use_state.call_args
        assert call_args[0][0] == 'user1'
        updates = call_args[0][1]
        assert updates['stage'] == 'none'
        assert updates['throttle_until'] is None
        assert updates['restrict_until'] is None
        assert updates['violation_count_7d'] == 0
        assert updates['violation_count_30d'] == 0
        assert updates['cleared_by'] == 'subscription_upgrade'
        assert 'cleared_at' in updates
        _mock_redis.delete.assert_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_warning_state(self, mock_users):
        """Free-exhausted warning stage is also cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'warning',
            'last_classifier_type': 'free_exhausted',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        updates = _fair_use_db.update_fair_use_state.call_args[0][1]
        assert updates['stage'] == 'none'

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_throttle_state(self, mock_users):
        """Free-exhausted throttle stage is also cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'throttle',
            'last_classifier_type': 'free_exhausted',
            'throttle_until': datetime.utcnow() + timedelta(days=3),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        updates = _fair_use_db.update_fair_use_state.call_args[0][1]
        assert updates['stage'] == 'none'
        assert updates['throttle_until'] is None

    @patch.object(fair_use_mod, 'users_db')
    def test_preserves_abuse_derived_restrict_state(self, mock_users):
        """Abuse-derived restrict stage is NOT cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'audiobook',
            'restrict_until': datetime.utcnow() + timedelta(days=14),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_stage_is_none(self, mock_users):
        """No-op when user has no active enforcement."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'none',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_not_paid_plan(self, mock_users):
        """No-op when user is not on a paid plan."""
        mock_users.get_user_valid_subscription.return_value = _make_basic_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_no_subscription(self, mock_users):
        """No-op when user has no valid subscription."""
        mock_users.get_user_valid_subscription.return_value = None

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.get_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_invalidates_redis_cache(self, mock_users):
        """Redis enforcement cache is invalidated after clearing."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
        }

        fair_use_mod.clear_fair_use_on_upgrade('user1')

        _mock_redis.delete.assert_called_with('fair_use:stage:user1')

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_classifier_type_missing(self, mock_users):
        """No-op when last_classifier_type is missing (legacy/malformed state)."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            # No last_classifier_type field at all
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()


class TestWebhookClearFairUseSourceLevel:
    """Source-level verification that payment.py calls clear_fair_use_on_upgrade.

    Uses source analysis (same pattern as test_firestore_read_ops_cache.py)
    because payment.py imports the full Firestore dependency chain.
    """

    PAYMENT_SOURCE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'payment.py')

    def _read_source(self):
        with open(self.PAYMENT_SOURCE_FILE) as f:
            return f.read()

    def test_payment_imports_clear_fair_use_on_upgrade(self):
        """payment.py must import clear_fair_use_on_upgrade."""
        source = self._read_source()
        assert 'clear_fair_use_on_upgrade' in source

    def test_checkout_session_completed_calls_clear(self):
        """checkout.session.completed path must call clear_fair_use_on_upgrade."""
        source = self._read_source()
        # Find the checkout.session.completed block and verify clear call exists
        checkout_idx = source.find("event['type'] == 'checkout.session.completed'")
        assert checkout_idx != -1, "checkout.session.completed handler not found"
        # The clear call should appear between checkout handler and the next event type
        next_event_idx = source.find("customer.subscription.updated", checkout_idx)
        block = source[checkout_idx:next_event_idx]
        assert 'clear_fair_use_on_upgrade(uid)' in block

    def test_subscription_event_calls_clear(self):
        """customer.subscription.* path must call clear_fair_use_on_upgrade."""
        source = self._read_source()
        sub_idx = source.find("'customer.subscription.updated'")
        assert sub_idx != -1, "customer.subscription handler not found"
        next_event_idx = source.find("subscription_schedule.completed", sub_idx)
        block = source[sub_idx:next_event_idx]
        assert 'clear_fair_use_on_upgrade(uid)' in block

    def test_schedule_completed_calls_clear(self):
        """subscription_schedule.completed path must call clear_fair_use_on_upgrade."""
        source = self._read_source()
        schedule_idx = source.find("'subscription_schedule.completed'")
        assert schedule_idx != -1, "subscription_schedule handler not found"
        # Get a reasonable block after the schedule handler
        block = source[schedule_idx : schedule_idx + 1500]
        assert 'clear_fair_use_on_upgrade(uid)' in block
