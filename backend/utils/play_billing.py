"""Google Play Billing for Omi Pro: verify, bind, acknowledge and keep the entitlement current.

Google's ``purchases.subscriptionsv2`` resource is the only source of truth; a notification or a
client report only names the token to re-read. Entitlement writes reuse the Stripe path's helpers
(``update_user_subscription`` + unlocks + fair-use clear), so a Play subscriber holds exactly what
a Stripe Omi Pro subscriber holds.
"""

from __future__ import annotations

import hmac
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Mapping, Optional

import stripe

import database.play_subscriptions as play_db
import database.users as users_db
from config import play_billing as config
from config import prepaid_code_redeem as prepaid_code_config
from database import action_items as action_items_db, conversations as conversations_db, memories as memories_db
from database import redis_db
from database.account_deletion_marker import account_deletion_blocks_user_work
from models.users import PlanType, Subscription, SubscriptionStatus
from utils.fair_use import clear_fair_use_on_upgrade
from utils.play_publisher import GooglePublisher, PublisherClient, PurchaseNotFound, default_publisher
from utils.observability.fallback import record_fallback
from utils.notification_dispatch import (
    NotificationDispatchStatus,
    NotificationIntent,
    NotificationKind,
    dispatch_notification,
)
from utils.stripe import TERMINAL_SUBSCRIPTION_STATUSES
from utils.subscription import get_plan_limits, is_paid_plan

logger = logging.getLogger(__name__)

PLAY_PLAN = PlanType.unlimited_v2

STATE_ACTIVE = 'SUBSCRIPTION_STATE_ACTIVE'
STATE_GRACE = 'SUBSCRIPTION_STATE_IN_GRACE_PERIOD'
STATE_CANCELED = 'SUBSCRIPTION_STATE_CANCELED'
STATE_ON_HOLD = 'SUBSCRIPTION_STATE_ON_HOLD'
STATE_PAUSED = 'SUBSCRIPTION_STATE_PAUSED'
STATE_EXPIRED = 'SUBSCRIPTION_STATE_EXPIRED'
STATE_PENDING = 'SUBSCRIPTION_STATE_PENDING'
STATE_PENDING_CANCELED = 'SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED'

# States that keep access until expiryTime. CANCELED = auto-renew off, still paid through.
ACCESS_STATES = frozenset({STATE_ACTIVE, STATE_GRACE, STATE_CANCELED})
# States that can still change on their own; reconcile keeps re-reading them.
OPEN_STATES = ACCESS_STATES | {STATE_ON_HOLD, STATE_PAUSED, STATE_PENDING}
RECHECK_SECONDS = 24 * 3600
# Google keeps extending expiryTime through a grace period; never cut access before a fresh read.
GRACE_RECHECK_SECONDS = 6 * 3600
GRACE_FLOOR_SECONDS = 24 * 3600


class PlayBillingError(Exception):
    """Typed refusal with the HTTP status and stable code the route returns."""

    def __init__(self, http_status: int, code: str, message: str):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message


# Back-compat names: the client lives in the light utils.play_publisher module.
_GooglePublisher = GooglePublisher
_publisher: Optional[PublisherClient] = None


def get_publisher() -> PublisherClient:
    return _publisher or default_publisher()


obfuscated_account_id = config.obfuscated_account_id


def _rfc3339_seconds(value: Any) -> Optional[int]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
    except ValueError:
        return None


@dataclass(frozen=True)
class PlayState:
    """Pure reading of one subscriptionsv2 resource."""

    state: str
    product_id: Optional[str]
    base_plan_id: Optional[str]
    offer_id: Optional[str]
    expiry: Optional[int]
    start: Optional[int]
    auto_renewing: bool
    acknowledged: bool
    obfuscated_account_id: Optional[str]
    linked_token: Optional[str]
    test_purchase: bool

    def has_access(self, now: int) -> bool:
        if self.state == STATE_GRACE:
            # During grace Google extends expiryTime and says the user keeps access.
            return True
        return self.state in ACCESS_STATES and self.expiry is not None and self.expiry > now

    def access_until(self, now: int) -> Optional[int]:
        if self.state == STATE_GRACE:
            return max(self.expiry or 0, now + GRACE_FLOOR_SECONDS)
        return self.expiry


