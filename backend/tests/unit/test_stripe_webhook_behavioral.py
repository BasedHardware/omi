"""Behavioral tests for Stripe webhook error handling (#7282).

These tests verify actual function behavior (not just source patterns) by extracting
the _build_subscription_from_stripe_object function and testing it with controlled inputs.

The full import chain (routers.payment → database._client → Firestore) requires GCP
credentials and Python 3.10+, so we extract and test the function logic directly.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Models import cleanly without database chain
from models.users import PlanType, SubscriptionStatus, Subscription

# ── Helper: extract and compile _build_subscription_from_stripe_object ──────


def _get_build_subscription_fn():
    """Extract _build_subscription_from_stripe_object from payment.py source and
    compile it into an executable function with controlled dependencies."""
    source = (Path(__file__).resolve().parents[2] / "routers" / "payment.py").read_text(encoding="utf-8")
    func_start = source.index('def _build_subscription_from_stripe_object')
    next_func = source.index('\ndef ', func_start + 1)
    func_source = source[func_start:next_func]

    # Strip Python 3.10+ type union syntax (Subscription | None) for 3.9 compat
    func_source = func_source.replace('Subscription | None', 'object')

    # Build a namespace with the dependencies the function needs
    namespace = {
        'PlanType': PlanType,
        'SubscriptionStatus': SubscriptionStatus,
        'Subscription': Subscription,
        'get_plan_type_from_price_id': None,  # set per-test
        'get_plan_limits': None,  # set per-test
        'get_basic_plan_limits': lambda: {'daily_chat_message_limit': 10, 'daily_speech_hours_limit': 1},
    }
    exec(compile(func_source, '<payment.py>', 'exec'), namespace)
    return namespace['_build_subscription_from_stripe_object'], namespace


# ── Behavioral tests for _build_subscription_from_stripe_object ─────────────


def _make_stripe_sub(status='active', price_id='price_test_123', cancel_at_period_end=False):
    """Create a minimal Stripe subscription dict for testing."""
    return {
        'id': 'sub_test_abc',
        'status': status,
        'items': {'data': [{'price': {'id': price_id}}]},
        'current_period_end': 1700000000,
        'cancel_at_period_end': cancel_at_period_end,
    }


class TestBuildSubscriptionFromStripeObject:
    """Test _build_subscription_from_stripe_object behavior with various inputs."""

    def setup_method(self):
        self.fn, self.ns = _get_build_subscription_fn()
        # Default stubs
        self.ns['get_plan_type_from_price_id'] = lambda price_id: PlanType.unlimited
        self.ns['get_plan_limits'] = lambda plan: {'daily_chat_message_limit': 100, 'daily_speech_hours_limit': 10}

    def test_active_subscription_with_valid_price(self):
        """Active subscription with known price ID returns correct Subscription."""
        result = self.fn(_make_stripe_sub(status='active', price_id='price_known'))
        assert result is not None
        assert result.plan == PlanType.unlimited
        assert result.status == SubscriptionStatus.active
        assert result.stripe_subscription_id == 'sub_test_abc'
        assert result.cancel_at_period_end is False

    def test_trialing_subscription_with_valid_price(self):
        """Trialing subscription treated same as active."""
        result = self.fn(_make_stripe_sub(status='trialing', price_id='price_known'))
        assert result is not None
        assert result.plan == PlanType.unlimited
        assert result.status == SubscriptionStatus.active

    def test_active_subscription_with_unknown_price_returns_none(self):
        """Active subscription with unknown price ID returns None (can't determine plan)."""
        self.ns['get_plan_type_from_price_id'] = MagicMock(side_effect=ValueError("Unknown price"))
        result = self.fn(_make_stripe_sub(status='active', price_id='price_unknown'))
        assert result is None

    def test_active_subscription_with_empty_items_returns_none(self):
        """Active subscription with no price items returns None."""
        sub = _make_stripe_sub(status='active')
        sub['items']['data'] = []
        result = self.fn(sub)
        assert result is None

    def test_canceled_subscription_downgrades_to_basic(self):
        """Canceled subscription always downgrades to Basic regardless of price ID."""
        result = self.fn(_make_stripe_sub(status='canceled', price_id='price_anything'))
        assert result is not None
        assert result.plan == PlanType.basic
        assert result.status == SubscriptionStatus.active
        assert result.cancel_at_period_end is False

    def test_canceled_subscription_with_unknown_price_still_downgrades(self):
        """Canceled subscription with unknown price ID still downgrades to Basic.
        This is the key fix — before PR #7284, this would return None and leave
        stale paid access."""
        self.ns['get_plan_type_from_price_id'] = MagicMock(side_effect=ValueError("Unknown"))
        result = self.fn(_make_stripe_sub(status='canceled', price_id='price_unknown'))
        assert result is not None
        assert result.plan == PlanType.basic

    def test_unpaid_subscription_downgrades_to_basic(self):
        """Unpaid subscription downgrades to Basic."""
        result = self.fn(_make_stripe_sub(status='unpaid', price_id='price_test'))
        assert result is not None
        assert result.plan == PlanType.basic

    def test_active_with_cancel_at_period_end(self):
        """Active subscription with cancel_at_period_end preserves that flag."""
        result = self.fn(_make_stripe_sub(status='active', cancel_at_period_end=True))
        assert result is not None
        assert result.cancel_at_period_end is True

    def test_canceled_ignores_cancel_at_period_end(self):
        """Canceled subscription always sets cancel_at_period_end to False."""
        result = self.fn(_make_stripe_sub(status='canceled', cancel_at_period_end=True))
        assert result is not None
        assert result.cancel_at_period_end is False

    def test_subscription_includes_stripe_id(self):
        """Result always includes the Stripe subscription ID."""
        result = self.fn(_make_stripe_sub())
        assert result.stripe_subscription_id == 'sub_test_abc'

    def test_subscription_includes_period_end(self):
        """Result always includes current_period_end."""
        result = self.fn(_make_stripe_sub())
        assert result.current_period_end == 1700000000
