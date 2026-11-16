"""A declined yearly renewal can move to the same plan's monthly price instead.

The declined-renewal Home row (utils/billing_recovery.py) offers it as ``payment_issue.monthly_switch``
next to Update. POST /v1/payments/payment-issue/monthly-switch applies it:

1. Charge the plan's configured monthly price now (``billing_cycle_anchor='now'``,
   ``proration_behavior='none'``: the unpaid yearly period earns no credit) with
   ``payment_behavior='error_if_incomplete'``, so a declined card changes nothing and the reader
   stays past_due on yearly with the same open invoice.
   Before that charge, the unpaid yearly invoice's automatic collection is paused
   (``auto_advance=False``) so a Stripe retry cannot collect it while the switch runs or while a
   failed void is retried. Any failure that did not switch restores it, so dunning and Update work
   exactly as before.
2. Only after that charge succeeds, void the unpaid yearly invoice. The invoice id rides the
   subscription's metadata; a void that fails here is retried by the ``invoice.paid`` webhook and
   by a repeated request. A yearly invoice found paid after the switch means the reader paid both:
   it is logged and reported for a refund, never refunded automatically.

Only a past_due, undiscounted USD subscription on the configured yearly price of a consumer plan
qualifies, with an open renewal invoice. The price is the plan's catalog monthly price as Stripe
returns it, and the charge must equal what the reader saw. No new prices, coupons or discounts.
PAYMENT_ISSUE_MONTHLY_SWITCH_ENABLED=false turns the offer and the switch off.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import stripe

from models.users import PaymentIssueMonthlySwitch
from utils.billing_flags import payment_issue_monthly_switch_enabled
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# Consumer plans the mobile row serves. Desktop plans (Operator, Architect) manage on desktop.
SWITCH_PLAN_IDS = frozenset({'unlimited', 'unlimited_v2', 'plus'})
SWITCH_CURRENCIES = frozenset({'usd'})
# Subscription metadata: the unpaid yearly invoice the switch replaced (voided after the charge).
SUPERSEDED_INVOICE_KEY = 'omi_monthly_switch_from_invoice'


class Refused(Exception):
    """The switch must not run (``reason`` names the rule)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Incomplete(Exception):
    """Stripe accepted the change but did not leave an active subscription."""


@dataclass(frozen=True)
class Target:
    plan_id: str
    price_id: str  # the plan's configured monthly price


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _item(sub: Any) -> Any:
    items = _get(_get(sub, 'items'), 'data') or []
    return items[0] if items else None


def _price_id(sub: Any) -> Optional[str]:
    price = _get(_item(sub), 'price')
    return price if isinstance(price, str) else _get(price, 'id')


def _plan_definitions() -> list[dict]:
    from utils.subscription import get_paid_plan_definitions

    return get_paid_plan_definitions()


def target_for(yearly_price_id: Optional[str]) -> Optional[Target]:
    """The plan's monthly price when ``yearly_price_id`` is a switchable plan's configured yearly price."""
    if not yearly_price_id:
        return None
    for definition in _plan_definitions():
        plan = definition['plan_type']
        plan_id = getattr(plan, 'value', plan)
        if plan_id not in SWITCH_PLAN_IDS or not definition.get('monthly_price_id'):
            continue
        if yearly_price_id == definition.get('annual_price_id'):
            return Target(plan_id=plan_id, price_id=definition['monthly_price_id'])
    return None


def _is_target_monthly(price_id: Optional[str]) -> bool:
    return bool(price_id) and any(
        getattr(d['plan_type'], 'value', d['plan_type']) in SWITCH_PLAN_IDS and price_id == d.get('monthly_price_id')
        for d in _plan_definitions()
    )


def _discounted(obj: Any) -> bool:
    if _get(obj, 'discount') or _get(obj, 'discounts'):
        return True
    return any(int(_get(d, 'amount') or 0) for d in (_get(obj, 'total_discount_amounts') or []))


def refusal(sub: Any, invoice: Any, now: Optional[int] = None) -> Optional[str]:
    """Why this declined yearly renewal cannot move to monthly; None when it can."""
    now = int(now if now is not None else time.time())
    if sub is None:
        return 'no_subscription'
    if _get(sub, 'status') != 'past_due':
        return 'status'
    trial_end = _get(sub, 'trial_end')
    if trial_end and int(trial_end) > now:
        return 'trial'
    if _get(sub, 'cancel_at_period_end') or _get(sub, 'cancel_at'):
        return 'cancel_scheduled'
    if _get(sub, 'schedule'):
        return 'scheduled_change'
    if _get(sub, 'pending_update'):
        return 'pending_update'
    if _discounted(sub):
        return 'discounted'
    if _get(sub, 'pause_collection'):
        return 'paused'
    if (_get(sub, 'collection_method') or 'charge_automatically') != 'charge_automatically':
        return 'collection_method'
    items = _get(_get(sub, 'items'), 'data') or []
    if len(items) != 1 or int(_get(items[0], 'quantity', 1) or 1) != 1:
        return 'items'
    price = _get(items[0], 'price')
    currency = _get(sub, 'currency') or _get(price, 'currency')
    if currency not in SWITCH_CURRENCIES or _get(price, 'currency', currency) not in SWITCH_CURRENCIES:
        return 'currency'
    if target_for(_price_id(sub)) is None:
        return 'not_offered'
    if invoice is None or _get(invoice, 'status') != 'open':
        return 'no_open_invoice'
    latest = _get(sub, 'latest_invoice')
    if _get(invoice, 'id') != (latest if isinstance(latest, str) else _get(latest, 'id')):
        return 'not_latest_invoice'
    if _get(invoice, 'billing_reason') != 'subscription_cycle':
        return 'not_renewal'
    if _get(invoice, 'currency', currency) not in SWITCH_CURRENCIES:
        return 'currency'
    if _discounted(invoice):
        return 'discounted'
    if int(_get(invoice, 'amount_remaining') or 0) <= 0:
        return 'nothing_due'
    return None


