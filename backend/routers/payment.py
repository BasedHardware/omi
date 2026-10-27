from config.plan_catalog import configured_ladder_prices, validate_ladder_price
from database.fsr_read_cache import fresh_reader, fresh_reads
import os
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Request, Header, HTTPException, APIRouter, Depends, Query
from google.api_core.exceptions import NotFound as FirestoreNotFound
import stripe
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import List, Optional
import uuid
import time
from urllib.parse import urljoin

from database import (
    users as users_db,
    conversations as conversations_db,
    memories as memories_db,
    action_items as action_items_db,
)
from database.locked_content import has_recoverable_locked_content
from database.redis_db import set_credits_invalidation_signal
from config.plan_catalog import _paid_period_still_open, plan_uses_overage
from utils.subscription_state_machine import (
    project_subscription,
    preserves_current_paid_subscription,
    ResolvedStripeEvent,
    transition,
    schedule_transition,
)
from utils.billing_currency import (
    BillingCurrencyUnavailable,
    management_binding,
    price_for_currency,
    subscription_currency,
)
from utils.storefront_copy import format_money
from utils.billing_flags import webhook_ledger_enabled
from utils.stripe_webhook_ledger import dispatch_with_ledger, RetryableBillingSkip
from config.stt_cap_dispatch import any_execution_admission_enabled as funded_processing_enabled
from utils.fair_use import clear_fair_use_on_upgrade
from utils.notifications import send_notification, send_subscription_paid_personalized_notification
from models.users import PlanType, Subscription, SubscriptionStatus, PlanLimits
from utils.subscription import (
    get_basic_plan_limits,
    get_paid_plan_definitions,
    get_plan_type_from_price_id,
    is_purchasable_price_id,
    get_plan_limits,
    is_paid_plan,
    filter_plans_for_user,
    desktop_to_consumer_plan_change_error,
    should_show_new_plans,
    adapt_plans_for_legacy_client,
    clear_trial_paywall_cache,
    find_active_paid_subscription_for_user,
    price_ids_match_plan_and_interval,
)
from utils.observability.fallback import record_fallback
from utils.observability.subscription_events import record_subscription_event
from database.users import (
    get_stripe_connect_account_id,
    set_stripe_connect_account_id,
    set_paypal_payment_details,
    get_default_payment_method,
    set_default_payment_method,
    get_paypal_payment_details,
    get_user_profile,
)
from utils import stripe as stripe_utils
from utils.apps import find_app_subscription, paid_app, set_user_app_sub_customer_id
from utils.other import endpoints as auth
from fastapi.responses import HTMLResponse

from utils.stripe import base_url, create_connect_account, refresh_connect_account_link, is_onboarding_complete
from utils import subscription as subscription_utils
from utils.overage import (
    OVERAGE_EXPLAINER_TITLE,
    PROVIDER_REFERENCE_RATES,
    build_explainer_text,
    get_user_overage,
)
from utils.executors import db_executor, stripe_executor, run_blocking
from utils.log_sanitizer import sanitize
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _stripe_client_error_detail(e: stripe.error.StripeError, fallback: str) -> str:
    """User-safe detail for a Stripe error HTTP response.

    Stripe's `user_message` is written to be shown to end users; anything else on
    the exception (internal error text, account/customer/subscription IDs) is
    diagnostic detail that belongs in server logs (via `sanitize()`), not the
    response body.
    """
    user_message = getattr(e, 'user_message', None)
    return user_message if user_message else fallback


class CreateCheckoutRequest(BaseModel):
    price_id: str = Field(..., min_length=1, max_length=255)
    promotion_code: Optional[str] = None
    # A free trial of this many days before the first charge. Honored only for a first-time
    # subscriber (no Stripe customer yet), so nobody chains trials by cancelling and re-subscribing.
    trial_days: Optional[int] = Field(None, ge=1, le=30)


class UpgradeSubscriptionRequest(BaseModel):
    price_id: str = Field(..., min_length=1, max_length=255)
    promotion_code: Optional[str] = None


class PaymentMutationResponse(BaseModel):
    status: str


class PaymentStatusMessageResponse(BaseModel):
    status: str
    message: str


class PaymentCheckoutSessionResponse(BaseModel):
    url: Optional[str] = None
    session_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    next_billing_date: Optional[int] = None

    @model_validator(mode='after')
    def validate_success_shape(self):
        if self.status == 'reactivated':
            if not self.message or self.next_billing_date is None:
                raise ValueError('reactivated checkout responses require message and next_billing_date')
            return self
        if not self.url or not self.session_id:
            raise ValueError('checkout session responses require url and session_id')
        return self


class PaymentSubscriptionResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    plan: str = 'basic'
    status: str = 'active'
    stripe_subscription_id: Optional[str] = None
    current_period_start: Optional[int] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: bool = False
    current_price_id: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    limits: PlanLimits = Field(default_factory=get_basic_plan_limits)
    deprecated: bool = False
    deprecation_message: Optional[str] = None


class AppSubscriptionDetails(BaseModel):
    id: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: Optional[bool] = None
    price_id: Optional[str] = None
    customer_id: Optional[str] = None


class AppSubscriptionResponse(BaseModel):
    subscription: Optional[AppSubscriptionDetails] = None


class AppSubscriptionCancelResponse(BaseModel):
    status: str
    message: str
    cancel_at_period_end: Optional[bool] = None
    current_period_end: Optional[int] = None


class PaymentUpgradeSubscriptionResponse(BaseModel):
    status: str
    message: str
    subscription: PaymentSubscriptionResponse
    days_remaining: int
    schedule_id: Optional[str] = None


class CustomerPortalSessionResponse(BaseModel):
    url: str


class StripeConnectAccountResponse(BaseModel):
    account_id: str
    url: str


class StripeOnboardingStatusResponse(BaseModel):
    onboarding_complete: bool


class StripeSupportedCountryResponse(BaseModel):
    id: str
    name: str


class PayPalPaymentDetailsResponse(BaseModel):
    email: str
    paypalme_url: str


class SavePayPalPaymentDetailsRequest(BaseModel):
    email: str
    paypalme_url: str


class PaymentMethodStatusResponse(BaseModel):
    stripe: str
    paypal: str
    default: Optional[str] = None


class SetDefaultPaymentMethodRequest(BaseModel):
    method: str


class PricingOption(BaseModel):
    id: str  # price_id
    plan_id: str = ''  # "unlimited", "operator", "architect"
    title: str  # "Monthly" or "Annual"
    price_string: str  # "$19/month" or "$199/year"
    description: Optional[str] = None
    subtitle: Optional[str] = None  # e.g. "2000 questions per month"
    eyebrow: Optional[str] = None  # e.g. "Starter", "Most popular"
    interval: str  # "month" or "year"
    unit_amount: int  # Stripe minor units (whole yen for JPY)
    currency: str = 'usd'
    billing_total: Optional[str] = None
    is_active: bool = False  # Added for active status


class AvailablePlansResponse(BaseModel):
    plans: List[PricingOption]


def _build_subscription_from_stripe_object(
    stripe_sub: dict, grant_cancel_grace: bool = False, now: int | None = None
) -> Subscription | None:
    """Builds a Subscription object from a Stripe Subscription object."""
    stripe_status = stripe_sub['status']

    # For inactive subscriptions (canceled, unpaid, etc.), always downgrade to Basic
    # regardless of price ID — ensures deleted/canceled users don't keep paid access.
    # Exception (subscription-event paths only): an immediately-canceled subscription
    # (e.g. the customer portal's "cancel immediately" mode) whose paid period has not
    # ended yet. The customer paid through current_period_end, so paid access must
    # survive the early terminal event. The candidate still routes through the
    # stale-downgrade shield in the webhook handler, so a newer stored paid
    # subscription or an adopted replacement always wins over this grace.
    if stripe_status not in ('active', 'trialing'):
        period_end = stripe_sub.get('current_period_end')
        if (
            grant_cancel_grace
            and stripe_status == 'canceled'
            and period_end
            and period_end > (now if now is not None else int(time.time()))
        ):
            items = stripe_sub.get('items', {}).get('data', [])
            price_id = items[0]['price']['id'] if items else None
            try:
                paid_plan = get_plan_type_from_price_id(price_id) if price_id else None
            except ValueError:
                paid_plan = None
            if paid_plan is not None:
                return Subscription(
                    plan=paid_plan,
                    status=SubscriptionStatus.active,
                    current_period_end=period_end,
                    current_period_start=stripe_sub.get('current_period_start'),
                    stripe_subscription_id=stripe_sub['id'],
                    cancel_at_period_end=True,
                    limits=get_plan_limits(paid_plan),
                )
        return project_subscription(stripe_sub, None, get_basic_plan_limits())

    # Active subscriptions: resolve plan from price ID
    price_id = stripe_sub['items']['data'][0]['price']['id'] if stripe_sub['items']['data'] else None

    if not price_id:
        return None

    try:
        plan = get_plan_type_from_price_id(price_id)
    except ValueError as e:
        # Preserve observable unknown-price skips (the prior multi-week billing
        # drop shape); see .github/agent-docs/plan-source-of-truth.md.
        record_fallback(
            component='other',
            from_mode='stripe_price_resolution',
            to_mode='skip_subscription_write',
            # Must be a member of ALLOWED_REASONS, or bucket_reason() relabels it
            # 'other' and the reason dimension is lost. The price is absent from both
            # the catalog ledger and the env binding: a configuration gap.
            reason='config_incomplete',
            outcome='degraded',
            log=logger,
        )
        logger.error(
            f"Unresolvable Stripe price {sanitize(str(price_id))} on an active subscription; "
            f"local row will not be updated: {sanitize(str(e))}"
        )
        return None

    return project_subscription(stripe_sub, plan, get_plan_limits(plan))


