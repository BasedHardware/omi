"""Subscription plan tests — migrated off module-scope ``sys.modules`` mutation.

``utils.subscription`` pulls in ``database.users`` at import time, which itself
imports back from ``utils.subscription`` (circular). The original test broke the
cycle by pre-corrupting ``sys.modules`` at module scope with empty stubs. This
file uses the sanctioned Tier-2 reserve seam: a module-scoped fixture that
installs the stubs via ``stub_modules`` and exec's ``utils.subscription`` fresh
with ``load_module_fresh``, then restores on teardown. See
backend/docs/test_isolation.md and testing/import_isolation.py.
"""

import os
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.users import PlanType
from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def subscription_module():
    """Load a fresh ``utils.subscription`` against stubbed circular-import deps."""
    announcements_stub = ModuleType("database.announcements")
    announcements_stub.compare_versions = lambda a, b: 0

    fakes = {
        "database.announcements": announcements_stub,
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


def test_architect_is_treated_as_paid_unlimited_plan(subscription_module):
    assert subscription_module.is_paid_plan(PlanType.architect) is True
    assert subscription_module.get_plan_limits(PlanType.architect).transcription_seconds is None
    assert "Automations and vibe coding" in subscription_module.get_plan_features(PlanType.architect)
    assert "Unlimited listening, memories, and insights" in subscription_module.get_plan_features(PlanType.architect)


def test_basic_plan_features_include_unlimited_memories(subscription_module):
    features = subscription_module.get_plan_features(PlanType.basic)
    assert "Unlimited memories" in features


def test_unlimited_transcription_plan_skips_monthly_usage_scan(monkeypatch, subscription_module):
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source: False)
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
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source: False)
    monkeypatch.setattr(subscription_module.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(subscription_module, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        subscription_module.users_db,
        'get_user_valid_subscription',
        lambda uid: SimpleNamespace(plan=PlanType.basic),
        raising=False,
    )
    monkeypatch.setattr(subscription_module, 'get_plan_limits', lambda plan: SimpleNamespace(transcription_seconds=60))
    monthly_usage = MagicMock(return_value={'transcription_seconds': 60})
    monkeypatch.setattr(subscription_module, 'get_monthly_usage_for_subscription', monthly_usage)

    assert subscription_module.has_transcription_credits('uid') is False
    monthly_usage.assert_called_once_with('uid')


def _stub_remaining_deps(monkeypatch, subscription_module, plan, used_seconds):
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda uid, source=None: False)
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
