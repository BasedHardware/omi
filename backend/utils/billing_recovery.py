"""Tell the client that a declined renewal can still be paid (read-only Stripe).

The webhook deliberately projects a past_due subscription to Basic
(utils/subscription_state_machine.py), so the stored plan alone cannot say why a
payer is on Free. This module reads Stripe for that one case and reports a
PaymentIssue only when the stored subscription is past_due or unpaid, the user
did not choose to cancel, it is not a trial's first charge, and its latest
invoice is open with money due. It never writes, never charges and never returns
a payment URL: the client opens a Stripe-hosted page through
POST /v1/payments/customer-portal.
"""

import logging
import time
from typing import Any, Mapping, Optional

import stripe

from models.users import PaymentIssue, PlanType, Subscription
from utils.observability.fallback import record_fallback
from utils.subscription import get_plan_type_from_price_id, is_paid_plan

logger = logging.getLogger(__name__)

RECOVERABLE_STATUSES = frozenset({'past_due', 'unpaid'})


def payment_issue_from_stripe(
    uid: str, subscription: Mapping[str, Any], invoice: Optional[Mapping[str, Any]]
) -> Optional[PaymentIssue]:
    """Pure decision over a retrieved Stripe subscription and its latest invoice."""
    status = subscription.get('status')
    if status not in RECOVERABLE_STATUSES:
        return None
    # Chose to cancel, or is billed by emailed invoice rather than a saved card.
    if subscription.get('cancel_at_period_end') or subscription.get('cancel_at'):
        return None
    if subscription.get('collection_method', 'charge_automatically') != 'charge_automatically':
        return None
    owner = (subscription.get('metadata') or {}).get('uid')
    if owner and owner != uid:
        return None
    items = (subscription.get('items') or {}).get('data') or []
    price_id = (items[0].get('price') or {}).get('id') if items else None
    if not price_id:
        return None
    try:
        plan = get_plan_type_from_price_id(price_id)
    except ValueError:
        return None
    if not is_paid_plan(plan):
        return None
    # A trial whose first charge failed simply ended: that reader never paid for the plan.
    trial_end = subscription.get('trial_end')
    period_start = subscription.get('current_period_start') or items[0].get('current_period_start')
    if trial_end and period_start and period_start <= trial_end:
        return None
    if not invoice or invoice.get('status') != 'open' or not invoice.get('attempted'):
        return None
    if (invoice.get('amount_remaining') or 0) <= 0:
        return None
    return PaymentIssue(status=status, plan=plan)


def payment_issue_for(uid: str, stored: Optional[Subscription], now: Optional[int] = None) -> Optional[PaymentIssue]:
    """The user's payable failed renewal, or None.

    Reads Stripe only for a stored Basic plan that still points at a Stripe
    subscription whose period has not ended: the shape the webhook leaves for a
    past_due payer. A subscription canceled by choice ends at its period end, so
    former subscribers cost no Stripe call. Any Stripe failure answers None.
    """
    if not stored or stored.plan != PlanType.basic:
        return None
    subscription_id = stored.stripe_subscription_id
    # Organization grants store a one-time PaymentIntent here, not a subscription.
    if not subscription_id or subscription_id.startswith('pi_'):
        return None
    period_end = stored.current_period_end
    if period_end is not None and period_end <= (now if now is not None else int(time.time())):
        return None
    try:
        subscription = stripe.Subscription.retrieve(subscription_id).to_dict()  # type: ignore[reportDeprecated]  # stripe public serialization API
        if subscription.get('status') not in RECOVERABLE_STATUSES:
            return None
        invoice_id = subscription.get('latest_invoice')
        invoice = (
            stripe.Invoice.retrieve(invoice_id).to_dict()  # type: ignore[reportDeprecated]  # stripe public serialization API
            if isinstance(invoice_id, str) and invoice_id
            else None
        )
    except Exception as error:
        # Provider errors can carry account data: log the type only. No row is the safe answer.
        logger.warning('payment issue lookup failed uid=%s error_type=%s', uid, type(error).__name__)
        record_fallback(
            component='other',
            from_mode='stripe_payment_issue',
            to_mode='none',
            reason='unavailable',
            outcome='degraded',
        )
        return None
    return payment_issue_from_stripe(uid, subscription, invoice)
