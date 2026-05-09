"""
Superwall webhook handler — receives normalized purchase lifecycle events from
Superwall (which itself reconciles App Store Server Notifications + Google Play
Real-Time Developer Notifications) and updates ``user.subscription`` in
Firestore.

Auth: svix signature verification over the **raw request body**. Body MUST NOT
be parsed before verification — re-serializing changes whitespace and the
HMAC fails. Set ``SUPERWALL_WEBHOOK_SECRET`` (the ``whsec_…`` string from the
Superwall dashboard) at deploy time.

Idempotency: each webhook carries a unique ``svix-id`` header. We persist
processed ids in Firestore (``superwall_events/{svix_id}``) and short-circuit
on duplicates so svix retries can't double-apply a purchase.

Conflict handling: if the resolved omi user already has an active Stripe
subscription (``source == stripe``), we still accept the new Superwall sub
(Apple/Google have already charged the user) but log a warning so ops can
follow up. The mobile app surfaces a one-time toast asking the user to cancel
the Stripe sub themselves — we cannot refund or auto-cancel from here.

Event types handled (per Superwall docs):
  initial_purchase    — first purchase / start of trial
  renewal             — billing cycle rolled over
  cancellation        — user clicked cancel; sub stays active until period_end
  expiration          — sub fully ended (post-period_end or after retry exhaustion)
  billing_issue       — payment failed; Apple/Google retry window in progress
  product_change      — mid-cycle plan switch (upgrade/downgrade)
  subscription_paused — Play Store pause feature
  non_renewing_purchase — one-time IAP (no consumables today; no-op)
  uncancellation      — user re-enabled an already-cancelled sub before it expired
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

import database.users as users_db
from database import superwall_events as events_db
from database.plan_caps_config import get_superwall_product_map
from models.users import PlanType, Subscription, SubscriptionSource, SubscriptionStatus
from utils.log_sanitizer import sanitize

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Signature verification (svix v1) ────────────────────────────────────────


# Ignore signatures whose timestamps are this far from now. svix retries up to
# ~24h, but a legitimate replay from > 5 minutes ago is suspicious. Set to 0 to
# disable timestamp gating (e.g. when replaying historical events in test).
_SIGNATURE_TOLERANCE_SECONDS = 5 * 60


def _decode_secret(secret: str) -> bytes:
    """svix secrets ship as ``whsec_<base64>``. Strip prefix + decode."""
    if secret.startswith('whsec_'):
        secret = secret[len('whsec_') :]
    return base64.b64decode(secret)


def _expected_signature(secret: bytes, svix_id: str, svix_timestamp: str, body: bytes) -> str:
    payload_to_sign = f'{svix_id}.{svix_timestamp}.'.encode() + body
    digest = hmac.new(secret, payload_to_sign, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_signature(
    secret: str,
    svix_id: Optional[str],
    svix_timestamp: Optional[str],
    svix_signature: Optional[str],
    body: bytes,
    now: Optional[int] = None,
) -> bool:
    """Verify a svix-format webhook signature over ``body``.

    The signature header is space-separated ``v<version>,<base64-hmac>`` tokens
    — only ``v1`` is checked. Comparison uses ``hmac.compare_digest`` for
    constant-time equality.
    """
    if not (secret and svix_id and svix_timestamp and svix_signature and body):
        return False

    # Replay protection: reject if the dispatcher's claimed timestamp is too old.
    if _SIGNATURE_TOLERANCE_SECONDS > 0:
        try:
            ts = int(svix_timestamp)
        except (TypeError, ValueError):
            return False
        if abs((now if now is not None else int(time.time())) - ts) > _SIGNATURE_TOLERANCE_SECONDS:
            return False

    try:
        expected = _expected_signature(_decode_secret(secret), svix_id, svix_timestamp, body)
    except Exception:
        return False

    for token in svix_signature.split():
        if not token.startswith('v1,'):
            continue
        candidate = token[len('v1,') :]
        if hmac.compare_digest(candidate, expected):
            return True
    return False


# ── Product → PlanType resolution ───────────────────────────────────────────


def resolve_plan(product_id: str) -> Optional[PlanType]:
    """Map a Superwall ``product_id`` (App Store or Play SKU) to a ``PlanType``.

    Reads the ``superwall_product_map`` from the ``app_config/plan_caps``
    Firestore doc so new SKUs can be wired in without a redeploy. Returns
    ``None`` if the product isn't recognized — caller should reject the event.
    """
    mapping = get_superwall_product_map() or {}
    plan_value = mapping.get(product_id)
    if not plan_value:
        return None
    try:
        return PlanType(plan_value)
    except ValueError:
        logger.error(
            f"[superwall] product {sanitize(product_id)} is mapped to unknown PlanType {sanitize(plan_value)} "
            "— check app_config/plan_caps.superwall_product_map"
        )
        return None


def _detect_source(event: dict) -> SubscriptionSource:
    """Infer ``superwall_ios`` vs ``superwall_android`` from event metadata."""
    store = (event.get('store') or event.get('app_store') or '').lower()
    if 'play' in store or 'google' in store or 'android' in store:
        return SubscriptionSource.superwall_android
    return SubscriptionSource.superwall_ios


# ── Per-event handlers ──────────────────────────────────────────────────────


def _build_subscription(
    plan: PlanType,
    source: SubscriptionSource,
    superwall_sub_id: Optional[str],
    current_period_end: Optional[int],
    cancel_at_period_end: bool = False,
) -> dict:
    sub = Subscription(
        plan=plan,
        status=SubscriptionStatus.active,
        source=source,
        superwall_subscription_id=superwall_sub_id,
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )
    return sub.dict()


def _existing_active_stripe(uid: str) -> bool:
    sub = users_db.get_user_valid_subscription(uid)
    if not sub:
        return False
    return sub.source == SubscriptionSource.stripe and sub.status == SubscriptionStatus.active


def handle_initial_purchase(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    if _existing_active_stripe(uid):
        # Apple/Google have already charged the card. We accept the Superwall
        # sub but flag the conflict so ops + the app can ask the user to cancel
        # the Stripe one. We do NOT auto-cancel Stripe — that's a manual call.
        logger.warning(
            f"[superwall] uid={uid} purchased Superwall {plan.value} while an active Stripe sub exists; "
            "accepting new sub, app will surface a manage-existing-sub toast"
        )
    users_db.update_user_subscription(
        uid,
        _build_subscription(
            plan=plan,
            source=source,
            superwall_sub_id=event.get('subscription_id') or event.get('id'),
            current_period_end=event.get('expires_at'),
        ),
    )


def handle_renewal(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """Bump period_end + ensure status=active. Treats renewal of a previously
    cancelled sub the same as fresh activation (cancel_at_period_end clears).
    """
    users_db.update_user_subscription(
        uid,
        _build_subscription(
            plan=plan,
            source=source,
            superwall_sub_id=event.get('subscription_id') or event.get('id'),
            current_period_end=event.get('expires_at'),
            cancel_at_period_end=False,
        ),
    )


def handle_cancellation(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """User clicked cancel. Sub stays active until period_end."""
    users_db.update_user_subscription(
        uid,
        _build_subscription(
            plan=plan,
            source=source,
            superwall_sub_id=event.get('subscription_id') or event.get('id'),
            current_period_end=event.get('expires_at'),
            cancel_at_period_end=True,
        ),
    )


def handle_uncancellation(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    handle_renewal(uid, plan, source, event)


def handle_expiration(uid: str, _plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """Sub fully ended — revert to free tier. Source still reflects last paid rail
    so the desktop manage-button copy can stay correct ("Manage in iOS Settings")
    until the user explicitly re-subscribes via Stripe.
    """
    sub = Subscription(
        plan=PlanType.basic,
        status=SubscriptionStatus.inactive,
        source=source,
        superwall_subscription_id=event.get('subscription_id') or event.get('id'),
        current_period_end=event.get('expires_at'),
        cancel_at_period_end=False,
    )
    users_db.update_user_subscription(uid, sub.dict())


def handle_billing_issue(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """Apple/Google retry window in progress. Keep caps in force; flip status so
    UI can show an "update payment" banner.
    """
    sub = Subscription(
        plan=plan,
        status=SubscriptionStatus.inactive,  # we have no `past_due` enum value yet
        source=source,
        superwall_subscription_id=event.get('subscription_id') or event.get('id'),
        current_period_end=event.get('expires_at'),
        cancel_at_period_end=False,
    )
    users_db.update_user_subscription(uid, sub.dict())


def handle_product_change(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """Mid-cycle upgrade/downgrade — overwrite plan in place."""
    handle_renewal(uid, plan, source, event)


def handle_subscription_paused(uid: str, plan: PlanType, source: SubscriptionSource, event: dict) -> None:
    """Play Store pause — sub goes inactive temporarily. Treat as expiration for
    cap purposes; resume will fire a renewal when the user un-pauses.
    """
    handle_expiration(uid, plan, source, event)


_HANDLERS = {
    'initial_purchase': handle_initial_purchase,
    'renewal': handle_renewal,
    'cancellation': handle_cancellation,
    'uncancellation': handle_uncancellation,
    'expiration': handle_expiration,
    'billing_issue': handle_billing_issue,
    'product_change': handle_product_change,
    'subscription_paused': handle_subscription_paused,
    # non_renewing_purchase: no consumables in the catalog today → no-op
}


def dispatch_event(event_type: str, payload: dict) -> str:
    """Route a parsed webhook payload to its handler. Returns a status string
    for the response body / log line.

    Payload shape (per Superwall normalized webhook):
      {
        "type": "initial_purchase",
        "app_user_id": "<omi uid>",
        "product_id": "com.omi.app.lite_monthly",
        "subscription_id": "<superwall sub id>",
        "expires_at": <unix seconds>,
        "store": "app_store" | "play_store" | ...
      }
    """
    handler = _HANDLERS.get(event_type)
    if handler is None:
        return 'ignored'

    uid = payload.get('app_user_id')
    if not uid:
        logger.error(f"[superwall] event {event_type} missing app_user_id")
        return 'missing_uid'

    product_id = payload.get('product_id') or ''
    plan = resolve_plan(product_id)
    if plan is None and event_type != 'expiration':
        # Expiration doesn't need a current plan (we revert to basic regardless),
        # but every other handler does.
        logger.error(f"[superwall] unknown product_id {sanitize(product_id)} for event {event_type}")
        return 'unknown_product'

    source = _detect_source(payload)
    handler(uid, plan or PlanType.basic, source, payload)
    return 'processed'


# ── Route ───────────────────────────────────────────────────────────────────


@router.post('/v1/superwall/webhook', tags=['v1', 'superwall', 'webhook'])
async def superwall_webhook(
    request: Request,
    svix_id: Optional[str] = Header(default=None, alias='svix-id'),
    svix_timestamp: Optional[str] = Header(default=None, alias='svix-timestamp'),
    svix_signature: Optional[str] = Header(default=None, alias='svix-signature'),
):
    raw_body = await request.body()

    secret = os.getenv('SUPERWALL_WEBHOOK_SECRET', '')
    if not verify_signature(secret, svix_id, svix_timestamp, svix_signature, raw_body):
        # Don't log the body — could leak PII / secrets
        logger.warning(f"[superwall] signature verification failed for svix-id={sanitize(svix_id or '')}")
        raise HTTPException(status_code=401, detail='invalid signature')

    if events_db.already_processed(svix_id):
        return {'status': 'duplicate', 'svix_id': svix_id}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='invalid json')

    event_type = payload.get('type') or ''
    result = dispatch_event(event_type, payload)

    # Record AFTER successful dispatch so a transient failure doesn't leave us
    # with a "processed" marker we'll never re-attempt. svix will retry on a
    # non-2xx and our second pass will succeed.
    events_db.record_processed(svix_id, event_type, payload.get('app_user_id'))

    return {'status': result, 'event_type': event_type}
