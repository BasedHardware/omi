"""Tests for the Neo desktop-access grandfather.

#7496 removed Neo from DESKTOP_ENTITLED_PLAN_TYPES, which immediately pulled
desktop access from every existing Neo subscriber mid-billing-cycle. The
grandfather added here keeps Neo subscribers whose current billing period
started before NEO_DESKTOP_GRANDFATHER_CUTOFF on the desktop until that
period ends; at their next renewal they fall into the new policy.

Test surface:
- plan_grants_desktop() with the new optional subscription arg
- neo_grandfather_until() helper
- Subscription.current_period_start populated by webhook builder
"""

from unittest.mock import MagicMock, patch

import pytest

# Import database before utils.subscription to satisfy the circular import.
import database.users  # noqa: F401
import utils.subscription as subscription_mod

from models.users import PlanType, Subscription  # noqa: E402
from utils.subscription import (  # noqa: E402
    NEO_DESKTOP_GRANDFATHER_CUTOFF,
    DESKTOP_ACCESS_TIER_ARCHITECT,
    DESKTOP_ACCESS_TIER_FREE,
    DESKTOP_ACCESS_TIER_FULL,
    desktop_trial_paywall_eligible,
    effective_desktop_access_tier,
    get_remaining_transcription_seconds,
    is_trial_paywalled,
    neo_grandfather_until,
    plan_grants_desktop,
)

# Anchor unit-test arithmetic to the constant the code uses so a future
# cutoff change doesn't silently invalidate these tests.
PRE_CUTOFF = NEO_DESKTOP_GRANDFATHER_CUTOFF - 1
POST_CUTOFF = NEO_DESKTOP_GRANDFATHER_CUTOFF + 1
FAR_FUTURE = NEO_DESKTOP_GRANDFATHER_CUTOFF + 10_000_000


class TestPlanGrantsDesktop:
    """Operator/Architect always; Neo only under the grandfather; basic never."""

    def test_architect_always_grants_desktop(self):
        sub = Subscription(plan=PlanType.architect, current_period_start=POST_CUTOFF)
        assert plan_grants_desktop(PlanType.architect, sub) is True

    def test_operator_always_grants_desktop(self):
        sub = Subscription(plan=PlanType.operator, current_period_start=POST_CUTOFF)
        assert plan_grants_desktop(PlanType.operator, sub) is True

    def test_architect_grants_desktop_without_subscription_arg(self):
        # Back-compat for callers that don't pass the subscription.
        assert plan_grants_desktop(PlanType.architect) is True

    def test_basic_never_grants_desktop(self):
        assert plan_grants_desktop(PlanType.basic) is False
        sub = Subscription(plan=PlanType.basic, current_period_start=PRE_CUTOFF)
        assert plan_grants_desktop(PlanType.basic, sub) is False

    def test_neo_pre_cutoff_period_grants_desktop(self):
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=PRE_CUTOFF,
            current_period_end=FAR_FUTURE,
        )
        assert plan_grants_desktop(PlanType.unlimited, sub) is True

    def test_neo_post_cutoff_period_does_not_grant_desktop(self):
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=POST_CUTOFF,
            current_period_end=FAR_FUTURE,
        )
        assert plan_grants_desktop(PlanType.unlimited, sub) is False

    def test_neo_none_period_start_grants_desktop(self):
        # Existing pre-deploy subs have current_period_start=None until their
        # next webhook fires. Treat as pre-cutoff so they keep desktop access
        # for the period they already paid for.
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=None,
            current_period_end=FAR_FUTURE,
        )
        assert plan_grants_desktop(PlanType.unlimited, sub) is True

    def test_neo_without_subscription_arg_does_not_grant_desktop(self):
        # If a caller doesn't pass the subscription, fall through to "no
        # grandfather" — safer than accidentally granting desktop to anyone
        # who happens to be on Neo when the caller didn't look at the sub.
        assert plan_grants_desktop(PlanType.unlimited) is False
        assert plan_grants_desktop(PlanType.unlimited, None) is False


