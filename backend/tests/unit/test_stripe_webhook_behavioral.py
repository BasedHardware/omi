"""Behavioral tests for Stripe webhook error handling (#7282).

These tests verify actual function behavior (not just source patterns) by extracting
the _build_subscription_from_stripe_object function and testing it with controlled inputs.

The full import chain (routers.payment → database._client → Firestore) requires GCP
credentials and Python 3.10+, so we extract and test the function logic directly.
"""

import os
import re
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
    from typing import Any, Dict, Optional, cast as _cast

    namespace = {
        'Any': Any,
        'Dict': Dict,
        'Optional': Optional,
        'cast': _cast,
        'PlanType': PlanType,
        'SubscriptionStatus': SubscriptionStatus,
        'Subscription': Subscription,
        'get_plan_type_from_price_id': None,  # set per-test
        'get_plan_limits': None,  # set per-test
        'get_basic_plan_limits': lambda: {'daily_chat_message_limit': 10, 'daily_speech_hours_limit': 1},
    }
    exec(compile(func_source, '<payment.py>', 'exec'), namespace)
    return namespace['_build_subscription_from_stripe_object'], namespace


def _get_current_paid_guard_fn():
    source = (Path(__file__).resolve().parents[2] / "routers" / "payment.py").read_text(encoding="utf-8")
    func_start = source.index('def _has_current_paid_subscription_for_different_stripe_sub')
    next_func = source.index('\ndef ', func_start + 1)
    func_source = source[func_start:next_func]
    func_source = func_source.replace('Subscription | None', 'object')
    func_source = func_source.replace('str | None', 'object')
    func_source = func_source.replace('int | None', 'object')

    namespace = {
        'SubscriptionStatus': SubscriptionStatus,
        'is_paid_plan': lambda plan: plan in {PlanType.unlimited, PlanType.architect, PlanType.operator},
        'time': MagicMock(time=MagicMock(return_value=1_700_000_000)),
    }
    exec(compile(func_source, '<payment.py>', 'exec'), namespace)
    return namespace['_has_current_paid_subscription_for_different_stripe_sub']


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


class TestStripeWebhookDuplicateAndCustomerSourceLevel:
    """Regression coverage for duplicate checkout + stale downgrade race.

    Scenario seen in prod: Stripe emits customer.subscription.created with
    status=incomplete before checkout.session.completed. The created event stored
    a Basic subscription with the same Stripe sub id, so checkout completion was
    treated as a duplicate and returned before storing stripe_customer_id. One
    day later, the first failed Checkout's incomplete_expired event downgraded
    the user because the active paid sub lived on a second customer and could not
    be discovered from Firestore.
    """

    PAYMENT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"

    def _read_source(self):
        return self.PAYMENT_SOURCE_FILE.read_text(encoding="utf-8")

    def test_checkout_duplicate_return_only_applies_to_paid_existing_subscription(self):
        source = self._read_source()
        duplicate_idx = source.find('Duplicate webhook event for existing subscription')
        assert duplicate_idx != -1, "duplicate checkout guard not found"
        guard_block = source[max(0, duplicate_idx - 600) : duplicate_idx]
        assert 'is_paid_plan(existing_subscription.plan)' in guard_block

    def test_subscription_events_persist_customer_id_for_uid_metadata_path(self):
        source = self._read_source()
        sub_idx = source.find("'customer.subscription.updated'")
        assert sub_idx != -1, "customer.subscription handler not found"
        next_idx = source.find("subscription_schedule.completed", sub_idx)
        assert next_idx != -1, "subscription_schedule handler not found after customer.subscription handler"
        block = source[sub_idx:next_idx]
        assert 'users_db.set_stripe_customer_id' in block
        assert "subscription_obj.get('customer')" in block

    def test_stale_downgrade_guard_does_not_clobber_customer_id(self):
        """When the active-paid adoption guard fires, the event's customer id
        must not be persisted, because it belongs to the stale/canceled sub
        (possibly a different Stripe customer) and would break later
        reconciliation via find_active_paid_subscription_for_user."""
        source = self._read_source()
        # Anchor to the subscription event handler block to avoid matching an
        # earlier set_stripe_customer_id in the checkout.session.completed path.
        sub_idx = source.find("'customer.subscription.updated'")
        assert sub_idx != -1, "customer.subscription handler not found"
        handler_block = source[sub_idx:]
        set_customer_idx = handler_block.find("users_db.set_stripe_customer_id")
        assert set_customer_idx != -1, "set_stripe_customer_id call not found in subscription handler"
        # The guard flag must precede the set_stripe_customer_id call
        guard_idx = handler_block.find("adopted_active_paid = False")
        assert guard_idx != -1, "adopted_active_paid flag not found"
        assert guard_idx < set_customer_idx, "guard flag must precede customer id write"
        # The write must be gated on NOT adopting active_paid
        guard_block = handler_block[max(0, set_customer_idx - 400) : set_customer_idx]
        assert "not adopted_active_paid" in guard_block, "customer id write must be gated on not adopted_active_paid"


