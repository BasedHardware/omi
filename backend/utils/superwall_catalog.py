"""Mobile catalog + subscription-source predicates used by the payment router.

Lives outside ``routers/payment.py`` so the helpers can be imported (and unit-
tested) without dragging in the router's heavy deps (Stripe, opus, fair-use,
notifications, etc.).
"""

from typing import List, Optional

from models.users import PlanType, Subscription, SubscriptionSource, SubscriptionStatus

# Local constant rather than importing ``utils.subscription.PAID_PLAN_TYPES`` —
# avoids a circular import (utils.subscription imports database.users, which
# imports back from utils.subscription). The set must mirror the legacy +
# mobile paid plans defined in ``utils.subscription``.
_PAID_PLAN_VALUES = {"unlimited", "architect", "operator", "lite", "plus", "unlimited_v2"}


# Mobile-only Superwall tiers — display fallback for clients that fetch the
# ``/v1/payments/available-plans`` endpoint. The actual paywall is rendered
# by the Superwall SDK via ``Superwall.shared.registerPlacement('upgrade')``,
# so these IDs are App Store / Play product IDs (matching
# ``app_config/plan_caps.superwall_product_map``) and prices are static; the
# Superwall dashboard remains the source of truth for what users see at
# purchase time.
_MOBILE_PLAN_DEFINITIONS = [
    {
        "plan_id": "lite",
        "title": "Lite",
        "subtitle": "1,500 listening minutes / 100 messages per month",
        "monthly": ("com.omi.app.lite_monthly", 999, "$9.99/mo"),
        "annual": ("com.omi.app.lite_yearly", 7999, "$6.67/mo"),
        "annual_description": "Save 33% with annual billing.",
        "eyebrow": "Starter",
    },
    {
        "plan_id": "plus",
        "title": "Plus",
        "subtitle": "4,000 listening minutes / 300 messages per month",
        "monthly": ("com.omi.app.plus_monthly", 2999, "$29.99/mo"),
        "annual": ("com.omi.app.plus_yearly", 19999, "$16.67/mo"),
        "annual_description": "Save 44% with annual billing.",
        "eyebrow": "Most popular",
    },
    {
        "plan_id": "unlimited_v2",
        "title": "Unlimited",
        "subtitle": "Unlimited listening + chat",
        "monthly": ("com.omi.app.unlimited_v2_monthly", 4999, "$49.99/mo"),
        "annual": ("com.omi.app.unlimited_v2_yearly", 29999, "$25.00/mo"),
        "annual_description": "Save 50% with annual billing.",
        "eyebrow": "Power user",
    },
]


def is_mobile_platform(platform: Optional[str]) -> bool:
    return (platform or '').lower() in ('ios', 'android')


def has_active_legacy_stripe_sub(subscription: Optional[Subscription]) -> bool:
    """A legacy Stripe sub: source is ``stripe``, status active, plan is paid.

    Per Q3=C such users keep seeing their current plan + Manage button and are
    NOT shown the new Lite/Plus/Max catalog until they cancel.
    """
    if not subscription:
        return False
    if subscription.source != SubscriptionSource.stripe:
        return False
    if subscription.status != SubscriptionStatus.active:
        return False
    return subscription.plan.value in _PAID_PLAN_VALUES


def has_active_superwall_sub(subscription: Optional[Subscription]) -> bool:
    if not subscription:
        return False
    if subscription.source not in (SubscriptionSource.superwall_ios, SubscriptionSource.superwall_android):
        return False
    return subscription.status == SubscriptionStatus.active


def build_mobile_plan_catalog(current_plan: PlanType) -> List[dict]:
    """Static Lite/Plus/Max display catalog. Returned as a list of dicts so the
    router layer can shape them into its own ``PricingOption`` model without
    this module importing it (avoids a router→utils→router cycle).
    """
    out: List[dict] = []
    for d in _MOBILE_PLAN_DEFINITIONS:
        plan_active = current_plan.value == d["plan_id"]
        m_id, m_amount, m_str = d["monthly"]
        a_id, a_amount, a_str = d["annual"]
        out.append(
            {
                "id": m_id,
                "plan_id": d["plan_id"],
                "title": f'{d["title"]} Monthly',
                "price_string": m_str,
                "description": None,
                "subtitle": d["subtitle"],
                "eyebrow": d["eyebrow"],
                "interval": "month",
                "unit_amount": m_amount,
                "is_active": plan_active,
            }
        )
        out.append(
            {
                "id": a_id,
                "plan_id": d["plan_id"],
                "title": f'{d["title"]} Annual',
                "price_string": a_str,
                "description": d["annual_description"],
                "subtitle": d["subtitle"],
                "eyebrow": d["eyebrow"],
                "interval": "year",
                "unit_amount": a_amount,
                "is_active": plan_active,
            }
        )
    return out
