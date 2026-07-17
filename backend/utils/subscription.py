import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from fastapi import HTTPException
from firebase_admin import auth as firebase_auth
import stripe

import database.users as users_db
import database.user_usage as user_usage_db
from database import redis_db
from database.announcements import compare_versions
from models.users import PlanType, SubscriptionStatus, Subscription, PlanLimits, TrialMetadata
from utils.byok import get_byok_key, get_byok_keys
from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback
import logging

logger = logging.getLogger(__name__)


def _get_user(uid: str) -> Any:
    return firebase_auth.get_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped


PAID_PLAN_TYPES = {PlanType.unlimited, PlanType.architect, PlanType.operator, PlanType.plus, PlanType.max}

# Mobile-only consumer tiers (transcription-metered). Sold on ios/android + web,
# hidden from the desktop catalog. Plus caps transcription; Max is unlimited.
MOBILE_PLAN_TYPES = {PlanType.plus, PlanType.max}

# Plans that unlock the full desktop (macOS) experience. This is deliberately
# narrower than basic desktop usability: every plan, including Neo, has at
# least the Free desktop tier. Operator and Architect add full desktop access.
# Keep this in sync with the per-plan feature copy and the mobile plans sheet.
DESKTOP_ENTITLED_PLAN_TYPES = {PlanType.operator, PlanType.architect}

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
        if users_db.is_byok_active(uid):
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

# Providers a fully-enrolled BYOK desktop client always sends headers for.
# Used by the request-level escape hatch in `_is_trial_expired_cached`.
_BYOK_REQUIRED_PROVIDERS = ("openai", "anthropic", "gemini", "deepgram")


def _request_has_all_byok_keys() -> bool:
    """True if the *current request* carries headers for all 4 enrolled BYOK
    providers.

    Firestore BYOK state is the source of truth for fingerprint validation,
    but it can be temporarily stale — heartbeat just expired, activation
    POST hasn't landed yet, cross-region read replica lag, etc. A user who is
    literally sending all 4 valid API keys on this request should never be
    paywalled because of a Firestore sync gap. The actual fingerprint check
    in `utils.byok._check_byok_validity` runs separately and still rejects
    forged headers (mismatched SHA-256 against the enrolled fingerprints) —
    we trust the headers' *presence* here, not their *contents*.
    """
    keys = get_byok_keys()
    return all(p in keys and keys[p] for p in _BYOK_REQUIRED_PROVIDERS)


def _is_trial_expired_uncached(uid: str) -> bool:
    """Is this user past their 3-day desktop trial?

    The trial applies only to the Free Desktop tier. Neo may use that tier for
    non-premium capabilities, but is paid and must never be reduced to zero
    access. BYOK users are also bypassed. Returns False on any lookup error so
    a Firebase blip never paywalls a paying user.
    """
    try:
        subscription = users_db.get_user_valid_subscription(uid)
        plan = subscription.plan if subscription else PlanType.basic
        if not desktop_trial_paywall_eligible(plan, subscription):
            return False
        if users_db.is_byok_active(uid):
            return False
        user_record = _get_user(uid)
        creation_ms: int = cast(int, user_record.user_metadata.creation_timestamp)
        if not creation_ms:
            return False
        age_seconds = time.time() - (creation_ms / 1000)
        return age_seconds > TRIAL_LENGTH_SECONDS
    except Exception as e:
        logger.warning("trial paywall lookup failed for uid=%s: %s", uid, e)
        return False


