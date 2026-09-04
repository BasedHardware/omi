import os
from dataclasses import dataclass
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from fastapi import HTTPException
from firebase_admin import auth as firebase_auth
import stripe

import database.users as users_db
import database.user_usage as user_usage_db
from database import redis_db
from database._client import get_customer_firestore_client
from database.announcements import compare_versions
from config.plan_catalog import (
    DESKTOP_ENTITLED_PLAN_TYPES,
    MOBILE_PLAN_TYPES,
    PAID_PLAN_TYPES,
    PLAN_DISPLAY_NAMES,
    PRIMARY_BILLING_ENV_VARS,
    RECOGNIZED_STRIPE_PRICE_INTERVALS,
    allocation_limit,
    get_plan_allocation,
    plan_uses_overage,
    resolve_stripe_price_plan,
)
from models.users import PlanType, SubscriptionStatus, Subscription, PlanLimits, TrialMetadata
from utils.byok import get_byok_key, get_byok_uid, get_cached_byok_state, has_validated_byok_keys
from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback
import logging

logger = logging.getLogger(__name__)


def _get_user(uid: str) -> Any:
    return firebase_auth.get_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped


# Effective desktop tiers are used for Desktop-specific admission decisions.
# Never use DESKTOP_ENTITLED_PLAN_TYPES as a zero-access check: it represents
# full Desktop entitlement, while ``desktop_free`` is a valid usable floor.
DESKTOP_ACCESS_TIER_FREE = "desktop_free"
DESKTOP_ACCESS_TIER_FULL = "desktop_full"
DESKTOP_ACCESS_TIER_ARCHITECT = "desktop_architect"

# Grandfather: Neo subscriptions whose current billing period started before
# this cutoff retain desktop access until that period ends. At their next
# renewal, current_period_start advances past the cutoff and they fall under
# the new policy. Default is the merge timestamp of #7496 — the PR that first
# removed Neo from DESKTOP_ENTITLED_PLAN_TYPES — so users who bought Neo when
# desktop was de facto included aren't pulled mid-cycle. Env-overridable so
# the cutoff can shift if the policy date changes.
NEO_DESKTOP_GRANDFATHER_CUTOFF = int(os.getenv('NEO_DESKTOP_GRANDFATHER_CUTOFF', '1779748479'))


def plan_grants_desktop(plan: PlanType, subscription: Optional[Subscription] = None) -> bool:
    """True iff this plan unlocks the desktop (macOS) app for this subscriber.

    Operator and Architect always grant desktop. Neo grants desktop only under
    the legacy grandfather: when the subscription's current_period_start is
    before NEO_DESKTOP_GRANDFATHER_CUTOFF (or is None — existing pre-deploy
    subs without the field set are treated as legacy until their next webhook
    populates the field).
    """
    if plan in DESKTOP_ENTITLED_PLAN_TYPES:
        return True
    if plan == PlanType.unlimited and subscription is not None:
        cps = subscription.current_period_start
        if cps is None or cps < NEO_DESKTOP_GRANDFATHER_CUTOFF:
            return True
    return False


def effective_desktop_access_tier(plan: PlanType, subscription: Optional[Subscription] = None) -> str:
    """Return the usable Desktop tier for a subscription.

    Free is the minimum Desktop tier. A Neo (``unlimited``) subscriber who is
    not in the full-Desktop grandfather period therefore receives
    ``desktop_free`` rather than no Desktop access. Operator and grandfathered
    Neo receive ``desktop_full``; Architect receives its separate premium tier.
    """
    if plan == PlanType.architect:
        return DESKTOP_ACCESS_TIER_ARCHITECT
    if plan_grants_desktop(plan, subscription):
        return DESKTOP_ACCESS_TIER_FULL
    return DESKTOP_ACCESS_TIER_FREE


def desktop_trial_paywall_eligible(plan: PlanType, subscription: Optional[Subscription] = None) -> bool:
    """Whether a plan can be blocked by the Desktop account-age trial paywall.

    The account-age paywall is only for users on the Free tier. Neo is mapped
    to the usable Free Desktop tier when it lacks full Desktop entitlement, but
    it is still an active paid plan and must never be converted into zero audio,
    chat, or realtime access.
    """
    return effective_desktop_access_tier(plan, subscription) == DESKTOP_ACCESS_TIER_FREE and plan not in PAID_PLAN_TYPES


def neo_grandfather_until(subscription: Optional[Subscription]) -> Optional[int]:
    """If the subscriber is currently grandfathered onto Neo desktop, return
    the unix-seconds timestamp when that access ends (their current period end).
    Otherwise None. Used by the API response so the desktop client can render a
    "Neo desktop access ends on <date>" notice.
    """
    if subscription is None or subscription.plan != PlanType.unlimited:
        return None
    if not plan_grants_desktop(subscription.plan, subscription):
        return None
    return subscription.current_period_end


# Cloud screen-activity vectors are a paid desktop capability.
#
# Screen rows themselves are cheap; the vector is not. Embedding and storing a 3,072-dim vector
# per delivered row is the large majority of what a synced screen row costs, and the vector's
# only purpose server-side is semantic screen search. Free-tier desktop users keep their rows in
# Firestore (so cloud chat can still read screen history by time and app) and keep on-device
# semantic search, which reads embeddings from the local store and never needs Pinecone.
#
# Because the rows are retained, a user who upgrades can have their vectors backfilled from the
# stored OCR text: this gate defers the cost, it does not destroy the ability to recover.
_SCREEN_VECTOR_ENTITLEMENT_CACHE_TTL_SECONDS = 300
_screen_vector_entitlement_cache: Dict[str, Tuple[bool, float]] = {}


def grants_cloud_screen_vectors(uid: str) -> bool:
    """True when this user's synced screen rows should also be written to the vector store.

    Uses the desktop access tier rather than `is_paid_plan`, because screen activity is a
    desktop capability: a mobile-only paid plan did not buy it. BYOK does NOT grant it either
    — BYOK means the user supplies their own LLM keys, but the vector store is ours and the
    cost being avoided here is ours.

    Fails OPEN (writes the vector) on any lookup error, matching
    `should_defer_desktop_processing`: a Firestore blip must never silently strip a paying
    user's screen search. The failure mode is a small overspend, not a lost capability.
    """
    cached = _screen_vector_entitlement_cache.get(uid)
    if cached is not None and time.monotonic() - cached[1] < _SCREEN_VECTOR_ENTITLEMENT_CACHE_TTL_SECONDS:
        return cached[0]
    try:
        subscription = users_db.get_user_valid_subscription(
            uid, firestore_client=get_customer_firestore_client(), provision=False
        )
        plan = subscription.plan if subscription else PlanType.basic
        entitled = effective_desktop_access_tier(plan, subscription) != DESKTOP_ACCESS_TIER_FREE
    except Exception as e:
        logger.warning("grants_cloud_screen_vectors lookup failed for uid=%s: %s", uid, e)
        return True
    _screen_vector_entitlement_cache[uid] = (entitled, time.monotonic())
    return entitled


def clear_cloud_screen_vector_entitlement_cache(uid: str) -> None:
    _screen_vector_entitlement_cache.pop(uid, None)


def should_defer_desktop_processing(uid: str) -> bool:
    """True for Desktop users on the Free effective tier without active BYOK.

    Free and non-grandfathered Neo users store a raw transcript on capture and
    defer expensive LLM enrichment until the first open. This cost policy must
    not be interpreted as a no-Desktop-access policy.

    Operator / Architect (desktop-entitled) and BYOK users (who pay their own LLM bill) are
    processed normally. The caller restricts this to `source == desktop`. Fails safe to False
    (process normally) on any error so a Firestore blip never silently strips a paid user's
    summaries.
    """
    try:
        if users_db.is_byok_active(uid) and get_byok_key('openai'):
            return False
        subscription = users_db.get_user_valid_subscription(uid)
        plan = subscription.plan if subscription else PlanType.basic
        return effective_desktop_access_tier(plan, subscription) == DESKTOP_ACCESS_TIER_FREE
    except Exception as e:
        logger.warning("should_defer_desktop_processing lookup failed for uid=%s: %s", uid, e)
        return False


# Desktop-only 3-day trial paywall.
#
# Applies to desktop users without a desktop-entitled plan (basic OR Neo) once
# their Firebase Auth account is older than TRIAL_LENGTH_SECONDS and they don't
# have BYOK active. Mobile (ios / android), Omi devices, desktop-entitled plans
# (Operator / Architect), BYOK users, and accounts inside the trial window are
# exempt.
TRIAL_LENGTH_SECONDS = 3 * 24 * 60 * 60  # 3 days

