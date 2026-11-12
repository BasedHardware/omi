import os
import re
from collections.abc import Mapping
from typing import Any, Dict, Optional, cast
from urllib.parse import urljoin

import pycountry
import stripe

from database import redis_db
import logging

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv('STRIPE_API_KEY')
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
connect_secret = os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET')
base_url = os.getenv('BASE_API_URL')
if base_url and not base_url.startswith(('http://', 'https://')):
    base_url = 'https://' + base_url


def create_product(name: str, description: str, image: str):
    """Create a new product in Stripe."""
    product = stripe.Product.create(
        name=name,
        description=description,
        images=[image] if image and len(image) > 0 else [],
        tax_code="txcd_10103000",  # saas
    )
    return product


def create_app_monthly_recurring_price(product_id: str, amount_in_cents: int, currency: str = 'usd'):
    """Create a price for the given product."""
    price = stripe.Price.create(
        unit_amount=amount_in_cents, currency=currency, product=product_id, recurring={'interval': 'month'}
    )
    return price


PROMOTION_ISSUANCE_METADATA_KEYS = (
    'attribution_schema',
    'attribution_source',
    'shopify_shop',
    'shopify_order_id',
    'bundle_order_line_item_id',
    'bundle_redemption_role',
)
PROMOTION_ATTRIBUTION_METADATA_KEYS = PROMOTION_ISSUANCE_METADATA_KEYS + ('bundle_promotion_code_id',)

_PROMOTION_ID = re.compile(r'^promo_[A-Za-z0-9_-]{1,246}$')
_SHOPIFY_SHOP = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$')
_SHOPIFY_ORDER_ID = re.compile(r'^(?:[0-9]{1,32}|gid://shopify/Order/[0-9]{1,32})$')
_SHOPIFY_LINE_ITEM_ID = re.compile(r'^(?:[0-9]{1,32}|gid://shopify/LineItem/[0-9]{1,32})$')


def _object_dict(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, 'to_dict'):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return converted
    return {}


def _validated_issuance_metadata(metadata: Any) -> Optional[Dict[str, str]]:
    """Return the complete issuer contract, or None for missing/invalid metadata."""
    if not isinstance(metadata, Mapping) or not any(key in metadata for key in PROMOTION_ISSUANCE_METADATA_KEYS):
        return None
    values = {key: metadata.get(key) for key in PROMOTION_ISSUANCE_METADATA_KEYS}
    if any(not isinstance(value, str) for value in values.values() if value is not None):
        return None
    if values['attribution_schema'] != '1' or values['attribution_source'] != 'shopify_bundle_code':
        return None
    if values['bundle_redemption_role'] not in ('self', 'gift', 'unknown'):
        return None
    if not _SHOPIFY_SHOP.fullmatch(values['shopify_shop'] or ''):
        return None
    if not _SHOPIFY_ORDER_ID.fullmatch(values['shopify_order_id'] or ''):
        return None
    line_item_id = values['bundle_order_line_item_id']
    if line_item_id is not None and not _SHOPIFY_LINE_ITEM_ID.fullmatch(line_item_id):
        return None
    return {key: value for key, value in values.items() if value is not None}


def promotion_code_attribution(promotion_code: Any) -> Dict[str, str]:
    """Validate optional, issuer-written Shopify provenance from a resolved PromotionCode.

    No client fields, shared-coupon inference, or partially valid attribution are accepted. Invalid
    or conflicting issuance metadata deliberately produces no attribution and never blocks billing.
    """
    promo = _object_dict(promotion_code)
    promo_id = promo.get('id')
    if not isinstance(promo_id, str) or not _PROMOTION_ID.fullmatch(promo_id):
        return {}
    # Only codes contractually constrained to one redemption are issuers of order
    # evidence. A shared or reusable PromotionCode is not unique order provenance.
    if isinstance(promo.get('max_redemptions'), bool) or promo.get('max_redemptions') != 1:
        return {}
    issuance = _validated_issuance_metadata(promo.get('metadata'))
    if issuance is None:
        return {}

    promotion = promo.get('promotion')
    coupon = promo.get('coupon') or (promotion.get('coupon') if isinstance(promotion, Mapping) else None)
    coupon_metadata = coupon.get('metadata') if isinstance(coupon, Mapping) else None
    if isinstance(coupon_metadata, Mapping) and any(key in coupon_metadata for key in PROMOTION_ISSUANCE_METADATA_KEYS):
        # A shared Coupon is never a source of order provenance. If its issuer also
        # stamps the full contract, it must agree exactly with the unique code.
        if _validated_issuance_metadata(coupon_metadata) != issuance:
            logger.warning('Ignoring conflicting promotion attribution metadata')
            return {}
    return {**issuance, 'bundle_promotion_code_id': promo_id}


