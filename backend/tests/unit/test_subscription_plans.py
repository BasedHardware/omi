"""Subscription plan tests — migrated off module-scope ``sys.modules`` mutation.

``utils.subscription`` pulls in ``database.users`` at import time, which itself
imports back from ``utils.subscription`` (circular). The original test broke the
cycle by pre-corrupting ``sys.modules`` at module scope with empty stubs. This
file uses the sanctioned Tier-2 reserve seam: a module-scoped fixture that
installs the stubs via ``stub_modules`` and exec's ``utils.subscription`` fresh
with ``load_module_fresh``, then restores on teardown. See
backend/docs/test_isolation.md and testing/import_isolation.py.
"""

import logging
import os
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from models.users import PlanType
from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def subscription_module():
    """Load a fresh ``utils.subscription`` against stubbed circular-import deps."""
    announcements_stub = ModuleType("database.announcements")
    announcements_stub.compare_versions = lambda a, b: 0
    client_stub = ModuleType("database._client")
    client_stub.get_customer_firestore_client = MagicMock()

    fakes = {
        "database.announcements": announcements_stub,
        "database._client": client_stub,
        "database.users": ModuleType("database.users"),
        "database.user_usage": ModuleType("database.user_usage"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.subscription",
            os.path.join(str(_BACKEND), "utils", "subscription.py"),
        )
        yield module


def test_architect_price_ids_map_to_architect_plan(monkeypatch, subscription_module):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")
    monkeypatch.setenv("STRIPE_ARCHITECT_MONTHLY_PRICE_ID", "price_architect_monthly")
    monkeypatch.setenv("STRIPE_ARCHITECT_ANNUAL_PRICE_ID", "price_architect_annual")

    get_plan_type_from_price_id = subscription_module.get_plan_type_from_price_id

    assert get_plan_type_from_price_id("price_unlimited_monthly") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_unlimited_annual") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_architect_monthly") == PlanType.architect
    assert get_plan_type_from_price_id("price_architect_annual") == PlanType.architect


def test_dev_startup_skips_stripe_price_validation(monkeypatch, subscription_module, caplog):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    caplog.set_level(logging.INFO, logger=subscription_module.__name__)
    definitions = MagicMock()
    retrieve = MagicMock()
    fallback = MagicMock()
    monkeypatch.setattr(subscription_module, 'get_paid_plan_definitions', definitions)
    monkeypatch.setattr(subscription_module.stripe.Price, 'retrieve', retrieve)
    monkeypatch.setattr(subscription_module, 'record_fallback', fallback)

    subscription_module.validate_stripe_price_ids()

    definitions.assert_not_called()
    retrieve.assert_not_called()
    fallback.assert_called_once_with(
        component='other',
        from_mode='stripe_price_validation',
        to_mode='dev_skip',
        reason='policy',
        outcome='degraded',
        log=subscription_module.logger,
    )
    assert 'Skipping Stripe price validation during dev startup.' in caplog.messages


def test_prod_startup_validates_stripe_price_ids(monkeypatch, subscription_module):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(
        subscription_module,
        'get_paid_plan_definitions',
        lambda: [
            {
                'plan_id': 'operator',
                'monthly_price_id': 'price_operator_monthly',
                'annual_price_id': 'price_operator_annual',
            }
        ],
    )
    retrieve = MagicMock()
    monkeypatch.setattr(subscription_module.stripe.Price, 'retrieve', retrieve)

    subscription_module.validate_stripe_price_ids()

    assert retrieve.call_args_list == [call('price_operator_monthly'), call('price_operator_annual')]


def test_architect_is_treated_as_paid_unlimited_plan(subscription_module):
    assert subscription_module.is_paid_plan(PlanType.architect) is True
    assert subscription_module.get_plan_limits(PlanType.architect).transcription_seconds is None
    assert "Automations and vibe coding" in subscription_module.get_plan_features(PlanType.architect)
    assert "Unlimited listening, memories, and insights" in subscription_module.get_plan_features(PlanType.architect)


