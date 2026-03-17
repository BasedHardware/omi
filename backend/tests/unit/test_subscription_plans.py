import sys
import types

sys.modules.setdefault("stripe", types.SimpleNamespace())
sys.modules.setdefault("database.users", types.SimpleNamespace())
sys.modules.setdefault("database.user_usage", types.SimpleNamespace())

from models.users import PlanType
from utils.subscription import get_plan_features, get_plan_limits, get_plan_type_from_price_id, is_paid_plan


def test_pro_price_ids_map_to_pro_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_pro_monthly")
    monkeypatch.setenv("STRIPE_PRO_ANNUAL_PRICE_ID", "price_pro_annual")

    assert get_plan_type_from_price_id("price_unlimited_monthly") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_unlimited_annual") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_pro_monthly") == PlanType.pro
    assert get_plan_type_from_price_id("price_pro_annual") == PlanType.pro


def test_pro_is_treated_as_paid_unlimited_plan():
    assert is_paid_plan(PlanType.pro) is True
    assert get_plan_limits(PlanType.pro).transcription_seconds is None
    assert "Automations" in get_plan_features(PlanType.pro)
    assert "Unlimited actions" in get_plan_features(PlanType.pro)
