"""Post-response, owner-confirmed Stripe billing projection. No entitlement writes."""

import logging

import stripe

from config.first_value_recovery import recovery_enabled
from database.first_value_recovery import (
    enroll_verified_paid_start,
    initial_direct_monthly_invoice_id,
)
from utils.observability import subscription_events as lifecycle

logger = logging.getLogger(__name__)


async def schedule_billing_webhook_events(background_tasks, **projection):
    from utils.executors import db_executor, run_blocking, stripe_executor

    projection = dict(projection)
    if recovery_enabled():
        invoice_id = initial_direct_monthly_invoice_id(projection)
        latest_invoice = (projection.get('subscription_obj') or {}).get('latest_invoice')
        if invoice_id is not None:
            try:
                invoice = (
                    dict(latest_invoice)
                    if isinstance(latest_invoice, dict)
                    else await run_blocking(stripe_executor, lambda: stripe.Invoice.retrieve(invoice_id).to_dict())
                )
                projection['paid_invoice'] = invoice
            except Exception as error:
                # Missing proof excludes this start; ordinary billing telemetry
                # and webhook acknowledgement remain fail-open.
                logger.warning('first-value paid invoice proof unavailable error_type=%s', type(error).__name__)

    if background_tasks is not None:
        background_tasks.add_task(emit_billing_webhook_events, **projection)
    else:
        # Direct Python callers do not get FastAPI's injected task container.
        await run_blocking(db_executor, emit_billing_webhook_events, **projection)


def emit_billing_webhook_events(**kwargs) -> None:
    """Fail open even when payload normalization or either capture fails."""
    try:
        first_value_args = dict(kwargs)
        kwargs.pop('paid_invoice', None)
        lifecycle_args = dict(kwargs)
        obj = kwargs.get('subscription_obj') or {}
        # W2's lifecycle emitter gets cancellation changes only while the same
        # confirmed paid subscription remains authoritative after reconciliation.
        if not (
            kwargs.get('stripe_event_type') == 'customer.subscription.updated'
            and kwargs.get('resulting_paid_subscription_id')
            and kwargs.get('previous_paid_subscription_id')
            == kwargs.get('resulting_paid_subscription_id')
            == obj.get('id')
        ):
            previous = dict(kwargs.get('previous_attributes') or {})
            previous.pop('cancel_at_period_end', None)
            lifecycle_args['previous_attributes'] = previous
        lifecycle.emit_billing_product_event(**lifecycle_args)
        lifecycle.emit_billing_plan_changed(**kwargs)
        # This persists only verified, admitted direct-paid monthly starts. Its
        # own default-dark gate runs before Firestore selection or any write.
        enroll_verified_paid_start(**first_value_args)
    except Exception as error:
        logger.warning('billing webhook telemetry failed error_type=%s', type(error).__name__)