def _is_trial_expired_cached(uid: str) -> bool:
    # Request-level escape hatch: a request carrying all 4 BYOK provider
    # headers is never paywalled, regardless of cached Firestore state. The
    # cache TTL is 5 min and Firestore's BYOK `is_active` heartbeat is 24 h,
    # so even a perfectly-configured BYOK user can transiently look stale to
    # Firestore. Trust the live request.
    if _request_has_all_byok_keys():
        return False

    cache_key = f"trial_paywall:expired:{uid}"
    cached = redis_db.get_generic_cache(cache_key)
    if cached is not None:
        # A cache entry may have been written before an entitlement correction
        # or a plan migration. Revalidate a positive value so a paid Neo user
        # is not left with a zero-access decision until this key's TTL expires.
        if cached:
            try:
                subscription = users_db.get_user_valid_subscription(uid)
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
    expired = _is_trial_expired_uncached(uid)
    try:
        redis_db.set_generic_cache(cache_key, expired, ttl=_TRIAL_PAYWALL_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.debug("trial paywall cache set failed for uid=%s: %s", uid, e)
    return expired


def is_trial_paywalled(uid: str, platform: Optional[str]) -> bool:
    """True iff the request is from a desktop client AND the user has used
    their full 3-day free trial without subscribing or activating BYOK.

    `platform` is the X-App-Platform header for HTTP requests or the
    `source` query param for the listen WebSocket. Mobile (ios/android),
    Omi devices, and any unknown/missing platform are never paywalled.
    """
    if not TRIAL_PAYWALL_ENABLED:
        return False  # trial paywall disabled — never block on account age
    if not platform or platform.lower() not in _TRIAL_PAYWALL_DESKTOP_TOKENS:
        return False
    return _is_trial_expired_cached(uid)


def clear_trial_paywall_cache(uid: str) -> None:
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
        # carrying all 4 BYOK provider headers is treated as BYOK-active even if
        # Firestore hasn't caught up yet.
        if (
            not desktop_trial_paywall_eligible(plan, subscription)
            or users_db.is_byok_active(uid)
            or _request_has_all_byok_keys()
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
            "subtitle": f"{NEO_CHAT_QUESTIONS_PER_MONTH} questions per month",
            "description": f"{NEO_CHAT_QUESTIONS_PER_MONTH} chat questions per month. Shared with mobile and web.",
            "eyebrow": "Starter",
            "monthly_price_id": os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.operator,
            "plan_id": "operator",
            "title": "Operator",
            "subtitle": f"{OPERATOR_CHAT_QUESTIONS_PER_MONTH} questions per month",
            "description": f"{OPERATOR_CHAT_QUESTIONS_PER_MONTH} chat questions per month. Shared with mobile and web.",
            "eyebrow": "Most popular",
            "monthly_price_id": os.getenv('STRIPE_OPERATOR_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_OPERATOR_ANNUAL_PRICE_ID'),
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
            "monthly_price_id": os.getenv('STRIPE_ARCHITECT_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_ARCHITECT_ANNUAL_PRICE_ID'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.plus,
            "plan_id": "plus",
            "title": "Plus",
            "subtitle": f"{PLUS_TIER_MINUTES_LIMIT_PER_MONTH:,} minutes of transcription per month",
            "description": f"{PLUS_TIER_MINUTES_LIMIT_PER_MONTH:,} minutes of transcription per month.",
            "eyebrow": "For everyday use",
            "monthly_price_id": os.getenv('STRIPE_PLUS_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_PLUS_ANNUAL_PRICE_ID'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.max,
            "plan_id": "max",
            "title": "Max",
            "subtitle": "Unlimited transcription",
            "description": "Unlimited transcription — record all day.",
            "eyebrow": "Most popular",
            "monthly_price_id": os.getenv('STRIPE_MAX_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_MAX_ANNUAL_PRICE_ID'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
    ]


# Old Stripe price IDs for subscribers who signed up before the Neo/Architect
# rename. Stripe webhooks still fire with these for renewals/cancellations.
LEGACY_PRICE_MAP = {
    # Old Unlimited ($19.99/mo, $199.99/yr) → PlanType.unlimited (now Neo)
    'price_1RtJPm1F8wnoWYvwhVJ38kLb': PlanType.unlimited,
    'price_1RtJQ71F8wnoWYvwKMPaGlGY': PlanType.unlimited,
    # Orphaned from the Apr 17–20 Neo-product window: between f30245338 (added
    # a separate Stripe product `prod_UM0IIpZ4iOgfk5` "Neo" wired via
    # STRIPE_NEO_* env vars) and 2e71145ab (reverted to STRIPE_UNLIMITED_*),
    # desktop signups landed on these prices. Stripe keeps billing them, but
    # post-revert code recognizes neither, so renewals raise "unknown price ID"
    # and drop active subscribers to free.
    'price_1TNIHd1F8wnoWYvwkIrekcQZ': PlanType.unlimited,  # Neo Monthly ($20/mo)
    'price_1TNIHd1F8wnoWYvwlKywJ8TO': PlanType.unlimited,  # Neo Annual ($200/yr)
    # Old Pro ($199/mo, $1999/yr) → PlanType.architect
    'price_1TAfBB1F8wnoWYvw8XBFM1dX': PlanType.architect,
    'price_1TLFac1F8wnoWYvwtPxZhtzE': PlanType.architect,
}


# Platform identifiers for the two mobile clients (X-App-Platform header).
_MOBILE_PLATFORM_TOKENS = {'ios', 'android'}


def _platform_hidden_plans(platform: Optional[str]) -> Set[PlanType]:
    """Plans that are hidden from the purchase catalog for the given platform.

    Mobile (ios/android) sells the consumer tiers Plus + Max, so the
    desktop-oriented Operator + Architect and the deprecated Neo are hidden.

    Desktop (macOS / Windows) sells Operator + Architect, so the mobile
    Plus + Max and the deprecated Neo are hidden.

    A subscriber already on a hidden plan still sees it (to manage/cancel) via
    `filter_plans_for_user`'s current-plan escape; lapsed Neo subscribers on
    mobile keep Neo visible via the ever-purchased escape.

    Web and any other client are left alone — their catalog is unchanged.
    """
    p = (platform or '').lower()
    if p in _MOBILE_PLATFORM_TOKENS:
        return {PlanType.unlimited, PlanType.operator, PlanType.architect}
    if p in DESKTOP_PLATFORMS:
        return {PlanType.unlimited, PlanType.plus, PlanType.max}
    return set()


def has_ever_purchased(uid: str, subscription: Optional[Subscription] = None) -> bool:
    """True if the user has ever gone through subscription checkout.

    Used to keep the deprecated Neo plan visible on mobile to lapsed/returning
    subscribers (so they can resubscribe) while hiding it from brand-new users
    who never bought a plan. A Stripe customer id is created at first checkout
    and persists across cancellations and plan changes; a current paid plan or
    a stored stripe_subscription_id are cheaper positive signals checked first.
    """
    if subscription is not None:
        if is_paid_plan(subscription.plan):
            return True
        if subscription.stripe_subscription_id:
            return True
    return bool(users_db.get_stripe_customer_id(uid))


def filter_plans_for_user(
    definitions: List[Dict[str, Any]],
    current_plan: PlanType,
    platform: Optional[str] = None,
    ever_purchased: bool = False,
) -> List[Dict[str, Any]]:
    """Drop legacy / platform-hidden plans from the purchase catalog.

    Subscribers already on a "wrong-platform" plan (e.g. a Neo subscriber
    opening the desktop app) still see their current plan so the management UI
    works. On mobile, Neo also stays visible to anyone who has ever purchased a
    plan (`ever_purchased`) so lapsed subscribers can resubscribe — new /
    never-paid users don't see it. Only the *purchase* catalog is filtered.
    """
    hidden = _platform_hidden_plans(platform)
    is_mobile = (platform or '').lower() in _MOBILE_PLATFORM_TOKENS
    out: List[Dict[str, Any]] = []
    for d in definitions:
        plan_type = d.get('plan_type')
        if d.get('legacy') and plan_type != current_plan:
            continue
        if plan_type in hidden and plan_type != current_plan:
            # Mobile-only escape: keep the deprecated Neo plan visible to users
            # who have bought a plan before (so they can resubscribe/manage).
            if is_mobile and plan_type == PlanType.unlimited and ever_purchased:
                pass
            else:
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
    Unknown platform: legacy catalog.
    """
    if not platform:
        return False

    platform_lower = platform.lower()

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


# Minimum client build whose local plan enum includes `plus`/`max`. Until an
# app build ships with those enum values, every current client must receive a
# known plan label instead, or it silently deserializes `plus`/`max` as Free
# (mobile) or fails to decode (desktop). Defaults are set far ahead of any
# shipped build so *all* current clients get the remap today; lower them to the
# real build number once a plus/max-aware client ships. Client fails *closed*:
# a missing/unparseable version does not understand plus/max.
PLUS_MAX_MIN_MOBILE_VERSION = os.getenv('PLUS_MAX_MIN_MOBILE_VERSION', '99.0.0')
PLUS_MAX_MIN_DESKTOP_VERSION = os.getenv('PLUS_MAX_MIN_DESKTOP_VERSION', '99.0.0')


def client_understands_plus_max(platform: Optional[str], app_version: Optional[str]) -> bool:
    """True iff this client's local plan enum includes `plus`/`max`."""
    if not platform or not app_version:
        return False
    platform_lower = platform.lower()
    if platform_lower in _MOBILE_PLATFORM_TOKENS:
        floor = PLUS_MAX_MIN_MOBILE_VERSION
    elif platform_lower in DESKTOP_PLATFORMS:
        floor = PLUS_MAX_MIN_DESKTOP_VERSION
    else:
        return False
    try:
        return compare_versions(app_version, floor) >= 0
    except Exception:
        return False


def wire_plan_for_client(plan: PlanType, platform: Optional[str], app_version: Optional[str]) -> PlanType:
    """Plan label to serialize for a client that may not understand `plus`/`max`.

    Remaps the mobile tiers to `unlimited` (a paid enum every current client
    understands) so buyers read as paid instead of Free. Only the serialized
    label is remapped — real entitlement/limits are computed from the true plan
    before this is called. This is the `plus`/`max` analogue of the existing
    `operator`→`unlimited` backward-compat remap.
    """
    if plan in MOBILE_PLAN_TYPES and not client_understands_plus_max(platform, app_version):
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
    """Determines the plan type based on the Stripe price ID.

    Checks active definitions first, then LEGACY_PRICE_MAP for subscribers
    on old pricing (pre-Neo/Architect rename).
    """
    for definition in get_paid_plan_definitions():
        if price_id in (definition["monthly_price_id"], definition["annual_price_id"]):
            return definition["plan_type"]
    if price_id in LEGACY_PRICE_MAP:
        return LEGACY_PRICE_MAP[price_id]
    raise ValueError(f"Price ID {price_id} does not correspond to a known plan.")


def validate_stripe_price_ids():
    """Validate all configured Stripe price IDs on startup. Logs errors for invalid/unreachable prices."""
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


BASIC_TIER_MINUTES_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_MINUTES_LIMIT_PER_MONTH', '0'))
BASIC_TIER_MONTHLY_SECONDS_LIMIT = BASIC_TIER_MINUTES_LIMIT_PER_MONTH * 60
BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH', '0'))
BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH', '0'))

# Chat caps per plan. Env-overridable for ops.
FREE_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('FREE_CHAT_QUESTIONS_PER_MONTH', '30'))
NEO_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('NEO_CHAT_QUESTIONS_PER_MONTH', '200'))
OPERATOR_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('OPERATOR_CHAT_QUESTIONS_PER_MONTH', '500'))
ARCHITECT_CHAT_COST_USD_PER_MONTH = float(os.getenv('ARCHITECT_CHAT_COST_USD_PER_MONTH', '400.0'))

# Mobile Plus / Max tiers. Plus caps transcription at PLUS_TIER minutes; Max is
# unlimited transcription (fair-use throttle is a fast-follow, not enforced here).
# Chat caps are env-overridable so ops can tune without a deploy.
PLUS_TIER_MINUTES_LIMIT_PER_MONTH = int(os.getenv('PLUS_TIER_MINUTES_LIMIT_PER_MONTH', '1500'))
PLUS_TIER_MONTHLY_SECONDS_LIMIT = PLUS_TIER_MINUTES_LIMIT_PER_MONTH * 60
PLUS_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('PLUS_CHAT_QUESTIONS_PER_MONTH', '200'))
MAX_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('MAX_CHAT_QUESTIONS_PER_MONTH', '1000'))

