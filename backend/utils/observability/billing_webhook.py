"""Post-response, owner-confirmed Stripe billing projection. No entitlement writes."""

import logging
from typing import Any, Mapping

import stripe

from config.first_value_recovery import recovery_enabled
from database.first_value_recovery import (
    enroll_verified_paid_start,
    initial_direct_monthly_invoice_id,
)
from utils.executors import db_executor, run_blocking, stripe_executor
from utils.observability import subscription_events as lifecycle

logger = logging.getLogger(__name__)

STRIPE_INVOICE_TIMEOUT_SECONDS = 5
STRIPE_INVOICE_MAX_RETRIES = 0


def _with_paid_invoice_proof(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Add bounded proof in a post-response task; failure excludes only experiment intake."""

    result = dict(projection)
    if not recovery_enabled() or isinstance(result.get('paid_invoice'), Mapping):
        return result
    invoice_id = initial_direct_monthly_invoice_id(result)
    latest_invoice = (result.get('subscription_obj') or {}).get('latest_invoice')
    if invoice_id is None:
        return result
    try:
        if isinstance(latest_invoice, Mapping):
            invoice = dict(latest_invoice)
        else:
            api_key = stripe.api_key
            if not isinstance(api_key, str) or not api_key:
                return result
            http = stripe.RequestsClient(timeout=STRIPE_INVOICE_TIMEOUT_SECONDS)
            try:
                invoice = (
                    stripe.StripeClient(
                        api_key,
                        stripe_version=stripe.api_version,
                        http_client=http,
                        max_network_retries=STRIPE_INVOICE_MAX_RETRIES,
                    )
                    .invoices.retrieve(invoice_id)
                    .to_dict()
                )
            finally:
                http.close()
        result['paid_invoice'] = invoice
    except Exception as error:
        # Missing proof excludes this start; ordinary billing telemetry and the
        # already-acknowledged webhook remain fail-open.
        logger.warning('first-value paid invoice proof unavailable error_type=%s', type(error).__name__)
    return result


async def schedule_billing_webhook_events(background_tasks, **projection):
    # FastAPI executes this sync callable after sending the webhook response.
    # In particular, Stripe retrieval never sits between the handler and ack.
    if background_tasks is not None:
        background_tasks.add_task(emit_billing_webhook_events, **projection)
        return

    # Direct Python callers have no post-response runner. Preserve the same
    # bounded proof path on the Stripe pool before the ordinary DB task.
    projection = await run_blocking(stripe_executor, _with_paid_invoice_proof, projection)
    await run_blocking(db_executor, emit_billing_webhook_events, **projection)


def emit_billing_webhook_events(**kwargs) -> None:
    """Fail open even when payload normalization or either capture fails."""
    try:
        first_value_args = _with_paid_invoice_proof(kwargs)
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
