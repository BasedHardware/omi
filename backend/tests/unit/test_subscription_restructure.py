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
from unittest.mock import MagicMock

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
    client = ModuleType("database._client")
    client.get_customer_firestore_client = MagicMock()
    return {
        "database._client": client,
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

    with stub_modules(_circular_import_fakes()):
        # Warm imports in fixture setup. Keep the fakes for the whole module so
        # repeated loads neither re-register protobuf descriptors nor re-import
        # the heavy dependency graph during each test's call phase.
        load_module_fresh("utils.subscription", _SUBSCRIPTION_PATH)

        @contextmanager
        def _loader():
            yield load_module_fresh("utils.subscription", _SUBSCRIPTION_PATH)

        yield _loader


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


def test_filter_plans_for_basic_user(load_subscription, monkeypatch):
    """A basic buyer with no platform header keeps the pre-ruling catalog.

    Desktop compatibility outranks closing the header-less direct-API gap: a
    missing or unknown platform is not restricted (the restriction follows the
    explicit first-party values — see the mobile/web tests below).
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic)
        plan_ids = [d['plan_id'] for d in filtered]
        assert 'operator' in plan_ids
        assert 'architect' in plan_ids


def test_filter_plans_keeps_legacy_for_current_subscriber(load_subscription, monkeypatch):
    """Unlimited subscribers see their plan in catalog for active-plan detection."""
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited)

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_filter_plans_mobile_new_user_sees_only_unlimited_v2(load_subscription, monkeypatch):
    """New / never-paid mobile users see only Omi Pro (unlimited_v2).

    2026-10-24 ruling. Neo (unlimited) is deprecated, Operator + Architect are
    desktop-only, and Plus is no longer sold to new buyers on mobile. The kill
    switch restores the two-tier mobile catalog.
    """
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android'):
            filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=platform)
            plan_ids = [d['plan_id'] for d in filtered]
            assert plan_ids == ['unlimited_v2'], (platform, plan_ids)

    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android'):
            filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=platform)
            plan_ids = [d['plan_id'] for d in filtered]
            assert plan_ids == ['plus', 'unlimited_v2'], (platform, plan_ids)


def test_filter_plans_desktop_hides_mobile_tiers(load_subscription, monkeypatch):
    """Desktop sells Operator + Architect; Plus/Unlimited/Neo are hidden there."""
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='macos')
        plan_ids = [d['plan_id'] for d in filtered]
        assert plan_ids == ['operator', 'architect'], plan_ids


def test_filter_plans_hides_neo_on_mobile_for_non_neo_subscribers(load_subscription, monkeypatch):
    """Neo is current-Neo only. Architect/Plus/Unlimited/basic must not see it.

    Regression: `ever_purchased` was any paid plan, so Architect subscribers
    saw Neo on the phone sheet next to cheaper Plus. Do not restore that leak.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for plan in (PlanType.basic, PlanType.plus):
            filtered = sub_mod.filter_plans_for_user(definitions, plan, platform='ios')
            plan_ids = [d['plan_id'] for d in filtered]
            assert 'unlimited' not in plan_ids, (plan, plan_ids)
            assert plan_ids == ['plus', 'unlimited_v2'], (plan, plan_ids)
        # Omi Pro grants desktop, so it is manage-only on mobile like Operator/Architect.
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited_v2, platform='ios')
        assert [d['plan_id'] for d in filtered] == ['unlimited_v2']


def test_filter_plans_mobile_desktop_plans_are_manage_only(load_subscription, monkeypatch):
    """Operator/Architect on iOS/Android see only their current plan.

    Cheaper mobile SKUs must not appear: Continue onto them is an immediate
    prorated swap that strips desktop. Desktop/web keep the full desktop catalog.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android'):
            architect = [
                d['plan_id'] for d in sub_mod.filter_plans_for_user(definitions, PlanType.architect, platform=platform)
            ]
            operator = [
                d['plan_id'] for d in sub_mod.filter_plans_for_user(definitions, PlanType.operator, platform=platform)
            ]
            assert architect == ['architect'], (platform, architect)
            assert operator == ['operator'], (platform, operator)

        desktop = [
            d['plan_id'] for d in sub_mod.filter_plans_for_user(definitions, PlanType.architect, platform='macos')
        ]
        assert desktop == ['operator', 'architect'], desktop


def test_filter_plans_shows_neo_on_mobile_for_current_neo_subscriber(load_subscription, monkeypatch):
    """Current Neo subscribers (including cancel-at-period-end) still see Neo to manage it.

    Plus + Unlimited stay visible so they can migrate off the deprecated SKU.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited, platform='android')

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' in plan_ids
    assert 'plus' in plan_ids
    assert 'unlimited_v2' in plan_ids
    assert 'architect' not in plan_ids
    assert 'operator' not in plan_ids


