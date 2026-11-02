"""Restore historical paid access without processing, billing or account sweeps."""

import logging
from typing import Any

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


class PaidLockRecovery:
    """One request's fresh authority, shared by candidate selection and page writes.

    Selection may admit eligible locked matches without mutating the scan. Only
    ``heal`` persists the selected response page, never skipped pages or lookahead.
    """

    def __init__(self, uid: str):
        self.uid = uid
        self._eligible: bool | None = None

    def can_recover(self, row: dict[str, Any]) -> bool:
        if not row.get('is_locked') or row.get('processing_deferred'):
            return False
        if self._eligible is None:
            self._eligible = eligible(self.uid)
        return self._eligible

    def heal(self, rows: list[dict[str, Any]]) -> None:
        locked = [row for row in rows if self.can_recover(row)]
        if not locked:
            return
        try:
            with external_write_fence(self.uid):
                for row in locked:
                    cid = row['id']
                    if not isinstance(cid, str) or not cid:
                        raise RecoveryUnavailable('Conversation identity unavailable')
                    saved = conversations_db.update_conversation(self.uid, cid, {'is_locked': False})
                    if saved is not True:
                        raise RecoveryUnavailable('Conversation unavailable')
                    row['is_locked'] = False
        except Exception as error:
            logger.warning('paid_lock_recovery write deferred error_type=%s', type(error).__name__)
            raise RecoveryUnavailable('Access recovery unavailable') from error
        try:
            redis_db.set_credits_invalidation_signal(self.uid)
        except Exception:
            record_fallback(
                component='other',
                from_mode='paid_lock_recovery',
                to_mode='cache_expiry',
                reason='dependency_unavailable',
                outcome='degraded',
                log=logger,
            )


def heal_conversations(uid: str, rows: list[dict[str, Any]]) -> None:
    PaidLockRecovery(uid).heal(rows)
