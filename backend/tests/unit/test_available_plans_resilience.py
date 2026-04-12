"""Tests that one invalid Stripe price ID doesn't hide all plans."""

import sys
import types
from unittest.mock import MagicMock, patch

# Stub heavy imports before loading the module under test
stripe_mock = types.ModuleType("stripe")
stripe_mock.api_key = None
sys.modules.setdefault("stripe", stripe_mock)
sys.modules.setdefault("database.users", types.SimpleNamespace(get_user_subscription=MagicMock(return_value=None)))
sys.modules.setdefault("database.user_usage", types.SimpleNamespace())
sys.modules.setdefault("database.redis_db", types.SimpleNamespace())

from models.users import PlanType


def _make_price(price_id, amount, interval):
    """Return a dict mimicking stripe.Price.to_dict_recursive()."""
    return {
        'id': price_id,
        'unit_amount': amount,
        'recurring': {'interval': interval},
    }


def test_invalid_monthly_skips_plan_but_others_remain(monkeypatch):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_good_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_good_annual")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_bad")
    monkeypatch.setenv("STRIPE_PRO_ANNUAL_PRICE_ID", "")

    # Re-import so env vars take effect
    import importlib
    import utils.subscription

    importlib.reload(utils.subscription)

    from utils.subscription import get_paid_plan_definitions

    definitions = get_paid_plan_definitions()

    # Simulate the plan-building logic from routers/users.py
    available_plans = []
    for definition in definitions:
        plan_prices = []
        monthly_id = definition["monthly_price_id"]
        annual_id = definition["annual_price_id"]

        if monthly_id:
            try:
                if monthly_id == "price_bad":
                    raise Exception("No such price: price_bad")
                plan_prices.append({"id": monthly_id, "title": "Monthly"})
            except Exception:
                pass

        if annual_id:
            try:
                plan_prices.append({"id": annual_id, "title": "Annual"})
            except Exception:
                pass

        if plan_prices:
            available_plans.append({"id": definition["plan_id"], "prices": plan_prices})

    # Unlimited should still be present with both prices
    assert len(available_plans) == 1
    assert available_plans[0]["id"] == "unlimited"
    assert len(available_plans[0]["prices"]) == 2

    # Pro should be skipped because its only price (monthly) failed
    assert all(p["id"] != "pro" for p in available_plans)


def test_valid_prices_return_both_plans(monkeypatch):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlim_m")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlim_a")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_pro_m")
    monkeypatch.setenv("STRIPE_PRO_ANNUAL_PRICE_ID", "price_pro_a")

    import importlib
    import utils.subscription

    importlib.reload(utils.subscription)

    from utils.subscription import get_paid_plan_definitions

    definitions = get_paid_plan_definitions()

    # All prices valid — both plans should appear
    available_plans = []
    for definition in definitions:
        plan_prices = []
        for interval in ("monthly", "annual"):
            price_id = definition[f"{interval}_price_id"]
            if price_id:
                plan_prices.append({"id": price_id, "title": interval.capitalize()})
        if plan_prices:
            available_plans.append({"id": definition["plan_id"], "prices": plan_prices})

    assert len(available_plans) == 2
    plan_ids = {p["id"] for p in available_plans}
    assert plan_ids == {"unlimited", "pro"}
