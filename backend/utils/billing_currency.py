"""Same-currency offers for managing an existing personal subscription.

The retained recognition ledger is not a purchase catalog. Only explicit
management bindings in the plan catalog may supplement the configured prices;
new Checkout cannot use these management targets. Stripe owns amounts.
"""

import stripe

from config.plan_catalog import MANAGEMENT_CURRENCY_PRICES, resolve_price_entitlements
from models.users import PlanType


class BillingCurrencyUnavailable(ValueError):
    pass


def subscription_currency(subscription: dict) -> str:
    currency = subscription.get('currency')
    if not currency:
        currency = subscription['items']['data'][0]['price'].get('currency')
    if not isinstance(currency, str) or len(currency) != 3:
        raise BillingCurrencyUnavailable('Could not verify the subscription currency. Please try again.')
    return currency.lower()


def management_binding(price_id: str) -> tuple[PlanType, str, str] | None:
    binding = MANAGEMENT_CURRENCY_PRICES.get(price_id)
    if binding:
        return PlanType(binding['plan_id']), binding['interval'], binding['currency']
    return None


def price_for_currency(price: stripe.Price, currency: str | None) -> stripe.Price:
    """Resolve an explicit currency variant; never convert or invent an amount."""
    if currency is None or price.currency == currency:
        return price
    resolved = resolve_price_entitlements(price.id)
    if not resolved or resolved['entitlement_version'] != 'legacy':
        raise BillingCurrencyUnavailable('This plan is not available in your subscription currency.')
    base_recurring = price.recurring
    if base_recurring is None:
        raise BillingCurrencyUnavailable('This plan price is not a recurring subscription.')
    for candidate, binding in MANAGEMENT_CURRENCY_PRICES.items():
        if (binding['plan_id'], binding['interval'], binding['currency']) != (
            resolved['plan_id'],
            base_recurring.interval,
            currency,
        ):
            continue
        if candidate:
            target = stripe.Price.retrieve(candidate)
            target_resolved = resolve_price_entitlements(target.id)
            recurring = target.recurring
            if (
                target.active is True
                and target.currency == currency
                and target.livemode == price.livemode
                and recurring is not None
                and recurring.interval == base_recurring.interval
                and recurring.interval_count == 1
                and target_resolved
                and target_resolved['plan_id'] == resolved['plan_id']
                and target_resolved['entitlement_version'] == resolved['entitlement_version']
                and type(target.unit_amount) is int
                and target.unit_amount > 0
            ):
                return target
    raise BillingCurrencyUnavailable('This plan is not available in your subscription currency.')
