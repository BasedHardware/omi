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