def read_state(resource: Mapping[str, Any]) -> PlayState:
    items = resource.get('lineItems') or []
    item = items[0] if items and isinstance(items[0], Mapping) else {}
    offer = item.get('offerDetails') or {}
    renewing = item.get('autoRenewingPlan') or {}
    identifiers = resource.get('externalAccountIdentifiers') or {}
    return PlayState(
        state=str(resource.get('subscriptionState') or ''),
        product_id=item.get('productId'),
        base_plan_id=offer.get('basePlanId'),
        offer_id=offer.get('offerId'),
        expiry=_rfc3339_seconds(item.get('expiryTime')),
        start=_rfc3339_seconds(resource.get('startTime')),
        auto_renewing=bool(renewing.get('autoRenewEnabled')),
        acknowledged=resource.get('acknowledgementState') == 'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED',
        obfuscated_account_id=identifiers.get('obfuscatedExternalAccountId'),
        linked_token=resource.get('linkedPurchaseToken'),
        test_purchase='testPurchase' in resource,
    )


def _record(state: PlayState, token: str, now: int, *, revoked_through: Optional[int] = None) -> dict:
    # A refund-only token can still renew at Google, so it keeps being re-read while its state is open.
    open_state = state.state in OPEN_STATES
    next_check = None
    if open_state:
        next_check = now + (GRACE_RECHECK_SECONDS if state.state == STATE_GRACE else RECHECK_SECONDS)
        if state.expiry is not None and state.expiry > now:
            next_check = min(next_check, state.expiry + 60)
    return {
        'purchase_token': token,
        'product_id': state.product_id,
        'base_plan_id': state.base_plan_id,
        'offer_id': state.offer_id,
        'state': state.state,
        'expiry_time': state.expiry,
        'auto_renewing': state.auto_renewing,
        'acknowledged': state.acknowledged,
        'obfuscated_account_id': state.obfuscated_account_id,
        'linked_token_key': play_db.token_key(state.linked_token) if state.linked_token else None,
        'test_purchase': state.test_purchase,
        'revoked_through': revoked_through,
        'next_check_at': next_check,
        'updated_at': now,
    }


# Paid states: a renewal Google charged for. Grace is a failed charge, so it never re-grants a refund.
PAID_STATES = frozenset({STATE_ACTIVE, STATE_CANCELED})


def refunded_through(existing: Mapping[str, Any]) -> Optional[int]:
    """Expiry of the period a refund or revoke removed, or None. Older records stored only a flag."""
    through = existing.get('revoked_through')
    if through is None and existing.get('revoked'):
        return 2**62  # legacy sticky revoke: never re-grant
    return through


def paid_after_refund(state: PlayState, through: Optional[int]) -> bool:
    """A refunded token grants again only for a later period Google has been paid for."""
    if through is None:
        return True
    return state.state in PAID_STATES and state.expiry is not None and state.expiry > through


def play_subscription(state: PlayState, now: Optional[int] = None) -> Subscription:
    """The Omi Pro row a Stripe subscription with the same period would store."""
    return Subscription(
        plan=PLAY_PLAN,
        status=SubscriptionStatus.active,
        current_period_end=state.access_until(now if now is not None else int(time.time())),
        current_period_start=state.start,
        cancel_at_period_end=not state.auto_renewing,
        limits=get_plan_limits(PLAY_PLAN),
        provider='play',
    )


def _grant(uid: str, state: PlayState, token_hash: str) -> Subscription:
    # Same write + side effects as the Stripe upgrade paths (routers/monthly_switch._store).
    subscription = play_subscription(state)
    play_db.set_user_fields(
        uid,
        {play_db.USER_POINTER_FIELD: token_hash, play_db.PENDING_FIELD: None, play_db.CUSTOMER_FIELD: True},
    )
    users_db.update_user_subscription(uid, subscription.model_dump())
    redis_db.set_credits_invalidation_signal(uid)
    conversations_db.unlock_all_conversations(uid)
    memories_db.unlock_all_memories(uid)
    action_items_db.unlock_all_action_items(uid)
    clear_fair_use_on_upgrade(uid)
    return subscription