# Features available during the 3-day desktop trial (matches paid-plan behavior).
TRIAL_FEATURES = [
    'unlimited_listening',
    'unlimited_transcription',
    'unlimited_memories',
    'unlimited_insights',
    f'{FREE_CHAT_QUESTIONS_PER_MONTH}_chat_questions_per_month',
]

# Display names shown to users. Internal PlanType stays the same for Stripe compat.
PLAN_DISPLAY_NAMES = {
    PlanType.basic: 'Free',
    PlanType.unlimited: 'Neo',
    PlanType.architect: 'Architect',
    PlanType.operator: 'Operator',
    PlanType.plus: 'Plus',
    PlanType.max: 'Max',
}


def get_plan_display_name(plan: PlanType) -> str:
    return PLAN_DISPLAY_NAMES.get(plan, plan.value.capitalize())


def get_chat_quota_snapshot(uid: str, platform: Optional[str] = None) -> Dict[str, Any]:
    """Cheap computation of `is_allowed / used / limit / unit / plan` — shared
    between the `/v1/users/me/usage-quota` endpoint and the enforcement helper.

    `platform` (X-App-Platform header) gates the paywall test override — only
    desktop callers can be paywalled; mobile callers fall through to the
    real plan logic.
    """
    # Paywall test override — surface as exhausted Free-plan quota so the
    # client renders the same over-limit popup it shows for normal users
    # past 30/mo.
    if is_trial_paywalled(uid, platform):
        usage = user_usage_db.get_monthly_chat_usage(uid)
        return {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': float(FREE_CHAT_QUESTIONS_PER_MONTH),
            'limit': float(FREE_CHAT_QUESTIONS_PER_MONTH),
            'allowed': False,
            'reset_at': usage['reset_at'],
        }

    subscription = users_db.get_user_valid_subscription(uid)
    plan = subscription.plan if subscription else PlanType.basic
    limits = get_plan_limits(plan)
    usage = user_usage_db.get_monthly_chat_usage(uid)

    if limits.chat_cost_usd_per_month is not None:
        unit = 'cost_usd'
        used = float(usage['cost_usd'])
        limit_value = float(limits.chat_cost_usd_per_month)
    else:
        unit = 'questions'
        used = float(usage['questions'])
        limit_value = float(limits.chat_questions_per_month) if limits.chat_questions_per_month is not None else None

    allowed = True
    if limit_value is not None and limit_value > 0:
        allowed = used < limit_value

    return {
        'plan': plan,
        'unit': unit,
        'used': used,
        'limit': limit_value,
        'allowed': allowed,
        'reset_at': usage['reset_at'],
    }


