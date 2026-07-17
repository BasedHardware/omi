"""Tests for subscription restructure: Basic + Operator ($49) + Architect ($400),
deprecate Unlimited for existing users. Issue #6734.

``utils.subscription`` pulls in ``database.users`` / ``database.user_usage`` at import
time, and ``database.users`` imports back from ``utils.subscription`` (circular). The
original test broke the cycle by pre-corrupting ``sys.modules`` at module scope with
empty stubs. This file uses the sanctioned Tier-2 reserve seam: a module-scoped
fixture exposing a context manager that installs the stubs via ``stub_modules`` and
exec's ``utils.subscription`` fresh with ``load_module_fresh`` each time, then
restores on exit. No ``importlib.reload`` and no reliance on a specific
``utils.subscription`` object identity surviving across tests. See
backend/docs/test_isolation.md and testing/import_isolation.py.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from models.users import PlanLimits, PlanType, Subscription
from testing.import_isolation import load_module_fresh, stub_modules

pytestmark = pytest.mark.slow

_BACKEND = Path(__file__).resolve().parents[2]
_SUBSCRIPTION_PATH = os.path.join(str(_BACKEND), "utils", "subscription.py")


def _compare_versions(a, b):
    """Semantic version comparison matching the real _compare_versions."""
    a_parts = [int(x) for x in a.split('.')]
    b_parts = [int(x) for x in b.split('.')]
    for x, y in zip(a_parts, b_parts):
        if x != y:
            return 1 if x > y else -1
    return len(a_parts) - len(b_parts)


def _circular_import_fakes():
    """Stubs for the circular-import deps of utils.subscription."""
    announcements = ModuleType("database.announcements")
    announcements._compare_versions = _compare_versions
    # subscription.py imports the public name `compare_versions`; expose it on the
    # stub so the fresh exec resolves without the real database.announcements.
    announcements.compare_versions = _compare_versions
    return {
        "database.users": SimpleNamespace(),
        "database.user_usage": SimpleNamespace(),
        "database.announcements": announcements,
    }


@pytest.fixture(scope="module")
def load_subscription():
    """Return a context manager that loads ``utils.subscription`` fresh.

    Each invocation re-installs the circular-import stubs (via ``stub_modules``) and
    re-execs ``utils.subscription`` so env-var-driven module constants are read
    against the current environment. Nothing relies on a specific module object
    surviving in ``sys.modules`` across tests, which keeps the file safe in a
    multi-file pytest run.
    """

    @contextmanager
    def _loader():
        with stub_modules(_circular_import_fakes()):
            yield load_module_fresh("utils.subscription", _SUBSCRIPTION_PATH)

    return _loader


def test_operator_chat_cap_independent_from_unlimited(monkeypatch, load_subscription):
    """F4: Operator and Unlimited chat caps must be independently configurable."""
    monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "750")
    monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "3000")

    with load_subscription() as sub_mod:
        operator_limits = sub_mod.get_plan_limits(PlanType.operator)
        unlimited_limits = sub_mod.get_plan_limits(PlanType.unlimited)

    assert operator_limits.chat_questions_per_month == 750
    assert unlimited_limits.chat_questions_per_month == 3000
    assert operator_limits.chat_questions_per_month != unlimited_limits.chat_questions_per_month


def test_operator_and_neo_defaults(monkeypatch, load_subscription):
    """Operator defaults to 500, Neo defaults to 200."""
    monkeypatch.delenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", raising=False)
    monkeypatch.delenv("NEO_CHAT_QUESTIONS_PER_MONTH", raising=False)

    with load_subscription() as sub_mod:
        operator_limits = sub_mod.get_plan_limits(PlanType.operator)
        unlimited_limits = sub_mod.get_plan_limits(PlanType.unlimited)

    assert operator_limits.chat_questions_per_month == 500
    assert unlimited_limits.chat_questions_per_month == 200


def test_architect_uses_dollar_cap(load_subscription):
    """Architect plan uses dollar cap, not question count."""
    with load_subscription() as sub_mod:
        limits = sub_mod.get_plan_limits(PlanType.architect)

    assert limits.chat_cost_usd_per_month is not None
    assert limits.chat_questions_per_month is None
    assert limits.transcription_seconds is None  # unlimited transcription


def test_operator_is_paid(load_subscription):
    with load_subscription() as sub_mod:
        assert sub_mod.is_paid_plan(PlanType.operator)
        assert sub_mod.is_paid_plan(PlanType.architect)
        assert sub_mod.is_paid_plan(PlanType.unlimited)
        assert not sub_mod.is_paid_plan(PlanType.basic)


def test_filter_plans_for_basic_user(load_subscription):
    """Basic users see Neo, Operator, and Architect in purchase catalog."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic)

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_filter_plans_keeps_legacy_for_current_subscriber(load_subscription):
    """Unlimited subscribers see their plan in catalog for active-plan detection."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited)

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_filter_plans_mobile_new_user_sees_only_plus_max(load_subscription):
    """New / never-paid mobile users see only the consumer tiers Plus + Max.

    Neo (unlimited) is deprecated, and Operator + Architect are desktop-only, so
    all three are hidden from the mobile purchase catalog.
    """
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android'):
            filtered = sub_mod.filter_plans_for_user(
                definitions, PlanType.basic, platform=platform, ever_purchased=False
            )
            plan_ids = [d['plan_id'] for d in filtered]
            assert plan_ids == ['plus', 'max'], (platform, plan_ids)


def test_filter_plans_desktop_hides_mobile_tiers(load_subscription):
    """Desktop sells Operator + Architect; Plus/Max/Neo are hidden there."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='macos')
        plan_ids = [d['plan_id'] for d in filtered]
        assert plan_ids == ['operator', 'architect'], plan_ids