class TestStripeSubscriptionEventPrecedence:
    PAYMENT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"
    USERS_SOURCE_FILE = Path(__file__).resolve().parents[2] / "database" / "users.py"

    def setup_method(self):
        self.fn = _get_current_paid_guard_fn()

    def test_inactive_event_cannot_clobber_different_current_paid_subscription(self):
        current = Subscription(
            plan=PlanType.operator,
            status=SubscriptionStatus.active,
            stripe_subscription_id="sub_current_paid",
            current_period_end=1_800_000_000,
        )

        assert self.fn(current, "sub_old_inactive", now=1_700_000_000) is True

    def test_matching_subscription_event_can_update_current_subscription(self):
        current = Subscription(
            plan=PlanType.operator,
            status=SubscriptionStatus.active,
            stripe_subscription_id="sub_current_paid",
            current_period_end=1_800_000_000,
        )

        assert self.fn(current, "sub_current_paid", now=1_700_000_000) is False

    def test_expired_paid_subscription_does_not_block_inactive_event(self):
        current = Subscription(
            plan=PlanType.operator,
            status=SubscriptionStatus.active,
            stripe_subscription_id="sub_expired_paid",
            current_period_end=1_600_000_000,
        )

        assert self.fn(current, "sub_old_inactive", now=1_700_000_000) is False

    def test_missing_period_end_does_not_preserve_paid_access(self):
        """A paid subscription with a missing/zero current_period_end is not
        provably valid, so it must not shield a downgrade from a stale inactive
        event (Codex P2). Without the guard, the truthiness check would skip the
        expiration test and the helper would incorrectly return True."""
        current = Subscription(
            plan=PlanType.operator,
            status=SubscriptionStatus.active,
            stripe_subscription_id="sub_no_period_end",
            current_period_end=None,
        )

        assert self.fn(current, "sub_old_inactive", now=1_700_000_000) is False

    def test_zero_period_end_does_not_preserve_paid_access(self):
        """A zero current_period_end is equivalent to missing and must not be
        treated as a valid unexpired period."""
        current = Subscription(
            plan=PlanType.operator,
            status=SubscriptionStatus.active,
            stripe_subscription_id="sub_zero_period_end",
            current_period_end=0,
        )

        assert self.fn(current, "sub_old_inactive", now=1_700_000_000) is False

    def test_webhook_uses_non_creating_subscription_read_for_stale_downgrade_guard(self):
        source = self.PAYMENT_SOURCE_FILE.read_text(encoding="utf-8")
        sub_idx = source.find("'customer.subscription.updated'")
        assert sub_idx != -1, "customer.subscription handler not found"
        next_idx = source.find("subscription_schedule.completed", sub_idx)
        assert next_idx != -1, "subscription_schedule handler end marker not found"
        block = source[sub_idx:next_idx]

        assert 'get_existing_user_subscription' in block
        assert 'get_user_subscription' not in block

    def test_existing_subscription_read_does_not_create_default_subscription(self):
        source = self.USERS_SOURCE_FILE.read_text(encoding="utf-8")
        func_start = source.index('def get_existing_user_subscription')
        next_func = source.index('\ndef ', func_start + 1)
        func_body = source[func_start:next_func]

        assert '.set(' not in func_body
        assert 'get_default_basic_subscription' not in func_body


class TestStripeEntitlementMismatchScannerDrift:
    """Guard against price→plan mapping drift between the standalone support
    scanner and the backend subscription mapping.

    find_stripe_entitlement_mismatches.py cannot import the backend chain
    (Firestore/Google Cloud deps), so it keeps its own DEFAULT_PRICE_TO_PLAN.
    If it drifts from backend/utils/subscription.py LEGACY_PRICE_MAP, the
    scanner silently skips active paid subscriptions and under-reports
    entitlement mismatches. This test catches that drift.
    """

    SUPPORT_FILE = Path(__file__).resolve().parents[2] / "scripts" / "support" / "find_stripe_entitlement_mismatches.py"
    SUBSCRIPTION_FILE = Path(__file__).resolve().parents[2] / "utils" / "subscription.py"

    def _extract_price_ids(self, source: str, start_marker: str) -> set:
        """Extract quoted price_ IDs between start_marker and the closing brace."""
        start = source.find(start_marker)
        assert start != -1, f"{start_marker} not found"
        end = source.find("\n}", start)
        block = source[start:end]
        return set(re.findall(r"['\"](price_[A-Za-z0-9]+)['\"]", block))

    def test_support_scanner_legacy_price_ids_match_backend(self):
        """Every legacy price id in the backend LEGACY_PRICE_MAP must appear in
        the support scanner's DEFAULT_PRICE_TO_PLAN so the scanner never silently
        skips a known paid price."""
        support_src = self.SUPPORT_FILE.read_text(encoding="utf-8")
        sub_src = self.SUBSCRIPTION_FILE.read_text(encoding="utf-8")

        backend_legacy = self._extract_price_ids(sub_src, "LEGACY_PRICE_MAP = {")
        support_default = self._extract_price_ids(support_src, "DEFAULT_PRICE_TO_PLAN = {")

        missing = backend_legacy - support_default
        assert not missing, (
            f"Support scanner is missing legacy price IDs that the backend knows about: {missing}. "
            "Add them to DEFAULT_PRICE_TO_PLAN to avoid under-reporting entitlement mismatches."
        )