# Plans that enter usage-based overage billing instead of hard-blocking when
# they exceed their included allowance. Paying users are never asked to
# "upgrade past their plan" — the excess is billed at end of cycle against
# the card on file. Free stays hard-capped (no payment method on file).
OVERAGE_ENABLED_PLANS = {PlanType.operator, PlanType.unlimited, PlanType.architect}


def enforce_chat_quota(uid: str, platform: Optional[str] = None) -> None:
    """Block or allow a chat request based on the user's plan + usage.

    - BYOK users with an LLM key attached: always allowed, no Omi-side cost.
    - Paid plans past their cap: ALLOWED — the call is served and the excess
      accrues an overage charge. See ``utils.overage``.
    - Free plan past its cap: blocked (no card on file) → 402, which the
      chat endpoint converts into a canned AI reply for mobile UX.
    """
    # Paywall test override — bypass BYOK + plan checks so the same 402
    # surfaces that a free user past 30 questions would hit. Desktop only;
    # mobile callers continue down the normal plan path.
    if is_trial_paywalled(uid, platform):
        snapshot = get_chat_quota_snapshot(uid, platform=platform)
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
    if users_db.is_byok_active(uid) and (get_byok_key('openai') or get_byok_key('anthropic')):
        return

    snapshot = get_chat_quota_snapshot(uid, platform=platform)
    if snapshot['allowed']:
        return

    plan = snapshot['plan']

    # Every paying plan goes into overage mode past its cap, regardless of
    # whether the cap is expressed in questions or dollars. Only Free
    # (PlanType.basic) falls through to the 402 below.
    if plan in OVERAGE_ENABLED_PLANS:
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