def _revoke(uid: str, token_hash: str) -> bool:
    """Drop Play access only when this token still owns the user's row. Returns True if written."""
    if play_db.get_user_pointer(uid) != token_hash:
        return False
    current = users_db.get_user_subscription(uid)
    if getattr(current, 'provider', None) != 'play':
        return False
    users_db.update_user_subscription(
        uid, Subscription(plan=PlanType.basic, status=SubscriptionStatus.active).model_dump()
    )
    redis_db.set_credits_invalidation_signal(uid)
    return True


def _holds_live_paid_row(uid: str, *, exclude_play: bool = False, require_billable_stripe: bool = False) -> bool:
    stored = users_db.get_user_valid_subscription(uid, include_promotions=False)
    return bool(
        stored is not None
        and is_paid_plan(stored.plan)
        and not (exclude_play and stored.provider == 'play')
        and (
            not require_billable_stripe
            or (not stored.prepaid and (stored.stripe_subscription_id or '').startswith('sub_'))
        )
        and stored.current_period_end
        and stored.current_period_end > int(time.time())
    )


def _is_billable_stripe_subscription(uid: str, data: Mapping[str, Any]) -> bool:
    """An active or trialing ``sub_`` subscription for this user that charges money (not a prepaid code)."""
    metadata = data.get('metadata') or {}
    return bool(
        not metadata.get('app_id')
        and metadata.get('uid') in (None, uid)
        and str(data.get('id') or '').startswith('sub_')
        and data.get('status') in ('active', 'trialing')
        and not prepaid_code_config.is_prepaid_subscription(data)
    )


def _live_stripe_evidence(uid: str) -> tuple[bool, tuple[str, ...]]:
    """Whether a paid non-Play entitlement is live, and the billable Stripe IDs seen while checking.

    The IDs let conflict recording keep what this listing already confirmed, so a later listing
    that fails part-way cannot erase a billable subscription found here.
    """
    if _holds_live_paid_row(uid, exclude_play=True):
        return True, ()
    customer_id = users_db.get_stripe_customer_id(uid)
    if not customer_id:
        return False, ()
    billable: list[str] = []
    live = False
    try:
        # Every page and every state Stripe can still bill or recover (unpaid, incomplete, paused too).
        for sub in stripe.Subscription.list(customer=customer_id, status='all', limit=100).auto_paging_iter():
            data = sub.to_dict()
            if (data.get('metadata') or {}).get('app_id'):
                continue
            if data.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES:
                live = True
                if _is_billable_stripe_subscription(uid, data):
                    billable.append(str(data['id']))
                    break
    except Exception as error:
        logger.warning('play_billing stripe check unavailable: %s', type(error).__name__)
        if live:
            # A live subscription was already seen; the answer is known even though a later page failed.
            return True, tuple(billable)
        raise PlayBillingError(503, 'billing_check_unavailable', 'Could not verify billing. Try again.') from None
    return live, tuple(billable)


def _live_stripe_subscription(uid: str) -> bool:
    """A paid non-Play entitlement this user still holds (stored row or Stripe itself)."""
    return _live_stripe_evidence(uid)[0]


def _fetch(publisher: PublisherClient, token: str) -> PlayState:
    try:
        resource = publisher.get_subscription(config.package_name(), token)
    except PurchaseNotFound:
        raise PlayBillingError(400, 'invalid_purchase', 'This purchase could not be found on Google Play.') from None
    except Exception as error:
        logger.warning('play_billing publisher read failed: %s', type(error).__name__)
        raise PlayBillingError(503, 'play_unavailable', 'Google Play is unavailable. Try again.') from None
    return read_state(resource)


def _check_product(state: PlayState) -> None:
    if state.product_id in config.LEGACY_PRODUCT_IDS:
        logger.warning('play_billing legacy product refused: product=%s', state.product_id)
        raise PlayBillingError(400, 'legacy_product', 'This older Omi subscription cannot be restored here.')
    if state.product_id != config.product_id() or state.base_plan_id not in config.base_plans():
        raise PlayBillingError(400, 'unknown_product', 'This purchase is not an Omi Pro subscription.')


def _acknowledge(publisher: PublisherClient, state: PlayState, token: str) -> None:
    if state.acknowledged:
        return
    try:
        publisher.acknowledge(config.package_name(), config.product_id(), token)
    except Exception as error:
        logger.warning('play_billing acknowledge failed: %s', type(error).__name__)
        raise PlayBillingError(503, 'play_unavailable', 'Google Play is unavailable. Try again.') from None