class TestEffectiveDesktopAccessTier:
    """Every plan resolves to a usable Desktop tier; Neo never resolves to none."""

    def test_free_neo_operator_and_architect_resolve_to_expected_tiers(self):
        post_cutoff_neo = Subscription(plan=PlanType.unlimited, current_period_start=POST_CUTOFF)

        assert effective_desktop_access_tier(PlanType.basic) == DESKTOP_ACCESS_TIER_FREE
        assert effective_desktop_access_tier(PlanType.unlimited, post_cutoff_neo) == DESKTOP_ACCESS_TIER_FREE
        assert effective_desktop_access_tier(PlanType.operator) == DESKTOP_ACCESS_TIER_FULL
        assert effective_desktop_access_tier(PlanType.architect) == DESKTOP_ACCESS_TIER_ARCHITECT

    def test_only_free_is_eligible_for_account_age_paywall(self):
        post_cutoff_neo = Subscription(plan=PlanType.unlimited, current_period_start=POST_CUTOFF)

        assert desktop_trial_paywall_eligible(PlanType.basic) is True
        assert desktop_trial_paywall_eligible(PlanType.unlimited, post_cutoff_neo) is False
        assert desktop_trial_paywall_eligible(PlanType.operator) is False
        assert desktop_trial_paywall_eligible(PlanType.architect) is False

    def test_post_cutoff_neo_cannot_receive_zero_desktop_audio_credits(self, monkeypatch):
        """Exercise the same resolver used by /v4/listen admission and refresh."""
        post_cutoff_neo = Subscription(plan=PlanType.unlimited, current_period_start=POST_CUTOFF)
        cache_values = iter((True, None))
        cleared_cache_keys = []

        def clear_cache(key):
            cleared_cache_keys.append(key)

        monkeypatch.setattr(subscription_mod, 'TRIAL_PAYWALL_ENABLED', True)
        monkeypatch.setattr(subscription_mod.users_db, 'get_user_valid_subscription', lambda _uid: post_cutoff_neo)
        monkeypatch.setattr(subscription_mod.users_db, 'is_byok_active', lambda _uid: False)
        monkeypatch.setattr(subscription_mod, '_request_has_all_byok_keys', lambda: False)
        monkeypatch.setattr(subscription_mod.redis_db, 'get_generic_cache', lambda _key: next(cache_values))
        monkeypatch.setattr(subscription_mod.redis_db, 'set_generic_cache', lambda *_args, **_kwargs: None)
        monkeypatch.setattr(subscription_mod.redis_db, 'delete_generic_cache', clear_cache)
        monkeypatch.setattr(subscription_mod, 'record_fallback', lambda **_kwargs: None)

        assert is_trial_paywalled('neo-uid', 'desktop') is False
        assert get_remaining_transcription_seconds('neo-uid', source='desktop') is None
        assert cleared_cache_keys == ['trial_paywall:expired:neo-uid']


class TestNeoGrandfatherUntil:
    """Surface the end-of-grandfather timestamp to the client; null otherwise."""

    def test_pre_cutoff_neo_returns_period_end(self):
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=PRE_CUTOFF,
            current_period_end=FAR_FUTURE,
        )
        assert neo_grandfather_until(sub) == FAR_FUTURE

    def test_post_cutoff_neo_returns_none(self):
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=POST_CUTOFF,
            current_period_end=FAR_FUTURE,
        )
        assert neo_grandfather_until(sub) is None

    def test_architect_returns_none(self):
        # Architect already has desktop natively — no "grandfather" concept.
        sub = Subscription(
            plan=PlanType.architect,
            current_period_start=PRE_CUTOFF,
            current_period_end=FAR_FUTURE,
        )
        assert neo_grandfather_until(sub) is None

    def test_basic_returns_none(self):
        assert neo_grandfather_until(None) is None
        sub = Subscription(plan=PlanType.basic)
        assert neo_grandfather_until(sub) is None

    def test_neo_none_period_start_returns_period_end(self):
        # Pre-deploy sub that hasn't had a webhook fire yet — still grandfathered
        # so it should surface the period_end.
        sub = Subscription(
            plan=PlanType.unlimited,
            current_period_start=None,
            current_period_end=FAR_FUTURE,
        )
        assert neo_grandfather_until(sub) == FAR_FUTURE


class TestSubscriptionModelHasPeriodStart:
    """Schema check: current_period_start was added in this PR with a None default."""

    def test_current_period_start_defaults_to_none(self):
        sub = Subscription()
        assert sub.current_period_start is None

    def test_current_period_start_round_trips(self):
        sub = Subscription(current_period_start=PRE_CUTOFF)
        assert sub.current_period_start == PRE_CUTOFF
        # Stays in dict form for Firestore persistence.
        assert sub.dict()['current_period_start'] == PRE_CUTOFF


class TestWebhookBuilderPopulatesPeriodStart:
    """_build_subscription_from_stripe_object must pull current_period_start out
    of the Stripe payload so the grandfather check has a value to compare against.
    Verified by reading the source so we don't have to wire the full Stripe SDK."""

    def test_builder_reads_current_period_start_active_path(self):
        with open('routers/payment.py', encoding='utf-8') as f:
            src = f.read()
        # Both the inactive-downgrade Subscription(...) and the active
        # Subscription(...) constructors must pass current_period_start.
        assert (
            src.count("current_period_start=stripe_sub.get('current_period_start')") >= 2
        ), "_build_subscription_from_stripe_object must set current_period_start on both branches"

    def test_reconcile_paths_set_current_period_start(self):
        with open('utils/subscription.py', encoding='utf-8') as f:
            src = f.read()
        # find_active_paid_subscription_for_user + reconcile_basic_plan_with_stripe.
        assert (
            "current_period_start=d.get('current_period_start')" in src
        ), "find_active_paid_subscription_for_user must set current_period_start"
        assert (
            "subscription.current_period_start = stripe_sub_dict.get('current_period_start')" in src
        ), "reconcile_basic_plan_with_stripe must set current_period_start"


class TestPolicyDocstring:
    """Sanity check that the policy comment + cutoff stay in sync with the code."""

    def test_cutoff_is_env_overridable(self):
        with open('utils/subscription.py', encoding='utf-8') as f:
            src = f.read()
        assert "NEO_DESKTOP_GRANDFATHER_CUTOFF" in src
        assert "os.getenv('NEO_DESKTOP_GRANDFATHER_CUTOFF'" in src

    def test_cutoff_default_matches_pr_7496_merge(self):
        # #7496 merged 2026-05-25 22:34:39 UTC. If the merge date moves, update
        # both the constant default and this assertion together.
        assert NEO_DESKTOP_GRANDFATHER_CUTOFF == 1779748479
