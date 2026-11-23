"""Google Play Billing for Omi Pro: verify, bind, acknowledge and keep the entitlement current.

Google's ``purchases.subscriptionsv2`` resource is the only source of truth; a notification or a
client report only names the token to re-read. Entitlement writes reuse the Stripe path's helpers
(``update_user_subscription`` + unlocks + fair-use clear), so a Play subscriber holds exactly what
a Stripe Omi Pro subscriber holds.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Mapping, Optional, Protocol

import stripe

import database.play_subscriptions as play_db
import database.users as users_db
from config import play_billing as config
from database import action_items as action_items_db, conversations as conversations_db, memories as memories_db
from database import redis_db
from database.account_deletion_marker import account_deletion_blocks_user_work
from models.users import PlanType, Subscription, SubscriptionStatus
from utils.fair_use import clear_fair_use_on_upgrade
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


class PlayBillingError(Exception):
    """Typed refusal with the HTTP status and stable code the route returns."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class PublisherClient(Protocol):
    def get_subscription(self, package_name: str, token: str) -> dict: ...

    def acknowledge(self, package_name: str, product_id: str, token: str) -> None: ...


class PurchaseNotFound(Exception):
    """Google says the token does not exist for this package."""


_PUBLISHER_API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications'


class _GooglePublisher:
    """Android Publisher v3 REST over google-auth (built lazily on first use)."""

    def __init__(self):
        from urllib.parse import quote

        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        scopes = ['https://www.googleapis.com/auth/androidpublisher']
        key_file = os.getenv('PLAY_PUBLISHER_SERVICE_ACCOUNT_FILE')
        if key_file:
            credentials = service_account.Credentials.from_service_account_file(key_file, scopes=scopes)
        else:
            credentials, _ = google.auth.default(scopes=scopes)
        self._session = AuthorizedSession(credentials)
        self._quote = lambda value: quote(value, safe='')

    def get_subscription(self, package_name: str, token: str) -> dict:
        url = f'{_PUBLISHER_API}/{self._quote(package_name)}/purchases/subscriptionsv2/tokens/{self._quote(token)}'
        response = self._session.get(url, timeout=15)
        if response.status_code in (400, 404, 410):
            raise PurchaseNotFound()
        response.raise_for_status()
        return response.json()

    def acknowledge(self, package_name: str, product_id: str, token: str) -> None:
        url = (
            f'{_PUBLISHER_API}/{self._quote(package_name)}/purchases/subscriptions/'
            f'{self._quote(product_id)}/tokens/{self._quote(token)}:acknowledge'
        )
        response = self._session.post(url, json={}, timeout=15)
        response.raise_for_status()


_publisher: Optional[PublisherClient] = None


def get_publisher() -> PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = _GooglePublisher()
    return _publisher


def obfuscated_account_id(uid: str) -> str:
    """Stable 64-char id the app passes to Play; Google echoes it on the purchase."""
    return hashlib.sha256(f'omi-play-account:{uid}'.encode('utf-8')).hexdigest()


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
        return self.state in ACCESS_STATES and self.expiry is not None and self.expiry > now


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


def _record(state: PlayState, token: str, now: int, *, revoked: bool = False) -> dict:
    open_state = state.state in OPEN_STATES and not revoked
    next_check = None
    if open_state:
        next_check = now + RECHECK_SECONDS
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
        'revoked': revoked,
        'next_check_at': next_check,
        'updated_at': now,
    }


def play_subscription(state: PlayState) -> Subscription:
    """The Omi Pro row a Stripe subscription with the same period would store."""
    return Subscription(
        plan=PLAY_PLAN,
        status=SubscriptionStatus.active,
        current_period_end=state.expiry,
        current_period_start=state.start,
        cancel_at_period_end=not state.auto_renewing,
        limits=get_plan_limits(PLAY_PLAN),
        provider='play',
    )


def _grant(uid: str, state: PlayState) -> Subscription:
    # Same write + side effects as the Stripe upgrade paths (routers/monthly_switch._store).
    subscription = play_subscription(state)
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


def _holds_live_paid_row(uid: str, *, exclude_play: bool = False) -> bool:
    stored = users_db.get_user_valid_subscription(uid, include_promotions=False)
    return bool(
        stored is not None
        and is_paid_plan(stored.plan)
        and not (exclude_play and stored.provider == 'play')
        and stored.current_period_end
        and stored.current_period_end > int(time.time())
    )


def _live_stripe_subscription(uid: str) -> bool:
    """A paid non-Play entitlement this user still holds (stored row or Stripe itself)."""
    if _holds_live_paid_row(uid, exclude_play=True):
        return True
    customer_id = users_db.get_stripe_customer_id(uid)
    if not customer_id:
        return False
    try:
        subs = stripe.Subscription.list(customer=customer_id, limit=10)
    except Exception as error:
        logger.warning('play_billing stripe check unavailable: %s', type(error).__name__)
        raise PlayBillingError(503, 'billing_check_unavailable', 'Could not verify billing. Try again.') from None
    for sub in subs.data:
        data = sub.to_dict()
        if (data.get('metadata') or {}).get('app_id'):
            continue
        if data.get('status') in ('active', 'trialing', 'past_due'):
            return True
    return False


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


