"""Restore a paid owner's historical access at the existing read boundary.

This performs no processing, billing, audio mutation or account-wide sweep.
The monthly reset worker remains separately gated; funded backlogs still need
their explicit processing choice.
"""

import logging

from database import conversations as conversations_db, users as users_db, redis_db
from database.legal_holds import external_write_fence
from database.fsr_read_cache import fresh_cache_reads
from models.users import SubscriptionStatus
from utils.subscription import is_paid_plan, resolve_transcription_allowance
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
_AVAILABLE = {'plan_within_allowance', 'plan_unlimited', 'usage_budget_available'}
_UNKNOWN = {'allowance_unavailable', 'usage_invalid'}


class RecoveryUnavailable(RuntimeError):
    """A dependency failure must offer retry rather than another purchase."""


def eligible(uid: str) -> bool:
    try:
        # Stats/checkout already reads fresh. A locked read must use the same
        # authority rather than a stale cached Free plan or a synthetic BYOK plan.
        with fresh_cache_reads(uid, 'subscription_cache'):
            subscription = users_db.get_user_valid_subscription(uid, provision=False)
        if not subscription or subscription.status != SubscriptionStatus.active or not is_paid_plan(subscription.plan):
            return False
        allowance = resolve_transcription_allowance(uid, subscription=subscription, byok_active=False)
        if allowance.reason in _UNKNOWN:
            raise RecoveryUnavailable('Allowance unavailable')
        return allowance.managed is True and allowance.reason in _AVAILABLE
    except RecoveryUnavailable:
        raise
    except Exception as error:
        logger.warning('paid_lock_recovery eligibility deferred error_type=%s', type(error).__name__)
        raise RecoveryUnavailable('Entitlement unavailable') from error


def heal_conversations(uid: str, rows: list[dict]) -> None:
    locked = [row for row in rows if row.get('is_locked') and not row.get('processing_deferred')]
    if not locked or not eligible(uid):
        return
    for row in locked:
        try:
            # Never use the URL's old ID when a sync redirect resolved a survivor.
            cid = row['id']
            with external_write_fence(uid):
                saved = conversations_db.update_conversation(uid, cid, {'is_locked': False})
            if saved is not True:
                raise RecoveryUnavailable('Conversation unavailable')
            row['is_locked'] = False
        except Exception as error:
            logger.warning('paid_lock_recovery write deferred error_type=%s', type(error).__name__)
            raise RecoveryUnavailable('Access recovery unavailable') from error
    # Each update preserves the database owner's people/search invalidations.
    # The signal also makes older mobile clients refresh their allowance state.
    try:
        redis_db.set_credits_invalidation_signal(uid)
    except Exception:
        record_fallback(
            component='other',
            from_mode='paid_lock_recovery',
            to_mode='cache_expiry',
            reason='dependency_unavailable',
            outcome='degraded',
            log=logger,
        )
