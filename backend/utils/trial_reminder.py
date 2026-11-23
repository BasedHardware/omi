"""Trial-ending reminder and checkout trial terms.

Readers who start a free trial are charged the full plan price when it ends. Support saw
customers surprised by that first charge, and the in-app trial offer promises a reminder
before anything is charged. Stripe sends `customer.subscription.trial_will_end` three days
before a trial ends; this module decides whether that event earns a reminder push and
what it says. Pure functions over Stripe dicts, so the webhook stays thin.
"""

import math
from typing import Any, Callable, Mapping, Optional

from utils import local_currency
from utils.storefront_copy import format_money
from utils.subscription import get_plan_type_from_price_id, is_paid_plan

TRIAL_ENDING_NOTIFICATION_TITLE = 'Your Omi Pro free trial ends soon'


def _when(trial_end: int, now: int) -> str:
    days = math.ceil((trial_end - now) / 86400)
    if days <= 1:
        return 'in less than a day' if days <= 0 else 'tomorrow'
    return f'in {days} days'


def recurring_terms(
    amount_minor: int, currency: str, interval: str, money: Optional[Callable[[int, str], str]] = None
) -> str:
    """`US$269.91 a year` / `US$29.99 a month`."""
    return f"{(money or format_money)(amount_minor, currency)} a {'year' if interval == 'year' else 'month'}"


def _billed(price: Mapping[str, Any], subscription: Mapping[str, Any], retrieve_price: Optional[Callable[[str], Any]]):
    """(amount, currency, formatter) Stripe bills, or None when it cannot be read (no reminder)."""
    currency = subscription.get('currency')
    try:
        amount = local_currency.billed_option_amount(price, currency, retrieve_price)
    except local_currency.OptionLookupFailed:
        return None
    if amount is None:
        return price.get('unit_amount'), price.get('currency'), None
    return amount, currency, local_currency.display_money


def trial_ending_reminder_body(
    uid: str,
    subscription: Mapping[str, Any],
    now: int,
    retrieve_price: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    """Push body for a trial that will convert to a paid charge, or None when no reminder applies.

    No reminder when the trial is already set to cancel, belongs to another account, has a
    discount (an included-year code makes the next charge something other than the list price),
    or is not a paid Omi plan.
    """
    if subscription.get('status') != 'trialing':
        return None
    if subscription.get('cancel_at_period_end') or subscription.get('cancel_at'):
        return None
    if subscription.get('collection_method', 'charge_automatically') != 'charge_automatically':
        return None
    owner = (subscription.get('metadata') or {}).get('uid')
    if owner and owner != uid:
        return None
    trial_end = subscription.get('trial_end')
    if not isinstance(trial_end, int) or trial_end <= now:
        return None
    if subscription.get('discount') or subscription.get('discounts'):
        return None
    items = (subscription.get('items') or {}).get('data') or []
    if len(items) != 1:
        return None
    price = items[0].get('price') or {}
    price_id = price.get('id')
    if not isinstance(price_id, str):
        return None
    try:
        if not is_paid_plan(get_plan_type_from_price_id(price_id)):
            return None
    except ValueError:
        return None
    billed = _billed(price, subscription, retrieve_price)
    if billed is None:
        return None
    amount, currency, money = billed
    interval = (price.get('recurring') or {}).get('interval')
    quantity = items[0].get('quantity') or 1
    if not isinstance(amount, int) or amount <= 0 or not currency or interval not in ('month', 'year'):
        return None
    terms = recurring_terms(amount * quantity, currency, interval, money)
    return (
        f'It ends {_when(trial_end, now)}, then your card is charged {terms}. '
        'To pay nothing, cancel before then in Settings.'
    )


def checkout_trial_terms(
    trial_days: int,
    amount_minor: Optional[int],
    currency: str,
    interval: Optional[str],
    money: Optional[Callable[[int, str], str]] = None,
) -> str:
    """The line shown above Stripe Checkout's button for a free-trial session."""
    if not isinstance(amount_minor, int) or amount_minor <= 0 or interval not in ('month', 'year'):
        return (
            f'No charge today. When your {trial_days}-day free trial ends, your card is charged '
            'unless you cancel before then in the Omi app.'
        )
    return (
        f'No charge today. When your {trial_days}-day free trial ends, your card is charged '
        f'{recurring_terms(amount_minor, currency, interval, money)}, less any code you apply, until you cancel. '
        'Cancel in the Omi app before the trial ends and you pay nothing.'
    )


__all__ = [
    'TRIAL_ENDING_NOTIFICATION_TITLE',
    'checkout_trial_terms',
    'recurring_terms',
    'trial_ending_reminder_body',
]
