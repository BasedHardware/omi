"""Default-off durable duplicate suppression around verified Stripe events."""

import asyncio
import logging
from typing import Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException

from utils.billing_flags import webhook_ledger_enabled
from utils.observability.billing_ledger import record_outcome
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
LEDGER_RPC_WAIT_SECONDS = 2.0

# Creator-app invoice handlers still swallow persistence exceptions;
# their HTTP 200 cannot certify completion. Keep them observation-only.
PROTECTED_EVENTS = frozenset(
    {
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
        'checkout.session.completed',
        'subscription_schedule.completed',
        'subscription_schedule.updated',
        'subscription_schedule.canceled',
    }
)


class RetryableBillingSkip(dict):
    """HTTP success whose unresolved entitlement must remain replayable."""


async def _ledger_call(run_db: Callable, function: Callable, *args, **kwargs):
    # Bound HTTP waiting. A running SDK operation can finish in its worker after
    # timeout; no handler runs without a confirmed claim, and completion tokens
    # fence receipts. The SDK's own retry lifecycle is not forcibly interrupted.
    return await asyncio.wait_for(run_db(function, *args, **kwargs), timeout=LEDGER_RPC_WAIT_SECONDS)


async def dispatch_with_ledger(event: dict, handler: Callable[[], Awaitable[dict]], run_db: Callable) -> dict:
    if not webhook_ledger_enabled():
        return await handler()
    from database import stripe_event_ledger as ledger

    creator_app = bool((event.get('data', {}).get('object', {}).get('metadata') or {}).get('app_id'))
    if event.get('type') not in PROTECTED_EVENTS or creator_app:
        result = await handler()
        record_outcome('unprotected')
        try:
            await _ledger_call(run_db, ledger.observe_event, event)
        except Exception as error:
            logger.warning('billing observation failed: %s', type(error).__name__)
            record_outcome('observe_error')
            record_fallback(
                component='other',
                from_mode='billing_event_observation',
                to_mode='skip_ledger_observation',
                reason='malformed_doc' if isinstance(error, ValueError) else 'connection_error',
                outcome='degraded',
                log=logger,
            )
        return result
    token = uuid4().hex
    try:
        claim = await _ledger_call(run_db, ledger.claim_event, event, token)
    except Exception as error:
        logger.error('billing claim failed: %s', type(error).__name__)
        record_outcome('claim_error')
        raise HTTPException(status_code=503, detail='Billing event receipt unavailable') from None
    if claim.outcome == 'duplicate':
        record_outcome('duplicate')
        return {'status': 'success'}
    if claim.outcome == 'busy':
        record_outcome('busy')
        raise HTTPException(status_code=503, detail='Billing event is already processing')
    record_outcome('claimed')
    try:
        result = await handler()
    except Exception:
        record_outcome('handler_error')
        try:
            await _ledger_call(run_db, ledger.finish_event, event, token, succeeded=False)
        except Exception:
            record_outcome('finish_error')
            logger.warning('billing event failure receipt unavailable')
        raise
    succeeded = not isinstance(result, RetryableBillingSkip)
    try:
        out_of_order = await _ledger_call(run_db, ledger.finish_event, event, token, succeeded=succeeded)
    except Exception as error:
        logger.error('billing completion failed: %s', type(error).__name__)
        record_outcome('finish_error')
        # A 2xx without a durable receipt would make future duplicate suppression unsafe.
        raise HTTPException(status_code=503, detail='Billing event completion receipt unavailable') from None
    record_outcome('acknowledged' if succeeded else 'retryable_skip')
    if out_of_order:
        record_outcome('out_of_order')
    return result