def test_basic_plan_features_include_unlimited_memories(subscription_module):
    features = subscription_module.get_plan_features(PlanType.basic)
    assert "Unlimited memories" in features


def test_cancellation_is_pending_until_period_end(subscription_module):
    subscription = SimpleNamespace(cancel_at_period_end=True, current_period_end=200)

    assert subscription_module.is_pending_cancellation(subscription, now=199)
    assert not subscription_module.is_pending_cancellation(subscription, now=200)


def test_missing_period_end_is_still_pending_cancellation(subscription_module):
    subscription = SimpleNamespace(cancel_at_period_end=True, current_period_end=None)

    assert subscription_module.is_pending_cancellation(subscription, now=200)


def test_can_pay_basic_stale_defers_plan_change_until_cancellation_ends(monkeypatch, subscription_module):
    """A cancel-at-period-end Stripe subscription must block a different target
    price even when the local Firestore record is missing/basic (lag or recovery).
    Same-price reactivation stays allowed in that branch."""
    sub = subscription_module

    # Firestore record is basic/stale -> no pending cancellation there.
    monkeypatch.setattr(sub, "users_db", SimpleNamespace())
    sub.users_db.get_user_valid_subscription = lambda uid: None
    sub.users_db.get_stripe_customer_id = lambda uid: "cus_x"
    # No active (non-canceling) subscription, so the basic branch proceeds.
    monkeypatch.setattr(sub, "_has_active_stripe_subscription", lambda uid: False)

    pending = SimpleNamespace(
        plan="paid",
        status="active",
        cancel_at_period_end=True,
        current_period_end=2_000_000_000,
        current_price_id="price_current",
    )
    monkeypatch.setattr(sub, "find_active_paid_subscription_for_user", lambda uid: pending)
    monkeypatch.setattr(
        sub,
        "price_ids_match_plan_and_interval",
        lambda current_price_id, target_price_id: current_price_id == target_price_id,
    )

    # Different target price must be deferred even though Firestore is basic.
    can_pay, reason = sub.can_user_make_payment("u1", target_price_id="price_target")
    assert can_pay is False
    assert "after the current subscription ends" in reason

    # Same-price reactivation is allowed.
    can_pay, reason = sub.can_user_make_payment("u1", target_price_id="price_current")
    assert can_pay is True
    assert "reactivate" in reason


def _mock_new_buyer(monkeypatch, subscription_module):
    """A buyer with no current paid subscription and no Stripe-side surprises."""
    sub = subscription_module
    monkeypatch.setattr(sub, "users_db", SimpleNamespace())
    sub.users_db.get_user_valid_subscription = lambda uid: None
    sub.users_db.get_stripe_customer_id = lambda uid: "cus_x"
    monkeypatch.setattr(sub, "_has_active_stripe_subscription", lambda uid: False)
    monkeypatch.setattr(sub, "find_active_paid_subscription_for_user", lambda uid: None)


def _set_catalog_prices(monkeypatch):
    monkeypatch.setenv("STRIPE_PLUS_MONTHLY_PRICE_ID", "price_plus_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID", "price_unlimited_v2_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID", "price_unlimited_v2_annual")
    monkeypatch.setenv("STRIPE_OPERATOR_MONTHLY_PRICE_ID", "price_operator_monthly")


def _subscriber(plan, subscription_id="sub_personal", price_id=None):
    return lambda uid, **kwargs: SimpleNamespace(
        plan=plan,
        status="active",
        cancel_at_period_end=False,
        current_period_end=2_000_000_000,
        stripe_subscription_id=subscription_id,
        current_price_id=price_id,
    )


def test_new_buyer_single_plan_rejects_retired_prices(monkeypatch, subscription_module):
    """Omi Pro (`unlimited_v2`) is the only plan sold. A buyer with no current
    paid subscription cannot start on a retired plan's price."""
    sub = subscription_module
    _mock_new_buyer(monkeypatch, sub)
    _set_catalog_prices(monkeypatch)

    for price_id in ("price_plus_monthly", "price_operator_monthly"):
        error = sub.new_buyer_single_plan_violation("u1", price_id)
        assert error is not None and "Omi Pro" in error, price_id


