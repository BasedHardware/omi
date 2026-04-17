import os
from datetime import datetime, timezone
from typing import List, Optional
import stripe

import database.users as users_db
import database.user_usage as user_usage_db
from models.users import PlanType, SubscriptionStatus, Subscription, PlanLimits
from utils.log_sanitizer import sanitize
import logging

logger = logging.getLogger(__name__)

PAID_PLAN_TYPES = {PlanType.unlimited, PlanType.pro, PlanType.operator}


def is_paid_plan(plan: PlanType) -> bool:
    return plan in PAID_PLAN_TYPES


def get_paid_plan_definitions() -> list[dict]:
    """All plan definitions.

    Pro is displayed as "Architect" — pure rename. Unlimited is kept as legacy
    so existing subscribers keep their access and Stripe webhooks still resolve,
    but it's filtered out of the "new user" purchase catalog via
    `filter_plans_for_user`.
    """
    return [
        {
            "plan_type": PlanType.operator,
            "plan_id": "operator",
            "title": "Operator",
            "monthly_price_id": os.getenv('STRIPE_OPERATOR_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_OPERATOR_ANNUAL_PRICE_ID'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.pro,
            "plan_id": "pro",
            "title": "Architect",
            "monthly_price_id": os.getenv('STRIPE_PRO_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_PRO_ANNUAL_PRICE_ID'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.unlimited,
            "plan_id": "unlimited",
            "title": "Unlimited (legacy)",
            "monthly_price_id": os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID'),
            "annual_price_id": os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID'),
            "annual_description": "Save 20% with annual billing.",
            "legacy": True,
        },
    ]


def filter_plans_for_user(definitions: list[dict], current_plan: PlanType) -> list[dict]:
    """Drop legacy plans from the purchase catalog — always.

    Legacy subscribers still see their current plan at the top of the Settings
    → Plan and Usage screen (rendered from `subscription.plan`, not from the
    purchase catalog) and can manage it via the Stripe customer portal, so
    there's no need to offer it as a picker card too.
    """
    return [d for d in definitions if not d.get('legacy')]


# Minimum desktop build that ships with the new plan catalog + quota UI.
# Clients below this threshold — older desktop, or any mobile build — get the
# pre-Operator plan shape. Once a stable release catches up, lower this.
NEW_PLANS_MIN_DESKTOP_VERSION = os.getenv('NEW_PLANS_MIN_DESKTOP_VERSION', '0.11.324')


def should_show_new_plans(platform: Optional[str], app_version: Optional[str]) -> bool:
    """True iff this caller's client has the Swift code that understands the new
    Operator + Architect plan shape and the /v1/users/me/usage-quota endpoint.

    Any macOS desktop build qualifies. iOS / Android clients always get the
    legacy plan catalog so the rollout is gated to desktop without cross-
    client breakage.

    The existing APIClient.swift doesn't send an X-App-Version header, so we
    cannot version-gate per-build — version is included only as an opt-in
    tightening hook once the client starts sending it.
    """
    from database.announcements import _compare_versions

    if not platform or platform.lower() != 'macos':
        return False

    # No version header: assume a recent-enough desktop build. Desktop clients
    # don't currently send X-App-Version (see APIClient.swift buildHeaders),
    # so requiring it here would fail-closed for every real desktop user.
    if not app_version:
        return True

    try:
        return _compare_versions(app_version, NEW_PLANS_MIN_DESKTOP_VERSION) >= 0
    except Exception as e:
        # Malformed version — fail-open on macOS rather than show the old
        # catalog to a desktop client. Logged so ops can distinguish a real
        # parser regression from a one-off bad header.
        logger.warning(
            f"should_show_new_plans: failed to parse X-App-Version, falling open "
            f"(platform={sanitize(str(platform))} version={sanitize(str(app_version))} err={sanitize(str(e))})"
        )
        return True


def adapt_plans_for_legacy_client(definitions: list[dict]) -> list[dict]:
    """Transform the new-shape plan catalog back into the pre-v0.11.324 shape
    so older clients (mobile, stable desktop) keep showing the old plan titles
    and don't see Operator in their purchase options.

    Hides the Operator entry entirely, renames Architect back to "Omi Pro",
    and drops the legacy suffix + flag from Unlimited so pre-rollout clients
    still see it as a normal (non-legacy) Unlimited Plan.
    """
    out: list[dict] = []
    for d in definitions:
        if d['plan_id'] == 'operator':
            continue
        adapted = dict(d)
        if d['plan_id'] == 'pro':
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
    if plan == PlanType.pro:
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
    """Determines the plan type based on the Stripe price ID."""
    for definition in get_paid_plan_definitions():
        if price_id in (definition["monthly_price_id"], definition["annual_price_id"]):
            return definition["plan_type"]
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
BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH', '0'))

# Chat caps per plan. Env-overridable for ops.
FREE_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('FREE_CHAT_QUESTIONS_PER_MONTH', '30'))
PLUS_CHAT_QUESTIONS_PER_MONTH = int(os.getenv('PLUS_CHAT_QUESTIONS_PER_MONTH', '500'))
PRO_CHAT_COST_USD_PER_MONTH = float(os.getenv('PRO_CHAT_COST_USD_PER_MONTH', '400.0'))

# Hard kill-switch for the cap. Default OFF so we can deploy the backend to
# prod without immediately blocking any existing over-cap user. Flip to "true"
# via Cloud Run env var once beta has validated the UX.
CHAT_CAP_ENFORCEMENT_ENABLED = os.getenv('CHAT_CAP_ENFORCEMENT_ENABLED', 'false').lower() in ('true', '1', 'yes', 'on')

# Display names shown to users. Internal PlanType stays the same for Stripe compat.
PLAN_DISPLAY_NAMES = {
    PlanType.basic: 'Free',
    PlanType.unlimited: 'Unlimited (legacy)',
    PlanType.pro: 'Architect',
    PlanType.operator: 'Operator',
}


def get_plan_display_name(plan: PlanType) -> str:
    return PLAN_DISPLAY_NAMES.get(plan, plan.value.capitalize())


def get_chat_quota_snapshot(uid: str) -> dict:
    """Cheap computation of `is_allowed / used / limit / unit / plan` — shared
    between the `/v1/users/me/usage-quota` endpoint and the enforcement helper.

    Imports are done locally to avoid the circular `utils.subscription` ↔
    `database.users` cycle at module import time.
    """
    from database import user_usage as _user_usage
    from database.users import get_user_valid_subscription as _get_sub

    subscription = _get_sub(uid)
    plan = subscription.plan if subscription else PlanType.basic
    limits = get_plan_limits(plan)
    usage = _user_usage.get_monthly_chat_usage(uid)

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


def enforce_chat_quota(uid: str) -> None:
    """Raise HTTPException(402) if the user is past their monthly chat cap.

    Guarded by CHAT_CAP_ENFORCEMENT_ENABLED so we can deploy the code first,
    ship the UI to beta, validate, then flip the kill-switch from ops.
    """
    from fastapi import HTTPException

    if not CHAT_CAP_ENFORCEMENT_ENABLED:
        return

    snapshot = get_chat_quota_snapshot(uid)
    if snapshot['allowed']:
        return

    plan = snapshot['plan']
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
        memories_created=BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH,
        chat_questions_per_month=FREE_CHAT_QUESTIONS_PER_MONTH,
    )


