"""Read-only billing fence for promotional claims. No provider IO inside a transaction."""

from datetime import datetime
from typing import Any, Mapping

import stripe

from utils.referral_campaign import commercial_access_active


class BillingAuthorityUnavailable(RuntimeError):
    pass


def billing_identity(user: Mapping[str, Any]) -> dict[str, Any]:
    return {'subscription': user.get('subscription', {}), 'stripe_customer_id': user.get('stripe_customer_id')}


def billing_allows_claim(uid: str, user: Mapping[str, Any], now: datetime) -> bool:
    stored = user.get('subscription', {})
    if commercial_access_active(stored, now):
        return False
    # A known recurring billing identity must be checked even after its stored
    # period lapsed: its next renewal may already exist before webhook delivery.
    customer = user.get('stripe_customer_id')
    subscription_id = stored.get('stripe_subscription_id')
    if subscription_id and subscription_id.startswith('pi_'):
        subscription_id = None
    if not customer and not subscription_id:
        return True
    try:
        subscriptions = []
        if subscription_id:
            subscriptions.append(stripe.Subscription.retrieve(subscription_id).to_dict())
        if customer:
            page = stripe.Subscription.list(customer=customer, status='all', limit=100)
            if page.has_more:
                raise BillingAuthorityUnavailable('billing pagination requires reconciliation')
            subscriptions.extend(item.to_dict() for item in page.data)
        for subscription in subscriptions:
            owner = (subscription.get('metadata') or {}).get('uid')
            if owner and owner != uid:
                raise BillingAuthorityUnavailable('billing owner mismatch')
            status = subscription.get('status')
            if not isinstance(status, str) or not status:
                raise BillingAuthorityUnavailable('invalid billing status')
            if status not in ('canceled', 'incomplete_expired'):
                return False
            end = subscription.get('current_period_end')
            if status == 'canceled' and isinstance(end, (int, float)) and end >= now.timestamp():
                return False
        return True
    except Exception as error:
        raise BillingAuthorityUnavailable('billing_authority_unavailable') from error