def checkout_promotion_code_ids(session: Any) -> list[str]:
    """Extract only Stripe server-provided PromotionCode IDs from a completed Session."""
    session_dict = _object_dict(session)
    breakdown = (session_dict.get('total_details') or {}).get('breakdown') or {}
    discounts = breakdown.get('discounts') or []
    if not isinstance(discounts, list):
        return []
    promotion_ids = []
    for entry in discounts:
        discount = entry.get('discount') if isinstance(entry, Mapping) else None
        promotion = discount.get('promotion_code') if isinstance(discount, Mapping) else None
        if isinstance(promotion, str):
            promotion_id = promotion
        else:
            promotion_id = _object_dict(promotion).get('id')
        if (
            isinstance(promotion_id, str)
            and _PROMOTION_ID.fullmatch(promotion_id)
            and promotion_id not in promotion_ids
        ):
            promotion_ids.append(promotion_id)
    return promotion_ids


def subscription_promotion_code_ids(subscription: Any) -> list[str]:
    """Extract PromotionCode references from expanded Subscription discounts only."""
    subscription_dict = _object_dict(subscription)
    discounts = subscription_dict.get('discounts') or []
    legacy_discount = subscription_dict.get('discount')
    if legacy_discount:
        discounts = [*discounts, legacy_discount]
    promotion_ids = []
    for discount in discounts:
        promotion = discount.get('promotion_code') if isinstance(discount, Mapping) else None
        if isinstance(promotion, str):
            promotion_id = promotion
        else:
            promotion_id = _object_dict(promotion).get('id')
        if (
            isinstance(promotion_id, str)
            and _PROMOTION_ID.fullmatch(promotion_id)
            and promotion_id not in promotion_ids
        ):
            promotion_ids.append(promotion_id)
    return promotion_ids


def merge_promotion_attribution(
    metadata: Optional[Mapping[str, Any]], attribution: Optional[Mapping[str, str]]
) -> Dict[str, Any]:
    """Merge deterministic provenance without ever replacing a conflicting historical order."""
    merged = dict(metadata or {})
    attribution = attribution or {}
    if any(key in merged and merged[key] != value for key, value in attribution.items()):
        logger.warning('Preserving conflicting existing subscription attribution')
        return merged
    merged.update(attribution)
    return merged


def create_subscription_checkout_session(
    uid: str,
    price_id: str,
    idempotency_key: Optional[str] = None,
    customer_id: Optional[str] = None,
    promotion_code_id: Optional[str] = None,
    trial_period_days: Optional[int] = None,
    promotion_attribution: Optional[Mapping[str, str]] = None,
):
    """Create a Stripe Checkout session for a subscription.

    `trial_period_days` starts the subscription with a free trial; Checkout still collects the
    card, and Stripe charges the first period when the trial ends unless the subscriber cancels.
    """
    try:
        success_url = urljoin(base_url, 'v1/payments/success?session_id={CHECKOUT_SESSION_ID}')  # type: ignore[reportArgumentType]  # base_url validated at runtime
        cancel_url = urljoin(base_url, 'v1/payments/cancel')  # type: ignore[reportArgumentType]  # base_url validated at runtime

        # Pin the selected price's original currency as well as disabling FX.
        # Multi-currency Prices can otherwise select a presentment currency by IP.
        # Existing non-USD management/reactivation stays outside new Checkout.
        price = stripe.Price.retrieve(price_id)
        currency = price.currency.lower()

        # Only the narrow, server-derived allowlist can cross this boundary. Authentication
        # and plan ownership always win over attribution supplied by another internal caller.
        attribution = {
            key: promotion_attribution[key]
            for key in PROMOTION_ATTRIBUTION_METADATA_KEYS
            if promotion_attribution and key in promotion_attribution
        }
        metadata = {**attribution, 'uid': uid, 'sub_type': 'unlimited'}

        # session creation parameters
        session_params: Dict[str, Any] = {
            'client_reference_id': uid,
            'payment_method_types': ['card'],
            'line_items': [
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            'mode': 'subscription',
            'currency': currency,
            # Language only; this does not choose or convert the currency.
            'locale': 'auto',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'metadata': dict(metadata),
            'subscription_data': {'metadata': dict(metadata)},
            # Charge in the price's own currency, the one every paywall shows. With the
            # account's Adaptive Pricing on, a non-US buyer who saw a USD price card was
            # charged a converted local-currency amount; Google Play rejected Android
            # release 1504 for that mismatch. It also keeps a promotion code's
            # minimum_amount evaluated against the USD-authored price (issue #23299).
            'adaptive_pricing': {'enabled': False},
        }

        if currency == 'usd':
            # Stripe owns its currency glyphs. Keep USD explicit even where its
            # hosted template uses a dollar glyph rather than the app's US$.
            session_params['custom_text'] = {'submit': {'message': 'All amounts are in USD (US dollars).'}}

        if trial_period_days:
            session_params['subscription_data']['trial_period_days'] = trial_period_days

        if promotion_code_id:
            session_params['discounts'] = [{'promotion_code': promotion_code_id}]
        else:
            session_params['allow_promotion_codes'] = True

        if customer_id:
            session_params['customer'] = customer_id
            session_params['customer_update'] = {'name': 'auto', 'address': 'auto'}

        if idempotency_key:
            session_params['idempotency_key'] = idempotency_key

        checkout_session = stripe.checkout.Session.create(**session_params)
        return checkout_session
    except stripe.error.InvalidRequestError:  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # stripe.error exposed dynamically at runtime
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        return None


def cancel_subscription(subscription_id: str):
    """Cancel a Stripe subscription at the end of the current period."""
    try:
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        )
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        return None