def test_filter_plans_shows_neo_on_mobile_for_past_purchaser(load_subscription):
    """Mobile users who have bought a plan before still see Neo (resubscribe)."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='ios', ever_purchased=True)

    assert 'unlimited' in [d['plan_id'] for d in filtered]


def test_filter_plans_shows_neo_on_mobile_for_current_neo_subscriber(load_subscription):
    """Current Neo subscribers always see Neo even without ever_purchased flag."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(
            definitions, PlanType.unlimited, platform='android', ever_purchased=False
        )

    assert 'unlimited' in [d['plan_id'] for d in filtered]


def test_filter_plans_keeps_neo_on_web_for_new_user(load_subscription):
    """Web / unknown platform is unaffected — Neo stays in the catalog."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=None, ever_purchased=False)

    assert 'unlimited' in [d['plan_id'] for d in filtered]


def test_filter_plans_hides_neo_on_windows_for_new_user(load_subscription):
    """New / never-paid Windows desktop users don't see Neo — same as macOS desktop.

    Regression for the platform defect: _platform_hidden_plans only hid Neo for
    'macos', so a Windows client would have been offered the deprecated Neo plan.
    """
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='windows', ever_purchased=False)
    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' not in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_windows_full_catalog_matches_macos_canonical(load_subscription):
    """End-to-end catalog resolution for a Windows client (X-App-Platform: windows).

    Pins the fix: a Windows client gets the SAME catalog macOS gets — Operator +
    Architect visible under their canonical titles, Neo hidden from a new basic
    desktop user — and NEVER the legacy 'Omi Pro' / 'Unlimited Plan' rename that
    adapt_plans_for_legacy_client produces for pre-rollout clients.
    """
    with load_subscription() as sub_mod:
        # Windows is a modern desktop client → new catalog, no legacy adaptation.
        assert sub_mod.should_show_new_plans('windows', '0.1.0') is True
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='windows', ever_purchased=False)
    by_id = {d['plan_id']: d for d in filtered}
    assert 'operator' in by_id
    assert 'architect' in by_id
    assert 'unlimited' not in by_id  # Neo hidden on desktop for a new user
    assert by_id['operator']['title'] == 'Operator'
    assert by_id['architect']['title'] == 'Architect'
    titles = [d['title'] for d in filtered]
    assert 'Omi Pro' not in titles
    assert 'Unlimited Plan' not in titles


def test_windows_is_a_desktop_platform(load_subscription):
    """Windows lives in the single-source-of-truth desktop platform set and tokens."""
    with load_subscription() as sub_mod:
        assert 'windows' in sub_mod.DESKTOP_PLATFORMS
        assert 'macos' in sub_mod.DESKTOP_PLATFORMS
        assert 'windows' in sub_mod._TRIAL_PAYWALL_DESKTOP_TOKENS
        assert 'desktop' in sub_mod._TRIAL_PAYWALL_DESKTOP_TOKENS
        # Mobile is never desktop.
        assert 'ios' not in sub_mod.DESKTOP_PLATFORMS
        assert 'android' not in sub_mod.DESKTOP_PLATFORMS


def test_has_ever_purchased_signals(monkeypatch, load_subscription):
    """Paid plan, stored stripe sub id, or a stripe customer id each count as purchased."""
    with load_subscription() as sub_mod:
        monkeypatch.setattr(sub_mod.users_db, 'get_stripe_customer_id', lambda uid: None, raising=False)

        paid = Subscription(plan=PlanType.operator, limits=PlanLimits())
        assert sub_mod.has_ever_purchased('u', paid)

        lapsed = Subscription(plan=PlanType.basic, stripe_subscription_id='sub_123', limits=PlanLimits())
        assert sub_mod.has_ever_purchased('u', lapsed)

        new_user = Subscription(plan=PlanType.basic, limits=PlanLimits())
        assert not sub_mod.has_ever_purchased('u', new_user)

        # No cheap signal on the subscription, but a stored Stripe customer id exists.
        monkeypatch.setattr(sub_mod.users_db, 'get_stripe_customer_id', lambda uid: 'cus_123', raising=False)
        assert sub_mod.has_ever_purchased('u', new_user)


def test_legacy_client_adaptation(load_subscription):
    """Old clients see Unlimited Plan (not legacy suffix) and no Operator."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        adapted = sub_mod.adapt_plans_for_legacy_client(definitions)

    plan_ids = [d['plan_id'] for d in adapted]
    assert 'operator' not in plan_ids
    assert 'unlimited' in plan_ids
    assert 'architect' in plan_ids

    unlimited_def = next(d for d in adapted if d['plan_id'] == 'unlimited')
    assert unlimited_def['title'] == 'Unlimited Plan'
    assert unlimited_def['legacy'] is False  # old clients don't know about legacy flag

    architect_def = next(d for d in adapted if d['plan_id'] == 'architect')
    assert architect_def['title'] == 'Omi Pro'


