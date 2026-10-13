import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
from testing.import_isolation import load_module_fresh, stub_modules
from config.plan_catalog import (
    RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
    get_plan_definition,
    resolve_stripe_price_plan,
    plan_uses_overage,
    DESKTOP_PROFILE_DEFAULTS,
    FAIR_USE_PROFILE_LIMITS,
    PHONE_CALL_PROFILE_DEFAULTS,
)
from models.users import Subscription


def legacy_snapshot():
    client = ModuleType('database._client')
    client.get_customer_firestore_client = MagicMock()
    announcements = ModuleType('database.announcements')
    announcements.compare_versions = MagicMock()
    fakes = {
        'database._client': client,
        'database.users': SimpleNamespace(),
        'database.user_usage': SimpleNamespace(),
        'database.announcements': announcements,
    }
    with stub_modules(fakes):
        sub = load_module_fresh(
            'utils.subscription',
            Path(__import__('config.plan_catalog', fromlist=['x']).__file__).parents[1] / 'utils/subscription.py',
        )
        result = {}
        for price in sorted(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES):
            plan = resolve_stripe_price_plan(price, {})
            result[price] = {
                'definition': get_plan_definition(plan),
                'limits': sub.get_plan_limits(plan).model_dump(),
                'features': sub.get_plan_features(plan),
                'simplified_features': sub.get_plan_features(plan, simplified=True),
                'overage': plan_uses_overage(plan),
                'desktop_cases': [
                    {
                        'period_start': start,
                        'tier': sub.effective_desktop_access_tier(
                            plan, Subscription(plan=plan, current_period_start=start)
                        ),
                        'paywall_eligible': sub.desktop_trial_paywall_eligible(
                            plan, Subscription(plan=plan, current_period_start=start)
                        ),
                    }
                    for start in (None, 1, 2000000000)
                ],
                'desktop_profiles': DESKTOP_PROFILE_DEFAULTS,
                'fair_use_profiles': FAIR_USE_PROFILE_LIMITS,
                'phone_call_profiles': PHONE_CALL_PROFILE_DEFAULTS,
            }
        return result