def get_basic_plan_limits() -> PlanLimits:
    """Returns the PlanLimits object for the basic (Free) tier."""
    return PlanLimits(
        transcription_seconds=BASIC_TIER_MONTHLY_SECONDS_LIMIT,
        words_transcribed=BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH,
        insights_gained=BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH,
        chat_questions_per_month=FREE_CHAT_QUESTIONS_PER_MONTH,
    )


def get_default_basic_subscription() -> Subscription:
    """Returns a default Subscription object for the basic plan."""
    return Subscription(limits=get_basic_plan_limits())


def get_plan_limits(plan: PlanType) -> PlanLimits:
    """Returns the PlanLimits object for the given plan.

    Chat caps:
      - Free: question count
      - Operator: question count (OPERATOR_CHAT_QUESTIONS_PER_MONTH, default 500)
      - Unlimited (legacy): question count (NEO_CHAT_QUESTIONS_PER_MONTH, default 200)
      - Architect: dollar cap ($400/mo default)
    """
    if plan == PlanType.operator:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            chat_questions_per_month=OPERATOR_CHAT_QUESTIONS_PER_MONTH,
        )
    if plan == PlanType.unlimited:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            chat_questions_per_month=NEO_CHAT_QUESTIONS_PER_MONTH,
        )
    if plan == PlanType.architect:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            chat_cost_usd_per_month=ARCHITECT_CHAT_COST_USD_PER_MONTH,
        )
    if plan == PlanType.plus:
        # Transcription-capped consumer tier. Enforced by has_transcription_credits.
        return PlanLimits(
            transcription_seconds=PLUS_TIER_MONTHLY_SECONDS_LIMIT,
            words_transcribed=None,
            insights_gained=None,
            chat_questions_per_month=PLUS_CHAT_QUESTIONS_PER_MONTH,
        )
    if plan == PlanType.max:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            chat_questions_per_month=MAX_CHAT_QUESTIONS_PER_MONTH,
        )
    return get_basic_plan_limits()