def test_version_gating_macos_always_new(load_subscription):
    """macOS always gets new plans (no version header = True)."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('macos', None) is True
        assert sub_mod.should_show_new_plans('macos', '99.99.999') is True


def test_version_gating_windows_always_new(load_subscription):
    """Windows is a desktop platform: always gets the new Operator + Architect catalog.

    Regression for the platform-recognition defect where only 'macos' was treated
    as desktop, so Windows (X-App-Platform: windows) fell through to the legacy
    catalog — hiding Operator and renaming Architect→'Omi Pro'. Windows defaults
    permissive (pre-release), so every version and a missing version qualify.
    """
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('windows', None) is True
        assert sub_mod.should_show_new_plans('windows', '1.0.0') is True
        assert sub_mod.should_show_new_plans('windows', '0.0.1') is True
        assert sub_mod.should_show_new_plans('windows', '99.99.999') is True
        # Case-insensitive, matching the macOS/mobile branches.
        assert sub_mod.should_show_new_plans('Windows', '1.0.0') is True
        # Unparseable version fails open on desktop (same as macOS).
        assert sub_mod.should_show_new_plans('windows', 'not.a.version') is True


def test_version_gating_mobile_requires_version(load_subscription):
    """Mobile requires version header and must meet minimum."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('android', None) is False
        assert sub_mod.should_show_new_plans('ios', None) is False

        assert sub_mod.should_show_new_plans('android', '99.99.999') is True
        assert sub_mod.should_show_new_plans('ios', '99.99.999') is True