# Master switch for the desktop trial paywall. Default OFF: basic/Neo desktop users are
# never locked out (no 402) AND the client never sees `trial_expired=True`, so the
# "you've hit your monthly limit" upgrade popup does not fire just from account age — only
# the actual chat-question quota (30/mo) gates them. Set TRIAL_PAYWALL_ENABLED=true to
# restore the 3-day trial lockout. NOTE: this changes ONLY the trial paywall — plan limits
# (Neo questions, data-intake caps) are untouched.
TRIAL_PAYWALL_ENABLED = os.getenv('TRIAL_PAYWALL_ENABLED', 'false').lower() == 'true'

# X-App-Platform header values that identify a desktop client. macOS and Windows
# are the two desktop OSes; both get the desktop plan catalog, the desktop trial
# paywall, and desktop entitlement treatment. This is the single source of truth
# for "is this a desktop platform" — every desktop-vs-mobile gate below reads
# from here so a new desktop OS is wired in one place.
DESKTOP_PLATFORMS = {'macos', 'windows'}

# Platform identifiers that count as desktop for paywall purposes. The desktop
# clients send X-App-Platform: macos / windows and the listen WS uses
# source=desktop. Anything else (ios, android, omi device, phone_call, unknown)
# is exempt.
_TRIAL_PAYWALL_DESKTOP_TOKENS = DESKTOP_PLATFORMS | {"desktop"}

# Cache the (slow) Firebase Auth + Firestore lookup result for a few minutes
# so chat-quota polling doesn't fan out to Firebase on every request.
_TRIAL_PAYWALL_CACHE_TTL_SECONDS = 300


def request_has_llm_byok_key() -> bool:
    """True when request carries validated LLM BYOK keys matching active enrollment."""
    uid = get_byok_uid()
    if not uid or not has_validated_byok_keys():
        return False
    try:
        fingerprints = get_cached_byok_state(uid).get('fingerprints', {})
    except Exception:
        return any(get_byok_key(provider) for provider in ('openrouter', 'openai', 'anthropic', 'gemini'))
    return any(
        provider in fingerprints and bool(get_byok_key(provider))
        for provider in ('openrouter', 'openai', 'anthropic', 'gemini')
    )


_request_has_llm_byok_key = request_has_llm_byok_key


def _request_has_byok_provider(provider: str) -> bool:
    return has_validated_byok_keys() and bool(get_byok_key(provider))


def _is_trial_expired_uncached(
    uid: str,
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_byok_provider: str | None = None,
    strict: bool = False,
) -> bool:
    """Is this user past their 3-day desktop trial?

    The trial applies only to the Free Desktop tier. Neo may use that tier for
    non-premium capabilities, but is paid and must never be reduced to zero
    access. BYOK users are also bypassed. Returns False on any lookup error so
    a Firebase blip never paywalls a paying user — unless ``strict``, the mode
    for a caller that must fail closed (a billed socket): there, a lookup error
    or an unreadable account record propagates, and a BYOK exemption needs a
    validated key on this request, never a stored fingerprint alone.
    """
    try:
        if required_byok_provider and _request_has_byok_provider(required_byok_provider):
            return False
        subscription = users_db.get_user_valid_subscription(uid, firestore_client=firestore_client, provision=provision)
        plan = subscription.plan if subscription else PlanType.basic
        if not desktop_trial_paywall_eligible(plan, subscription):
            return False
        if users_db.is_byok_active(uid, firestore_client=firestore_client):
            if not required_byok_provider:
                return False
            # A stored fingerprint exempts ordinary callers; the strict caller
            # already required the key on this request (checked first above).
            if not strict:
                fingerprints = users_db.get_byok_state(uid, firestore_client=firestore_client).get('fingerprints')
                if isinstance(fingerprints, dict) and fingerprints.get(required_byok_provider):
                    return False
        user_record = _get_user(uid)
        creation_ms: int = cast(int, user_record.user_metadata.creation_timestamp)
        if not creation_ms:
            if strict:
                raise ValueError('account creation timestamp unavailable')
            return False
        age_seconds = time.time() - (creation_ms / 1000)
        return age_seconds > TRIAL_LENGTH_SECONDS
    except Exception as e:
        if strict:
            raise
        logger.warning("trial paywall lookup failed for uid=%s: %s", uid, e)
        return False