@dataclass(frozen=True)
class VerifyResult:
    status: Literal['active', 'pending', 'inactive']
    subscription: Optional[Subscription]


_OWNED_ELSEWHERE = (409, 'purchase_owned_elsewhere', 'This purchase belongs to another Omi account.')
_REFUNDED = (409, 'purchase_refunded', 'This Google Play purchase was refunded and no longer includes Omi Pro.')
_STRIPE_ACTIVE = (
    409,
    'stripe_subscription_active',
    'You already have Omi Pro billed outside Google Play. Cancel it before subscribing here.',
)


def _clear_pending(uid: str, token_hash: str) -> None:
    if play_db.get_user_fields(uid).get(play_db.PENDING_FIELD) == token_hash:
        play_db.set_user_fields(uid, {play_db.PENDING_FIELD: None})


CONFLICT_FIELD = 'stripe_conflict_at'
CONFLICT_UNVERIFIED_FIELD = 'stripe_conflict_listing_failed_at'
CONFLICT_NOTIFIED_FIELD = 'stripe_conflict_notified_at'
CONFLICT_NOTICE_CLAIM_FIELD = 'stripe_conflict_notice_claimed_at'
NOTICE_CLAIM_SECONDS = 600
DOUBLE_CHARGE_LOG = 'play_billing_double_charge uid=%s purchase=%s state=%s'


def _paid_stripe_subscription_ids(uid: str) -> tuple[list[str], list[str], bool]:
    """Return active or trialing Stripe IDs, their prepaid codes, and whether listing failed.

    Stricter than ``_live_stripe_subscription``: a stored row, a one-time ``pi_`` grant, an ended
    subscription or an ``incomplete`` one is never reported as a double charge.
    """
    customer_id = users_db.get_stripe_customer_id(uid)
    if not customer_id:
        return [], [], False
    ids = []
    prepaid = []
    try:
        for sub in stripe.Subscription.list(customer=customer_id, status='all', limit=100).auto_paging_iter():
            data = sub.to_dict()
            metadata = data.get('metadata') or {}
            if metadata.get('app_id') or metadata.get('uid') not in (None, uid):
                continue
            if str(data.get('id') or '').startswith('sub_') and data.get('status') in ('active', 'trialing'):
                ids.append(data['id'])
                if prepaid_code_config.is_prepaid_subscription(data):
                    prepaid.append(str(metadata.get('redeemed_promotion_code_id')))
    except Exception as error:
        logger.warning('play_billing stripe conflict check unavailable: %s', type(error).__name__)
        return ids, prepaid, True
    return ids, prepaid, False


