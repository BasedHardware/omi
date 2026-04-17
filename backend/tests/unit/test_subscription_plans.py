import sys
import types

sys.modules.setdefault("database.users", types.SimpleNamespace())
sys.modules.setdefault("database.user_usage", types.SimpleNamespace())

from models.users import PlanType
from utils.subscription import get_plan_features, get_plan_limits, get_plan_type_from_price_id, is_paid_plan


def test_architect_price_ids_map_to_architect_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")
    monkeypatch.setenv("STRIPE_ARCHITECT_MONTHLY_PRICE_ID", "price_architect_monthly")
    monkeypatch.setenv("STRIPE_ARCHITECT_ANNUAL_PRICE_ID", "price_architect_annual")

    assert get_plan_type_from_price_id("price_unlimited_monthly") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_unlimited_annual") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_architect_monthly") == PlanType.architect
    assert get_plan_type_from_price_id("price_architect_annual") == PlanType.architect


def test_architect_is_treated_as_paid_unlimited_plan():
    assert is_paid_plan(PlanType.architect) is True
    assert get_plan_limits(PlanType.architect).transcription_seconds is None
    assert "Automations and vibe coding" in get_plan_features(PlanType.architect)
    assert "Unlimited listening, memories, and insights" in get_plan_features(PlanType.architect)
