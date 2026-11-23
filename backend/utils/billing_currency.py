"""Same-currency offers for managing an existing personal subscription.

The retained recognition ledger is not a purchase catalog. Only explicit
management bindings in the plan catalog may supplement the configured prices;
new Checkout cannot use these management targets. Stripe owns amounts.
"""

from types import SimpleNamespace

import stripe

from config.plan_catalog import MANAGEMENT_CURRENCY_PRICES, resolve_price_entitlements
from models.users import PlanType
from utils import local_currency


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


def price_for_currency(price: stripe.Price, currency: str | None, *, allow_options: bool = False) -> stripe.Price:
    """Resolve an explicit currency variant; never convert or invent an amount.

    ``allow_options``: the subscription is billed through a currency option of a
    multi-currency Price (utils.local_currency), so the same Price id is offered at its
    own ``currency_options`` amount in that currency.
    """
    if currency is None or price.currency == currency:
        return price
    if allow_options:
        try:
            amount = local_currency.billed_option_amount(price, currency)
        except local_currency.OptionLookupFailed as error:
            raise BillingCurrencyUnavailable('Could not verify the subscription currency. Please try again.') from error
        recurring = price.recurring
        if amount is None or recurring is None or price.active is not True:
            raise BillingCurrencyUnavailable('This plan is not available in your subscription currency.')
        return SimpleNamespace(  # type: ignore[return-value]
            id=price.id,
            currency=currency,
            unit_amount=amount,
            recurring=recurring,
            active=price.active,
            livemode=price.livemode,
        )
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