def _record_stripe_conflict(
    uid: str, token_hash: str, state: PlayState, confirmed_billable_ids: tuple[str, ...] = ()
) -> None:
    """Play is live next to a paid Stripe subscription. Nothing is cancelled: a person fixes it.

    Logs ``play_billing_double_charge`` every time (an alert watches it), stamps the first time it was seen,
    and tells the user once; a failed notice is sent again on the next observation.
    Runbook: backend/docs/runbooks/play-billing-double-charge.md.

    ``confirmed_billable_ids`` are billable subscriptions an earlier listing in the same call already
    found; they count even if this second listing fails before reaching them.
    """
    stripe_ids, prepaid_codes, listing_failed = _paid_stripe_subscription_ids(uid)
    has_billable_id = len(stripe_ids) > len(prepaid_codes) or bool(confirmed_billable_ids)
    unverified = (
        not has_billable_id
        and listing_failed
        and _holds_live_paid_row(uid, exclude_play=True, require_billable_stripe=True)
    )
    if unverified:
        # Degraded evidence: the Stripe listing failed, so the conflict rests on the stored row alone.
        record_fallback(
            component='play_billing',
            from_mode='stripe_listing',
            to_mode='local_row',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
    if not has_billable_id and not unverified:
        if prepaid_codes:
            # Only prepaid codes were found. They charge nothing, so there is no double charge to report.
            logger.error(prepaid_code_config.PLAY_OVERLAP_LOG, uid, token_hash[:12], prepaid_codes[0])
        else:
            logger.warning('play_billing Stripe overlap not confirmed as a paid subscription uid=%s', uid)
        return
    logger.error(DOUBLE_CHARGE_LOG, uid, token_hash[:12], state.state)
    now = int(time.time())
    play_db.mark_once(token_hash, CONFLICT_FIELD, now)
    if unverified:
        play_db.mark_once(token_hash, CONFLICT_UNVERIFIED_FIELD, now)
    if (play_db.get_purchase(token_hash) or {}).get(CONFLICT_NOTIFIED_FIELD):
        return
    # One sender at a time: claim the notice atomically; an abandoned claim expires and is retried.
    if not play_db.compare_and_set(
        token_hash,
        CONFLICT_NOTICE_CLAIM_FIELD,
        now,
        lambda claimed: not claimed or claimed < now - NOTICE_CLAIM_SECONDS,
    ):
        return
    try:
        outcome = dispatch_notification(
            NotificationIntent(
                user_id=uid,
                title='You already have Omi Pro',
                body='You are billed for Omi Pro by card and by Google Play. We will cancel one and refund it.',
                source='play_billing_double_billing',
                kind=NotificationKind.BILLING_CONFLICT,
            )
        )
    except Exception:
        outcome = None
    if outcome is not None and outcome.status == NotificationDispatchStatus.DISPATCHED and (outcome.delivered or 0) > 0:
        play_db.mark_once(token_hash, CONFLICT_NOTIFIED_FIELD, now)
        return
    logger.warning('play_billing double charge notice not delivered for uid=%s', uid)
    play_db.compare_and_set(token_hash, CONFLICT_NOTICE_CLAIM_FIELD, None, lambda claimed: claimed == now)


def _settle(uid: str, token_hash: str, state: PlayState, token: str, publisher: PublisherClient, *, fresh: bool) -> str:
    """Project Google's state for a token already bound to ``uid``: grant, hold pending, or remove.

    ``fresh`` means this call is the first to bind the token, so a live Stripe subscription refuses
    it outright (unacknowledged, Google refunds it). For an older token a live Stripe row is
    never overwritten: the two are logged as double billing instead of flip-flopping each period.
    """
    if state.has_access(int(time.time())):
        if account_deletion_blocks_user_work(uid):
            raise PlayBillingError(409, 'account_deletion_pending', 'This account is being deleted.')
        pointer = play_db.get_user_pointer(uid)
        live_stripe, billable_ids = _live_stripe_evidence(uid)
        if live_stripe:
            if fresh or not state.acknowledged:
                raise PlayBillingError(*_STRIPE_ACTIVE)
            _record_stripe_conflict(uid, token_hash, state, billable_ids)
            return 'stripe_conflict'
        if pointer and pointer != token_hash and _holds_live_paid_row(uid):
            return 'not_current'  # a newer Play token owns the live row
        _acknowledge(publisher, state, token)
        _grant(uid, replace(state, acknowledged=True), token_hash)
        if state.test_purchase:
            # License-tester purchases grant like real ones (internal testing); keep them visible.
            logger.warning('play_billing test purchase granted uid=%s token=%s', uid, token_hash[:12])
        if state.offer_id == config.trial_offer_id() and not fresh:
            logger.info('play_billing trial granted via notification uid=%s', uid)
        return 'active'
    if state.state == STATE_PENDING:
        play_db.set_user_fields(uid, {play_db.PENDING_FIELD: token_hash})
        return 'pending'
    _clear_pending(uid, token_hash)
    return 'revoked' if _revoke(uid, token_hash) else 'inactive'


def verify_and_bind(uid: str, purchase_token: str, product_id: str, publisher: Optional[PublisherClient] = None):
    """Validate a client-reported purchase, bind it to ``uid`` and grant Omi Pro when Google says it is paid."""
    publisher = publisher or get_publisher()
    if product_id in config.LEGACY_PRODUCT_IDS:
        logger.warning('play_billing legacy product refused: product=%s', product_id)
        raise PlayBillingError(400, 'legacy_product', 'This older Omi subscription cannot be restored here.')
    if product_id != config.product_id():
        raise PlayBillingError(400, 'unknown_product', 'This purchase is not an Omi Pro subscription.')
    now = int(time.time())
    state = _fetch(publisher, purchase_token)
    _check_product(state)
    try:
        expected_account = obfuscated_account_id(uid)
    except config.AccountIdKeyMissing:
        logger.error('play_billing verify refused: %s is not configured', config.ACCOUNT_ID_KEY_ENV)
        raise PlayBillingError(503, 'play_not_configured', 'Google Play purchases are unavailable. Try again later.')
    if state.obfuscated_account_id and not hmac.compare_digest(
        state.obfuscated_account_id.encode(), expected_account.encode()
    ):
        raise PlayBillingError(*_OWNED_ELSEWHERE)
    if account_deletion_blocks_user_work(uid):
        raise PlayBillingError(409, 'account_deletion_pending', 'This account is being deleted.')

    token_hash = play_db.token_key(purchase_token)
    existing = play_db.get_purchase(token_hash) or {}
    if existing.get('uid') and existing['uid'] != uid:
        raise PlayBillingError(*_OWNED_ELSEWHERE)
    if state.linked_token:
        linked = play_db.get_purchase(play_db.token_key(state.linked_token))
        if linked and linked.get('uid') and linked['uid'] != uid:
            raise PlayBillingError(*_OWNED_ELSEWHERE)
    through = refunded_through(existing)
    if not paid_after_refund(state, through):
        raise PlayBillingError(*_REFUNDED)

    fresh = existing.get('uid') != uid
    if fresh and state.has_access(now) and _live_stripe_subscription(uid):
        raise PlayBillingError(*_STRIPE_ACTIVE)
    play_db.remember_account(expected_account, uid)
    # History marker first: checkout must never see a bound purchase without it (a marker alone is harmless).
    play_db.mark_play_history(uid)
    owner = play_db.bind_purchase(token_hash, uid, _record(state, purchase_token, now, revoked_through=through))
    if owner != uid:
        raise PlayBillingError(*_OWNED_ELSEWHERE)
    outcome = _settle(uid, token_hash, state, purchase_token, publisher, fresh=fresh)
    if outcome == 'active':
        return VerifyResult('active', play_subscription(replace(state, acknowledged=True), now))
    if outcome == 'pending':
        return VerifyResult('pending', None)
    return VerifyResult('inactive', None)


def _resolve_unbound_owner(state: PlayState) -> Optional[str]:
    """uid for a token no client delivered: through the previous token, else the obfuscated account id."""
    linked_owner = None
    if state.linked_token:
        linked_owner = (play_db.get_purchase(play_db.token_key(state.linked_token)) or {}).get('uid')
    account_owner = play_db.account_uid(state.obfuscated_account_id) if state.obfuscated_account_id else None
    if account_owner and not hmac.compare_digest(
        obfuscated_account_id(account_owner).encode(), (state.obfuscated_account_id or '').encode()
    ):
        # The map only ever holds ids the server issued; anything else is refused.
        logger.warning('play_billing account map entry does not match its uid; not bound')
        account_owner = None
    if linked_owner and account_owner and linked_owner != account_owner:
        logger.warning('play_billing unbound token: linked and account owners disagree; not bound')
        return None
    return linked_owner or account_owner


def _latest_order_ids(resource: Mapping[str, Any]) -> set[str]:
    ids = {str(resource.get('latestOrderId') or '')}
    for item in resource.get('lineItems') or []:
        if isinstance(item, Mapping):
            ids.add(str(item.get('latestSuccessfulOrderId') or ''))
    ids.discard('')
    return ids


def apply_token(
    purchase_token: str,
    publisher: Optional[PublisherClient] = None,
    *,
    revoked: bool = False,
    voided_order_id: Optional[str] = None,
) -> str:
    """Re-read one token from Google and project it onto its account. Returns the outcome label."""
    publisher = publisher or get_publisher()
    now = int(time.time())
    token_hash = play_db.token_key(purchase_token)
    try:
        resource = publisher.get_subscription(config.package_name(), purchase_token)
    except PurchaseNotFound:
        play_db.update_purchase(token_hash, {'next_check_at': None, 'state': 'NOT_FOUND', 'updated_at': now})
        existing = play_db.get_purchase(token_hash) or {}
        if existing.get('uid'):
            _revoke(existing['uid'], token_hash)
        return 'not_found'
    except Exception as error:
        # Transport errors can carry the request URL, which holds the token: keep the type name only.
        logger.warning('play_billing publisher read failed: %s', type(error).__name__)
        raise PlayBillingError(503, 'play_unavailable', 'Google Play is unavailable. Try again.') from None
    state = read_state(resource)
    latest_orders = _latest_order_ids(resource)
    # Without Google's order ids the voided order cannot be shown to be an earlier one: revoke (fail closed).
    if revoked and voided_order_id and latest_orders and voided_order_id not in latest_orders:
        # A refund of an earlier order: the current period was paid separately and keeps its access.
        logger.info('play_billing refund of an earlier order; current period kept')
        revoked = False
    existing = play_db.get_purchase(token_hash) or {}
    through = refunded_through(existing)
    if revoked:
        # Refund or revoke: the period Google showed at that moment is no longer paid for.
        through = max(through or 0, state.expiry or now)
    record = _record(state, purchase_token, now, revoked_through=through)
    uid = existing.get('uid')
    if state.product_id != config.product_id():
        play_db.record_unbound(token_hash, record) if not uid else play_db.update_purchase(token_hash, record)
        if state.product_id in config.LEGACY_PRODUCT_IDS:
            logger.warning('play_billing legacy product notification ignored: product=%s', state.product_id)
            return 'legacy_product'
        return 'ignored_product'
    fresh = False
    if not uid:
        uid = _resolve_unbound_owner(state)
        if not uid:
            play_db.record_unbound(token_hash, record)
            logger.warning('play_billing notification for a token with no known owner; recorded, not granted')
            return 'unbound'
        play_db.mark_play_history(uid)  # before the bind: see verify_and_bind
        if play_db.bind_purchase(token_hash, uid, record) != uid:
            return 'unbound'
        fresh = True
    else:
        play_db.mark_play_history(uid)  # repairs a marker an earlier attempt never wrote
        play_db.update_purchase(token_hash, record)
    if revoked or not paid_after_refund(state, through):
        _clear_pending(uid, token_hash)
        return 'revoked' if _revoke(uid, token_hash) else 'inactive'
    return _settle(uid, token_hash, state, purchase_token, publisher, fresh=fresh)


def reconcile_due(publisher: Optional[PublisherClient] = None, limit: int = 200) -> dict[str, int]:
    """Re-read open purchases whose next check has passed (missed notifications, expiries)."""
    publisher = publisher or get_publisher()
    counts: dict[str, int] = {}
    for record in play_db.due_for_reconcile(int(time.time()), limit):
        token = record.get('purchase_token')
        if not token:
            continue
        try:
            outcome = apply_token(token, publisher)
        except PlayBillingError as error:
            outcome = error.code
        except Exception as error:
            logger.warning('play_billing reconcile failed: %s', type(error).__name__)
            outcome = 'error'
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


# RTDN SubscriptionNotification types that remove access regardless of Google's current state read.
NOTIFICATION_REVOKED = 12


def handle_developer_notification(notification: Mapping[str, Any], publisher: Optional[PublisherClient] = None) -> str:
    """Apply one decoded DeveloperNotification. Unknown packages and test pings are acknowledged and ignored."""
    if notification.get('packageName') != config.package_name():
        return 'ignored_package'
    if 'testNotification' in notification:
        return 'test'
    voided = notification.get('voidedPurchaseNotification')
    if isinstance(voided, Mapping) and voided.get('purchaseToken'):
        # Refund or chargeback on a subscription purchase: access ends now.
        order = voided.get('orderId')
        return apply_token(
            str(voided['purchaseToken']), publisher, revoked=True, voided_order_id=str(order) if order else None
        )
    sub = notification.get('subscriptionNotification')
    if isinstance(sub, Mapping) and sub.get('purchaseToken'):
        revoked = sub.get('notificationType') == NOTIFICATION_REVOKED
        return apply_token(str(sub['purchaseToken']), publisher, revoked=revoked)
    return 'ignored'


def client_config(uid: str):
    """The ``play_billing`` block of the subscription response."""
    from models.users import PlayBillingConfig

    return PlayBillingConfig.model_validate(config.client_config_payload(uid))