def verify_and_bind(uid: str, purchase_token: str, product_id: str, publisher: Optional[PublisherClient] = None):
    """Validate a client-reported purchase, bind it to ``uid`` and grant Omi Pro when Google says it is paid."""
    publisher = publisher or get_publisher()
    if product_id != config.product_id():
        raise PlayBillingError(400, 'unknown_product', 'This purchase is not an Omi Pro subscription.')
    now = int(time.time())
    state = _fetch(publisher, purchase_token)
    _check_product(state)
    expected_account = obfuscated_account_id(uid)
    if state.obfuscated_account_id and state.obfuscated_account_id != expected_account:
        raise PlayBillingError(409, 'purchase_owned_elsewhere', 'This purchase belongs to another Omi account.')
    if account_deletion_blocks_user_work(uid):
        raise PlayBillingError(409, 'account_deletion_pending', 'This account is being deleted.')

    token_hash = play_db.token_key(purchase_token)
    existing = play_db.get_purchase(token_hash)
    if existing and existing.get('uid') and existing['uid'] != uid:
        raise PlayBillingError(409, 'purchase_owned_elsewhere', 'This purchase belongs to another Omi account.')
    if state.linked_token:
        linked = play_db.get_purchase(play_db.token_key(state.linked_token))
        if linked and linked.get('uid') and linked['uid'] != uid:
            raise PlayBillingError(409, 'purchase_owned_elsewhere', 'This purchase belongs to another Omi account.')

    granting = state.has_access(now)
    already_ours = bool(existing and existing.get('uid') == uid)
    if granting and not already_ours and _live_stripe_subscription(uid):
        raise PlayBillingError(
            409,
            'stripe_subscription_active',
            'You already have Omi Pro billed outside Google Play. Cancel it before subscribing here.',
        )

    if granting:
        _acknowledge(publisher, state, purchase_token)
        state = replace(state, acknowledged=True)
    owner = play_db.bind_purchase(token_hash, uid, _record(state, purchase_token, now))
    if owner != uid:
        raise PlayBillingError(409, 'purchase_owned_elsewhere', 'This purchase belongs to another Omi account.')

    if granting:
        play_db.set_user_pointer(uid, token_hash)
        return VerifyResult('active', _grant(uid, state))
    if state.state == STATE_PENDING:
        return VerifyResult('pending', None)
    _revoke(uid, token_hash)
    return VerifyResult('inactive', None)


def apply_token(purchase_token: str, publisher: Optional[PublisherClient] = None, *, revoked: bool = False) -> str:
    """Re-read one token from Google and project it onto its bound account. Returns the outcome label."""
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
    state = read_state(resource)
    record = _record(state, purchase_token, now, revoked=revoked)
    existing = play_db.get_purchase(token_hash)
    uid = (existing or {}).get('uid')
    if not uid:
        play_db.record_unbound(token_hash, record)
        return 'unbound'
    play_db.update_purchase(token_hash, record)
    if state.product_id != config.product_id():
        return 'ignored_product'
    if not revoked and state.has_access(now):
        if account_deletion_blocks_user_work(uid):
            return 'deletion_fenced'
        if play_db.get_user_pointer(uid) != token_hash and _holds_live_paid_row(uid):
            # Never overwrite another live entitlement (Stripe, or a newer Play token).
            return 'not_current'
        if not state.acknowledged:
            _acknowledge(publisher, state, purchase_token)
        play_db.set_user_pointer(uid, token_hash)
        _grant(uid, state)
        return 'active'
    return 'revoked' if _revoke(uid, token_hash) else 'inactive'


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
        return apply_token(str(voided['purchaseToken']), publisher, revoked=True)
    sub = notification.get('subscriptionNotification')
    if isinstance(sub, Mapping) and sub.get('purchaseToken'):
        revoked = sub.get('notificationType') == NOTIFICATION_REVOKED
        return apply_token(str(sub['purchaseToken']), publisher, revoked=revoked)
    return 'ignored'


def client_config(uid: str):
    """The ``play_billing`` block of the subscription response."""
    from models.users import PlayBasePlan, PlayBillingConfig

    return PlayBillingConfig(
        product_id=config.product_id(),
        base_plans=[
            PlayBasePlan(id=plan_id, interval='year' if interval == 'year' else 'month')
            for plan_id, interval in config.base_plans().items()
        ],
        trial_offer_id=config.trial_offer_id(),
        obfuscated_account_id=obfuscated_account_id(uid),
    )