def test_version_gating_old_mobile_gets_legacy(load_subscription):
    """Old mobile builds get legacy catalog."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('android', '0.0.1') is False
        assert sub_mod.should_show_new_plans('ios', '0.0.1') is False


def test_version_gating_exact_threshold(load_subscription):
    """Exact threshold version gets new plans."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('android', '1.0.530') is True
        assert sub_mod.should_show_new_plans('ios', '1.0.530') is True
        assert sub_mod.should_show_new_plans('macos', '0.11.324') is True


def test_version_gating_just_below_threshold(load_subscription):
    """One version below threshold gets legacy."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('android', '1.0.529') is False
        assert sub_mod.should_show_new_plans('ios', '1.0.529') is False
        assert sub_mod.should_show_new_plans('macos', '0.11.323') is False


def test_version_gating_malformed_version(load_subscription):
    """Malformed version: macOS fail-open, mobile fail-closed."""
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans('macos', 'not.a.version') is True
        assert sub_mod.should_show_new_plans('android', 'not.a.version') is False
        assert sub_mod.should_show_new_plans('ios', 'not.a.version') is False


def test_version_gating_unknown_platform(load_subscription):
    """Unknown / unrecognized platform gets legacy catalog.

    'linux' is not a shipping desktop plan platform, so it stays on the legacy
    catalog (see DESKTOP_PLATFORMS — only macOS and Windows are wired for plans).
    """
    with load_subscription() as sub_mod:
        assert sub_mod.should_show_new_plans(None, None) is False
        assert sub_mod.should_show_new_plans('linux', '1.0.0') is False
        assert sub_mod.should_show_new_plans('web', '1.0.0') is False


def test_subscription_deprecation_fields():
    """Subscription model supports deprecated + deprecation_message."""
    sub = Subscription(plan=PlanType.unlimited, deprecated=True, deprecation_message="Your plan is retiring.")

    assert sub.deprecated is True
    assert sub.deprecation_message == "Your plan is retiring."

    # Non-deprecated plan
    sub2 = Subscription(plan=PlanType.operator)
    assert sub2.deprecated is False
    assert sub2.deprecation_message is None


def test_operator_price_id_mapping(monkeypatch, load_subscription):
    """Operator price IDs resolve to operator plan type."""
    monkeypatch.setenv("STRIPE_OPERATOR_MONTHLY_PRICE_ID", "price_op_monthly")
    monkeypatch.setenv("STRIPE_OPERATOR_ANNUAL_PRICE_ID", "price_op_annual")

    with load_subscription() as sub_mod:
        assert sub_mod.get_plan_type_from_price_id("price_op_monthly") == PlanType.operator
        assert sub_mod.get_plan_type_from_price_id("price_op_annual") == PlanType.operator


def test_plan_features_differentiate_operator_neo(monkeypatch, load_subscription):
    """Operator and Neo show separate feature lists with their own caps."""
    monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "600")
    monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "300")

    with load_subscription() as sub_mod:
        op_features = sub_mod.get_plan_features(PlanType.operator)
        neo_features = sub_mod.get_plan_features(PlanType.unlimited)

    assert "600 chat questions per month" in op_features
    assert "300 chat questions per month" in neo_features
    assert "Desktop capture with Free-tier allowance" in neo_features
    assert "No desktop access" not in neo_features


def test_plan_display_names(load_subscription):
    with load_subscription() as sub_mod:
        assert sub_mod.get_plan_display_name(PlanType.basic) == 'Free'
        assert sub_mod.get_plan_display_name(PlanType.operator) == 'Operator'
        assert sub_mod.get_plan_display_name(PlanType.architect) == 'Architect'
        assert sub_mod.get_plan_display_name(PlanType.unlimited) == 'Neo'