def _is_trial_expired_cached(
    uid: str,
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_byok_provider: str | None = None,
    strict: bool = False,
) -> bool:
    # Request-level escape hatch: a request carrying an enrolled LLM BYOK
    # provider header is never paywalled, regardless of cached Firestore state.
    # The cache TTL is 5 min and Firestore's BYOK `is_active` heartbeat is 24 h,
    # so even a perfectly-configured BYOK user can transiently look stale to
    # Firestore. Trust the live request.
    if required_byok_provider:
        if _request_has_byok_provider(required_byok_provider):
            return False
    elif _request_has_llm_byok_key():
        return False

    cache_key = (
        f"trial_paywall:expired:{uid}:{required_byok_provider}"
        if required_byok_provider
        else f"trial_paywall:expired:{uid}"
    )
    if strict:
        # Strict answers are computed under stricter rules (no fingerprint-only
        # exemption, unreadable record is an error) and must never consume a
        # False that an ordinary caller cached under the lenient ones.
        cache_key = f"{cache_key}:strict"
    cached = redis_db.get_generic_cache(cache_key)
    if cached is not None:
        # A cache entry may have been written before an entitlement correction
        # or a plan migration. Revalidate a positive value so a paid Neo user
        # is not left with a zero-access decision until this key's TTL expires.
        if cached:
            try:
                subscription = users_db.get_user_valid_subscription(
                    uid, firestore_client=firestore_client, provision=provision
                )
                plan = subscription.plan if subscription else PlanType.basic
                if not desktop_trial_paywall_eligible(plan, subscription):
                    clear_trial_paywall_cache(uid)
                    record_fallback(
                        component='other',
                        from_mode='trial_paywall',
                        to_mode=effective_desktop_access_tier(plan, subscription),
                        reason='local_heal',
                        outcome='recovered',
                        log=logger,
                    )
                    return False
            except Exception as e:
                if strict:
                    raise
                # Match the uncached lookup's fail-open behavior. An
                # entitlement lookup outage must not preserve a zero-access
                # decision for a paid subscriber from stale cache state.
                logger.warning("trial paywall cache revalidation failed for uid=%s: %s", uid, e)
                record_fallback(
                    component='other',
                    from_mode='trial_paywall',
                    to_mode='fail_open',
                    reason='policy',
                    outcome='degraded',
                    log=logger,
                )
                return False
        return bool(cached)
    expired = _is_trial_expired_uncached(
        uid,
        firestore_client=firestore_client,
        provision=provision,
        required_byok_provider=required_byok_provider,
        strict=strict,
    )
    try:
        redis_db.set_generic_cache(cache_key, expired, ttl=_TRIAL_PAYWALL_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.debug("trial paywall cache set failed for uid=%s: %s", uid, e)
    return expired


def is_trial_paywalled(
    uid: str,
    platform: Optional[str],
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_byok_provider: str | None = None,
    strict: bool = False,
) -> bool:
    """True iff the request is from a desktop client AND the user has used
    their full 3-day free trial without subscribing or activating BYOK.

    `platform` is the X-App-Platform header for HTTP requests or the
    `source` query param for the listen WebSocket. Mobile (ios/android),
    Omi devices, and any unknown/missing platform are never paywalled.

    A lookup failure answers False (fail open: a Firebase blip never paywalls
    a paying user) unless ``strict``, where it propagates to the caller, an
    unreadable account record counts as a failure, and a BYOK exemption needs
    a validated key on this request rather than a stored fingerprint.
    """
    if not TRIAL_PAYWALL_ENABLED:
        return False  # trial paywall disabled — never block on account age
    if not platform or platform.lower() not in _TRIAL_PAYWALL_DESKTOP_TOKENS:
        return False
    return _is_trial_expired_cached(
        uid,
        firestore_client=firestore_client,
        provision=provision,
        required_byok_provider=required_byok_provider,
        strict=strict,
    )


def clear_trial_paywall_cache(uid: str) -> None:
    # Every key `_is_trial_expired_cached` can write: the LLM providers, Deepgram
    # (the transcription allowance's key) and that allowance's strict variant.
    for provider in ("openrouter", "openai", "anthropic", "gemini", "deepgram"):
        redis_db.delete_generic_cache(f"trial_paywall:expired:{uid}:{provider}")
    redis_db.delete_generic_cache(f"trial_paywall:expired:{uid}:deepgram:strict")
    redis_db.delete_generic_cache(f"trial_paywall:expired:{uid}")


def get_trial_metadata(uid: str) -> TrialMetadata:
    """Compute structured trial metadata for the given user.

    Returns trial timing info regardless of platform — the client decides
    whether to render the countdown UI. Paid-plan and BYOK users get
    `trial_expired=False` with zeroed timing (trial is irrelevant to them).

    This reuses the same Firebase Auth lookup path as `_is_trial_expired_uncached`
    and benefits from the same Redis cache for the expensive bits.
    """
    try:
        # Trial paywall disabled → there is no trial to expire. Report an always-active
        # (non-expired) trial so the desktop client never renders the "trial expired /
        # you've hit your monthly limit" upgrade popup from account age alone.
        if not TRIAL_PAYWALL_ENABLED:
            return TrialMetadata(
                trial_expired=False,
                trial_duration_seconds=TRIAL_LENGTH_SECONDS,
                trial_features=TRIAL_FEATURES,
                plan_after_trial=get_plan_display_name(PlanType.basic),
            )

        subscription = users_db.get_user_valid_subscription(uid)
        plan = subscription.plan if subscription else PlanType.basic

        # Any plan that is not eligible for the Free account-age trial, plus
        # BYOK users, has usable Desktop access. In particular, Neo's Free
        # Desktop tier is a floor, not a trial-only or zero-access state.
        # Same request-level escape hatch as `_is_trial_expired_cached`: a request
        # carrying an enrolled LLM BYOK provider header is treated as BYOK-active
        # even if Firestore hasn't caught up yet.
        if (
            not desktop_trial_paywall_eligible(plan, subscription)
            or users_db.is_byok_active(uid)
            or _request_has_llm_byok_key()
        ):
            return TrialMetadata(
                trial_expired=False,
                trial_duration_seconds=TRIAL_LENGTH_SECONDS,
                trial_features=TRIAL_FEATURES,
                plan_after_trial=get_plan_display_name(PlanType.basic),
            )

        user_record = _get_user(uid)
        creation_ms: int = cast(int, user_record.user_metadata.creation_timestamp)
        if not creation_ms:
            # No creation timestamp — treat as active trial (fail-open).
            return TrialMetadata(
                trial_expired=False,
                trial_duration_seconds=TRIAL_LENGTH_SECONDS,
                trial_features=TRIAL_FEATURES,
                plan_after_trial=get_plan_display_name(PlanType.basic),
            )

        creation_seconds = int(creation_ms / 1000)
        trial_ends_at = creation_seconds + TRIAL_LENGTH_SECONDS
        now = int(time.time())
        remaining = max(0, trial_ends_at - now)
        expired = remaining == 0

        return TrialMetadata(
            trial_started_at=creation_seconds,
            trial_ends_at=trial_ends_at,
            trial_remaining_seconds=remaining,
            trial_expired=expired,
            trial_duration_seconds=TRIAL_LENGTH_SECONDS,
            trial_features=TRIAL_FEATURES,
            plan_after_trial=get_plan_display_name(PlanType.basic),
        )
    except Exception as e:
        logger.warning("get_trial_metadata failed for uid=%s: %s", uid, e)
        # Fail-open: report as active trial so UI doesn't flash paywall.
        return TrialMetadata(
            trial_expired=False,
            trial_duration_seconds=TRIAL_LENGTH_SECONDS,
            trial_features=TRIAL_FEATURES,
            plan_after_trial=get_plan_display_name(PlanType.basic),
        )


def is_paid_plan(plan: PlanType) -> bool:
    return plan in PAID_PLAN_TYPES


def _configured_plan_price_id(plan: PlanType, interval: str) -> Optional[str]:
    return os.getenv(PRIMARY_BILLING_ENV_VARS[plan][interval])


def get_paid_plan_definitions() -> List[Dict[str, Any]]:
    """All plan definitions.

    Unlimited is kept as legacy so existing subscribers keep their access
    and Stripe webhooks still resolve, but it's filtered out of the "new user"
    purchase catalog via `filter_plans_for_user`.
    """
    return [
        {
            "plan_type": PlanType.unlimited,
            "plan_id": "unlimited",
            "title": "Neo",
            "subtitle": f"{_chat_allowance_text(PlanType.unlimited)}",
            "description": f"{_chat_allowance_text(PlanType.unlimited)}. Shared with mobile and web.",
            "eyebrow": "Starter",
            "monthly_price_id": _configured_plan_price_id(PlanType.unlimited, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.unlimited, 'year'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.operator,
            "plan_id": "operator",
            "title": "Operator",
            "subtitle": f"{_chat_allowance_text(PlanType.operator)}",
            "description": f"{_chat_allowance_text(PlanType.operator)}. Shared with mobile and web.",
            "eyebrow": "Most popular",
            "monthly_price_id": _configured_plan_price_id(PlanType.operator, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.operator, 'year'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.architect,
            "plan_id": "architect",
            "title": "Architect",
            "subtitle": "Power-user AI — thousands of chats + agentic automations",
            "description": "Power-user AI for heavy agentic workflows and vibe coding.",
            "eyebrow": "Automation + coding",
            "monthly_price_id": _configured_plan_price_id(PlanType.architect, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.architect, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.plus,
            "plan_id": "plus",
            "title": "Plus",
            "subtitle": f"{_transcription_allowance_text(PlanType.plus)}",
            "description": f"{_transcription_allowance_text(PlanType.plus)}.",
            "eyebrow": "For everyday use",
            "monthly_price_id": _configured_plan_price_id(PlanType.plus, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.plus, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.unlimited_v2,
            "plan_id": "unlimited_v2",
            "title": "Unlimited",
            "subtitle": "Unlimited transcription",
            "description": "Unlimited transcription — record all day.",
            "eyebrow": "Most popular",
            "monthly_price_id": _configured_plan_price_id(PlanType.unlimited_v2, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.unlimited_v2, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
    ]


# Platform identifiers for the two mobile clients (X-App-Platform header).
_MOBILE_PLATFORM_TOKENS = {'ios', 'android'}

# The web storefront (X-App-Platform: web). It's an always-latest client that
# renders the full new catalog (Plus + Unlimited + Operator + Architect) and is
# the primary Stripe checkout surface; only deprecated Neo is hidden there.
WEB_PLATFORMS = {'web'}


def _platform_hidden_plans(platform: Optional[str]) -> Set[PlanType]:
    """Plans hidden from the purchase catalog per platform.

    Mobile sells Plus + Unlimited; desktop sells Operator + Architect; web sells
    all four. Neo is deprecated everywhere and hidden on every platform. A
    subscriber on a hidden plan still sees it via `filter_plans_for_user`'s
    current-plan escape (Neo) or the mobile manage-only fast path (Operator /
    Architect). See .github/agent-docs/plan-catalog.md.
    """
    p = (platform or '').lower()
    if p in _MOBILE_PLATFORM_TOKENS:
        return {PlanType.unlimited, PlanType.operator, PlanType.architect}
    if p in DESKTOP_PLATFORMS:
        return {PlanType.unlimited, PlanType.plus, PlanType.unlimited_v2}
    if p in WEB_PLATFORMS:
        return {PlanType.unlimited}
    return set()


def desktop_to_consumer_plan_change_error(current_plan: PlanType, target_plan: PlanType) -> Optional[str]:
    """Error text if a desktop-entitled plan would be swapped onto a consumer tier.

    Operator and Architect are manage-only from mobile: cancel or wait out the
    period. Immediate proration onto Plus / Unlimited / Neo strips desktop.
    Same-family desktop changes (Operator ↔ Architect) stay allowed for the
    desktop and web storefronts. Do not add a "user confirmed in the app"
    exception — confirmation is not this boundary. See .github/agent-docs/plan-catalog.md.
    """
    if current_plan in DESKTOP_ENTITLED_PLAN_TYPES and target_plan not in DESKTOP_ENTITLED_PLAN_TYPES:
        return (
            "This plan is managed from desktop. Switching to a mobile plan is not "
            "available here. Cancel at period end or contact support."
        )
    return None


def filter_plans_for_user(
    definitions: List[Dict[str, Any]],
    current_plan: PlanType,
    platform: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Drop legacy / platform-hidden plans from the purchase catalog.

    Locked audience rules (.github/agent-docs/plan-catalog.md) — do not re-widen:

    1. Neo (`unlimited`) is shown only when `current_plan` is already Neo
       (active or cancel-at-period-end). Never gate it on "has ever paid".
    2. On mobile, Operator / Architect are manage-only: return *only* the
       current desktop plan so cheaper mobile tiers cannot be purchased
       from the phone. Desktop and web keep selling both.
    3. Fully churned ex-Neo users are `basic` and receive Plus + Unlimited,
       the replacement catalog, not the deprecated Neo SKU.

    The current-plan escape still applies on desktop/web so a Neo subscriber
    opening those surfaces can manage/cancel.
    """
    is_mobile = (platform or '').lower() in _MOBILE_PLATFORM_TOKENS
    if is_mobile and current_plan in DESKTOP_ENTITLED_PLAN_TYPES:
        return [d for d in definitions if d.get('plan_type') == current_plan]

    hidden = _platform_hidden_plans(platform)
    out: List[Dict[str, Any]] = []
    for d in definitions:
        plan_type = d.get('plan_type')
        if d.get('legacy') and plan_type != current_plan:
            continue
        if plan_type in hidden and plan_type != current_plan:
            continue
        out.append(d)
    return out


# Minimum macOS desktop build that ships with the new plan catalog + quota UI.
NEW_PLANS_MIN_DESKTOP_VERSION = os.getenv('NEW_PLANS_MIN_DESKTOP_VERSION', '0.11.324')

# Minimum Windows desktop build that ships the new plan catalog. Windows is
# pre-release and versions independently of macOS, so this defaults permissive
# ('0.0.0' → every Windows build qualifies); set a floor once Windows ships a
# build that must be gated out.
NEW_PLANS_MIN_WINDOWS_VERSION = os.getenv('NEW_PLANS_MIN_WINDOWS_VERSION', '0.0.0')

# Minimum mobile build that ships with the `operator` enum value and new plan UI.
# Mobile builds below this version get the legacy catalog with operator→unlimited mapping.
NEW_PLANS_MIN_MOBILE_VERSION = os.getenv('NEW_PLANS_MIN_MOBILE_VERSION', '1.0.530')

# Per-desktop-platform minimum client version that understands the Operator +
# Architect plan shape. Desktop platforms fail *open* (a missing/unparseable
# version still gets the new catalog); mobile fails *closed* (old builds crash
# on the operator enum).
_NEW_PLANS_MIN_DESKTOP_VERSION_BY_PLATFORM = {
    'macos': NEW_PLANS_MIN_DESKTOP_VERSION,
    'windows': NEW_PLANS_MIN_WINDOWS_VERSION,
}


def should_show_new_plans(platform: Optional[str], app_version: Optional[str]) -> bool:
    """True iff this caller's client understands the Operator + Architect plan shape.

    Desktop (macOS / Windows): any build at or above the platform's minimum
    qualifies; a missing or unparseable version defaults to the new catalog
    (macOS shipped it long ago, Windows is pre-release).
    Mobile (android/ios): any build at or above NEW_PLANS_MIN_MOBILE_VERSION
    qualifies; a missing or unparseable version defaults to the legacy catalog
    (old mobile builds crash on the operator enum).
    Web: always the new catalog (it's an always-latest client, version-agnostic).
    Unknown platform: legacy catalog.
    """
    if not platform:
        return False

    platform_lower = platform.lower()

    if platform_lower in WEB_PLATFORMS:
        return True

    if platform_lower in DESKTOP_PLATFORMS:
        if not app_version:
            return True
        try:
            return compare_versions(app_version, _NEW_PLANS_MIN_DESKTOP_VERSION_BY_PLATFORM[platform_lower]) >= 0
        except Exception:
            return True

    if platform_lower in _MOBILE_PLATFORM_TOKENS:
        if not app_version:
            return False
        try:
            return compare_versions(app_version, NEW_PLANS_MIN_MOBILE_VERSION) >= 0
        except Exception:
            return False

    return False


# Minimum client build whose plan enum includes `plus`/`max`. Defaulted ahead of
# any shipped build so every current client is remapped today (see
# wire_plan_for_client); lower once a plus/unlimited_v2-aware client ships.
PLUS_UNLIMITED_V2_MIN_MOBILE_VERSION = os.getenv('PLUS_UNLIMITED_V2_MIN_MOBILE_VERSION', '99.0.0')
PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION = os.getenv('PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION', '99.0.0')


def client_understands_plus_unlimited_v2(platform: Optional[str], app_version: Optional[str]) -> bool:
    if not platform or not app_version:
        return False
    platform_lower = platform.lower()
    if platform_lower in _MOBILE_PLATFORM_TOKENS:
        floor = PLUS_UNLIMITED_V2_MIN_MOBILE_VERSION
    elif platform_lower in DESKTOP_PLATFORMS:
        floor = PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION
    else:
        return False
    try:
        return compare_versions(app_version, floor) >= 0
    except Exception:
        return False


def wire_plan_for_client(plan: PlanType, platform: Optional[str], app_version: Optional[str]) -> PlanType:
    """Serialize `plus`/`max` as `unlimited` for clients whose enum predates them.

    Only the label is remapped — real entitlement/limits are computed from the
    true plan before this is called. Mirrors the `operator`→`unlimited` remap.
    """
    if plan in MOBILE_PLAN_TYPES and not client_understands_plus_unlimited_v2(platform, app_version):
        return PlanType.unlimited
    return plan


def adapt_plans_for_legacy_client(definitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform the new-shape plan catalog back into the pre-v0.11.324 shape
    so older clients (mobile, stable desktop) keep showing the old plan titles
    and don't see desktop-only plans.

    Hides Operator and Architect (pro) entirely — both are desktop-only.
    Drops the legacy suffix + flag from Unlimited so pre-rollout clients
    still see it as "Omi Unlimited".
    """
    out: List[Dict[str, Any]] = []
    for d in definitions:
        if d['plan_id'] in ('operator', 'pro'):
            continue
        adapted = dict(d)
        if d['plan_id'] == 'architect':
            adapted['title'] = 'Omi Pro'
        elif d['plan_id'] == 'unlimited':
            adapted['title'] = 'Unlimited Plan'
            adapted['legacy'] = False
        out.append(adapted)
    return out


def legacy_plan_features(plan: PlanType) -> List[str]:
    """Feature strings matching the pre-v0.11.324 plan catalog.

    Mirrors what `get_plan_features` used to return before the Operator /
    Architect rename so older clients' UI doesn't change under them.
    """
    if plan == PlanType.architect:
        return [
            "Automations",
            "Vibe coding",
            "Unlimited actions",
            "Priority desktop AI features",
        ]
    if plan in (PlanType.unlimited, PlanType.operator):
        return [
            "Unlimited listening time",
            "Unlimited words transcribed",
            "Unlimited insights",
            "Unlimited memories",
        ]
    return get_plan_features(plan)


def get_plan_type_from_price_id(price_id: str) -> PlanType:
    """Resolve retained and configured Stripe prices through the catalog."""

    return resolve_stripe_price_plan(price_id)


def price_ids_match_plan_and_interval(
    current_price_id: Optional[str], target_price_id: Optional[str], current_interval: Optional[str] = None
) -> bool:
    if not current_price_id or not target_price_id:
        return False
    try:
        if get_plan_type_from_price_id(current_price_id) != get_plan_type_from_price_id(target_price_id):
            return False
    except ValueError:
        return False

    target_interval = RECOGNIZED_STRIPE_PRICE_INTERVALS.get(target_price_id)
    for definition in get_paid_plan_definitions():
        if target_price_id == definition['monthly_price_id']:
            target_interval = 'month'
        elif target_price_id == definition['annual_price_id']:
            target_interval = 'year'
        if target_interval:
            break
    if not target_interval:
        return False

    if not current_interval:
        current_interval = RECOGNIZED_STRIPE_PRICE_INTERVALS.get(current_price_id)
    if not current_interval:
        for definition in get_paid_plan_definitions():
            if current_price_id == definition['monthly_price_id']:
                current_interval = 'month'
            elif current_price_id == definition['annual_price_id']:
                current_interval = 'year'
            if current_interval:
                break
    if not current_interval:
        try:
            current_price = stripe.Price.retrieve(current_price_id)
            recurring = getattr(current_price, 'recurring', None)
            if recurring is not None:
                current_interval = getattr(recurring, 'interval', None)
        except Exception as e:
            logger.error(f"Error retrieving current price interval: {sanitize(str(e))}")
            return False
    return current_interval == target_interval


def is_purchasable_price_id(price_id: str) -> bool:
    """True only if price_id is a currently-purchasable plan price (the active catalog).

    Unlike get_plan_type_from_price_id, this deliberately excludes the retained recognition
    ledger: retained prices exist for current subscribers' renewals and reconciliation, not as
    new checkout or upgrade targets. Use this at the checkout/upgrade request boundary so a
    caller cannot select a hidden or deprecated price by posting its ID directly.
    """
    if not price_id:
        return False
    for definition in get_paid_plan_definitions():
        if price_id in (definition["monthly_price_id"], definition["annual_price_id"]):
            return True
    return False


def validate_stripe_price_ids():
    """Validate configured Stripe price IDs at startup outside the dev environment."""
    if os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'dev':
        record_fallback(
            component='other',
            from_mode='stripe_price_validation',
            to_mode='dev_skip',
            reason='policy',
            outcome='degraded',
            log=logger,
        )
        logger.info('Skipping Stripe price validation during dev startup.')
        return

    for definition in get_paid_plan_definitions():
        for interval in ('monthly', 'annual'):
            price_id = definition[f'{interval}_price_id']
            if not price_id:
                continue
            try:
                stripe.Price.retrieve(price_id)
            except Exception as e:
                logger.error(
                    f"STARTUP: Stripe price validation failed for {definition['plan_id']} {interval} "
                    f"(price_id={price_id}): {sanitize(str(e))} — this plan will be invisible to users"
                )


_basic_tier_seconds_raw = allocation_limit(PlanType.basic, 'transcription')
if _basic_tier_seconds_raw is None:
    # allocation_limit returns None for an unlimited allocation. Free is metered by
    # design, so an unlimited basic transcription allowance is a catalog authoring
    # mistake, not a configuration choice. Fail with a sentence that says what is
    # wrong rather than letting `None // 60` raise TypeError at import time.
    raise ValueError(
        'basic.transcription must declare a finite allowance; an unlimited free tier '
        'would make transcription spend unbounded per user'
    )

# Narrowed above, so the rest of the module (and pyright) can treat it as a plain int.
_BASIC_TIER_SECONDS_DEFAULT: int = _basic_tier_seconds_raw


def _legacy_overlay(env_name: str) -> Tuple[bool, Optional[int]]:
    """Read a pre-catalog quota overlay, honoring the sentinel it was written under.

    These env vars predate the catalog and were authored when ``0`` meant
    *unlimited* -- production sets BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH and
    BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH to exactly ``0`` on that meaning.
    The catalog retires the sentinel, but retiring it must not silently
    *reinterpret configuration that is already deployed*: reading those zeros as a
    finite zero would hand every Free user a zero words/insights allowance and
    advertise "0 words transcribed per month".

    So the sentinel is honored where the legacy value is read, and only there. The
    catalog's own values use the typed representation and are untouched. D2 deletes
    these overlays, and this bridge goes with them.

    Returns ``(present, value)``; ``value`` is ``None`` for a legacy unlimited zero.
    """
    raw = os.getenv(env_name)
    if raw is None:
        return False, None
    parsed = int(raw)
    return True, (None if parsed == 0 else parsed)


def _basic_transcription_overlay() -> Tuple[int, Optional[int]]:
    """Resolve ``(minutes, seconds)`` for Free transcription.

    ``seconds`` is ``None`` when the allowance is unlimited. Charts currently set
    300, so the legacy-zero branch is latent -- but reading a deployed ``0`` as a
    finite zero would make ``has_transcription_credits`` return False for every Free
    user, which is the same inversion as words/insights with worse consequences.
    """
    present, value = _legacy_overlay('BASIC_TIER_MINUTES_LIMIT_PER_MONTH')
    if not present:
        return _BASIC_TIER_SECONDS_DEFAULT // 60, _BASIC_TIER_SECONDS_DEFAULT
    if value is None:
        return 0, None
    return value, value * 60


BASIC_TIER_MINUTES_LIMIT_PER_MONTH, BASIC_TIER_MONTHLY_SECONDS_LIMIT = _basic_transcription_overlay()


def _catalog_or_legacy_basic_limit(allocation: str) -> Optional[int]:
    """Return a catalog limit, preserving the temporary Basic env overlays.

    D2 removes these per-service plan quota overlays. Until then, the catalog
    remains the default and a configured overlay remains effective at runtime.
    ``None`` is the only unlimited representation; zero is a finite zero.
    """
    catalog_value = allocation_limit(PlanType.basic, allocation)
    legacy_env_names = {
        'words_transcribed': 'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH',
        'insights_gained': 'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH',
    }
    env_name = legacy_env_names.get(allocation)
    if env_name is None:
        return catalog_value
    present, overlay = _legacy_overlay(env_name)
    return overlay if present else catalog_value


BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH = _catalog_or_legacy_basic_limit('words_transcribed')
BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH = _catalog_or_legacy_basic_limit('insights_gained')

# Fixed non-human UID the desktop-backend release probe signs in as
# (`PROBE_UID` in backend/scripts/firebase_release_probe_token.py). Its chat turns
# are deploy-gate traffic, not a user's questions, so they must never be metered
# against a plan cap — otherwise the gate blocks itself once the probe's own turns
# exhaust the Free allowance and every desktop-backend deploy fails with 402.
RELEASE_PROBE_UID = 'omi-release-probe'


def _effective_plan_limit(plan: PlanType, allocation: str) -> Optional[int]:
    """Resolve a typed allocation from the catalog plus temporary legacy overlays."""
    catalog_value = allocation_limit(plan, allocation)
    if plan == PlanType.basic:
        if allocation == 'transcription':
            return BASIC_TIER_MONTHLY_SECONDS_LIMIT
        return _catalog_or_legacy_basic_limit(allocation)
    if plan == PlanType.plus and allocation == 'transcription':
        raw_minutes = os.getenv('PLUS_TIER_MINUTES_LIMIT_PER_MONTH')
        return int(raw_minutes) * 60 if raw_minutes is not None else catalog_value
    return catalog_value


def _legacy_chat_env_name(plan: PlanType, unit: str) -> str:
    """Return the historical chat overlay name for a catalog plan/unit."""
    prefix = {'basic': 'FREE', 'unlimited': 'NEO'}.get(plan.value, plan.value.upper())
    if unit == 'question':
        return f'{prefix}_CHAT_QUESTIONS_PER_MONTH'
    if unit == 'usd_cent':
        return 'ARCHITECT_CHAT_COST_USD_PER_MONTH'
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {unit!r}')


def _effective_chat_limit(plan: PlanType) -> Optional[int]:
    """Return the catalog chat limit in its declared unit.

    Chat env overlays are retained only as a migration bridge until D2 removes
    plan quota values from service configuration. Reporting and admission both
    call this helper, so an overlay cannot recreate the old B3 disagreement.
    """
    allocation = get_plan_allocation(plan, 'chat')
    unit = allocation['unit']
    catalog_value = allocation_limit(plan, 'chat')
    env_name = _legacy_chat_env_name(plan, unit)
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return catalog_value
    if unit == 'question':
        return int(raw_value)
    if unit == 'usd_cent':
        return int(round(float(raw_value) * 100))
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {unit!r}')


def _chat_allowance_text(plan: PlanType) -> str:
    allocation = get_plan_allocation(plan, 'chat')
    limit = _effective_chat_limit(plan)
    if allocation['unit'] == 'question':
        if limit is None:
            return 'Unlimited chat questions per month'
        # Keep the word "chat": the pre-catalog copy was
        # "{N} chat questions per month. Shared with mobile and web." and this is
        # user-visible storefront text. A consolidation must not quietly reword the
        # product; changing it is a copy decision, not a refactor.
        return f'{limit} chat questions per month'
    if allocation['unit'] == 'usd_cent':
        if limit is None:
            return 'Unlimited AI compute per month'
        return f'~${limit / 100:g} of monthly AI compute included'
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {allocation["unit"]!r}')


def _transcription_allowance_text(plan: PlanType) -> str:
    limit = _effective_plan_limit(plan, 'transcription')
    if limit is None:
        return 'Unlimited transcription'
    return f'{limit // 60:,} minutes of transcription per month'


# Compatibility names for callers and fixtures still importing the old
# projections. These are derived values, not plan policy sources; all runtime
# decisions below resolve the catalog allocation through the helpers above.
FREE_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.basic)
NEO_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.unlimited)
OPERATOR_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.operator)
_architect_chat_cents = _effective_chat_limit(PlanType.architect)
ARCHITECT_CHAT_COST_USD_PER_MONTH = None if _architect_chat_cents is None else _architect_chat_cents / 100.0
PLUS_TIER_MONTHLY_SECONDS_LIMIT = _effective_plan_limit(PlanType.plus, 'transcription')
PLUS_TIER_MINUTES_LIMIT_PER_MONTH = (
    None if PLUS_TIER_MONTHLY_SECONDS_LIMIT is None else PLUS_TIER_MONTHLY_SECONDS_LIMIT // 60
)
PLUS_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.plus)
UNLIMITED_V2_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.unlimited_v2)


# Features available during the 3-day desktop trial (matches paid-plan behavior).
TRIAL_FEATURES = [
    'unlimited_listening',
    'unlimited_transcription',
    'unlimited_memories',
    'unlimited_insights',
    f'{_effective_chat_limit(PlanType.basic)}_chat_questions_per_month',
]


def get_plan_display_name(plan: PlanType) -> str:
    return PLAN_DISPLAY_NAMES.get(plan, plan.value.capitalize())


def get_chat_quota_snapshot(
    uid: str,
    platform: Optional[str] = None,
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_llm_provider: str | None = None,
) -> Dict[str, Any]:
    """Cheap computation of `is_allowed / used / limit / unit / plan` — shared
    between the `/v1/users/me/usage-quota` endpoint and the enforcement helper.

    `platform` (X-App-Platform header) gates the paywall test override — only
    desktop callers can be paywalled; mobile callers fall through to the
    real plan logic.
    """
    # Paywall test override — surface as exhausted Free-plan quota so the
    # client renders the same over-limit popup it shows for normal users
    # past 30/mo.
    if is_trial_paywalled(
        uid,
        platform,
        firestore_client=firestore_client,
        provision=provision,
        required_byok_provider=required_llm_provider,
    ):
        usage = user_usage_db.get_monthly_chat_usage(uid, firestore_client=firestore_client)
        free_chat_limit = _effective_chat_limit(PlanType.basic)
        if free_chat_limit is None:
            raise ValueError('basic.chat must declare a finite question allowance for trial paywalling')
        return {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': float(free_chat_limit),
            'limit': float(free_chat_limit),
            'allowed': False,
            'reset_at': usage['reset_at'],
        }

    subscription = users_db.get_user_valid_subscription(uid, firestore_client=firestore_client, provision=provision)
    plan = subscription.plan if subscription else PlanType.basic
    limits = get_plan_limits(plan)
    usage = user_usage_db.get_monthly_chat_usage(uid, firestore_client=firestore_client)

    chat_unit = get_plan_allocation(plan, 'chat')['unit']
    if chat_unit == 'usd_cent':
        unit = 'cost_usd'
        used = float(usage['cost_usd'])
        limit_value = None if limits.chat_cost_usd_per_month is None else float(limits.chat_cost_usd_per_month)
    elif chat_unit == 'question':
        unit = 'questions'
        used = float(usage['questions'])
        limit_value = float(limits.chat_questions_per_month) if limits.chat_questions_per_month is not None else None
    else:
        raise ValueError(f'{plan.value}.chat has unsupported catalog unit {chat_unit!r}')

    allowed = True
    if limit_value is not None:
        allowed = used < limit_value

    return {
        'plan': plan,
        'unit': unit,
        'used': used,
        'limit': limit_value,
        'allowed': allowed,
        'reset_at': usage['reset_at'],
    }


def enforce_chat_quota(
    uid: str,
    platform: Optional[str] = None,
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_llm_provider: str | None = None,
    byok_exempt: bool = True,
) -> None:
    """Block or allow a chat request based on the user's plan + usage.

    - BYOK users with an LLM key attached: always allowed, no Omi-side cost —
      unless ``byok_exempt`` is False, for surfaces that only ever spend Omi's
      own key regardless of the user's (the realtime hub mints platform tokens).
    - Plans whose catalog exhaustion policy is overage: ALLOWED — the call is
      served and the excess accrues a charge. See ``utils.overage``.
    - Hard-capped plans: blocked → 402, which the chat endpoint converts into
      a canned AI reply for mobile UX. Plus and Unlimited-v2 are explicitly
      hard-capped by the catalog.
    """
    # Release-probe traffic is the deploy gate proving the candidate can chat at
    # all — never paywall it, or the gate hard-blocks its own deploys once the
    # probe's turns exhaust the Free cap.
    if uid == RELEASE_PROBE_UID:
        return

    # Paywall test override — bypass BYOK + plan checks so the same 402
    # surfaces that a free user past 30 questions would hit. Desktop only;
    # mobile callers continue down the normal plan path.
    if is_trial_paywalled(
        uid,
        platform,
        firestore_client=firestore_client,
        provision=provision,
        required_byok_provider=required_llm_provider,
    ):
        snapshot = get_chat_quota_snapshot(
            uid,
            platform=platform,
            firestore_client=firestore_client,
            provision=provision,
            required_llm_provider=required_llm_provider,
        )
        raise HTTPException(
            status_code=402,
            detail={
                'error': 'quota_exceeded',
                'plan': get_plan_display_name(PlanType.basic),
                'plan_type': PlanType.basic.value,
                'unit': snapshot['unit'],
                'used': round(snapshot['used'], 4),
                'limit': snapshot['limit'],
                'reset_at': snapshot['reset_at'],
            },
        )

    # BYOK users pay their own LLM provider — no Omi-side cost to cap.
    # Require an LLM provider key on this request (not just any BYOK header)
    # so a user can't activate with fake fingerprints or send only x-byok-deepgram
    # to bypass chat quota while chat falls back to Omi's OpenAI/Anthropic keys.
    has_exempt_llm = (
        _request_has_byok_provider(required_llm_provider) if required_llm_provider else _request_has_llm_byok_key()
    )
    if byok_exempt and users_db.is_byok_active(uid, firestore_client=firestore_client) and has_exempt_llm:
        return

    snapshot = get_chat_quota_snapshot(
        uid,
        platform=platform,
        firestore_client=firestore_client,
        provision=provision,
        required_llm_provider=required_llm_provider,
    )
    if snapshot['allowed']:
        return

    plan = snapshot['plan']

    # Reporting and enforcement share the catalog's one exhaustion predicate.
    if plan_uses_overage(plan):
        return

    raise HTTPException(
        status_code=402,
        detail={
            'error': 'quota_exceeded',
            'plan': get_plan_display_name(plan),
            'plan_type': plan.value,
            'unit': snapshot['unit'],
            'used': round(snapshot['used'], 4),
            'limit': snapshot['limit'],
            'reset_at': snapshot['reset_at'],
        },
    )


def enforce_desktop_chat_quota(uid: str, platform: Optional[str] = None, *, byok_exempt: bool = True) -> None:
    """Quota for the desktop serving plane: production customer data, no Free provision.

    Development desktop-backend ADC stays on the compute project for ``agentVm``.
    Entitlements read the customer SA (``SERVICE_ACCOUNT_JSON`` or the Auth file).
    ``byok_exempt=False`` is for surfaces that hand out Omi's own credential no
    matter what key the user holds (the realtime hub); a user's Anthropic key
    must not buy them a managed OpenAI or Gemini session past the cap.
    """
    # Desktop agent chat only consumes Anthropic. An OpenRouter/Gemini/OpenAI
    # key must not exempt this path while the request still uses Omi's managed
    # Anthropic credential.
    enforce_chat_quota(
        uid,
        platform,
        firestore_client=get_customer_firestore_client(),
        provision=False,
        required_llm_provider='anthropic',
        byok_exempt=byok_exempt,
    )


def is_desktop_trial_paywalled(uid: str, platform: Optional[str], *, required_byok_provider: str | None = None) -> bool:
    """Desktop trial gate against the customer Firestore, never a compute-project shadow.

    The decisions that need no Firestore run first: resolving the customer client
    initializes credentials, so a disabled paywall or a non-desktop platform must
    neither pay for that nor require ambient ADC to answer "not paywalled".
    """
    if not TRIAL_PAYWALL_ENABLED:
        return False
    if not platform or platform.lower() not in _TRIAL_PAYWALL_DESKTOP_TOKENS:
        return False
    return is_trial_paywalled(
        uid,
        platform,
        firestore_client=get_customer_firestore_client(),
        provision=False,
        required_byok_provider=required_byok_provider,
    )


def get_basic_plan_limits() -> PlanLimits:
    """Returns the PlanLimits object for the basic (Free) tier."""
    return get_plan_limits(PlanType.basic)


def get_default_basic_subscription() -> Subscription:
    """Returns a default Subscription object for the basic plan."""
    return Subscription(limits=get_basic_plan_limits())


def get_plan_limits(plan: PlanType) -> PlanLimits:
    """Return typed limits projected from the catalog allocation row.

    ``None`` means the catalog explicitly declared ``kind=unlimited``. A
    finite zero remains zero and is therefore enforced as exhausted.
    """
    plan = PlanType(plan)
    chat_allocation = get_plan_allocation(plan, 'chat')
    chat_limit = _effective_chat_limit(plan)
    chat_questions: Optional[int] = None
    chat_cost_usd: Optional[float] = None
    if chat_allocation['unit'] == 'question':
        chat_questions = chat_limit
    elif chat_allocation['unit'] == 'usd_cent':
        chat_cost_usd = None if chat_limit is None else chat_limit / 100.0
    else:
        raise ValueError(f'{plan.value}.chat has unsupported catalog unit {chat_allocation["unit"]!r}')

    return PlanLimits(
        transcription_seconds=_effective_plan_limit(plan, 'transcription'),
        words_transcribed=_effective_plan_limit(plan, 'words_transcribed'),
        insights_gained=_effective_plan_limit(plan, 'insights_gained'),
        chat_questions_per_month=chat_questions,
        chat_cost_usd_per_month=chat_cost_usd,
    )


def get_plan_features(plan: PlanType, simplified: bool = False) -> List[str]:
    """Returns the list of feature strings for the given plan.

    Args:
        plan: The plan type.
        simplified: If True, returns only plan-differentiating features (for mobile),
                    omitting items already shown in the top-level highlights section.
                    If False, returns the full feature list (for desktop).
    """
    chat_feature = _chat_allowance_text(plan)
    transcription_feature = _transcription_allowance_text(plan)
    definition = get_plan_allocation(plan, 'transcription')

    if get_plan_allocation(plan, 'chat')['unit'] == 'usd_cent':
        if simplified:
            return [
                "Automations and vibe coding",
                "Priority desktop AI features",
                chat_feature,
            ]
        return [
            "Automations and vibe coding",
            "Unlimited listening, memories, and insights",
            "Priority desktop AI features",
            chat_feature,
        ]

    if plan in (PlanType.operator, PlanType.unlimited):
        if simplified:
            return [chat_feature]
        return [
            chat_feature,
            "Unlimited listening and transcription",
            "Unlimited memories and insights",
            (
                "Available on Mac, mobile, and web"
                if plan == PlanType.operator
                else "Desktop capture with Free-tier allowance"
            ),
        ]

    if plan == PlanType.basic:
        limits = get_plan_limits(plan)
        transcription_limit = limits.transcription_seconds
        words_limit = limits.words_transcribed
        insights_limit = limits.insights_gained
        return [
            (
                f'{transcription_limit // 60:,} minutes of listening per month'
                if transcription_limit is not None
                else 'Unlimited listening'
            ),
            (
                f'{words_limit:,} words transcribed per month'
                if words_limit is not None
                else 'Unlimited words transcribed'
            ),
            (f'{insights_limit:,} insights per month' if insights_limit is not None else 'Unlimited insights'),
            'Unlimited memories',
        ]

    if definition['limit']['kind'] == 'finite':
        if simplified:
            return [
                transcription_feature,
                chat_feature,
            ]
        return [
            transcription_feature,
            chat_feature,
            "Unlimited memories and insights",
        ]

    if simplified:
        return [transcription_feature, chat_feature]
    return [transcription_feature, chat_feature, "Unlimited memories and insights"]


def _has_active_stripe_subscription(uid: str) -> bool:
    """Check Stripe directly for active subscriptions owned by this user.

    This catches cases where Firestore hasn't been updated yet (e.g. webhook
    write hasn't propagated) but Stripe already has an active subscription.
    """
    customer_id = users_db.get_stripe_customer_id(uid)
    if not customer_id:
        return False
    try:
        subs = stripe.Subscription.list(customer=customer_id, status='active', limit=5)
        for sub in subs.data:
            sub_dict: Dict[str, Any] = sub.to_dict()  # type: ignore[reportDeprecated]  # stripe public serialization API
            if sub_dict.get('cancel_at_period_end'):
                continue
            if sub_dict.get('metadata', {}).get('uid') == uid:
                return True
    except Exception as e:
        logger.error(f"Error checking Stripe for active subscriptions: {e}")
        return True  # fail-closed: block checkout if Stripe is unreachable
    return False


def find_active_paid_subscription_for_user(uid: str) -> Optional[Subscription]:
    """Resolve the user's current active *paid* subscription straight from Stripe.

    Lists the customer's active subscriptions and returns the first one that
    maps to a paid plan (matching this uid's metadata when present). Returns
    None if there's no customer, no active paid sub, or Stripe is unreachable.

    Used to (a) self-heal a Firestore record stuck on `basic` whose stored
    subscription id points at an old/canceled sub, and (b) stop an old
    subscription's cancellation webhook from clobbering an active plan when the
    user canceled one sub and started another near-simultaneously (possibly on a
    different Stripe customer).
    """
    customer_id = users_db.get_stripe_customer_id(uid)
    if not customer_id:
        return None
    try:
        subs = stripe.Subscription.list(customer=customer_id, status='active', limit=10)
    except Exception as e:
        logger.error(f"[find_active_paid_subscription_for_user] Stripe lookup failed for uid={uid}: {e}")
        return None

    for sub in subs.data:
        d: Dict[str, Any] = sub.to_dict()  # type: ignore[reportDeprecated]  # stripe public serialization API
        sub_uid = d.get('metadata', {}).get('uid')
        if sub_uid and sub_uid != uid:
            continue
        items: List[Dict[str, Any]] = d.get('items', {}).get('data') or []
        if not items or not items[0].get('price'):
            continue
        price_id: Any = items[0]['price'].get('id')
        try:
            plan = get_plan_type_from_price_id(price_id)
        except ValueError:
            continue
        if not is_paid_plan(plan):
            continue
        return Subscription(
            plan=plan,
            status=SubscriptionStatus.active,
            stripe_subscription_id=d.get('id'),
            current_price_id=price_id,
            current_period_end=d.get('current_period_end'),
            current_period_start=d.get('current_period_start'),
            cancel_at_period_end=d.get('cancel_at_period_end', False),
            limits=get_plan_limits(plan),
        )
    return None


def is_pending_cancellation(subscription: Optional[Subscription], now: Optional[int] = None) -> bool:
    if not subscription or not subscription.cancel_at_period_end:
        return False
    if not subscription.current_period_end:
        return True
    return subscription.current_period_end > (now or int(time.time()))


def can_user_make_payment(uid: str, target_price_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Checks if a user can make a new payment based on their current subscription status.

    Args:
        uid: User ID
        target_price_id: Optional target price ID to check if this is an upgrade/downgrade

    Returns:
        tuple: (can_pay: bool, reason: str)
    """
    subscription = users_db.get_user_valid_subscription(uid)

    # If no subscription or basic plan, check Stripe as source of truth
    # to guard against Firestore read-after-write lag
    if not subscription or subscription.plan == PlanType.basic:
        if _has_active_stripe_subscription(uid):
            return False, "User already has an active subscription (pending sync)"
        # A cancel-at-period-end subscription is still active until the period
        # ends but is skipped by _has_active_stripe_subscription (it continues
        # past cancel_at_period_end subs). Enforce the same defer-plan-change rule
        # so a different target price can't be checked out before the current
        # period ends, while allowing same-price reactivation.
        pending_cancel_sub = find_active_paid_subscription_for_user(uid)
        if pending_cancel_sub is not None and is_pending_cancellation(pending_cancel_sub):
            if target_price_id and not price_ids_match_plan_and_interval(
                pending_cancel_sub.current_price_id, target_price_id
            ):
                return False, "Plan changes are available after the current subscription ends"
            return True, "User can reactivate the current subscription"
        return True, "User can make payment"

    # If unlimited plan but inactive, user can pay
    if is_paid_plan(subscription.plan) and subscription.status == SubscriptionStatus.inactive:
        return True, "User can make payment"

    # If subscription is canceled (cancel_at_period_end=True), allow resubscription
    # This handles the case where user canceled but period hasn't ended yet
    if is_pending_cancellation(subscription):
        if target_price_id:
            current_price_id = subscription.current_price_id
            if not current_price_id and subscription.stripe_subscription_id:
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                    stripe_sub_dict = stripe_sub.to_dict() if stripe_sub else {}
                    items = stripe_sub_dict.get('items', {}).get('data', [])
                    if items:
                        current_price_id = items[0].get('price', {}).get('id')
                except Exception as e:
                    logger.error(f"Error retrieving current price ID: {sanitize(str(e))}")

            if price_ids_match_plan_and_interval(current_price_id, target_price_id):
                return True, "User can reactivate the current subscription"

            return False, "Plan changes are available after the current subscription ends"

        return True, "User can resubscribe (current subscription is scheduled for cancellation)"

    # If unlimited plan and active, check if this is a plan change
    if is_paid_plan(subscription.plan) and subscription.status == SubscriptionStatus.active:
        if subscription.current_period_end:
            period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)

            # If subscription has expired, user can pay
            if period_end_dt <= datetime.now(timezone.utc):
                return True, "User's subscription has expired, can make new payment"

            # If target price is provided, check if it's different from current plan
            if target_price_id:
                current_price_id = None
                # Try to get current price ID from Stripe subscription
                if subscription.stripe_subscription_id:
                    try:
                        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                        if stripe_sub:
                            stripe_sub_dict: Dict[str, Any] = stripe_sub.to_dict()  # type: ignore[reportDeprecated]  # stripe public serialization API
                            if stripe_sub_dict['items']['data']:
                                current_price_id = stripe_sub_dict['items']['data'][0]['price']['id']
                    except Exception as e:
                        logger.error(f"Error retrieving current price ID: {e}")

                # If different price, allow upgrade/downgrade
                if current_price_id and current_price_id != target_price_id:
                    return True, "User can upgrade/downgrade to different plan"
                elif not current_price_id:
                    return True, "User can make payment (current price unknown)"

            # Same plan, active subscription
            return False, "User already has an active subscription for this plan"

    return True, "User can make payment"


def get_monthly_usage_for_subscription(uid: str) -> Dict[str, Any]:
    """
    Gets the current monthly usage for subscription purposes, considering the launch date from env variables.
    The launch date format is expected to be YYYY-MM-DD.
    If the launch date is not set, not valid, or in the future, usage is considered zero.
    """
    subscription_launch_date_str = os.getenv('SUBSCRIPTION_LAUNCH_DATE')
    if not subscription_launch_date_str:
        # Subscription not launched, so no usage is counted against limits.
        return {}

    try:
        # Use strptime to enforce YYYY-MM-DD format
        launch_date = datetime.strptime(subscription_launch_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        # Invalid date format, treat as not launched.
        return {}

    now = datetime.now(timezone.utc)
    if now < launch_date:
        # Launch date is in the future, so no usage is counted yet.
        return {}

    return user_usage_db.get_monthly_usage_stats_since(uid, now, launch_date)


# --- transcription allowance: one answer -------------------------------------------------------

TRANSCRIPTION_MODE_MANAGED = 'managed'
TRANSCRIPTION_MODE_ON_DEVICE = 'on_device'
TRANSCRIPTION_MODE_BLOCKED = 'blocked'
# Sentinel for "the caller did not pass one; read it" — distinct from None,
# which is a real answer (no valid subscription).
_UNRESOLVED: Any = object()


@dataclass(frozen=True)
class TranscriptionAllowance:
    """The one answer to "may this user's audio be transcribed on Omi's managed STT right now?".

    ``mode`` is what the client should open: ``managed`` (Omi-billed socket),
    ``on_device`` (no managed minutes to spend — the plan's are used up, the
    subscription is not active, or the answer could not be resolved; the local
    engine is free on every plan), or ``blocked`` (the desktop trial paywall;
    nothing opens). ``remaining_seconds`` is ``None`` when the allowance is
    unlimited (unlimited plans, BYOK, reviewers), else the managed seconds
    left this month. ``reason`` is a low-cardinality label for logs and tests.
    """

    mode: str
    remaining_seconds: Optional[int]
    reason: str

    @property
    def managed(self) -> bool:
        return self.mode == TRANSCRIPTION_MODE_MANAGED

    def as_dict(self) -> Dict[str, Any]:
        return {'mode': self.mode, 'remaining_seconds': self.remaining_seconds, 'reason': self.reason}


def _closed(reason: str) -> TranscriptionAllowance:
    """No managed minutes: the free local path, never a billed socket."""
    return TranscriptionAllowance(TRANSCRIPTION_MODE_ON_DEVICE, 0, reason)


def transcription_allowance_seconds(plan: PlanType) -> Optional[int]:
    """The plan's managed transcription allowance, from the catalog alone.

    ``None`` is unlimited. Deliberately not ``get_plan_limits``: that path lets
    the ``BASIC_TIER_MINUTES_LIMIT_PER_MONTH`` / ``PLUS_TIER_MINUTES_LIMIT_PER_MONTH``
    environment overlays outrank the catalog, and no plan quota may be read
    from the environment (NOW.md item 4). Production's overlay equals the
    catalog today (basic 300 min, plus 1,500 min), so this changes no served
    number there; only a divergent overlay (dev's) stops applying.
    """
    return allocation_limit(plan, 'transcription')


def _usage_seconds(usage: Any) -> Optional[int]:
    """Transcription seconds used this month, or ``None`` when the record is not trustworthy."""
    if not isinstance(usage, dict):
        return None
    value = usage.get('transcription_seconds', 0)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def is_marketplace_reviewer(uid: str) -> bool:
    """The app-store reviewer identities the subscription snapshot already treats as unlimited."""
    return uid in os.getenv('MARKETPLACE_APP_REVIEWERS', '').split(',')


def resolve_transcription_allowance(
    uid: str,
    source: Optional[str] = None,
    *,
    subscription: Any = _UNRESOLVED,
    usage: Any = _UNRESOLVED,
    byok_active: Any = _UNRESOLVED,
) -> TranscriptionAllowance:
    """Resolve the managed-transcription allowance for one uid, once. Never raises.

    ``source`` is the listen-WS ``source`` query param (``desktop``, ``omi``,
    ``phone_call``, ...) or the HTTP ``X-App-Platform`` header. It gates only
    the desktop trial paywall, so phone-call / Omi-device traffic for cohort
    UIDs is unaffected.

    ``subscription`` / ``usage`` / ``byok_active`` let a caller that has
    already read the valid subscription (``None`` when there is none), the
    monthly usage and the BYOK enrolment pass them in, so the startup snapshot
    and this answer come from the same reads. (The trial paywall keeps its own
    cached reads; they are not shared.)

    Order: reviewer → paywall → BYOK → plan → unlimited → remaining. A
    subscription the lookup calls invalid (an inactive basic account) has no
    managed minutes; an expired paid subscription is downgraded to a fresh
    basic one by that lookup and gets basic's minutes. Any dependency that
    cannot be read — including the paywall's, which fails open for every
    other caller — and any usage record that cannot be trusted, resolves to
    the free local path rather than a billed socket.
    """
    try:
        # The reviewer identities the subscription snapshot already treats as
        # unlimited; resolved first so the paywall cannot contradict that snapshot.
        if is_marketplace_reviewer(uid):
            return TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, None, 'marketplace_reviewer')
        # A Deepgram BYOK request is exempt from the trial paywall, as it is
        # from the quota: the user pays Deepgram directly. strict: a paywall
        # lookup failure must not open a billed socket for a paywalled account,
        # and only a validated key on this request (not a stored fingerprint)
        # exempts.
        if is_trial_paywalled(uid, source, required_byok_provider='deepgram', strict=True):
            return TranscriptionAllowance(TRANSCRIPTION_MODE_BLOCKED, 0, 'trial_paywalled')
        # Require the Deepgram header on this request so a user cannot activate
        # BYOK with fake fingerprints and then omit x-byok-deepgram to ride Omi's key.
        if byok_active is _UNRESOLVED:
            byok_active = users_db.is_byok_active(uid)
        if byok_active and get_byok_key('deepgram'):
            return TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, None, 'byok')
        if subscription is _UNRESOLVED:
            subscription = users_db.get_user_valid_subscription(uid)
        if not subscription:
            return _closed('subscription_inactive')
        allowance = transcription_allowance_seconds(subscription.plan)
        # The catalog's explicit unlimited marker projects to None. A finite
        # zero is a real zero allowance and must therefore fail closed.
        if allowance is None:
            return TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, None, 'plan_unlimited')
        if usage is _UNRESOLVED:
            usage = get_monthly_usage_for_subscription(uid)
        used = _usage_seconds(usage)
        if used is None:
            logger.warning('transcription allowance: untrusted usage record for uid=%s', uid)
            return _closed('usage_invalid')
        remaining = max(0, allowance - used)
        if remaining > 0:
            return TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, remaining, 'plan_within_allowance')
        return _closed('plan_allowance_exhausted')
    except Exception as exc:  # fail closed: a billed socket is never the default
        logger.warning('transcription allowance unavailable for uid=%s: %s', uid, type(exc).__name__)
        return _closed('allowance_unavailable')


def has_transcription_credits(uid: str, source: Optional[str] = None) -> bool:
    """Whether the user may open Omi's managed STT right now — a thin wrapper over the one resolver.

    ``source`` is the listen-WS ``source`` query param (see
    :func:`resolve_transcription_allowance`).
    """
    return resolve_transcription_allowance(uid, source).managed


def get_remaining_transcription_seconds(uid: str, source: Optional[str] = None) -> int | None:
    """Managed transcription seconds left this month — a thin wrapper over the one resolver.

    ``None`` means unlimited (unlimited plans, BYOK, reviewers); ``0`` means
    spent, inactive, paywalled or unresolvable. Used for the freemium switch to
    on-device transcription.
    """
    return resolve_transcription_allowance(uid, source).remaining_seconds


def reconcile_basic_plan_with_stripe(uid: str, subscription: Subscription | None) -> Subscription | None:
    """
    If Firestore says `basic` but there is a Stripe subscription with a future period end
    that actually maps to an unlimited plan, fix it once by reconciling with Stripe.
    """
    if not subscription or subscription.plan != PlanType.basic:
        return subscription

    try:
        if subscription.stripe_subscription_id and subscription.current_period_end:
            period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            if period_end_dt >= datetime.now(timezone.utc):
                stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                stripe_sub_dict: Optional[Dict[str, Any]] = stripe_sub.to_dict() if stripe_sub else None  # type: ignore[reportDeprecated]  # stripe public serialization API
                if stripe_sub_dict:
                    items: List[Dict[str, Any]] = stripe_sub_dict.get('items', {}).get('data') or []
                    price_id: Optional[str] = None
                    if items and items[0].get('price'):
                        price_id = items[0]['price'].get('id')

                    stripe_status = stripe_sub_dict.get('status')
                    if stripe_status in ('active', 'trialing') and price_id:
                        try:
                            plan_type = get_plan_type_from_price_id(price_id)
                        except ValueError:
                            plan_type = None

                        if plan_type and is_paid_plan(plan_type):
                            subscription.plan = plan_type
                            subscription.status = SubscriptionStatus.active
                            subscription.current_period_end = stripe_sub_dict.get('current_period_end')
                            subscription.current_period_start = stripe_sub_dict.get('current_period_start')
                            subscription.cancel_at_period_end = stripe_sub_dict.get('cancel_at_period_end', False)
                            subscription.current_price_id = price_id
                            subscription.limits = get_plan_limits(plan_type)
                            users_db.update_user_subscription(uid, subscription.model_dump())
                            return subscription

        active = find_active_paid_subscription_for_user(uid)
        if active:
            users_db.update_user_subscription(uid, active.model_dump())
            return active

    except Exception as e:
        # Don't break user flows on reconciliation issues; just log and continue with existing data.
        logger.error(f"[reconcile_basic_plan_with_stripe] Error reconciling Stripe subscription for user {uid}: {e}")

    return subscription