def monthly_amount(price: Any, target: Target) -> Optional[int]:
    """The monthly price's amount in minor units when it is a plain monthly USD price, else None."""
    recurring = _get(price, 'recurring') or {}
    if (
        price is None
        or _get(price, 'id') != target.price_id
        or _get(price, 'active') is False
        or _get(recurring, 'interval') != 'month'
        or int(_get(recurring, 'interval_count', 1) or 1) != 1
        or _get(price, 'currency') not in SWITCH_CURRENCIES
        or not _get(price, 'unit_amount')
    ):
        return None
    return int(_get(price, 'unit_amount'))


def offer(sub: Any, invoice: Any, now: Optional[int] = None) -> Optional[PaymentIssueMonthlySwitch]:
    """The row's offer for a payable declined renewal. Never raises: no offer is the safe answer."""
    if not payment_issue_monthly_switch_enabled():
        return None
    try:
        if refusal(sub, invoice, now):
            return None
        target = target_for(_price_id(sub))
        if target is None:
            return None
        amount = monthly_amount(stripe.Price.retrieve(target.price_id), target)
        if amount is None:
            return None
        return PaymentIssueMonthlySwitch(
            price_id=target.price_id,
            amount=amount,
            currency='usd',
            yearly_amount=int(_get(invoice, 'amount_remaining')),
        )
    except Exception as error:  # noqa: BLE001 - the offer is optional; Update still works
        logger.warning('monthly switch offer unavailable error_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='stripe_monthly_switch_offer',
            to_mode='none',
            reason='unavailable',
            outcome='degraded',
        )
        return None


def preview_amount(sub: Any, price_id: str) -> int:
    """Stripe's own amount due for the switch: the same items, anchor and proration as the charge."""
    invoice = stripe.Invoice.create_preview(
        customer=_get(sub, 'customer'),
        subscription=_get(sub, 'id'),
        subscription_details={
            'items': [{'id': _get(_item(sub), 'id'), 'price': price_id}],
            'proration_behavior': 'none',
            'billing_cycle_anchor': 'now',
        },
    )
    if _get(invoice, 'currency') not in SWITCH_CURRENCIES or _get(invoice, 'amount_due') is None:
        raise Refused('preview_mismatch')
    if _discounted(invoice):
        raise Refused('discounted')
    return int(_get(invoice, 'amount_due'))


def already_switched(sub: Any, uid: str) -> bool:
    """This subscription was moved to monthly by an earlier request (a replay must not charge again)."""
    metadata = _get(sub, 'metadata') or {}
    return bool(
        _get(metadata, SUPERSEDED_INVOICE_KEY)
        and _get(metadata, 'uid') == uid
        and _get(sub, 'status') == 'active'
        and _is_target_monthly(_price_id(sub))
    )


def void_superseded(sub: Any) -> bool:
    """Void the unpaid yearly invoice this subscription's switch replaced. True once it is not collectible.

    Idempotent: a voided or uncollectible invoice is left alone; a paid one is reported for a refund.
    Raises on a Stripe failure so a webhook retry can try again.
    """
    invoice_id = _get(_get(sub, 'metadata') or {}, SUPERSEDED_INVOICE_KEY)
    if not invoice_id or _get(sub, 'status') != 'active':
        return False
    invoice = stripe.Invoice.retrieve(invoice_id)
    parent = _get(_get(invoice, 'parent'), 'subscription_details')
    owner = _get(invoice, 'subscription') or _get(parent, 'subscription')
    owner_id = owner if isinstance(owner, str) else _get(owner, 'id')
    if owner_id and owner_id != _get(sub, 'id'):
        return False
    if not owner_id and _get(invoice, 'customer') != _get(sub, 'customer'):
        return False
    if _get(invoice, 'status') == 'paid' and int(_get(invoice, 'amount_paid') or 0) > 0:
        # Both the yearly and the monthly charge went through: someone must refund the yearly one.
        logger.error(
            'monthly switch: superseded yearly invoice %s of %s was paid; refund needed',
            invoice_id,
            _get(sub, 'id'),
        )
        record_fallback(
            component='other',
            from_mode='monthly_switch_superseded_invoice',
            to_mode='paid_twice',
            reason='other',
            outcome='exhausted',
        )
        return True
    if _get(invoice, 'status') != 'open':
        return True
    stripe.Invoice.void_invoice(invoice_id, idempotency_key=f'omi-monthly-switch-void-{invoice_id}')
    logger.info('monthly switch voided the superseded yearly invoice of %s', _get(sub, 'id'))
    return True