# Stripe statuses in which a subscription can no longer bill the customer. Stripe rejects
# `cancel_at_period_end` on these ("A canceled subscription can only update its
# cancellation_details and metadata"), so callers that only need the goal state — the
# subscription is not billing — must ask Stripe rather than treat that 400 as a failure.
TERMINAL_SUBSCRIPTION_STATUSES = frozenset({'canceled', 'incomplete_expired'})


def cancel_subscription_for_account_deletion(subscription_id: str) -> None:
    """Cancel now for erasure; absent/terminal subscriptions already satisfy it.

    Unlike period-end cancellation, transport/rate-limit/server errors propagate
    so the deletion task can retry without mistaking an outage for success.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        if subscription.get('status') in TERMINAL_SUBSCRIPTION_STATUSES:
            return
        canceled = subscription.delete()
        if canceled.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES:
            raise RuntimeError('Stripe immediate cancellation did not reach a terminal status')
    except stripe.InvalidRequestError as error:
        if error.code == 'resource_missing' or 'no such subscription' in str(error).lower():
            return
        # A concurrent cancellation can win between retrieve and delete. Verify
        # the goal state rather than accepting an arbitrary Stripe 400.
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.InvalidRequestError as read_error:
            if read_error.code == 'resource_missing' or 'no such subscription' in str(read_error).lower():
                return
            raise
        if subscription.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES:
            raise error


def is_subscription_terminal(subscription_id: str) -> bool:
    """Whether Stripe currently reports the subscription in a terminal, non-billing state.

    Fails closed: an unreadable subscription or any non-terminal status returns False, so a
    caller never mistakes a transport error for a subscription that is already canceled. A
    subscription that does not exist at all (Stripe ``resource_missing``) is terminal: nothing
    can bill through an id Stripe does not know.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except stripe.InvalidRequestError as e:
        if getattr(e, 'code', None) == 'resource_missing' or getattr(e, 'http_status', None) == 404:
            # A subscription id Stripe has never heard of (a stale or synthetic id stored on the
            # user) cannot bill anyone, so the billing goal state is already met. Treating it as a
            # failure left account-deletion wipes retrying forever behind the auth fence.
            logger.warning(f"Subscription {subscription_id} does not exist in Stripe; treating as terminal")
            return True
        logger.error(f"Error retrieving subscription: {e}")
        return False
    except Exception as e:
        logger.error(f"Error retrieving subscription: {e}")
        return False
    return subscription.get('status') in TERMINAL_SUBSCRIPTION_STATUSES


def find_billable_app_subscription_ids(uid: str) -> list[str]:
    if not stripe.api_key:
        return []
    subscriptions = stripe.Subscription.search(query=f"metadata['uid']:'{uid}'")
    return [
        subscription.id
        for subscription in subscriptions.auto_paging_iter()
        if subscription.get('metadata', {}).get('app_id')
        and subscription.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES
    ]


def find_app_subscription_by_customer_id(
    customer_id: str, app_id: str, uid: str, status_filter: str = 'all'
) -> Optional[Dict[str, Any]]:
    """Find app subscription using customer ID (fast path)."""
    try:
        subscriptions = stripe.Subscription.list(customer=customer_id, status=cast(Any, status_filter), limit=5)
        latest_subscription = None

        for sub in subscriptions.data:
            sub_dict = sub.to_dict()  # type: ignore[reportDeprecated, reportUnknownVariableType]  # legacy stripe to_dict
            if sub_dict.get('metadata', {}).get('app_id') == app_id and sub_dict.get('metadata', {}).get('uid') == uid:
                if latest_subscription is None or sub_dict.get('created', 0) > latest_subscription.get('created', 0):
                    latest_subscription = sub_dict

        return latest_subscription
    except Exception as e:
        logger.error(f"Error finding app subscription by customer ID {customer_id}: {e}")
        return None


