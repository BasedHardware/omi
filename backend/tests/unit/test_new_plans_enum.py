"""Tests for the new mobile plan tiers (Lite / Plus / Max) and ``SubscriptionSource``.

Mobile-only purchase tiers — Lite ($9.99/mo, $79.99/yr), Plus ($29.99/$199.99),
and Max ($49.99/$299.99) — must:
  - exist on ``PlanType``
  - count as paid plans
  - resolve to the correct caps (with the doc-missing fallback values
    matching issue #23: 100/1500, 300/4000, unlimited/unlimited)
  - have human display names
  - NOT collide with the legacy ``'pro'`` alias that still resolves to
    ``PlanType.architect`` for any user docs not yet rewritten

``Subscription.source`` is a new field that records which billing rail
created the sub — ``stripe`` for the existing book, ``superwall_ios`` /
``superwall_android`` for new App Store / Play Store purchases. Default
remains ``stripe`` so untouched legacy rows behave exactly as before.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy deps before importing production code.
sys.modules.setdefault(
    "database._client",
    types.SimpleNamespace(db=MagicMock(), document_id_from_seed=MagicMock(return_value="seed_id")),
)
sys.modules.setdefault("database.cache", types.SimpleNamespace(get_memory_cache=MagicMock()))

from models.users import PlanType, PlanLimits, Subscription, SubscriptionSource

# ── PlanType enum ───────────────────────────────────────────────────────────


class TestPlanTypeEnum:
    def test_new_plans_exist(self):
        assert PlanType.lite.value == "lite"
        assert PlanType.plus.value == "plus"
        assert PlanType.max.value == "max"

    def test_legacy_pro_alias_still_maps_to_architect(self):
        """Pre-rename `'pro'` strings in Firestore must keep resolving to architect."""
        assert PlanType("pro") == PlanType.architect

    def test_lite_is_distinct_from_architect(self):
        """Sanity: new Lite isn't an alias for any legacy plan."""
        assert PlanType.lite != PlanType.architect
        assert PlanType.lite != PlanType.unlimited
        assert PlanType.lite != PlanType.operator


# ── is_paid_plan ────────────────────────────────────────────────────────────


class TestIsPaidPlan:
    def test_new_plans_are_paid(self):
        from utils.subscription import is_paid_plan

        assert is_paid_plan(PlanType.lite) is True
        assert is_paid_plan(PlanType.plus) is True
        assert is_paid_plan(PlanType.max) is True

    def test_basic_still_unpaid(self):
        from utils.subscription import is_paid_plan

        assert is_paid_plan(PlanType.basic) is False


# ── Display names ───────────────────────────────────────────────────────────


class TestDisplayNames:
    def test_new_plans_have_display_names(self):
        from utils.subscription import get_plan_display_name

        assert get_plan_display_name(PlanType.lite) == "Lite"
        assert get_plan_display_name(PlanType.plus) == "Plus"
        assert get_plan_display_name(PlanType.max) == "Max"


# ── Cap defaults (Firestore doc absent → fallback to issue #23 spec) ────────


def _reload_config_module():
    import importlib
    import database.plan_caps_config as mod

    importlib.reload(mod)
    return mod


class TestNewPlanCapsDefaults:
    """Without a Firestore override, new plan caps match issue #23."""

    def test_lite_defaults(self):
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.lite)
        assert caps["chat_questions_per_month"] == 100
        assert caps["transcription_seconds"] == 1500 * 60  # 90,000s
        assert caps["chat_cost_usd_per_month"] is None

    def test_plus_defaults(self):
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.plus)
        assert caps["chat_questions_per_month"] == 300
        assert caps["transcription_seconds"] == 4000 * 60  # 240,000s

    def test_max_unlimited_caps(self):
        """Max tier is unlimited on both axes."""
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.max)
        assert caps["chat_questions_per_month"] is None
        assert caps["transcription_seconds"] is None

    def test_get_plan_limits_returns_planlimits(self):
        from utils.subscription import get_plan_limits

        with patch("database.plan_caps_config._get_config", return_value={}):
            limits = get_plan_limits(PlanType.lite)
        assert isinstance(limits, PlanLimits)
        assert limits.chat_questions_per_month == 100
        assert limits.transcription_seconds == 1500 * 60


# ── SubscriptionSource ──────────────────────────────────────────────────────


class TestSubscriptionSource:
    def test_source_enum_values(self):
        assert SubscriptionSource.stripe.value == "stripe"
        assert SubscriptionSource.superwall_ios.value == "superwall_ios"
        assert SubscriptionSource.superwall_android.value == "superwall_android"

    def test_subscription_default_source_is_stripe(self):
        """Existing rows that don't set source must behave as Stripe-sourced."""
        sub = Subscription()
        assert sub.source == SubscriptionSource.stripe

    def test_subscription_explicit_superwall_source(self):
        sub = Subscription(source=SubscriptionSource.superwall_ios)
        assert sub.source == SubscriptionSource.superwall_ios

    def test_subscription_source_round_trips_via_string(self):
        """Firestore stores enum values as strings; round-trip must preserve."""
        sub = Subscription(source="superwall_android")
        assert sub.source == SubscriptionSource.superwall_android