def _set_collection(invoice_id: str, paused: bool) -> None:
    stripe.Invoice.modify(invoice_id, auto_advance=not paused)


def _restore_collection(invoice_id: str) -> None:
    """Resume Stripe's automatic collection of the yearly invoice after a switch that did not happen."""
    try:
        _set_collection(invoice_id, paused=False)
    except Exception as error:  # noqa: BLE001 - reported; the reader can still pay it with Update
        logger.error('monthly switch could not resume collection of %s error_type=%s', invoice_id, type(error).__name__)
        record_fallback(
            component='other',
            from_mode='stripe_yearly_collection_paused',
            to_mode='paused',
            reason='unavailable',
            outcome='degraded',
        )


def _switch_landed(subscription_id: str, invoice_id: str) -> bool:
    """After an unclear failure: did Stripe apply the switch? An unreadable answer counts as no."""
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
    except Exception:  # noqa: BLE001 - resuming is the safe default; the invoice.paid webhook voids if it landed
        return False
    return _get(_get(sub, 'metadata') or {}, SUPERSEDED_INVOICE_KEY) == invoice_id and _is_target_monthly(
        _price_id(sub)
    )


def switch(uid: str, subscription_id: str, price_id: str, expected_amount: int, attempt: str) -> dict:
    """Move a declined yearly renewal to monthly. Returns the updated Stripe subscription.

    Raises Refused (nothing changed), stripe.CardError (declined, nothing changed), Incomplete,
    or another Stripe error (unknown: a repeated request replays or refuses, it never charges twice).
    The yearly invoice's automatic collection is paused for the charge and restored unless it switched.
    """
    from utils.billing_recovery import payment_issue_from_stripe

    if not payment_issue_monthly_switch_enabled():
        raise Refused('disabled')
    sub = stripe.Subscription.retrieve(subscription_id).to_dict()
    if already_switched(sub, uid):
        try:
            void_superseded(sub)
        except Exception as error:  # noqa: BLE001 - the invoice.paid webhook retries the void
            logger.warning('monthly switch void retry failed error_type=%s', type(error).__name__)
        return sub
    latest = _get(sub, 'latest_invoice')
    invoice_id = latest if isinstance(latest, str) else _get(latest, 'id')
    if not invoice_id:
        raise Refused('no_open_invoice')
    invoice = stripe.Invoice.retrieve(invoice_id).to_dict()
    if payment_issue_from_stripe(uid, sub, invoice) is None:
        raise Refused('no_payment_issue')
    reason = refusal(sub, invoice)
    if reason:
        raise Refused(reason)
    target = target_for(_price_id(sub))
    if target is None or price_id != target.price_id:
        raise Refused('not_monthly_of_plan')
    amount = monthly_amount(stripe.Price.retrieve(target.price_id), target)
    if amount is None:
        raise Refused('no_monthly_price')
    if amount != expected_amount:
        raise Refused('price_changed')
    if preview_amount(sub, price_id) != expected_amount:
        raise Refused('preview_changed')

    # No Stripe retry may collect the yearly invoice while (or after) the monthly charge runs.
    try:
        _set_collection(invoice_id, paused=True)
    except BaseException:
        _restore_collection(invoice_id)  # a timed-out pause may still have landed
        raise
    try:
        updated = stripe.Subscription.modify(
            _get(sub, 'id'),
            items=[{'id': _get(_item(sub), 'id'), 'price': price_id}],
            proration_behavior='none',
            billing_cycle_anchor='now',
            payment_behavior='error_if_incomplete',
            metadata={'uid': uid, 'sub_type': target.plan_id, SUPERSEDED_INVOICE_KEY: invoice_id},
            idempotency_key=f'omi-monthly-switch-{_get(sub, "id")}-{invoice_id}-{attempt}',
        ).to_dict()
        if _get(updated, 'status') != 'active' or _get(updated, 'pending_update'):
            raise Incomplete(str(_get(updated, 'status')))
    except stripe.CardError:
        _restore_collection(invoice_id)  # declined: Stripe changed nothing
        raise
    except BaseException:
        # Unknown outcome: keep collection paused only if the switch landed (the void follows on retry).
        if not _switch_landed(_get(sub, 'id'), invoice_id):
            _restore_collection(invoice_id)
        raise
    try:
        void_superseded(updated)
    except Exception as error:  # noqa: BLE001 - the invoice.paid webhook retries the void
        logger.warning('monthly switch void failed, webhook retries error_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='stripe_monthly_switch_void',
            to_mode='webhook_retry',
            reason='unavailable',
            outcome='degraded',
        )
    return updated
