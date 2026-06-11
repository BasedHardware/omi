"""Tests for the mobile catalog + source predicates that drive Phase 3 of the
Superwall rollout — catalog filtering on ``/v1/payments/available-plans`` and
the conflict guard on ``/v1/payments/checkout-session``.

Catalog policy (manager-locked, see plans/superwall_mobile_plans):
  - Mobile + no sub | Superwall sub  → Lite/Plus/Max display catalog
  - Mobile + legacy Stripe sub       → empty (legacy users keep their existing
                                       management surface; new offers hidden)
  - Desktop/web + Superwall sub      → empty (no new desktop purchase path)
  - Desktop/web + Stripe / no sub    → existing legacy catalog (untested here —
                                       covered by test_subscription_plans)

Checkout-session guard:
  - Active Superwall sub at user → 422; UIs hide the trigger anyway but this
    catches a stray call before Stripe gets a duplicate billing rail.

Helpers live in ``utils.superwall_catalog`` (extracted from the router) so
these tests stay router-import-free — no opuslib / Stripe / fastapi pulled in.
"""

import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault(
    "database._client",
    types.SimpleNamespace(db=MagicMock(), document_id_from_seed=MagicMock(return_value="seed_id")),
)
sys.modules.setdefault("database.cache", types.SimpleNamespace(get_memory_cache=MagicMock()))

from models.users import PlanType, Subscription, SubscriptionSource, SubscriptionStatus
from utils.superwall_catalog import (
    build_mobile_plan_catalog,
    has_active_legacy_stripe_sub,
    has_active_superwall_sub,
    is_mobile_platform,
)


def _sub(
    plan: PlanType,
    source: SubscriptionSource,
    status: SubscriptionStatus = SubscriptionStatus.active,
) -> Subscription:
    return Subscription(plan=plan, source=source, status=status)


# ── Mobile catalog ──────────────────────────────────────────────────────────


class TestMobileCatalog:
    """Mobile users see Lite/Plus/Unlimited if not on a legacy Stripe sub."""

    def test_mobile_no_sub_returns_three_tiers(self):
        opts = build_mobile_plan_catalog(PlanType.basic)
        plan_ids = sorted({o["plan_id"] for o in opts})
        assert plan_ids == ["lite", "plus", "unlimited_v2"]
        # Each tier ships monthly + annual = 6 options total.
        assert len(opts) == 6

    def test_mobile_catalog_marks_active_plan(self):
        opts = build_mobile_plan_catalog(PlanType.plus)
        active = [o for o in opts if o["is_active"]]
        # Both monthly + annual rows for the user's current tier flag active.
        assert {o["plan_id"] for o in active} == {"plus"}
        assert len(active) == 2

    def test_mobile_catalog_pricing(self):
        opts = build_mobile_plan_catalog(PlanType.basic)
        by_id = {o["id"]: o for o in opts}
        assert by_id["com.omi.app.lite_monthly"]["unit_amount"] == 999
        assert by_id["com.omi.app.lite_yearly"]["unit_amount"] == 7999
        assert by_id["com.omi.app.plus_monthly"]["unit_amount"] == 2999
        assert by_id["com.omi.app.unlimited_v2_monthly"]["unit_amount"] == 4999

    def test_mobile_catalog_unknown_current_plan(self):
        """A legacy Stripe-paid plan should not match any mobile tier as active."""
        opts = build_mobile_plan_catalog(PlanType.unlimited)
        assert all(o["is_active"] is False for o in opts)


# ── Predicate helpers ───────────────────────────────────────────────────────


class TestSourcePredicates:
    def test_legacy_stripe_active_paid(self):
        assert has_active_legacy_stripe_sub(_sub(PlanType.unlimited, SubscriptionSource.stripe)) is True
        assert has_active_legacy_stripe_sub(_sub(PlanType.architect, SubscriptionSource.stripe)) is True
        assert has_active_legacy_stripe_sub(_sub(PlanType.operator, SubscriptionSource.stripe)) is True

    def test_legacy_stripe_inactive_not_legacy(self):
        sub = _sub(PlanType.unlimited, SubscriptionSource.stripe, SubscriptionStatus.inactive)
        assert has_active_legacy_stripe_sub(sub) is False

    def test_basic_plan_not_legacy_paid(self):
        assert has_active_legacy_stripe_sub(_sub(PlanType.basic, SubscriptionSource.stripe)) is False

    def test_superwall_sub_not_legacy(self):
        assert has_active_legacy_stripe_sub(_sub(PlanType.lite, SubscriptionSource.superwall_ios)) is False

    def test_no_sub_not_legacy(self):
        assert has_active_legacy_stripe_sub(None) is False

    def test_active_superwall(self):
        assert has_active_superwall_sub(_sub(PlanType.lite, SubscriptionSource.superwall_ios)) is True
        assert has_active_superwall_sub(_sub(PlanType.plus, SubscriptionSource.superwall_android)) is True

    def test_inactive_superwall(self):
        sub = _sub(PlanType.lite, SubscriptionSource.superwall_ios, SubscriptionStatus.inactive)
        assert has_active_superwall_sub(sub) is False

    def test_stripe_not_superwall(self):
        assert has_active_superwall_sub(_sub(PlanType.unlimited, SubscriptionSource.stripe)) is False


class TestPlatformDetection:
    def test_mobile_platforms(self):
        assert is_mobile_platform("ios") is True
        assert is_mobile_platform("android") is True
        assert is_mobile_platform("IOS") is True

    def test_non_mobile_platforms(self):
        assert is_mobile_platform("macos") is False
        assert is_mobile_platform("web") is False
        assert is_mobile_platform(None) is False