def test_filter_plans_hides_neo_on_web_for_new_user(load_subscription, monkeypatch):
    """Web new buyers get the single-plan catalog; Neo stays hidden either way.

    2026-10-24 ruling: a basic web caller is offered only Omi Pro. With the
    kill switch off, web again sells the full new catalog (Plus + Unlimited +
    Operator + Architect) — deprecated Neo stays hidden for new users in both
    shapes (regression: web previously hid nothing, offering Neo for purchase).
    """
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='web')
    plan_ids = [d['plan_id'] for d in filtered]
    assert plan_ids == ['unlimited_v2'], plan_ids

    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='web')
    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' not in plan_ids  # Neo hidden
    assert 'plus' in plan_ids
    assert 'unlimited_v2' in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_filter_plans_shows_neo_on_web_for_current_neo_subscriber(load_subscription):
    """Existing Neo subscribers still see Neo on web so they can manage/cancel."""
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited, platform='web')
    assert 'unlimited' in [d['plan_id'] for d in filtered]


def test_filter_plans_keeps_neo_for_unknown_platform(load_subscription, monkeypatch):
    """Unknown/missing platform keeps the pre-ruling catalog entirely.

    The single-plan restriction follows the explicit first-party platform
    values (ios/android/web); a header-less or unrecognized caller is not
    restricted, so the current-Neo escape and the unfiltered new-buyer catalog
    both keep working for desktop compatibility.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=None)
        assert 'unlimited' in [d['plan_id'] for d in filtered]
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.unlimited, platform=None)
        assert 'unlimited' in [d['plan_id'] for d in filtered]


def test_filter_plans_hides_neo_on_windows_for_new_user(load_subscription, monkeypatch):
    """New / never-paid Windows desktop users don't see Neo — same as macOS desktop.

    Regression for the platform defect: _platform_hidden_plans only hid Neo for
    'macos', so a Windows client would have been offered the deprecated Neo plan.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='windows')
    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' not in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_neo_hidden_from_purchase_on_every_client_platform(load_subscription):
    """Reusable guard: the deprecated Neo plan is never offered for purchase to a
    new user on ANY real client platform.

    Twice now a platform was omitted from the Neo-hidden set and started offering
    Neo: first Windows (only 'macos' was hidden), then web (hid nothing). This
    pins the invariant across every X-App-Platform a client actually sends, so the
    next platform added can't silently reintroduce the deprecated-plan-for-sale bug.
    """
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android', 'macos', 'windows', 'web'):
            filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=platform)
            plan_ids = [d['plan_id'] for d in filtered]
            assert 'unlimited' not in plan_ids, (platform, plan_ids)
            assert plan_ids, platform  # never an empty catalog


def test_windows_full_catalog_matches_macos_canonical(load_subscription, monkeypatch):
    """End-to-end catalog resolution for a Windows client (X-App-Platform: windows).

    Pins the fix: a Windows client gets the SAME catalog macOS gets — Operator +
    Architect visible under their compatible wire titles, Neo hidden from a new basic
    desktop user — and NEVER the legacy 'Omi Pro' / 'Unlimited Plan' rename that
    adapt_plans_for_legacy_client produces for pre-rollout clients.
    """
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')  # per-platform catalog (kill switch)
    with load_subscription() as sub_mod:
        # Windows is a modern desktop client → new catalog, no legacy adaptation.
        assert sub_mod.should_show_new_plans('windows', '0.1.0') is True
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='windows')
    by_id = {d['plan_id']: d for d in filtered}
    assert 'operator' in by_id
    assert 'architect' in by_id
    assert 'unlimited' not in by_id  # Neo hidden on desktop for a new user
    assert by_id['operator']['title'] == 'Operator'
    assert by_id['architect']['title'] == 'Architect'
    titles = [d['title'] for d in filtered]
    assert 'Omi Pro' not in titles
    assert 'Unlimited Plan' not in titles