def get_plan_features(plan: PlanType, simplified: bool = False) -> List[str]:
    """Returns the list of feature strings for the given plan.

    Args:
        plan: The plan type.
        simplified: If True, returns only plan-differentiating features (for mobile),
                    omitting items already shown in the top-level highlights section.
                    If False, returns the full feature list (for desktop).
    """
    if plan == PlanType.architect:
        if simplified:
            return [
                "Automations and vibe coding",
                "Priority desktop AI features",
                f"~${int(ARCHITECT_CHAT_COST_USD_PER_MONTH)} of monthly AI compute included",
            ]
        return [
            "Automations and vibe coding",
            "Unlimited listening, memories, and insights",
            "Priority desktop AI features",
            f"~${int(ARCHITECT_CHAT_COST_USD_PER_MONTH)} of monthly AI compute included",
        ]

    if plan == PlanType.operator:
        if simplified:
            return [
                f"{OPERATOR_CHAT_QUESTIONS_PER_MONTH} chat questions per month",
            ]
        return [
            f"{OPERATOR_CHAT_QUESTIONS_PER_MONTH} chat questions per month",
            "Unlimited listening and transcription",
            "Unlimited memories and insights",
            "Available on Mac, mobile, and web",
        ]

    if plan == PlanType.unlimited:
        if simplified:
            return [
                f"{NEO_CHAT_QUESTIONS_PER_MONTH} chat questions per month",
            ]
        return [
            f"{NEO_CHAT_QUESTIONS_PER_MONTH} chat questions per month",
            "Unlimited listening and transcription",
            "Unlimited memories and insights",
            "Desktop capture with Free-tier allowance",
        ]

    # Basic plan
    return [
        (
            f"{BASIC_TIER_MINUTES_LIMIT_PER_MONTH} minutes of listening per month"
            if BASIC_TIER_MINUTES_LIMIT_PER_MONTH > 0
            else "Unlimited listening time"
        ),
        (
            f"{BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH:,} words transcribed per month"
            if BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH > 0
            else "Unlimited words transcribed"
        ),
        (
            f"{BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH:,} insights per month"
            if BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH > 0
            else "Unlimited insights"
        ),
        "Unlimited memories",
    ]


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
        return True, "User can make payment"

    # If unlimited plan but inactive, user can pay
    if is_paid_plan(subscription.plan) and subscription.status == SubscriptionStatus.inactive:
        return True, "User can make payment"

    # If subscription is canceled (cancel_at_period_end=True), allow resubscription
    # This handles the case where user canceled but period hasn't ended yet
    if subscription.cancel_at_period_end:
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