def find_app_subscription_by_metadata(app_id: str, uid: str, status_filter: str = 'all') -> Optional[Dict[str, Any]]:
    """Find app subscription by searching metadata (slow path)."""
    try:
        subscriptions = stripe.Subscription.list(limit=100, status=cast(Any, status_filter))
        latest_subscription = None

        for sub in subscriptions.data:
            sub_dict = sub.to_dict()  # type: ignore[reportDeprecated, reportUnknownVariableType]  # legacy stripe to_dict
            if sub_dict.get('metadata', {}).get('app_id') == app_id and sub_dict.get('metadata', {}).get('uid') == uid:
                if latest_subscription is None or sub_dict.get('created', 0) > latest_subscription.get('created', 0):
                    latest_subscription = sub_dict

        return latest_subscription
    except Exception as e:
        logger.error(f"Error finding app subscription by metadata: {e}")
        return None


def modify_subscription(subscription_id: str, **kwargs: Any) -> Any:
    """Modify a Stripe subscription with given parameters."""
    try:
        return stripe.Subscription.modify(subscription_id, **kwargs)
    except Exception as e:
        logger.error(f"Error modifying subscription {subscription_id}: {e}")
        return None


def create_app_payment_link(price_id: str, app_id: str, stripe_acc_id: str):
    """Create a payment link for the specified price."""
    payment_link = stripe.PaymentLink.create(
        line_items=[
            {
                'price': price_id,
                'quantity': 1,
            }
        ],
        transfer_data={
            'destination': stripe_acc_id,
        },
        subscription_data={'metadata': {'app_id': app_id}},
        metadata={'app_id': app_id},
    )
    return payment_link


def parse_event(payload: Any, sig_header: Any) -> Any:
    """Parse the Stripe event."""
    return stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)  # type: ignore[reportUnknownMemberType]  # stripe Webhook.construct_event partially typed


def parse_connect_event(payload: Any, sig_header: Any) -> Any:
    """Parse the Stripe Connect event."""
    return stripe.Webhook.construct_event(payload, sig_header, connect_secret)  # type: ignore[reportUnknownMemberType]  # stripe Webhook.construct_event partially typed


def create_connect_account(uid: str, country: str):
    account = stripe.Account.create(
        controller={
            "stripe_dashboard": {
                "type": "express",
            },
            "fees": {"payer": "application"},
            "losses": {"payments": "application"},
        },
        country=country,
        tos_acceptance={"service_agreement": "full" if country == "US" else "recipient"},
        capabilities={"transfers": {"requested": True}},
        metadata={
            "uid": uid,
        },
        settings={
            "payouts": {
                "schedule": {"interval": "monthly", "monthly_anchor": 2},
            },
        },
    )

    # Generate the onboarding URL with dynamic return and refresh URLs
    account_links = stripe.AccountLink.create(
        account=account.id,
        refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account.id}"),  # type: ignore[reportArgumentType]  # base_url validated at runtime
        return_url=urljoin(base_url, f"/v1/stripe/return/{account.id}"),  # type: ignore[reportArgumentType]  # base_url validated at runtime
        type="account_onboarding",
    )

    return {"account_id": account.id, "url": account_links.url}


def refresh_connect_account_link(account_id: str):
    account_link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account_id}"),  # type: ignore[reportArgumentType]  # base_url validated at runtime
        return_url=urljoin(base_url, f"/v1/stripe/return/{account_id}"),  # type: ignore[reportArgumentType]  # base_url validated at runtime
        type="account_onboarding",
    )
    return {"account_id": account_id, "url": account_link.url}


def is_onboarding_complete(account_id: str):
    account = stripe.Account.retrieve(account_id)  # type: ignore[reportUnknownMemberType]  # stripe Account.retrieve partially typed
    return account.charges_enabled and account.payouts_enabled and account.details_submitted


# Stripe does not have any official API to get a list of supported countries for connect
def get_supported_countries():
    if countries := redis_db.get_generic_cache('stripe_supported_countries'):
        return countries
    country_codes: list[str] = []
    starting_after: str | None = None
    while True:
        kwargs: Dict[str, Any] = {"limit": 100}
        if starting_after:
            kwargs["starting_after"] = starting_after
        page = stripe.CountrySpec.list(**kwargs)
        country_codes.extend(c['id'] for c in page.data)
        if not page.has_more or not page.data:
            break
        starting_after = page.data[-1]['id']
    # Gibraltar is not supported by us since it does not allow transfers
    country_codes = [c for c in country_codes if c != "GI"]
    if "US" not in country_codes:
        country_codes.append("US")
    country_codes = sorted(set(country_codes))
    countries = [
        {"id": code, "name": country.name}
        for code in country_codes
        if (country := pycountry.countries.get(alpha_2=code)) is not None
    ]
    # cache in redis for 7 days since it does not change that often. Maybe cache it for 30 days?
    redis_db.set_generic_cache('stripe_supported_countries', countries, 604800)
    return countries