def _update_subscription_from_session(uid: str, session: stripe.checkout.Session) -> bool:
    with fresh_reads():
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        try:
            if customer_id:
                users_db.set_stripe_customer_id(uid, customer_id)

            if subscription_id:
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                if stripe_sub:
                    new_subscription = _build_subscription_from_stripe_object(stripe_sub.to_dict())
                    if new_subscription is None:
                        return False
                    users_db.update_user_subscription(uid, new_subscription.model_dump())
                    logger.info(f"Subscription for user {uid} updated from session {session.id}.")
        except FirestoreNotFound:
            logger.warning(
                f"Stripe webhook: user {uid} not found in Firestore, " f"skipping checkout session subscription update"
            )

        return True


@fresh_reader
def _try_reactivate_subscription(uid: str, target_price_id: str) -> dict | None:
    """
    Admit fresh checkout only after ruling out an existing Stripe subscription.

    When the local Firestore row is missing or stale (no ``stripe_subscription_id``),
    fall back to Stripe as the source of truth so a pending-cancellation
    subscription Stripe still holds for this user can be reactivated instead of
    dropping into a fresh-checkout flow.

    Returns:
        Reactivation details, or None when fresh checkout is safe. An existing
        nonterminal subscription raises 409; an inconclusive check raises 503.
    """
    current_subscription = users_db.get_user_subscription(uid)
    recovered_from_stripe = False
    if not current_subscription or not current_subscription.stripe_subscription_id:
        # The local row may be missing/stale (e.g. read-after-write lag or a
        # sync issue). Stripe is the recovery source of truth: find the active
        # paid subscription there and use its id to attempt reactivation.
        current_subscription = find_active_paid_subscription_for_user(uid)
        recovered_from_stripe = True
        if not current_subscription or not current_subscription.stripe_subscription_id:
            record_fallback(
                component='other',
                from_mode='firestore_subscription',
                to_mode='stripe_subscription',
                reason='local_heal',
                outcome='exhausted',
                log=logger,
            )
            return None

    # Organization grants store a one-time PaymentIntent in this legacy field;
    # it is not a recurring subscription and must not be retrieved as one.
    if current_subscription.stripe_subscription_id.startswith('pi_'):
        return None

    try:
        # Retrieve current subscription from Stripe to check status
        try:
            stripe_sub = stripe.Subscription.retrieve(current_subscription.stripe_subscription_id)
        except stripe.InvalidRequestError as exc:
            # Only a definitive absence from *retrieve* permits new checkout.
            # A timeout, bad credentials, or a failed modify is not that proof.
            if exc.code == 'resource_missing' and exc.http_status == 404:
                return None
            raise
        stripe_sub_dict = stripe_sub.to_dict()
        status = stripe_sub_dict['status']
        if not isinstance(status, str) or not status:
            raise ValueError('Missing subscription status')
        if status in stripe_utils.TERMINAL_SUBSCRIPTION_STATUSES:
            return None

        # Check if subscription is active but scheduled to cancel
        if status == 'active' and stripe_sub_dict.get('cancel_at_period_end') == True:
            current_price_id = stripe_sub_dict['items']['data'][0]['price']['id']

            # If resubscribing to the same plan, just remove cancellation
            current_interval = stripe_sub_dict['items']['data'][0]['price'].get('recurring', {}).get('interval')
            if price_ids_match_plan_and_interval(current_price_id, target_price_id, current_interval):
                stripe.Subscription.modify(current_subscription.stripe_subscription_id, cancel_at_period_end=False)

                # Update our database
                current_subscription.cancel_at_period_end = False
                users_db.update_user_subscription(uid, current_subscription.model_dump())
                set_credits_invalidation_signal(uid)
                clear_trial_paywall_cache(uid)
                if recovered_from_stripe:
                    record_fallback(
                        component='other',
                        from_mode='firestore_subscription',
                        to_mode='stripe_subscription',
                        reason='local_heal',
                        outcome='recovered',
                        log=logger,
                    )

                # Calculate next billing date
                next_billing = datetime.fromtimestamp(stripe_sub_dict['current_period_end'], tz=timezone.utc).strftime(
                    '%B %d, %Y'
                )

                return {
                    "status": "reactivated",
                    "message": f"Your subscription has been reactivated! No charge now - your plan will automatically renew on {next_billing}.",
                    "next_billing_date": stripe_sub_dict['current_period_end'],
                }
        # Nonterminal Stripe state takes precedence over the projected Free
        # plan, even when the root customer ID or local billing period is stale.
        # Plan changes belong on the existing upgrade/management rail.
        raise HTTPException(
            status_code=409,
            detail='You already have a subscription. Manage your existing subscription instead of starting a new checkout.',
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Provider errors may contain account data. Log only the failure type.
        logger.error('Checkout subscription verification failed (%s)', type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="We couldn't verify your existing subscription. Please try again before starting checkout.",
        ) from exc


@router.get('/v1/payments/available-plans', response_model=AvailablePlansResponse)
def get_available_plans_endpoint(
    # Payment / plan surfaces must stay reachable even if BYOK fingerprints
    # drift (e.g. user rotated a key locally without re-activating). Otherwise
    # a broken-BYOK user can't see or change their plan to recover.
    uid: str = Depends(auth.get_current_user_uid_no_byok_validation),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
    x_billing_currency: Optional[str] = Header(None, alias='X-Omi-Billing-Currency'),
):
    """Get available subscription plans with their price IDs and billing intervals."""
    try:
        # Get user's current subscription to determine which plan is active
        current_subscription = users_db.get_user_subscription(uid)
        current_price_id = None
        scheduled_price_id = None
        billing_currency = None

        # Read currency for current paid subscriptions, including pending cancellation.
        if (
            current_subscription
            and is_paid_plan(current_subscription.plan)
            and current_subscription.status == SubscriptionStatus.active
            and current_subscription.stripe_subscription_id
            and current_subscription.stripe_subscription_id.startswith('sub_')
            and (
                not current_subscription.current_period_end
                or current_subscription.current_period_end > int(time.time())
            )
        ):
            try:
                stripe_sub = stripe.Subscription.retrieve(current_subscription.stripe_subscription_id).to_dict()
                billing_currency = subscription_currency(stripe_sub)
                if stripe_sub and stripe_sub['items']['data']:
                    current_price_id = stripe_sub['items']['data'][0]['price']['id']

                    # Check for pending subscription schedules
                    customer_id = stripe_sub.get('customer')
                    if customer_id:
                        try:
                            # Get all subscription schedules for this customer
                            schedules = stripe.SubscriptionSchedule.list(customer=customer_id, limit=2)

                            for schedule in schedules.data:
                                # Check if this is an active schedule (not completed or canceled)
                                if schedule.status in ['active', 'not_started']:
                                    if hasattr(schedule, 'phases') and schedule.phases and len(schedule.phases) > 1:
                                        phase = schedule.phases[1]
                                        if hasattr(phase, 'items') and phase.items:
                                            phase_dict = phase.to_dict()
                                            if phase_dict.get('items') and len(phase_dict['items']) > 0:
                                                scheduled_price_id = phase_dict['items'][0]['price']
                                                break
                        except Exception as e:
                            logger.error(f"Error checking subscription schedules: {sanitize(str(e))}")

            except Exception as e:
                logger.error(f"Error retrieving current subscription: {sanitize(str(e))}")
                raise HTTPException(status_code=503, detail="Could not verify your billing currency. Please try again.")
        else:
            logger.info(f"No active paid subscription found for user {uid}")

        # Older installed sheets hardcode USD in the annual confirmation. Do
        # not offer them JPY targets until they advertise currency-safe rendering.
        if billing_currency and billing_currency != 'usd' and x_billing_currency != '1':
            raise HTTPException(status_code=409, detail="Please update Omi to change plans in your billing currency.")

        # Version-gate the new Operator + Architect catalog. Mobile and older
        # desktop builds see the pre-rollout plan shape. Then legacy-filter so
        # existing subscribers still see their current plan.
        new_plans_enabled = should_show_new_plans(x_app_platform, x_app_version)
        all_definitions = get_paid_plan_definitions()
        if not new_plans_enabled:
            all_definitions = adapt_plans_for_legacy_client(all_definitions)
            # Operator subscriber on old client: map their Stripe prices to Unlimited
            # so is_active detection works against the legacy catalog.
            if current_subscription and current_subscription.plan == PlanType.operator:
                op_monthly = os.getenv('STRIPE_OPERATOR_MONTHLY_PRICE_ID', '')
                op_annual = os.getenv('STRIPE_OPERATOR_ANNUAL_PRICE_ID', '')
                unlim_monthly = os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID', '')
                unlim_annual = os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID', '')
                price_map = {}
                if op_monthly and unlim_monthly:
                    price_map[op_monthly] = unlim_monthly
                if op_annual and unlim_annual:
                    price_map[op_annual] = unlim_annual
                current_price_id = price_map.get(current_price_id, current_price_id)
                scheduled_price_id = price_map.get(scheduled_price_id, scheduled_price_id)

        # Catalog filtering keys off the same period-valid plan lookup as
        # checkout (new_buyer_single_plan_violation): a lapsed Operator or
        # Architect record keeps its stored plan after the paid period ends,
        # and the mobile manage-only fast path would otherwise leave that user
        # with only their expired desktop SKU instead of the Omi Pro offer.
        valid_subscription = users_db.get_user_valid_subscription(uid)
        current_plan = valid_subscription.plan if valid_subscription else PlanType.basic
        if not new_plans_enabled and current_plan == PlanType.operator:  # old clients: remapped Unlimited price
            current_plan = PlanType.unlimited
        pricing_options: List[PricingOption] = []
        active_price_ids = {current_price_id, scheduled_price_id}
        if current_subscription and current_subscription.cancel_at_period_end:
            active_price_ids.clear()
        for definition in filter_plans_for_user(all_definitions, current_plan, platform=x_app_platform):
            monthly_price_id = definition["monthly_price_id"]
            annual_price_id = definition["annual_price_id"]
            if monthly_price_id:
                try:
                    monthly_price = price_for_currency(stripe.Price.retrieve(monthly_price_id), billing_currency)
                    pricing_options.append(
                        PricingOption(
                            id=monthly_price.id,
                            plan_id=definition["plan_id"],
                            title=f'{definition["title"]} Monthly',
                            price_string=f"{format_money(monthly_price.unit_amount, monthly_price.currency)}/mo",
                            currency=monthly_price.currency,
                            billing_total=format_money(monthly_price.unit_amount, monthly_price.currency),
                            description=definition.get("description"),
                            subtitle=definition.get("subtitle"),
                            eyebrow=definition.get("eyebrow"),
                            interval=monthly_price.recurring.interval,
                            unit_amount=monthly_price.unit_amount,
                            is_active=monthly_price.id in active_price_ids,
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Error retrieving monthly price from Stripe for {definition['plan_id']} "
                        f"(price_id={monthly_price_id}): {sanitize(str(e))}"
                    )
            if annual_price_id:
                try:
                    annual_price = price_for_currency(stripe.Price.retrieve(annual_price_id), billing_currency)
                    pricing_options.append(
                        PricingOption(
                            id=annual_price.id,
                            plan_id=definition["plan_id"],
                            title=f'{definition["title"]} Annual',
                            price_string=f"{format_money(annual_price.unit_amount // 12, annual_price.currency)}/mo",
                            currency=annual_price.currency,
                            billing_total=format_money(annual_price.unit_amount, annual_price.currency),
                            description=f'{definition.get("description", "")} {definition["annual_description"]}'.strip(),
                            subtitle=definition.get("subtitle"),
                            eyebrow=definition.get("eyebrow"),
                            interval=annual_price.recurring.interval,
                            unit_amount=annual_price.unit_amount,
                            is_active=annual_price.id in active_price_ids,
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Error retrieving annual price from Stripe for {definition['plan_id']} "
                        f"(price_id={annual_price_id}): {sanitize(str(e))}"
                    )

        if not pricing_options:
            raise HTTPException(
                status_code=409 if billing_currency else 500,
                detail="No plans are available in your billing currency. Please contact support.",
            )

        return AvailablePlansResponse(plans=pricing_options)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching available plans: {sanitize(str(e))}")
        raise HTTPException(status_code=500, detail="Failed to fetch available plans")


class OverageInfoResponse(BaseModel):
    plan: str
    plan_type: str
    is_overage_plan: bool
    included_questions: Optional[int] = None
    included_cost_usd: Optional[float] = None
    used_questions: int = 0
    excess_questions: int = 0
    real_cost_usd: float = 0.0
    overage_usd: float = 0.0
    markup_multiplier: float
    markup_percent: float
    reset_at: Optional[int] = None
    explainer_title: str
    explainer_body: str
    provider_reference_rates: dict
    byok_available: bool = True


@router.get('/v1/payments/overage-info', response_model=OverageInfoResponse)
def get_overage_info_endpoint(uid: str = Depends(auth.get_current_user_uid_no_byok_validation)):
    """Explain overage billing + return the user's current accrued charge.

    Powers the clickable "What happens past the limit?" text on the plan page.
    Safe to call on any plan — non-overage plans just get a zero snapshot plus
    the explainer copy.
    """
    subscription = users_db.get_user_subscription(uid)
    plan = subscription.plan if subscription else PlanType.basic
    snapshot = get_user_overage(uid, plan)

    return OverageInfoResponse(
        plan=subscription_utils.get_plan_display_name(plan),
        plan_type=plan.value,
        is_overage_plan=plan_uses_overage(plan),
        included_questions=snapshot['included_questions'],
        included_cost_usd=snapshot.get('included_cost_usd'),
        used_questions=snapshot['used_questions'],
        excess_questions=snapshot['excess_questions'],
        real_cost_usd=snapshot['real_cost_usd'],
        overage_usd=snapshot['overage_usd'],
        markup_multiplier=snapshot['markup_multiplier'],
        markup_percent=round((snapshot['markup_multiplier'] - 1.0) * 100.0, 2),
        reset_at=snapshot['reset_at'],
        explainer_title=OVERAGE_EXPLAINER_TITLE,
        explainer_body=build_explainer_text(),
        provider_reference_rates=PROVIDER_REFERENCE_RATES,
    )


def _validate_price_id(price_id: str) -> None:
    """Reject a blank/whitespace-only or non-purchasable price_id before any Stripe call.

    A valid checkout or upgrade target must be a currently-purchasable plan price. Retained catalog
    prices are intentionally rejected here: they exist for existing subscribers' renewals and
    reconciliation, not as new purchase targets, so a caller cannot select a hidden or deprecated
    price by posting its ID directly. This is the checkout and upgrade boundary check.
    """
    if not price_id or not price_id.strip():
        raise HTTPException(status_code=400, detail="price_id is required")
    if not is_purchasable_price_id(price_id):
        raise HTTPException(status_code=400, detail="Unknown price_id")
    if price_id in configured_ladder_prices():
        try:
            validate_ladder_price(price_id, stripe.Price.retrieve(price_id).to_dict_recursive())
        except Exception as error:
            raise HTTPException(status_code=503, detail='Ladder price unavailable') from error


@router.post(
    '/v1/payments/checkout-session',
    response_model=PaymentCheckoutSessionResponse,
    response_model_exclude_none=True,
)
@fresh_reader
def create_checkout_session_endpoint(
    request: CreateCheckoutRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    # Retained currency prices are management-only; ordinary targets keep the
    # existing purchase and eligibility checks before promotion-code lookup.
    currency_binding = management_binding(request.price_id)
    management_only = currency_binding is not None and not is_purchasable_price_id(request.price_id)
    if not management_only:
        _validate_price_id(request.price_id)
        # Check if user can make a new payment
        can_pay, reason = subscription_utils.can_user_make_payment(uid, request.price_id)
        if not can_pay:
            raise HTTPException(status_code=400, detail=reason)

    # Validate promotion code early — reject invalid codes before any subscription changes
    resolved_checkout_promo_id = None
    if request.promotion_code:
        promo_list = stripe.PromotionCode.list(code=request.promotion_code, active=True, limit=1)
        if not promo_list.data:
            raise HTTPException(status_code=400, detail="Invalid or expired promotion code.")
        resolved_checkout_promo_id = promo_list.data[0].id

    # Only the exact current JPY price may reactivate; never open new Checkout.
    if management_only and currency_binding is not None:
        current = users_db.get_user_subscription(uid)
        if current and current.stripe_subscription_id and current.stripe_subscription_id.startswith('sub_'):
            try:
                snapshot = stripe.Subscription.retrieve(current.stripe_subscription_id).to_dict()
            except stripe.error.StripeError as error:
                logger.warning(f"Could not verify subscription for reactivation: {sanitize(str(error))}")
                raise HTTPException(status_code=503, detail="Could not verify your subscription. Please try again.")
            current_price = snapshot['items']['data'][0]['price']['id']
            if current_price == request.price_id and subscription_currency(snapshot) == currency_binding[2]:
                reactivation = _try_reactivate_subscription(uid, request.price_id)
                if reactivation:
                    return reactivation
        raise HTTPException(status_code=400, detail="This price is only available to manage an existing subscription.")

    # Try to reactivate canceled subscription (Scenario A)
    reactivation_result = _try_reactivate_subscription(uid, request.price_id)
    if reactivation_result:
        return reactivation_result

    # Omi Pro only; runs after every subscriber escape (stale records can look basic).
    single_plan_error = subscription_utils.new_buyer_single_plan_violation(uid, request.price_id)
    if single_plan_error:
        raise HTTPException(status_code=400, detail=single_plan_error)

    # Normal checkout flow for new subscriptions (Scenario B or first-time subscribers)
    idempotency_key = str(uuid.uuid4())
    existing_customer_id = users_db.get_stripe_customer_id(uid)
    # A trial is only for a first-time subscriber. A client that asked for one on behalf of a former
    # subscriber promised something this checkout cannot give, so refuse rather than charge at once.
    if request.trial_days and existing_customer_id:
        raise HTTPException(status_code=400, detail="trial_unavailable")
    trial_period_days = request.trial_days or None
    try:
        session = stripe_utils.create_subscription_checkout_session(
            uid,
            request.price_id,
            idempotency_key,
            customer_id=existing_customer_id,
            promotion_code_id=resolved_checkout_promo_id,
            trial_period_days=trial_period_days,
        )
    except stripe.error.InvalidRequestError as e:
        detail = str(e.user_message) if hasattr(e, 'user_message') and e.user_message else str(e)
        raise HTTPException(status_code=400, detail=detail)
    if not session:
        raise HTTPException(status_code=500, detail="Could not create checkout session.")
    return {"url": session.url, "session_id": session.id}


def _release_attached_schedules(stripe_sub: dict) -> None:
    """Detach any active/not-started SubscriptionSchedule from this subscription.

    Stripe rejects both Subscription.modify() and SubscriptionSchedule.create()
    with "You cannot migrate a subscription that is already attached to a
    schedule" once a schedule is attached — e.g. a user who earlier scheduled a
    monthly→annual change. That left those users unable to change plans at all.
    Releasing detaches the schedule without canceling the subscription (billing
    continues on the current phase), which unblocks the new change. Mirrors the
    release pattern already used by the cancel-subscription endpoint.
    """
    customer_id = stripe_sub.get('customer')
    sub_id = stripe_sub.get('id')
    if not customer_id or not sub_id:
        return
    try:
        schedules = stripe.SubscriptionSchedule.list(customer=customer_id, limit=10)
    except Exception as e:
        logger.error(f"Error listing subscription schedules before plan change: {sanitize(str(e))}")
        return
    for schedule in schedules.data:
        if schedule.status in ('active', 'not_started') and getattr(schedule, 'subscription', None) == sub_id:
            try:
                stripe.SubscriptionSchedule.release(schedule.id)
                logger.info(f"Released subscription schedule {schedule.id} for {sub_id} before plan change")
            except Exception as e:
                logger.error(f"Error releasing subscription schedule {schedule.id}: {sanitize(str(e))}")


def _unlock_paid_content(uid: str) -> None:
    """Idempotent unlock for a paid plan that is already stored.

    ``DestructiveOperationInProgress`` and data-plane read errors propagate.
    Callers must not acknowledge the upgrade until this returns.
    """
    conversations_db.unlock_all_conversations(uid)
    memories_db.unlock_all_memories(uid)
    action_items_db.unlock_all_action_items(uid)


@router.post('/v1/payments/upgrade-subscription', response_model=PaymentUpgradeSubscriptionResponse)
@fresh_reader
def upgrade_subscription_endpoint(request: UpgradeSubscriptionRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Upgrade or change a user's subscription plan.

    - Cross-plan changes (e.g. Unlimited→Pro): immediate swap via Subscription.modify(),
      Stripe prorates automatically. User gets new features right away.
    - Same plan, different interval (e.g. monthly→annual): scheduled via SubscriptionSchedule,
      takes effect at end of current billing period.
    """
    currency_binding = management_binding(request.price_id)
    if currency_binding is None:
        _validate_price_id(request.price_id)
    current_subscription = users_db.get_user_subscription(uid)

    if not current_subscription or not current_subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found to upgrade.")

    if not is_paid_plan(current_subscription.plan):
        raise HTTPException(status_code=400, detail="Can only upgrade paid plan subscriptions.")

    try:
        # Retrieve current subscription to get current price ID
        stripe_sub = stripe.Subscription.retrieve(current_subscription.stripe_subscription_id).to_dict()
        if stripe_sub.get('cancel_at_period_end') and (
            not stripe_sub.get('current_period_end') or stripe_sub['current_period_end'] > int(time.time())
        ):
            raise HTTPException(
                status_code=409,
                detail="Plan changes are available after the current subscription ends. Reactivate your current plan to keep it.",
            )
        current_price_id = stripe_sub['items']['data'][0]['price']['id']
        current_item_id = stripe_sub['items']['data'][0]['id']

        # Same price as the stored plan. A previous attempt may have stored
        # this paid price and then failed the unlock fence. Replay the
        # unbounded unlock only when locked rows remain, then clear free-tier
        # fair use before the 400. The response body stays the installed-client
        # contract. A fence or data-plane error stays a 500 so the client retries.
        if current_price_id == request.price_id:
            if has_recoverable_locked_content(uid):
                _unlock_paid_content(uid)
            clear_fair_use_on_upgrade(uid)
            raise HTTPException(
                status_code=400,
                detail="You are already subscribed to this plan. Please select a different plan to upgrade or downgrade.",
            )

        target_plan = get_plan_type_from_price_id(request.price_id)
        target_price = stripe.Price.retrieve(request.price_id)
        target_recurring = target_price.recurring
        if target_recurring is None:
            raise HTTPException(status_code=409, detail="This plan price is not a recurring subscription.")
        target_interval = target_recurring.interval  # "month" or "year"
        try:
            currency = subscription_currency(stripe_sub)
            if target_price.currency != currency:
                raise BillingCurrencyUnavailable(
                    'Please reopen Plans & Billing to select a price in your billing currency.'
                )
            if currency_binding is not None:
                plan, interval, expected_currency = currency_binding
                if stripe_sub.get('status') not in ('active', 'trialing'):
                    raise BillingCurrencyUnavailable('An active subscription is required to change this plan.')
                base_id = next(
                    (
                        definition['monthly_price_id' if interval == 'month' else 'annual_price_id']
                        for definition in get_paid_plan_definitions()
                        if definition['plan_type'] == plan
                    ),
                    None,
                )
                if not base_id or expected_currency != currency:
                    raise BillingCurrencyUnavailable('This price is not available for your subscription.')
                offered = price_for_currency(stripe.Price.retrieve(base_id), currency)
                if offered.id != request.price_id:
                    raise BillingCurrencyUnavailable(
                        'This price is no longer available. Please reopen Plans & Billing.'
                    )
        except BillingCurrencyUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error))

        current_plan = get_plan_type_from_price_id(current_price_id)

        change_error = desktop_to_consumer_plan_change_error(
            current_plan, target_plan
        ) or subscription_utils.retired_plan_change_error(current_plan, target_plan)
        if change_error:
            raise HTTPException(status_code=400, detail=change_error)

        # Validate and resolve promotion code if provided
        resolved_promo_id = None
        if request.promotion_code:
            promo_list = stripe.PromotionCode.list(code=request.promotion_code, active=True, limit=1)
            if not promo_list.data:
                raise HTTPException(status_code=400, detail="Invalid or expired promotion code.")
            resolved_promo_id = promo_list.data[0].id

        # A previously-scheduled change (e.g. monthly→annual) leaves a schedule
        # attached to the subscription, which Stripe then refuses to modify or
        # re-schedule. Release it first so the user can switch plans again.
        _release_attached_schedules(stripe_sub)

        # Cross-plan change (e.g. Unlimited→Architect): immediate swap with proration
        if current_plan != target_plan:
            modify_params = {
                'items': [{'id': current_item_id, 'price': request.price_id}],
                'proration_behavior': 'always_invoice',
                'payment_behavior': 'error_if_incomplete',
                'metadata': {'uid': uid, 'sub_type': target_plan.value},
            }
            if resolved_promo_id:
                modify_params['discounts'] = [{'promotion_code': resolved_promo_id}]

            updated_sub = stripe.Subscription.modify(stripe_sub['id'], **modify_params)
            updated_sub_dict = updated_sub.to_dict()
            if updated_sub_dict.get('status') not in ('active', 'trialing') or updated_sub_dict.get('pending_update'):
                logger.warning(
                    f"Subscription upgrade payment incomplete for user {uid}: status={sanitize(str(updated_sub_dict.get('status')))}"
                )
                raise HTTPException(
                    status_code=402,
                    detail="Payment for the plan change could not be completed. Your current subscription remains active.",
                )

            # Update our database immediately
            new_subscription = _build_subscription_from_stripe_object(updated_sub_dict)
            if new_subscription:
                users_db.update_user_subscription(uid, new_subscription.model_dump())
                set_credits_invalidation_signal(uid)
                clear_trial_paywall_cache(uid)
                if is_paid_plan(new_subscription.plan):
                    conversations_db.unlock_all_conversations(uid)
                    memories_db.unlock_all_memories(uid)
                    action_items_db.unlock_all_action_items(uid)
                    clear_fair_use_on_upgrade(uid)
                    if funded_processing_enabled(uid):
                        from utils.processing_backlog import allowance_increased
                        from utils.processing_backlog_worker import upgrade

                        if allowance_increased(current_subscription, new_subscription):
                            upgrade(
                                uid,
                                f'plan-change:{new_subscription.stripe_subscription_id}:{request.price_id}:{new_subscription.current_period_start}',
                                intent_at=time.time(),
                            )

            logger.info(f"Immediate plan change for user {uid}: {current_plan.value} -> {target_plan.value}")

            return {
                "status": "success",
                "message": f"You've been upgraded to {target_plan.value.title()}! Your new plan is active now.",
                "subscription": (
                    new_subscription.model_dump() if new_subscription else current_subscription.model_dump()
                ),
                "days_remaining": 0,
                "schedule_id": None,
            }

        # Same plan, different interval (e.g. monthly→annual): schedule for end of period
        schedule = stripe.SubscriptionSchedule.create(
            from_subscription=stripe_sub['id'],
        )

        updated_schedule = stripe.SubscriptionSchedule.modify(
            schedule.id,
            phases=[
                {
                    'items': [
                        {
                            'price': current_price_id,
                            'quantity': 1,
                        }
                    ],
                    'start_date': stripe_sub['current_period_start'],
                    'end_date': stripe_sub['current_period_end'],
                },
                {
                    'items': [
                        {
                            'price': request.price_id,
                        }
                    ],
                    **({'discounts': [{'promotion_code': resolved_promo_id}]} if resolved_promo_id else {}),
                },
            ],
            metadata={'uid': uid, 'upgrade_type': f'{current_plan.value}_{target_interval}'},
        )

        logger.info(f"Scheduled interval change for user {uid}: {current_plan.value} monthly -> {target_interval}")

        remaining_seconds = stripe_sub['current_period_end'] - int(time.time())
        remaining_days = max(0, remaining_seconds // 86400)

        return {
            "status": "success",
            "message": f"Upgrade scheduled! Your monthly plan continues for {remaining_days} more days, then automatically switches to annual.",
            "subscription": current_subscription.model_dump(),
            "days_remaining": remaining_days,
            "schedule_id": schedule.id,
        }

    except HTTPException:
        raise
    except stripe.error.CardError as e:
        logger.warning(f"Stripe declined subscription change for user {uid}: {sanitize(str(e))}")
        raise HTTPException(
            status_code=402,
            detail=_stripe_client_error_detail(
                e, "Payment for the plan change was declined. Your current subscription remains active."
            ),
        )
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe rejected subscription change: {sanitize(str(e))}")
        detail = str(e.user_message) if hasattr(e, 'user_message') and e.user_message else str(e)
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error(f"Error processing subscription change: {sanitize(str(e))}")
        raise HTTPException(status_code=500, detail="Failed to process subscription change. Please try again.")


class CancelSubscriptionRequest(BaseModel):
    reason: Optional[str] = None
    reason_details: Optional[str] = None


@router.delete('/v1/payments/subscription', response_model=PaymentStatusMessageResponse)
@fresh_reader
def cancel_subscription_endpoint(
    request: CancelSubscriptionRequest = CancelSubscriptionRequest(),
    uid: str = Depends(auth.get_current_user_uid),
):
    subscription = users_db.get_user_subscription(uid)
    if not subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found.")

    # Store cancellation reason
    if request.reason:
        users_db.set_user_cancellation_feedback(uid, request.reason, request.reason_details)

    try:
        # First, check if the subscription is managed by a subscription schedule
        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

        # Look for active subscription schedules for this customer
        customer_id = stripe_sub.get('customer')
        if not customer_id:
            raise HTTPException(status_code=400, detail="No customer ID found for subscription.")

        schedules = stripe.SubscriptionSchedule.list(customer=customer_id, limit=10)

        # Check if there's an active schedule managing this subscription
        active_schedule = None
        for schedule in schedules.data:
            if schedule.status in ['active', 'not_started']:
                # Check if this schedule is for the current subscription
                if hasattr(schedule, 'subscription') and schedule.subscription == subscription.stripe_subscription_id:
                    active_schedule = schedule
                    break

        if active_schedule:
            # Cancel the subscription schedule but let the current subscription continue until period end
            logger.info(
                f"Canceling subscription schedule {active_schedule.id} for subscription {subscription.stripe_subscription_id}"
            )
            stripe.SubscriptionSchedule.release(active_schedule.id)

            # Also cancel the current subscription at period end
            stripe.Subscription.modify(subscription.stripe_subscription_id, cancel_at_period_end=True)

            # Update our database to reflect the scheduled cancellation
            subscription.cancel_at_period_end = True
            users_db.update_user_subscription(uid, subscription.model_dump())

            return {"status": "ok", "message": "Subscription scheduled for cancellation."}
        else:
            # No active schedule, cancel the subscription directly
            updated_sub = stripe_utils.cancel_subscription(subscription.stripe_subscription_id)
            if not updated_sub:
                raise HTTPException(status_code=500, detail="Could not cancel subscription with Stripe.")

            subscription.cancel_at_period_end = updated_sub.cancel_at_period_end
            users_db.update_user_subscription(uid, subscription.model_dump())

            return {"status": "ok", "message": "Subscription scheduled for cancellation."}

    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error canceling subscription: {sanitize(str(e))}")
        raise HTTPException(
            status_code=500,
            detail=_stripe_client_error_detail(e, "Could not cancel subscription. Please try again."),
        )
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription. Please try again.")


@router.post('/v1/stripe/webhook', tags=['v1', 'stripe', 'webhook'], response_model=PaymentMutationResponse)
async def stripe_webhook(
    request: Request, stripe_signature: str = Header(None), background_tasks: BackgroundTasks = None
):
    payload = await request.body()

    try:
        event = stripe_utils.parse_event(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    async def run_db(function, *args, **kwargs):
        return await run_blocking(db_executor, function, *args, **kwargs)

    return await dispatch_with_ledger(event, lambda: _handle_stripe_event(event, background_tasks), run_db)


@fresh_reader
async def _handle_stripe_event(event: dict, background_tasks: BackgroundTasks | None = None):
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_reference_id = session.get('client_reference_id')

        # App payments for creators
        if session.get('metadata', {}).get('app_id'):
            logger.info(f"Payment completed for session: {session['id']}")
            app_id = session['metadata']['app_id']
            uid = session['client_reference_id']
            if not uid or len(uid) < 4:
                raise HTTPException(status_code=400, detail="Invalid client")
            uid = uid[4:]

            current_period_end = None
            if session.get("subscription"):
                subscription_id = session["subscription"]
                subscription = await run_blocking(
                    stripe_executor,
                    stripe_utils.modify_subscription,
                    subscription_id,
                    metadata={"uid": uid, "app_id": app_id},
                )
                current_period_end = subscription.get('current_period_end') if subscription else None
                # Store the customer ID for app subscription so that it is easy to cancel the subscription
                customer_id = session.get("customer")
                if customer_id:
                    await run_blocking(db_executor, set_user_app_sub_customer_id, app_id, uid, customer_id)
            await run_blocking(db_executor, paid_app, app_id, uid, current_period_end)

        # Regular user subscription - check for sub_type metadata or client_reference_id
        elif client_reference_id or session.get('metadata', {}).get('sub_type'):
            # Get uid from client_reference_id or fallback to metadata
            uid = client_reference_id or session.get('metadata', {}).get('uid')

            if not uid:
                # It should not happen, ref id might be missing but never the metadata
                logger.error(f"[WEBHOOK ERROR] No uid found in checkout session {session.get('id')}")
                return {"status": "error", "message": "No user identifier found"}

            logger.info(
                f"Processing subscription for user {uid} (from {'client_reference_id' if client_reference_id else 'metadata'})"
            )

            # Verify user exists before processing — the subscription getter has
            # create-on-miss behavior that would resurrect a deleted user's doc
            if not await run_blocking(db_executor, users_db.get_user_profile, uid):
                logger.warning(
                    f"Stripe webhook: user {uid} not found in Firestore, " f"skipping checkout session processing"
                )
                return {"status": "success"}

            # An incomplete Basic row is not a completed paid checkout;
            # preserve the existing duplicate/replacement decision in pure code.
            existing_subscription = await run_blocking(db_executor, users_db.get_user_valid_subscription, uid)
            checkout_decision = transition(
                existing_subscription,
                ResolvedStripeEvent(event['type'], session.get('subscription'), None, int(time.time())),
            )
            if checkout_decision.outcome in ('duplicate_checkout', 'replacement_checkout'):
                if checkout_decision.outcome == 'duplicate_checkout':
                    logger.warning(f"Duplicate webhook event for existing subscription: {session.get('subscription')}")
                    # The paid plan is already stored. Stripe retries this
                    # delivery when unlock raises. Do not acknowledge it until
                    # unlock and the idempotent fair-use clear both finish:
                    # the first delivery writes metadata uid only after that
                    # clear, so this retry is what drops free_exhausted.
                    await run_blocking(db_executor, _unlock_paid_content, uid)
                    await run_blocking(db_executor, clear_fair_use_on_upgrade, uid)
                    return {"status": "success", "message": "Subscription already processed."}
                elif 'cancel_old_subscription' in checkout_decision.effects:
                    # Cancel the old subscription to prevent double-charging
                    old_sub_id = existing_subscription.stripe_subscription_id
                    logger.info(
                        f"User {uid} upgrading: canceling old subscription {old_sub_id}, activating new {session.get('subscription')}"
                    )
                    try:
                        await run_blocking(stripe_executor, lambda: stripe.Subscription.cancel(old_sub_id))
                        logger.info(f"Old subscription {old_sub_id} canceled for user {uid}")
                    except Exception as e:
                        logger.error(
                            f"Failed to cancel old subscription {old_sub_id} for user {uid}: {sanitize(str(e))}"
                        )

            persisted = await run_blocking(stripe_executor, _update_subscription_from_session, uid, session)
            await run_blocking(db_executor, set_credits_invalidation_signal, uid)
            await run_blocking(db_executor, clear_trial_paywall_cache, uid)
            # A stored paid label with a missing, zero, or past period is Basic
            # on get_user_valid_subscription. Unlock only an open paid period.
            subscription = await run_blocking(db_executor, users_db.get_user_valid_subscription, uid)
            period_open = subscription is not None and _paid_period_still_open(
                subscription.current_period_end, datetime.fromtimestamp(time.time(), tz=timezone.utc)
            )
            if subscription and is_paid_plan(subscription.plan) and period_open:
                await run_blocking(db_executor, conversations_db.unlock_all_conversations, uid)
                await run_blocking(db_executor, memories_db.unlock_all_memories, uid)
                await run_blocking(db_executor, action_items_db.unlock_all_action_items, uid)
                await run_blocking(db_executor, clear_fair_use_on_upgrade, uid)
                if funded_processing_enabled(uid):
                    from utils.processing_backlog import allowance_increased
                    from utils.processing_backlog_worker import upgrade_async

                    if allowance_increased(existing_subscription, subscription):
                        await upgrade_async(uid, f'checkout:{session.get("id")}', intent_at=event.get("created"))
            if persisted is False and webhook_ledger_enabled():
                return RetryableBillingSkip(status='success')
            subscription_id = session.get('subscription')
            if subscription_id:
                try:
                    price_id = None
                    stripe_sub = await run_blocking(
                        stripe_executor, lambda: stripe.Subscription.retrieve(subscription_id)
                    )
                    if stripe_sub:
                        subscription_obj = stripe_sub.to_dict()
                        if subscription_obj and subscription_obj['items']['data']:
                            price_id = subscription_obj['items']['data'][0]['price']['id']
                    sub_type = get_plan_type_from_price_id(price_id).value if price_id else "unknown"
                    await run_blocking(
                        stripe_executor,
                        lambda: stripe.Subscription.modify(
                            subscription_id, metadata={"uid": uid, "sub_type": sub_type}
                        ),
                    )
                except Exception as e:
                    logger.error(f"Error updating subscription metadata: {e}")

                # Send paid notification if applicable
                try:
                    stripe_sub = await run_blocking(
                        stripe_executor, lambda: stripe.Subscription.retrieve(subscription_id)
                    )
                    if stripe_sub:
                        subscription_obj = stripe_sub.to_dict()
                        if subscription_obj and subscription_obj['items']['data']:
                            price_id = subscription_obj['items']['data'][0]['price']['id']
                            try:
                                plan_type = get_plan_type_from_price_id(price_id)
                                if is_paid_plan(plan_type):
                                    await send_subscription_paid_personalized_notification(uid)
                            except ValueError:
                                logger.warning(
                                    f"Ignoring checkout session for subscription with unknown price_id: {price_id}"
                                )
                except Exception as e:
                    logger.error(f"Error retrieving subscription for notification: {sanitize(str(e))}")

    if event['type'] in [
        'customer.subscription.updated',
        'customer.subscription.deleted',
        'customer.subscription.created',
    ]:
        subscription_obj = event['data']['object']
        record_subscription_event(
            stripe_event_type=event['type'],
            subscription_obj=subscription_obj,
            previous_attributes=event.get('data', {}).get('previous_attributes'),
        )
        uid = subscription_obj.get('metadata', {}).get('uid')

        if not uid:
            customer_id = subscription_obj.get('customer')
            if not customer_id:
                return {"status": "success", "message": "No customer ID or UID in subscription event."}

            user = await run_blocking(db_executor, users_db.get_user_by_stripe_customer_id, customer_id)
            if user and user.get('uid'):
                uid = user['uid']

        if uid:
            now = int(time.time())
            new_subscription = _build_subscription_from_stripe_object(
                subscription_obj, grant_cancel_grace=True, now=now
            )
            if new_subscription:
                # Resolve prior entitlement before reconciliation; emit only
                # after the authoritative write so stale deletion is not churn.
                billing_owner_confirmed = False
                previous_paid_id = None
                try:
                    owner = await run_blocking(db_executor, users_db.get_user_profile, uid)
                    if owner:
                        previous_subscription = await run_blocking(
                            db_executor, users_db.get_existing_user_subscription, uid
                        )
                        billing_owner_confirmed = True
                        if (
                            previous_subscription
                            and previous_subscription.stripe_subscription_id
                            and previous_subscription.status == SubscriptionStatus.active
                            and is_paid_plan(previous_subscription.plan)
                        ):
                            previous_paid_id = previous_subscription.stripe_subscription_id
                except Exception:
                    logger.warning(
                        'Stripe billing product telemetry owner lookup skipped for event=%s',
                        event.get('type'),
                        exc_info=True,
                    )
                # Preserve the existing stale-downgrade guard before looking up
                # an alternative Stripe subscription. Decisions are pure;
                # all customer/storage IO remains in this adapter.
                current_subscription = None
                active_paid = None
                # A paid-through canceled snapshot (grace) is downgrade-shaped for
                # the stale shield: a newer stored paid sub or an adoptable active
                # paid sub must still win over the grace candidate.
                if not is_paid_plan(new_subscription.plan) or subscription_obj.get('status') == 'canceled':
                    event_sub_id = subscription_obj.get('id')
                    current_subscription = await run_blocking(db_executor, users_db.get_existing_user_subscription, uid)
                    if preserves_current_paid_subscription(current_subscription, event_sub_id, now):
                        logger.info(
                            f"Ignoring downgrade from {event['type']} (sub {event_sub_id}) for user {uid}: "
                            f"stored paid sub {current_subscription.stripe_subscription_id} is still valid."
                        )
                        return {"status": "success"}
                    active_paid = await run_blocking(stripe_executor, find_active_paid_subscription_for_user, uid)
                    if active_paid and active_paid.stripe_subscription_id != event_sub_id:
                        logger.info(
                            f"Ignoring downgrade from {event['type']} (sub {event_sub_id}) for user {uid}: "
                            f"a different active paid sub {active_paid.stripe_subscription_id} exists."
                        )
                decision_candidate = new_subscription
                # Paid-through grace applies only when the canceled event belongs
                # to the user's current subscription (the portal cancel flow). A
                # canceled snapshot for a different, superseded subscription id
                # keeps main's downgrade semantics: project Basic and let the
                # stale guard / replacement adoption decide.
                grace_candidate = (
                    subscription_obj.get('status') == 'canceled'
                    and is_paid_plan(new_subscription.plan)
                    and (
                        current_subscription is None
                        or current_subscription.stripe_subscription_id == subscription_obj.get('id')
                    )
                )
                if (
                    subscription_obj.get('status') == 'canceled'
                    and is_paid_plan(new_subscription.plan)
                    and not grace_candidate
                ):
                    decision_candidate = project_subscription(subscription_obj, None, get_basic_plan_limits())
                decision = transition(
                    None,
                    ResolvedStripeEvent(
                        event['type'],
                        subscription_obj.get('id'),
                        decision_candidate,
                        now,
                        active_paid,
                        billing_owner_confirmed,
                        grace_paid=grace_candidate,
                    ),
                )
                if decision.next_state is None:
                    raise ValueError('Subscription transition requires a projected state')
                new_subscription = decision.next_state
                adopted_active_paid = decision.adopted_active_paid
                if adopted_active_paid:
                    logger.info(
                        f"Early-cancel paid-through grace for user {uid}: adopted replacement paid sub "
                        f"{new_subscription.stripe_subscription_id} over canceled event sub "
                        f"{subscription_obj.get('id')}."
                    )
                elif (
                    is_paid_plan(new_subscription.plan)
                    and decision.outcome != 'preserved_current'
                    and subscription_obj.get('status') == 'canceled'
                ):
                    logger.info(
                        f"Early-cancel paid-through grace for user {uid}: keeping plan until period end "
                        f"for canceled sub {subscription_obj.get('id')}."
                    )
                try:
                    if 'unlock_conversations' in decision.effects:
                        # An adopted replacement keeps its own customer identity;
                        # the incoming event belongs to the stale subscription.
                        if 'set_customer' in decision.effects:
                            customer_id = subscription_obj.get('customer')
                            if customer_id:
                                await run_blocking(db_executor, users_db.set_stripe_customer_id, uid, customer_id)
                        await run_blocking(db_executor, conversations_db.unlock_all_conversations, uid)
                        await run_blocking(db_executor, memories_db.unlock_all_memories, uid)
                        await run_blocking(db_executor, action_items_db.unlock_all_action_items, uid)
                    await run_blocking(
                        db_executor, users_db.update_user_subscription, uid, new_subscription.model_dump()
                    )
                    # Emit after the durable write; replacement adoption is
                    # reconciliation, not an incoming-event start or churn.
                    if 'billing_telemetry' in decision.effects:
                        from utils.observability.billing_webhook import schedule_billing_webhook_events

                        await schedule_billing_webhook_events(
                            background_tasks,
                            uid=uid,
                            stripe_event_id=str(event.get('id') or ''),
                            stripe_event_created=event.get('created'),
                            stripe_event_type=event['type'],
                            subscription_obj=subscription_obj,
                            previous_attributes=event.get('data', {}).get('previous_attributes'),
                            previous_paid_subscription_id=previous_paid_id,
                            resulting_paid_subscription_id=(
                                new_subscription.stripe_subscription_id
                                if new_subscription.status == SubscriptionStatus.active
                                and is_paid_plan(new_subscription.plan)
                                else None
                            ),
                        )
                    await run_blocking(db_executor, set_credits_invalidation_signal, uid)
                    await run_blocking(db_executor, clear_trial_paywall_cache, uid)
                    if 'clear_fair_use' in decision.effects:
                        await run_blocking(db_executor, clear_fair_use_on_upgrade, uid)
                    if funded_processing_enabled(uid) and not adopted_active_paid:
                        from utils.processing_backlog import allowance_increased
                        from utils.processing_backlog_worker import upgrade_async

                        if allowance_increased(current_subscription, new_subscription):
                            await upgrade_async(
                                uid, f'subscription-upgrade:{event.get("id")}', intent_at=event.get("created")
                            )
                    logger.info(f"Subscription for user {uid} updated from webhook event: {event['type']}.")
                except FirestoreNotFound:
                    logger.warning(
                        f"Stripe webhook: user {uid} not found in Firestore, "
                        f"skipping subscription update for event {event['type']}"
                    )
            else:
                subscription_id = subscription_obj.get('id', 'unknown')
                price_id = 'unknown'
                if subscription_obj.get('items', {}).get('data'):
                    price_id = subscription_obj['items']['data'][0].get('price', {}).get('id', 'unknown')
                logger.warning(
                    f"Stripe webhook: could not build subscription for user {uid}, "
                    f"subscription {subscription_id}, price {price_id} — unknown price ID"
                )
                return RetryableBillingSkip(status='success')

    # Handle subscription schedule events
    if event['type'] in [
        'subscription_schedule.completed',
        'subscription_schedule.updated',
        'subscription_schedule.canceled',
    ]:
        schedule_obj = event['data']['object']
        uid = schedule_obj.get('metadata', {}).get('uid')

        if uid:
            if schedule_obj.get('status') == 'completed':
                try:
                    if schedule_obj.get('subscription'):
                        new_subscription_id = schedule_obj['subscription']
                        new_stripe_sub = await run_blocking(
                            stripe_executor, lambda: stripe.Subscription.retrieve(new_subscription_id)
                        )
                        new_subscription = _build_subscription_from_stripe_object(new_stripe_sub.to_dict())
                        if not new_subscription:
                            logger.warning(
                                f"Could not build subscription from scheduled upgrade for user {uid}, "
                                f"subscription {new_subscription_id} — unknown price ID"
                            )
                            return RetryableBillingSkip(status='success')
                        else:
                            decision = schedule_transition(event, new_subscription, int(time.time()))
                            if decision.next_state is None:
                                raise ValueError('Schedule transition requires a projected state')
                            new_subscription = decision.next_state
                            await run_blocking(
                                db_executor, users_db.update_user_subscription, uid, new_subscription.model_dump()
                            )
                            await run_blocking(db_executor, set_credits_invalidation_signal, uid)
                            await run_blocking(db_executor, clear_trial_paywall_cache, uid)
                            if 'clear_fair_use' in decision.effects:
                                await run_blocking(db_executor, clear_fair_use_on_upgrade, uid)
                            logger.info(
                                f"Scheduled upgrade completed for user {uid}. New subscription: {new_subscription_id}"
                            )
                except FirestoreNotFound:
                    logger.warning(
                        f"Stripe webhook: user {uid} not found in Firestore, " f"skipping scheduled upgrade update"
                    )
                except Exception as e:
                    if isinstance(e, stripe.error.InvalidRequestError) and e.code == 'resource_missing':
                        logger.warning('Schedule subscription no longer exists in Stripe')
                        return {"status": "success"}
                    logger.error(f"Error updating subscription after scheduled upgrade: {sanitize(str(e))}")
                    if webhook_ledger_enabled():
                        raise HTTPException(503, "Subscription schedule update must be retried") from None
            elif schedule_obj.get('status') == 'canceled':
                try:
                    if schedule_obj.get('subscription'):
                        subscription_id = schedule_obj['subscription']
                        stripe_sub = await run_blocking(
                            stripe_executor, lambda: stripe.Subscription.retrieve(subscription_id)
                        )
                        subscription_obj = stripe_sub.to_dict()

                        new_subscription = _build_subscription_from_stripe_object(subscription_obj)
                        if not new_subscription:
                            logger.warning(
                                f"Could not build subscription from schedule cancellation for user {uid}, "
                                f"subscription {subscription_id} — unknown price ID"
                            )
                            return RetryableBillingSkip(status='success')
                        else:
                            decision = schedule_transition(event, new_subscription, int(time.time()))
                            if decision.next_state is None:
                                raise ValueError('Schedule transition requires a projected state')
                            new_subscription = decision.next_state
                            await run_blocking(
                                db_executor, users_db.update_user_subscription, uid, new_subscription.model_dump()
                            )
                            await run_blocking(db_executor, set_credits_invalidation_signal, uid)
                            await run_blocking(db_executor, clear_trial_paywall_cache, uid)
                            logger.info(
                                f"Subscription schedule canceled for user {uid}. Subscription: {subscription_id}"
                            )
                except FirestoreNotFound:
                    logger.warning(
                        f"Stripe webhook: user {uid} not found in Firestore, " f"skipping schedule cancellation update"
                    )
                except Exception as e:
                    if isinstance(e, stripe.error.InvalidRequestError) and e.code == 'resource_missing':
                        logger.warning('Schedule subscription no longer exists in Stripe')
                        return {"status": "success"}
                    logger.error(f"Error updating subscription after schedule cancellation: {sanitize(str(e))}")
                    if webhook_ledger_enabled():
                        raise HTTPException(503, "Subscription schedule update must be retried") from None

    if event['type'] in ['invoice.paid', 'invoice.payment_succeeded']:
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        if subscription_id:
            try:
                subscription = await run_blocking(
                    stripe_executor, lambda: stripe.Subscription.retrieve(subscription_id)
                )
                metadata = subscription.get('metadata') or {}
                app_id = metadata.get('app_id')
                uid = metadata.get('uid')
                if app_id and uid:
                    await run_blocking(db_executor, paid_app, app_id, uid, subscription.get('current_period_end'))
                    logger.info(f"Paid app entitlement renewed for user {uid}. App: {app_id}")
            except Exception as e:
                logger.error(f"Error renewing paid app entitlement for subscription {subscription_id}: {e}")

    return {"status": "success"}


@router.post('/v1/stripe/connect/webhook', tags=['v1', 'stripe', 'webhook'], response_model=PaymentMutationResponse)
async def stripe_connect_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe_utils.parse_connect_event(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'account.updated':
        # this event occurs for the connected account, check if the account is fully onboarded to set default method
        account = event['data']['object']
        if account['charges_enabled'] and account['details_submitted']:
            # account is fully onboarded
            uid = (account.get('metadata') or {}).get('uid')
            if uid and await run_blocking(db_executor, get_default_payment_method, uid) is None:
                await run_blocking(db_executor, set_default_payment_method, uid, 'stripe')

    return {"status": "success"}


@router.post("/v1/stripe/connect-accounts", response_model=StripeConnectAccountResponse)
def create_connect_account_endpoint(
    country: str | None = Query(default=None), uid: str = Depends(auth.get_current_user_uid)
):
    """
    Create a Stripe Connect account and return the account creation response
    """
    try:
        account_id = get_stripe_connect_account_id(uid)

        if account_id:
            account = refresh_connect_account_link(account_id)
        else:
            # Require a real user record before creating a Stripe Connect account, so a UID that is
            # valid in auth but missing from Firestore surfaces as a 404 rather than leaving an
            # orphaned Stripe account (cubic on #8567).
            if not get_user_profile(uid):
                raise HTTPException(status_code=404, detail="User not found")
            if country is None or country.strip() == "":
                raise HTTPException(status_code=400, detail="Country is required")
            account = create_connect_account(uid, country)
            set_stripe_connect_account_id(uid, account['account_id'])

        return account
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating connect account for {uid}: {sanitize(str(e))}")
        raise HTTPException(
            status_code=400,
            detail=_stripe_client_error_detail(e, "Could not create Stripe account. Please try again."),
        )


@router.get('/v1/stripe/supported-countries', response_model=List[StripeSupportedCountryResponse])
def get_supported_countries():
    return stripe_utils.get_supported_countries()


@router.get("/v1/stripe/onboarded", response_model=StripeOnboardingStatusResponse, tags=['v1', 'stripe'])
def check_onboarding_status(uid: str = Depends(auth.get_current_user_uid)):
    """
    Check the onboarding status of a Connect account
    """
    try:
        account_id = get_stripe_connect_account_id(uid)
        if not account_id:
            return {"onboarding_complete": False}
        return {"onboarding_complete": is_onboarding_complete(account_id)}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error checking onboarding status for {uid}: {sanitize(str(e))}")
        raise HTTPException(
            status_code=400,
            detail=_stripe_client_error_detail(e, "Could not check onboarding status. Please try again."),
        )


@router.post("/v1/stripe/refresh/{account_id}", response_model=StripeConnectAccountResponse)
def refresh_account_link_endpoint(request: Request, account_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate a fresh account link if the previous one expired
    """
    user_account_id = get_stripe_connect_account_id(uid)
    if not user_account_id or user_account_id != account_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        account = refresh_connect_account_link(account_id)
        return account
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error refreshing account link for {account_id}: {sanitize(str(e))}")
        raise HTTPException(
            status_code=400,
            detail=_stripe_client_error_detail(e, "Could not refresh account link. Please try again."),
        )


@router.get("/v1/stripe/return/{account_id}", response_class=HTMLResponse)
def stripe_return(account_id: str):
    """
    Handle the return flow from Stripe Connect account creation.
    Account onboarding status is updated via webhook and queried by authenticated
    clients at /v1/stripe/onboarded. This landing page provides user feedback without
    leaking account onboarding status to unauthenticated callers.
    """
    title = "Stripe Account Setup"
    message = "Your setup session has ended. You can now close this window and return to the app to verify your account status."

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Return to App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{                
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                box-sizing: border-box;
            }}
            .heading {{
                font-size: clamp(20px, 5vw, 24px);
                font-weight: bold;
                margin-bottom: 20px;
                color: #333;
                text-align: center;
            }}
            .message {{
                font-size: clamp(14px, 4vw, 16px);
                color: #666;
                text-align: center;
                margin-bottom: 30px;
                max-width: 600px;
                line-height: 1.5;
            }}
            .close-instruction {{
                font-size: clamp(14px, 4vw, 16px);
                color: #4CAF50;
                text-align: center;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <h1 class="heading">{title}</h1>
        <p class="message">{message}</p>
        <p class="close-instruction">You can now close this window and return to the app</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/v1/paypal/payment-details", response_model=PaymentMutationResponse)
def save_paypal_payment_details(data: SavePayPalPaymentDetailsRequest, uid: str = Depends(auth.get_current_user_uid)):
    """
    Save PayPal payment details (email and paypal.me link)
    """
    try:
        email = data.email.lower()
        paypalme_url = data.paypalme_url.lower()
        if paypalme_url and not paypalme_url.startswith('http'):
            paypalme_url = 'https://' + paypalme_url
        set_paypal_payment_details(uid, {'email': email, 'paypalme_url': paypalme_url})
        if get_default_payment_method(uid) is None:
            set_default_payment_method(uid, 'paypal')
        return {"status": "success"}
    except Exception as e:
        # Broad catch around a Firestore write — unlike the ValidationError/
        # StripeError sites elsewhere in this file (whose messages are
        # designed to be user-facing), an unexpected exception here could be
        # anything, so log the real detail server-side and don't echo it.
        logger.error(f"Failed to save PayPal payment details for uid={uid}: {e}")
        raise HTTPException(status_code=400, detail="Could not save PayPal payment details. Please try again.")


@router.get("/v1/paypal/payment-details", response_model=Optional[PayPalPaymentDetailsResponse])
def get_paypal_payment_details_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """
    Get the PayPal payment details for the user
    """
    details = get_paypal_payment_details(uid)
    # remove the starting https:// from the paypalme_url
    if details:
        details['paypalme_url'] = details.get('paypalme_url', '').replace('https://', '')
    return details


@router.get("/v1/payments/success", response_class=HTMLResponse)
def stripe_success(session_id: str = Query(...)):
    # The subscription is updated via webhook. This page is just for user feedback.
    return HTMLResponse(content="""
        <html>
            <head><title>Success</title></head>
            <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
                <h1>Payment Successful!</h1>
                <p>Your subscription is now active. You can close this window and return to the app.</p>
            </body>
        </html>
    """)


@router.get("/v1/payments/cancel", response_class=HTMLResponse)
def stripe_cancel():
    return HTMLResponse(content="""
        <html>
            <head><title>Cancelled</title></head>
            <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
                <h1>Payment Cancelled</h1>
                <p>Your payment process was cancelled. You can return to the app.</p>
            </body>
        </html>
    """)


@router.post('/v1/payments/customer-portal', response_model=CustomerPortalSessionResponse)
def create_customer_portal_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Create a Stripe Customer Portal session for managing payment methods and subscriptions."""

    customer_id = users_db.get_stripe_customer_id(uid)

    # If no customer ID stored, try to get it from subscription
    if not customer_id:
        subscription = users_db.get_user_subscription(uid)
        if subscription and subscription.stripe_subscription_id:
            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            customer_id = stripe_sub.customer
            if customer_id:
                users_db.set_stripe_customer_id(uid, customer_id)

    if not customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found. Please create a subscription first.")

    return_url = urljoin(base_url, 'v1/payments/portal-return')

    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )

    return {"url": portal_session.url}


@router.get("/v1/payments/portal-return", response_class=HTMLResponse)
def portal_return():
    return HTMLResponse(content="""
        <html>
            <head><title>Portal Complete</title></head>
            <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
                <h1>Settings Updated</h1>
                <p>Your payment settings have been updated. You can close this window and return to the app.</p>
            </body>
        </html>
    """)


@router.get("/v1/payment-methods/status", response_model=PaymentMethodStatusResponse)
def get_payment_method_status(uid: str = Depends(auth.get_current_user_uid)):
    """Get the statuses of the payment methods for the user"""
    default_payment_method = get_default_payment_method(uid)

    # Check Stripe status
    stripe_account_id = get_stripe_connect_account_id(uid)
    stripe_status = 'not_connected'
    if stripe_account_id:
        stripe_status = 'connected' if is_onboarding_complete(stripe_account_id) else 'incomplete'

    # Check PayPal status
    paypal_status = 'connected' if get_paypal_payment_details(uid) else 'not_connected'

    return {"stripe": stripe_status, "paypal": paypal_status, "default": default_payment_method}


@router.post("/v1/payment-methods/default", response_model=PaymentMutationResponse)
def set_default_payment_method_endpoint(
    data: SetDefaultPaymentMethodRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Set the default payment method for the user"""
    method = data.method
    if method not in ['stripe', 'paypal']:
        raise HTTPException(status_code=400, detail="Invalid method")
    set_default_payment_method(uid, method)
    return {"status": "success"}


@router.get("/v1/apps/{app_id}/subscription", response_model=AppSubscriptionResponse)
def get_app_subscription(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get user's subscription for a specific app"""
    try:

        latest_subscription = find_app_subscription(app_id, uid, status_filter='all')

        if latest_subscription:
            return {
                "subscription": {
                    "id": latest_subscription.get('id'),
                    "status": latest_subscription.get('status'),
                    "current_period_end": latest_subscription.get('current_period_end'),
                    "cancel_at_period_end": latest_subscription.get('cancel_at_period_end'),
                    "price_id": (
                        latest_subscription.get('items', {}).get('data', [{}])[0].get('price', {}).get('id')
                        if latest_subscription.get('items', {}).get('data')
                        else None
                    ),
                    "customer_id": latest_subscription.get('customer'),
                }
            }

        return {"subscription": None}
    except Exception as e:
        logger.error(f"Error getting app subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve subscription information")


@router.delete("/v1/apps/{app_id}/subscription", response_model=AppSubscriptionCancelResponse)
def cancel_app_subscription(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Cancel user's subscription for a specific app"""
    try:

        target_subscription = find_app_subscription(app_id, uid, status_filter='active')

        if not target_subscription:
            raise HTTPException(status_code=404, detail="Active subscription not found for this app")

        target_subscription_id = target_subscription.get('id')
        if not target_subscription_id:
            raise HTTPException(status_code=404, detail="Invalid subscription data")

        # Cancel the subscription at period end
        updated_sub = stripe_utils.modify_subscription(
            target_subscription_id,
            cancel_at_period_end=True,
        )

        updated_sub_dict = updated_sub.to_dict()

        return {
            "status": "success",
            "message": "Subscription scheduled for cancellation at the end of the current billing period",
            "cancel_at_period_end": updated_sub_dict.get('cancel_at_period_end'),
            "current_period_end": updated_sub_dict.get('current_period_end'),
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error canceling app subscription: {sanitize(str(e))}")
        raise HTTPException(
            status_code=400,
            detail=_stripe_client_error_detail(e, "Could not cancel subscription. Please try again."),
        )
    except Exception as e:
        logger.error(f"Error canceling app subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription")