def test_granted_plan_without_personal_subscription_is_not_exempt(monkeypatch, subscription_module):
    """Organization grants store a one-time PaymentIntent (`pi_…`) or no id at
    all; only a current *recurring* personal subscription exempts a caller.
    A grant recipient is a new buyer for checkout."""
    sub = subscription_module
    _set_catalog_prices(monkeypatch)
    monkeypatch.setattr(sub, "users_db", SimpleNamespace())
    for granted_id in ("pi_org_grant", None):
        sub.users_db.get_user_valid_subscription = _subscriber(PlanType.operator, granted_id)
        assert sub.new_buyer_single_plan_violation("u1", "price_operator_monthly") is not None, granted_id


def test_current_subscriber_exempt_only_for_their_own_plan(monkeypatch, subscription_module):
    """A subscriber on a retired plan keeps managing that plan, but cannot buy
    a different retired plan."""
    sub = subscription_module
    _set_catalog_prices(monkeypatch)
    monkeypatch.setattr(sub, "users_db", SimpleNamespace())
    sub.users_db.get_user_valid_subscription = _subscriber(PlanType.operator, price_id="price_operator_monthly")
    assert sub.new_buyer_single_plan_violation("u1", "price_operator_monthly") is None
    assert sub.new_buyer_single_plan_violation("u1", "price_plus_monthly") is not None
    assert sub.new_buyer_single_plan_violation("u1", "price_unlimited_v2_monthly") is None


def test_new_buyer_single_plan_accepts_unlimited_v2(monkeypatch, subscription_module):
    sub = subscription_module
    _mock_new_buyer(monkeypatch, sub)
    _set_catalog_prices(monkeypatch)

    for price_id in ("price_unlimited_v2_monthly", "price_unlimited_v2_annual"):
        assert sub.new_buyer_single_plan_violation("u1", price_id) is None, price_id


def test_new_buyer_single_plan_kill_switch_restores_old_targets(monkeypatch, subscription_module):
    for off_value in ("false", "0", "off", "no"):
        monkeypatch.setenv("NEW_BUYER_SINGLE_PLAN_ENABLED", off_value)
        sub = subscription_module
        _mock_new_buyer(monkeypatch, sub)
        _set_catalog_prices(monkeypatch)
        assert sub.new_buyer_single_plan_violation("u1", "price_plus_monthly") is None, off_value
    monkeypatch.delenv("NEW_BUYER_SINGLE_PLAN_ENABLED", raising=False)


def test_new_buyer_single_plan_rejection_metric_counts_by_reason_and_plan(monkeypatch, subscription_module):
    from prometheus_client import REGISTRY

    sub = subscription_module
    _mock_new_buyer(monkeypatch, sub)
    _set_catalog_prices(monkeypatch)
    labels = {"reason": "non_omi_pro_price", "plan": "plus"}
    before = REGISTRY.get_sample_value("omi_new_buyer_checkout_rejected_total", labels) or 0.0

    assert sub.new_buyer_single_plan_violation("u1", "price_plus_monthly") is not None
    assert sub.new_buyer_single_plan_violation("u1", "price_plus_monthly") is not None
    # A rejection-free call must not move the counter.
    assert sub.new_buyer_single_plan_violation("u1", "price_unlimited_v2_monthly") is None

    after = REGISTRY.get_sample_value("omi_new_buyer_checkout_rejected_total", labels)
    assert after == before + 2.0


