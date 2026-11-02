"""Bounded reset recovery on authenticated HTTP requests, without STT or AI work.

The current quota window is a UTC calendar month, not the Stripe billing period.
Remaining is_locked rows are the durable checkpoint after any partial failure.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Callable

from utils.locked_content_flags import reset_recovery_enabled

logger = logging.getLogger(__name__)
PAGE_SIZE = 100
LEASE_SECONDS = 300
RETRY_SECONDS = 60
_cap_audio_recovery: Callable[[str], None] | None = None


def register_cap_audio_recovery(callback: Callable[[str], None]) -> None:
    """The API sync owner supplies STT recovery; lean auth consumers do not."""
    global _cap_audio_recovery
    _cap_audio_recovery = callback


def _memory_page_drained(count: int, page_size: int) -> bool:
    """True when neither memory collection filled its page.

    The unlock helper returns the summed row count. A 60 + 60 pair is fully
    drained and still sums past ``page_size``. ``page_saturated`` records that
    either collection returned a full page. A missing attribute keeps the
    single-count comparison used by one-collection callers and older doubles.
    """
    saturated = getattr(count, 'page_saturated', None)
    if isinstance(saturated, bool):
        return not saturated
    return count < page_size


def recover_locked_content(uid: str, *, now: datetime | None = None) -> None:
    # Funded audio/text backlog requires explicit choice. A calendar reset or
    # ordinary authenticated request must never mint processing intent.
    if not reset_recovery_enabled():
        return
    # Lazy imports keep the flag-off auth path free of additional dependencies.
    from database import action_items, conversations, memories, redis_db
    from database._client import db
    from utils.fair_use import invalidate_enforcement_cache
    from utils.subscription import clear_trial_paywall_cache, resolve_transcription_allowance
    from utils.observability.fallback import record_fallback

    now = now or datetime.now(timezone.utc)
    period = now.strftime('%Y-%m')
    next_month = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    period_ttl = max(1, int((next_month - now).total_seconds()))
    prefix = f'users:{uid}:locked_content_reset'
    done_key = f'{prefix}:done:{period}'
    lease_key = f'{prefix}:lease'
    token = uuid4().hex
    acquired = False
    try:
        if redis_db.r.get(done_key):
            return
        # Coalesce retries before reading usage (up to ~744 hourly documents).
        if not redis_db.r.set(f'{prefix}:retry', '1', nx=True, ex=RETRY_SECONDS):
            return
        acquired = bool(redis_db.r.set(lease_key, token, nx=True, ex=LEASE_SECONDS))
        if not acquired:
            return
        state = db.collection('users').document(uid).collection('locked_content_recovery').document('reset')
        completed_period = (state.get().to_dict() or {}).get('completed_period')
        if completed_period == period:
            redis_db.r.set(done_key, '1', ex=period_ttl)
            return

        # No reviewer/BYOK/trial override may authorize a persistent unlock.
        # Only the ordinary plan allowance, successfully resolved, qualifies.
        def eligible() -> bool:
            allowance = resolve_transcription_allowance(uid, byok_active=False)
            return allowance.managed and allowance.reason in {'plan_within_allowance', 'plan_unlimited'}

        if not eligible():
            return
        # Same helpers as the paid-upgrade webhook, now with bounded pages.
        # Children first; each collection drains independently over retries.
        # A page can expose a parent before all child pages finish.
        try:
            memory_count = memories.unlock_all_memories(uid, limit=PAGE_SIZE)
            if not eligible():
                return
            action_count = action_items.unlock_all_action_items(uid, limit=PAGE_SIZE)
            if not eligible():
                return
            conversation_count = conversations.unlock_all_conversations(uid, limit=PAGE_SIZE)
        finally:
            # Repair access caches even when a later recheck denies or fails,
            # or a helper raises after an already-committed page. A paywall
            # cache error must not skip fair-use invalidation.
            redis_db.set_credits_invalidation_signal(uid)
            try:
                clear_trial_paywall_cache(uid)
            finally:
                invalidate_enforcement_cache(uid)
        # Each memory collection has its own page. A full page stays incomplete
        # until a later short page proves the tail. Two short pages (60 + 60)
        # are drained even though their sum reaches PAGE_SIZE.
        if (
            _memory_page_drained(memory_count, PAGE_SIZE)
            and action_count < PAGE_SIZE
            and conversation_count < PAGE_SIZE
        ):
            state.set({'completed_period': period, 'completed_at': now})
            redis_db.r.set(done_key, '1', ex=period_ttl)
    except Exception as error:
        # Recovery is optional; auth still succeeds. No user/content in logs.
        logger.warning('locked_content_reset_recovery deferred error_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='locked_content_reset',
            to_mode='deferred',
            reason='dependency_unavailable',
            outcome='degraded',
            log=logger,
        )
    finally:
        if acquired:
            try:
                # Existing token-fenced Redis lease-release primitive.
                redis_db.release_token_lock(lease_key, token)
            except Exception:
                pass  # TTL releases it; never delete a successor's lease.