def test_omi_pro_is_the_only_plan_sold_on_every_platform(load_subscription, monkeypatch):
    """Default catalog: Omi Pro only; a retired-plan subscriber also sees their own plan."""
    monkeypatch.delenv('NEW_BUYER_SINGLE_PLAN_ENABLED', raising=False)
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        for platform in ('ios', 'android', 'web', 'macos', 'windows', 'not-a-platform', None):
            ids = {d['plan_id'] for d in sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform=platform)}
            assert ids == {'unlimited_v2'}, platform
            for current in (PlanType.plus, PlanType.operator, PlanType.architect, PlanType.unlimited):
                ids = {d['plan_id'] for d in sub_mod.filter_plans_for_user(definitions, current, platform=platform)}
                assert ids == {'unlimited_v2', current.value}, (platform, current)


def test_omi_pro_grants_full_desktop(load_subscription):
    with load_subscription() as sub_mod:
        assert PlanType.unlimited_v2 in sub_mod.DESKTOP_ENTITLED_PLAN_TYPES
        assert sub_mod.plan_grants_desktop(PlanType.unlimited_v2)
        assert sub_mod.effective_desktop_access_tier(PlanType.unlimited_v2) == sub_mod.DESKTOP_ACCESS_TIER_FULL


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


def test_desktop_to_consumer_plan_change_is_blocked(load_subscription):
    """Architect/Operator cannot swap onto Plus/Neo. Omi Pro and Operator ↔ Architect stay open."""
    with load_subscription() as sub_mod:
        err = sub_mod.desktop_to_consumer_plan_change_error
        for current in (PlanType.architect, PlanType.operator):
            for target in (PlanType.plus, PlanType.unlimited, PlanType.basic):
                assert err(current, target), (current, target)
            assert err(current, PlanType.unlimited_v2) is None  # Omi Pro grants full desktop
        assert err(PlanType.architect, PlanType.operator) is None
        assert err(PlanType.operator, PlanType.architect) is None
        assert err(PlanType.plus, PlanType.unlimited_v2) is None
        assert err(PlanType.unlimited, PlanType.plus) is None


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


def test_version_gating_web_always_new(load_subscription):
    """Web is an always-latest client: always gets the new catalog, version-agnostic."""
    with load_subscription() as sub_mod:
        assert 'web' in sub_mod.WEB_PLATFORMS
        assert sub_mod.should_show_new_plans('web', None) is True
        assert sub_mod.should_show_new_plans('web', '0.0.1') is True
        assert sub_mod.should_show_new_plans('web', '99.99.999') is True
        assert sub_mod.should_show_new_plans('Web', '1.0.0') is True  # case-insensitive


def test_web_full_catalog_shows_new_plans_and_hides_neo(load_subscription, monkeypatch):
    """End-to-end catalog resolution for a web client (X-App-Platform: web).

    2026-10-24 ruling: a new web buyer gets the single-plan catalog (Omi Pro
    only) under canonical titles — never the legacy 'Omi Pro' / 'Unlimited
    Plan' rename, and never deprecated Neo. With the kill switch off, web again
    renders the full new catalog: Plus + Unlimited (mobile tiers) AND Operator
    + Architect (desktop tiers), still Neo-free.
    """
    with load_subscription() as sub_mod:
        new_plans_enabled = sub_mod.should_show_new_plans('web', None)
        assert new_plans_enabled is True
        definitions = sub_mod.get_paid_plan_definitions()
        # No legacy adaptation for web (new_plans_enabled) → raw canonical catalog.
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='web')
    by_id = {d['plan_id']: d for d in filtered}
    assert set(by_id) == {'unlimited_v2'}, by_id
    assert 'unlimited' not in by_id  # Neo hidden
    assert by_id['unlimited_v2']['title'] == 'Unlimited'
    titles = [d['title'] for d in filtered]
    assert 'Omi Pro' not in titles
    assert 'Unlimited Plan' not in titles

    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    with load_subscription() as sub_mod:
        definitions = sub_mod.get_paid_plan_definitions()
        filtered = sub_mod.filter_plans_for_user(definitions, PlanType.basic, platform='web')
    by_id = {d['plan_id']: d for d in filtered}
    assert set(by_id) == {'plus', 'unlimited_v2', 'operator', 'architect'}, by_id
    assert 'unlimited' not in by_id  # Neo hidden
    assert by_id['operator']['title'] == 'Operator'
    assert by_id['architect']['title'] == 'Architect'


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
        # 'web' is NOT unknown: it is an always-latest client that always gets
        # the new catalog (see test_version_gating_web_always_new).


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
        assert sub_mod.get_plan_display_name(PlanType.operator) == 'Pro'
        assert sub_mod.get_plan_display_name(PlanType.architect) == 'Architect'
        assert sub_mod.get_plan_display_name(PlanType.unlimited) == 'Neo'