def test_retired_plan_change_allows_only_omi_pro_or_same_plan(monkeypatch, subscription_module):
    sub = subscription_module
    monkeypatch.delenv("NEW_BUYER_SINGLE_PLAN_ENABLED", raising=False)
    assert sub.retired_plan_change_error(PlanType.plus, PlanType.unlimited_v2) is None
    assert sub.retired_plan_change_error(PlanType.operator, PlanType.operator) is None
    assert sub.retired_plan_change_error(PlanType.plus, PlanType.operator) is not None
    assert sub.retired_plan_change_error(PlanType.unlimited_v2, PlanType.architect) is not None
    monkeypatch.setenv("NEW_BUYER_SINGLE_PLAN_ENABLED", "false")
    assert sub.retired_plan_change_error(PlanType.plus, PlanType.operator) is None


def test_retained_price_matches_current_price_with_same_plan_and_interval(monkeypatch, subscription_module):
    sub = subscription_module
    retained_price_id = "price_1RtJPm1F8wnoWYvwhVJ38kLb"
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")

    retrieve = MagicMock(side_effect=AssertionError("retained catalog prices must not require a Stripe read"))
    monkeypatch.setattr(sub.stripe.Price, "retrieve", retrieve)

    assert sub.price_ids_match_plan_and_interval(retained_price_id, "price_unlimited_monthly")
    assert not sub.price_ids_match_plan_and_interval(retained_price_id, "price_unlimited_annual")
    retrieve.assert_not_called()


def test_price_interval_lookup_handles_price_without_recurring(monkeypatch, subscription_module):
    sub = subscription_module
    configured_alias_price_id = "price_configured_neo_alias"
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")
    monkeypatch.setenv("STRIPE_NEO_MONTHLY_PRICE_ID", configured_alias_price_id)

    # A configured migration alias without a catalog-ledger interval whose
    # Stripe object carries no recurring block must not crash the lookup.
    price_without_recurring = MagicMock()
    del price_without_recurring.recurring
    monkeypatch.setattr(sub.stripe.Price, "retrieve", MagicMock(return_value=price_without_recurring))

    assert not sub.price_ids_match_plan_and_interval(configured_alias_price_id, "price_unlimited_monthly")
    assert not sub.price_ids_match_plan_and_interval(configured_alias_price_id, "price_unlimited_annual")


def test_reconcile_basic_subscription_without_stored_stripe_id(monkeypatch, subscription_module):
    sub = subscription_module
    stored = SimpleNamespace(plan=PlanType.basic, stripe_subscription_id=None, current_period_end=None)
    recovered = MagicMock()
    recovered.model_dump.return_value = {"stripe_subscription_id": "sub_recovered"}
    users_db = SimpleNamespace(update_user_subscription=MagicMock())
    monkeypatch.setattr(sub, "users_db", users_db)
    monkeypatch.setattr(sub, "find_active_paid_subscription_for_user", lambda uid: recovered)

    assert sub.reconcile_basic_plan_with_stripe("u1", stored) is recovered
    users_db.update_user_subscription.assert_called_once_with("u1", {"stripe_subscription_id": "sub_recovered"})