def get_default_basic_subscription() -> Subscription:
    """Returns a default Subscription object for the basic plan."""
    return Subscription(limits=get_basic_plan_limits())


def get_plan_limits(plan: PlanType) -> PlanLimits:
    """Returns the PlanLimits object for the given plan.

    Chat caps:
      - Free: question count
      - Oracle + legacy Unlimited: question count (200/mo default)
      - Pro (Architect): dollar cap ($400/mo default)
    """
    if plan in (PlanType.unlimited, PlanType.operator):
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            memories_created=None,
            chat_questions_per_month=PLUS_CHAT_QUESTIONS_PER_MONTH,
        )
    if plan == PlanType.pro:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            memories_created=None,
            chat_cost_usd_per_month=PRO_CHAT_COST_USD_PER_MONTH,
        )
    return get_basic_plan_limits()


def get_plan_features(plan: PlanType) -> List[str]:
    """Returns the list of feature strings for the given plan."""
    if plan == PlanType.pro:
        # Lead with what you GET, keep the $400 as a soft fair-use line at the bottom.
        return [
            "Automations and vibe coding",
            "Unlimited listening, memories, and insights",
            "Priority desktop AI features",
            f"~${int(PRO_CHAT_COST_USD_PER_MONTH)} of monthly AI compute included (fair-use cap)",
        ]

    if plan in (PlanType.unlimited, PlanType.operator):
        return [
            f"{PLUS_CHAT_QUESTIONS_PER_MONTH} chat questions per month",
            "Unlimited listening and transcription",
            "Unlimited memories and insights",
            "Shared with mobile and web",
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
        (
            f"{BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH} memories per month"
            if BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH > 0
            else "Unlimited memories"
        ),
    ]


