"""Post-response, owner-confirmed Stripe billing projection. No entitlement writes."""

import logging

from utils.observability import subscription_events as lifecycle

logger = logging.getLogger(__name__)


async def schedule_billing_webhook_events(background_tasks, **projection):
    from utils.executors import db_executor, run_blocking

    if background_tasks is not None:
        background_tasks.add_task(emit_billing_webhook_events, **projection)
    else:
        # Direct Python callers do not get FastAPI's injected task container.
        await run_blocking(db_executor, emit_billing_webhook_events, **projection)


def emit_billing_webhook_events(**kwargs) -> None:
    """Fail open even when payload normalization or either capture fails."""
    try:
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
    except Exception as error:
        logger.warning('billing webhook telemetry failed error_type=%s', type(error).__name__)