def test_unlimited_transcription_plan_skips_monthly_usage_scan(monkeypatch, subscription_module):
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source=None, **kw: False)
    monkeypatch.setattr(subscription_module.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(subscription_module, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        subscription_module.users_db,
        'get_user_valid_subscription',
        lambda uid: SimpleNamespace(plan=PlanType.architect),
        raising=False,
    )
    monthly_usage = MagicMock(return_value={'transcription_seconds': 999999})
    monkeypatch.setattr(subscription_module, 'get_monthly_usage_for_subscription', monthly_usage)

    assert subscription_module.has_transcription_credits('uid') is True
    monthly_usage.assert_not_called()


def test_bounded_transcription_plan_reads_monthly_usage_and_enforces_cap(monkeypatch, subscription_module):
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source=None, **kw: False)
    monkeypatch.setattr(subscription_module.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(subscription_module, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        subscription_module.users_db,
        'get_user_valid_subscription',
        lambda uid: SimpleNamespace(plan=PlanType.basic),
        raising=False,
    )
    # The allowance resolver reads the catalog through `transcription_allowance_seconds`
    # (never the env overlay behind `get_plan_limits`), so that is the seam to stub.
    monkeypatch.setattr(subscription_module, 'transcription_allowance_seconds', lambda plan: 60)
    monthly_usage = MagicMock(return_value={'transcription_seconds': 60})
    monkeypatch.setattr(subscription_module, 'get_monthly_usage_for_subscription', monthly_usage)

    assert subscription_module.has_transcription_credits('uid') is False
    monthly_usage.assert_called_once_with('uid')


def test_zero_transcription_allowance_is_exhausted_not_unlimited(monkeypatch, subscription_module):
    _stub_remaining_deps(monkeypatch, subscription_module, PlanType.basic, used_seconds=0)
    monkeypatch.setattr(subscription_module, 'transcription_allowance_seconds', lambda plan: 0)

    assert subscription_module.has_transcription_credits('uid') is False
    assert subscription_module.get_remaining_transcription_seconds('uid') == 0


def test_malformed_transcription_allowance_fails_loudly(monkeypatch, subscription_module):
    original_allocation_limit = subscription_module.allocation_limit

    def malformed_allocation_limit(plan, allocation):
        if allocation == 'transcription':
            raise KeyError('basic.transcription limit is missing')
        return original_allocation_limit(plan, allocation)

    monkeypatch.setattr(subscription_module, 'allocation_limit', malformed_allocation_limit)

    with pytest.raises(KeyError, match='limit is missing'):
        subscription_module.get_plan_limits(PlanType.basic)


def _stub_remaining_deps(monkeypatch, subscription_module, plan, used_seconds):
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source=None, **kw: False)
    monkeypatch.setattr(subscription_module.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(subscription_module, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        subscription_module.users_db,
        'get_user_valid_subscription',
        lambda uid: SimpleNamespace(plan=plan),
        raising=False,
    )
    monkeypatch.setattr(
        subscription_module,
        'get_monthly_usage_for_subscription',
        lambda uid: {'transcription_seconds': used_seconds},
    )


def test_remaining_transcription_seconds_enforces_plus_bounded_cap(monkeypatch, subscription_module):
    # Plus is a paid plan but carries a bounded 1500-min/month transcription cap. The
    # remaining seconds must be reported (so the freemium on-device switch can fire), not
    # short-circuited to None as if the plan were unlimited.
    cap = subscription_module.PLUS_TIER_MONTHLY_SECONDS_LIMIT
    assert cap and cap > 0  # Plus is bounded by construction
    _stub_remaining_deps(monkeypatch, subscription_module, PlanType.plus, used_seconds=cap - 10000)
    assert subscription_module.get_remaining_transcription_seconds('uid') == 10000


def test_remaining_transcription_seconds_zero_at_plus_cap(monkeypatch, subscription_module):
    cap = subscription_module.PLUS_TIER_MONTHLY_SECONDS_LIMIT
    _stub_remaining_deps(monkeypatch, subscription_module, PlanType.plus, used_seconds=cap + 5000)
    assert subscription_module.get_remaining_transcription_seconds('uid') == 0


def test_remaining_transcription_seconds_none_for_unlimited_paid_plan(monkeypatch, subscription_module):
    # Genuinely-unlimited paid plans (transcription_seconds unset) must still report None,
    # i.e. dropping the is_paid_plan short-circuit must not start capping them.
    for plan in (PlanType.architect, PlanType.operator, PlanType.unlimited, PlanType.unlimited_v2):
        _stub_remaining_deps(monkeypatch, subscription_module, plan, used_seconds=10_000_000)
        assert subscription_module.get_remaining_transcription_seconds('uid') is None, plan


def test_plus_and_unlimited_v2_price_ids_resolve(monkeypatch, subscription_module):
    monkeypatch.setenv("STRIPE_PLUS_MONTHLY_PRICE_ID", "price_plus_monthly")
    monkeypatch.setenv("STRIPE_PLUS_ANNUAL_PRICE_ID", "price_plus_annual")
    monkeypatch.setenv("STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID", "price_unlimited_v2_monthly")

    resolve = subscription_module.get_plan_type_from_price_id
    assert resolve("price_plus_monthly") == PlanType.plus
    assert resolve("price_plus_annual") == PlanType.plus
    assert resolve("price_unlimited_v2_monthly") == PlanType.unlimited_v2


def test_plus_is_capped_unlimited_v2_is_unlimited(subscription_module):
    plus = subscription_module.get_plan_limits(PlanType.plus)
    max_ = subscription_module.get_plan_limits(PlanType.unlimited_v2)
    assert plus.transcription_seconds == subscription_module.PLUS_TIER_MONTHLY_SECONDS_LIMIT
    assert plus.transcription_seconds and plus.transcription_seconds > 0
    assert max_.transcription_seconds is None
    assert subscription_module.is_paid_plan(PlanType.plus) is True
    assert subscription_module.is_paid_plan(PlanType.unlimited_v2) is True


def test_wire_plan_remaps_mobile_tiers_only_for_clients_without_the_enum(monkeypatch, subscription_module):
    # The module fixture stubs compare_versions to a no-op; use a real semver
    # comparator so the version floor actually gates the remap.
    def _cmp(a, b):
        pa = [int(x) for x in a.split('.')]
        pb = [int(x) for x in b.split('.')]
        return (pa > pb) - (pa < pb)

    monkeypatch.setattr(subscription_module, 'compare_versions', _cmp)
    wire = subscription_module.wire_plan_for_client
    # Current clients (below the plus/unlimited_v2-aware floor) must see a known paid label.
    assert wire(PlanType.plus, 'ios', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.unlimited_v2, 'android', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.plus, 'macos', '0.12.0') == PlanType.unlimited
    # A plus/unlimited_v2-aware client (at/above the floor) receives the real plan.
    assert wire(PlanType.plus, 'ios', '999.0.0') == PlanType.plus
    assert wire(PlanType.unlimited_v2, 'ios', '999.0.0') == PlanType.unlimited_v2
    # Non-mobile plans are never remapped.
    assert wire(PlanType.unlimited, 'ios', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.operator, 'ios', '1.0.600') == PlanType.operator


def test_plus_and_unlimited_v2_features_state_transcription_limits(subscription_module):
    """Mobile cards render get_plan_features; Plus/Unlimited must state their
    transcription terms, not fall through to the Free-tier feature list."""
    m = subscription_module
    plus_mobile = m.get_plan_features(PlanType.plus, simplified=True)
    unlim_mobile = m.get_plan_features(PlanType.unlimited_v2, simplified=True)

    assert any("minutes of transcription" in f for f in plus_mobile), plus_mobile
    assert any(f"{m.PLUS_TIER_MINUTES_LIMIT_PER_MONTH:,}" in f for f in plus_mobile), plus_mobile
    assert any("Unlimited transcription" in f for f in unlim_mobile), unlim_mobile
    # Must not leak the Free-tier "Unlimited listening time" fallback.
    assert not any("listening" in f for f in plus_mobile), plus_mobile


def test_basic_feature_defaults_project_from_plan_limits(monkeypatch, subscription_module):
    monkeypatch.setattr(
        subscription_module,
        'get_plan_limits',
        lambda plan: SimpleNamespace(transcription_seconds=600, words_transcribed=7, insights_gained=9),
    )

    features = subscription_module.get_plan_features(PlanType.basic)

    assert '10 minutes of listening per month' in features
    assert '7 words transcribed per month' in features
    assert '9 insights per month' in features


@pytest.mark.parametrize(
    'platform,version,capable',
    [
        ('macos', '0.12.196', False),
        ('macos', '0.12.197', True),
        ('macos', '0.12.198', True),
        ('macos', None, False),
        ('windows', '1.0.35', False),
        ('windows', None, False),
        ('ios', '1.0.552', False),
        ('android', '1.0.552', False),
        ('web', '0.1.0', True),
        ('web', '0.0.9', False),
        ('web', None, False),
        ('web', 'invalid', False),
        (None, '0.1.0', False),
        ('desktop', '99.0.0', False),
    ],
)
def test_true_plan_wire_capability_boundaries(subscription_module, monkeypatch, platform, version, capable):
    def compare(a, b):
        left, right = tuple(map(int, a.split('.'))), tuple(map(int, b.split('.')))
        return (left > right) - (left < right)

    monkeypatch.setattr(subscription_module, 'compare_versions', compare)
    for plan in (PlanType.plus, PlanType.unlimited_v2):
        expected = plan if capable else PlanType.unlimited
        assert subscription_module.wire_plan_for_client(plan, platform, version) == expected


def test_macos_capability_floor_remains_operator_configurable(subscription_module, monkeypatch):
    from utils import plan_wire_capabilities

    monkeypatch.setattr(plan_wire_capabilities, 'MIN_MACOS_VERSION', '99.0.0')
    monkeypatch.setattr(subscription_module, 'compare_versions', lambda a, b: -1)
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'macos', '0.12.197') == PlanType.unlimited