def can_user_make_payment(uid: str, target_price_id: str = None) -> tuple[bool, str]:
    """
    Checks if a user can make a new payment based on their current subscription status.

    Args:
        uid: User ID
        target_price_id: Optional target price ID to check if this is an upgrade/downgrade

    Returns:
        tuple: (can_pay: bool, reason: str)
    """
    subscription = users_db.get_user_valid_subscription(uid)

    # If no subscription or basic plan, user can pay
    if not subscription or subscription.plan == PlanType.basic:
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
                            stripe_sub_dict = stripe_sub.to_dict()
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


def get_monthly_usage_for_subscription(uid: str) -> dict:
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
        launch_date = datetime.strptime(subscription_launch_date_str, '%Y-%m-%d')
    except ValueError:
        # Invalid date format, treat as not launched.
        return {}

    now = datetime.utcnow()
    if now < launch_date:
        # Launch date is in the future, so no usage is counted yet.
        return {}

    return user_usage_db.get_monthly_usage_stats_since(uid, now, launch_date)


def has_transcription_credits(uid: str) -> bool:
    """
    Checks if a user has transcribing credits by verifying their valid subscription and usage.
    """
    subscription = users_db.get_user_valid_subscription(uid)
    if not subscription:
        return False

    usage = get_monthly_usage_for_subscription(uid)
    limits = get_plan_limits(subscription.plan)

    # Check transcription seconds (0 means unlimited)
    if limits.transcription_seconds and limits.transcription_seconds > 0:
        if usage.get('transcription_seconds', 0) >= limits.transcription_seconds:
            return False

    return True


def get_remaining_transcription_seconds(uid: str) -> int | None:
    """
    Get remaining transcription seconds for the user.
    Returns None if unlimited, otherwise the remaining seconds (>= 0).
    Used for freemium auto-switch to on-device transcription.
    """
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
        stripe_sub_dict = stripe_sub.to_dict() if stripe_sub else None
        if not stripe_sub_dict:
            return subscription

        items = stripe_sub_dict.get('items', {}).get('data') or []
        price_id = None
        if items and items[0].get('price'):
            price_id = items[0]['price'].get('id')

        stripe_status = stripe_sub_dict.get('status')
        if stripe_status not in ('active', 'trialing') or not price_id:
            return subscription

        try:
            plan_type = get_plan_type_from_price_id(price_id)
        except ValueError:
            plan_type = None

        # If Stripe says this is actually a paid plan, fix our local record.
        if plan_type and is_paid_plan(plan_type):
            subscription.plan = plan_type
            subscription.status = SubscriptionStatus.active
            subscription.current_period_end = stripe_sub_dict.get('current_period_end')
            subscription.cancel_at_period_end = stripe_sub_dict.get('cancel_at_period_end', False)
            subscription.current_price_id = price_id
            subscription.limits = get_plan_limits(plan_type)

            # Persist the corrected subscription back to Firestore (without dynamic fields).
            users_db.update_user_subscription(uid, subscription.dict())

    except Exception as e:
        # Don't break user flows on reconciliation issues; just log and continue with existing data.
        logger.error(f"[reconcile_basic_plan_with_stripe] Error reconciling Stripe subscription for user {uid}: {e}")

    return subscription