def has_transcription_credits(uid: str, source: Optional[str] = None) -> bool:
    """
    Checks if a user has transcribing credits by verifying their valid subscription and usage.

    `source` is the listen-WS `source` query param (`desktop`, `omi`, `phone_call`,
    etc). The paywall test override only fires for desktop sources so that
    phone-call / Omi-device traffic for cohort UIDs is unaffected.
    """
    # Desktop trial paywall: paywalled users have zero transcription credits.
    if is_trial_paywalled(uid, source):
        return False

    # BYOK users pay Deepgram directly — there's no Omi-side transcription quota to enforce.
    # Require the Deepgram header on this request so a user can't activate BYOK
    # with fake fingerprints then omit x-byok-deepgram to ride Omi's key.
    if users_db.is_byok_active(uid) and get_byok_key('deepgram'):
        return True

    subscription = users_db.get_user_valid_subscription(uid)
    if not subscription:
        return False

    limits = get_plan_limits(subscription.plan)

    # Paid and other unlimited-transcription plans do not need a monthly usage scan.
    if not limits.transcription_seconds or limits.transcription_seconds <= 0:
        return True

    usage = get_monthly_usage_for_subscription(uid)
    if usage.get('transcription_seconds', 0) >= limits.transcription_seconds:
        return False

    return True


def get_remaining_transcription_seconds(uid: str, source: Optional[str] = None) -> int | None:
    """
    Get remaining transcription seconds for the user.
    Returns None if unlimited, otherwise the remaining seconds (>= 0).
    Used for freemium auto-switch to on-device transcription.

    `source` gates the desktop-only paywall test override (see
    `is_trial_paywalled`).
    """
    # Single-user paywall test override — surface 0 so the freemium-threshold
    # event fires and the client renders its usage-limit popup.
    if is_trial_paywalled(uid, source):
        return 0

    # BYOK: user brings their own Deepgram — no Omi quota, no freemium threshold.
    # Require the Deepgram header to prevent fake-fingerprint abuse.
    if users_db.is_byok_active(uid) and get_byok_key('deepgram'):
        return None

    subscription = users_db.get_user_valid_subscription(uid)
    if not subscription:
        # No subscription = use basic limits
        limits = get_basic_plan_limits()
    elif is_paid_plan(subscription.plan):
        return None  # Unlimited
    else:
        limits = get_plan_limits(subscription.plan)

    if not limits.transcription_seconds or limits.transcription_seconds <= 0:
        return None  # Unlimited (limit is 0 or not set)

    usage = get_monthly_usage_for_subscription(uid)
    used_seconds = usage.get('transcription_seconds', 0)

    return max(0, limits.transcription_seconds - used_seconds)


def reconcile_basic_plan_with_stripe(uid: str, subscription: Subscription | None) -> Subscription | None:
    """
    If Firestore says `basic` but there is a Stripe subscription with a future period end
    that actually maps to an unlimited plan, fix it once by reconciling with Stripe.
    """
    if (
        not subscription
        or subscription.plan != PlanType.basic
        or not subscription.stripe_subscription_id
        or not subscription.current_period_end
    ):
        return subscription

    try:
        period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        # Only bother reconciling if the stored period end is still in the future.
        if period_end_dt < datetime.now(timezone.utc):
            return subscription

        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
        stripe_sub_dict: Optional[Dict[str, Any]] = stripe_sub.to_dict() if stripe_sub else None  # type: ignore[reportDeprecated]  # stripe public serialization API
        if not stripe_sub_dict:
            return subscription

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

            # If the stored Stripe sub is actually a paid plan, fix our local record.
            if plan_type and is_paid_plan(plan_type):
                subscription.plan = plan_type
                subscription.status = SubscriptionStatus.active
                subscription.current_period_end = stripe_sub_dict.get('current_period_end')
                subscription.current_period_start = stripe_sub_dict.get('current_period_start')
                subscription.cancel_at_period_end = stripe_sub_dict.get('cancel_at_period_end', False)
                subscription.current_price_id = price_id
                subscription.limits = get_plan_limits(plan_type)

                # Persist the corrected subscription back to Firestore (without dynamic fields).
                users_db.update_user_subscription(uid, subscription.model_dump())
                return subscription

        # Stored sub is canceled / unknown / not a paid plan. The user may have
        # canceled it and started a *different* active subscription (possibly on
        # a new Stripe customer) — the stored sub id alone can't see that. Adopt
        # the customer's current active paid sub so an old sub's cancellation
        # can't leave a paying user stranded on basic.
        active = find_active_paid_subscription_for_user(uid)
        if active:
            users_db.update_user_subscription(uid, active.model_dump())
            return active

    except Exception as e:
        # Don't break user flows on reconciliation issues; just log and continue with existing data.
        logger.error(f"[reconcile_basic_plan_with_stripe] Error reconciling Stripe subscription for user {uid}: {e}")

    return subscription