@pytest.mark.parametrize('platform', ['ios', 'android', 'macos', 'windows', 'web'])
@pytest.mark.parametrize('plan', [PlanType.plus, PlanType.unlimited_v2])
def test_declared_safe_decoder_receives_true_plan_before_version_resolves(subscription_module, platform, plan):
    assert subscription_module.wire_plan_for_client(plan, platform, None, '1') == plan


@pytest.mark.parametrize('capability', [None, '', '0', '2', 'true'])
def test_absent_or_unrecognized_capability_keeps_old_clients_safe(subscription_module, monkeypatch, capability):
    monkeypatch.setattr(subscription_module, 'compare_versions', lambda a, b: -1)
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'ios', '1.0.0', capability) == PlanType.unlimited
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'unknown', '1.0.0', '1') == PlanType.unlimited


@pytest.mark.parametrize('plan', [PlanType.basic, PlanType.unlimited, PlanType.operator, PlanType.architect])
def test_capability_never_changes_plan_membership(subscription_module, plan):
    assert subscription_module.wire_plan_for_client(plan, 'ios', None, '1') == plan


@pytest.mark.parametrize('desktop_floor,windows_floor', [(None, None), ('0.12.197', None), ('0.12.197', '2.0.0')])
def test_windows_import_time_floor_does_not_inherit_macos(monkeypatch, desktop_floor, windows_floor):
    import importlib.util

    for name, value in [
        ('PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION', desktop_floor),
        ('PLUS_UNLIMITED_V2_MIN_WINDOWS_VERSION', windows_floor),
    ]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location('windows_floor_fixture', _BACKEND / 'utils/plan_wire_capabilities.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def compare(a, b):
        left, right = tuple(map(int, a.split('.'))), tuple(map(int, b.split('.')))
        return (left > right) - (left < right)

    assert module.MIN_WINDOWS_VERSION == (windows_floor or '99.0.0')
    assert not module.understands_plan_identity('windows', '1.0.35', None, compare)
    assert module.understands_plan_identity('macos', '0.12.197', None, compare)
    if windows_floor:
        assert module.understands_plan_identity('windows', '2.0.0', None, compare)


@pytest.mark.parametrize('interval', ['Monthly', 'Annual'])
def test_operator_wire_title_preserves_released_macos_price_ownership(subscription_module, interval):
    # Released normalizedPlanId routes titles containing "pro" to Architect.
    # Payments appends these intervals to the definition title; the old merger
    # then unions those prices into that inferred plan, even when IDs are sent.
    definition = next(d for d in subscription_module.get_paid_plan_definitions() if d['plan_id'] == 'operator')
    title = f"{definition['title']} {interval}".lower()
    assert definition['title'] == 'Operator'
    assert 'operator' in title and 'pro' not in title
    assert subscription_module.PLAN_DISPLAY_NAMES[PlanType.operator] == 'Pro'
