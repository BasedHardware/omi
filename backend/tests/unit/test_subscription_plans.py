import importlib
import sys
import types

import pytest

_announcements_mod = types.ModuleType("database.announcements")
_announcements_mod.compare_versions = lambda a, b: 0
sys.modules.setdefault("database.announcements", _announcements_mod)
sys.modules.setdefault("database.users", types.SimpleNamespace())
sys.modules.setdefault("database.user_usage", types.SimpleNamespace())

from models.users import PlanType

_MISSING = object()


@pytest.fixture
def subscription_module():
    previous_module = sys.modules.pop("utils.subscription", _MISSING)
    utils_package = sys.modules.get("utils")
    previous_attr = getattr(utils_package, "subscription", _MISSING) if utils_package is not None else _MISSING

    if utils_package is not None and hasattr(utils_package, "subscription"):
        delattr(utils_package, "subscription")

    try:
        module = importlib.import_module("utils.subscription")
        yield module
    finally:
        sys.modules.pop("utils.subscription", None)
        if previous_module is not _MISSING:
            sys.modules["utils.subscription"] = previous_module

        current_utils_package = sys.modules.get("utils")
        if current_utils_package is not None:
            if previous_attr is _MISSING:
                if hasattr(current_utils_package, "subscription"):
                    delattr(current_utils_package, "subscription")
            else:
                current_utils_package.subscription = previous_attr


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
