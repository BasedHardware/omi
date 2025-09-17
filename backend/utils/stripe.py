import os
from urllib.parse import urljoin

import pycountry
import stripe

from database import redis_db

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


def create_subscription_checkout_session(uid: str, price_id: str, idempotency_key: str = None):
    """Create a Stripe Checkout session for a subscription."""
    try:
        success_url = urljoin(base_url, 'v1/payments/success?session_id={CHECKOUT_SESSION_ID}')
        cancel_url = urljoin(base_url, 'v1/payments/cancel')
        
        # session creation parameters
        session_params = {
            'client_reference_id': uid,
            'payment_method_types': ['card'],
            'line_items': [
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            'mode': 'subscription',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'allow_promotion_codes': True,
        }
        
        if idempotency_key:
            session_params['idempotency_key'] = idempotency_key
            
        checkout_session = stripe.checkout.Session.create(**session_params)
        return checkout_session
    except Exception as e:
        print(f"Error creating checkout session: {e}")
        return None


def cancel_subscription(subscription_id: str):
    """Cancel a Stripe subscription at the end of the current period."""
    try:
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        )
    except Exception as e:
        print(f"Error canceling subscription: {e}")
        return None


def find_app_subscription_by_customer_id(customer_id: str, app_id: str, uid: str, status_filter: str = 'all'):
    """Find app subscription using customer ID (fast path)."""
    try:
        subscriptions = stripe.Subscription.list(customer=customer_id, status=status_filter, limit=5)
        latest_subscription = None

        for sub in subscriptions.data:
            sub_dict = sub.to_dict()
            if sub_dict.get('metadata', {}).get('app_id') == app_id and sub_dict.get('metadata', {}).get('uid') == uid:
                if latest_subscription is None or sub_dict.get('created', 0) > latest_subscription.get('created', 0):
                    latest_subscription = sub_dict

        return latest_subscription
    except Exception as e:
        print(f"Error finding app subscription by customer ID {customer_id}: {e}")
        return None


def find_app_subscription_by_metadata(app_id: str, uid: str, status_filter: str = 'all'):
    """Find app subscription by searching metadata (slow path)."""
    try:
        subscriptions = stripe.Subscription.list(limit=100, status=status_filter)
        latest_subscription = None

        for sub in subscriptions.data:
            sub_dict = sub.to_dict()
            if sub_dict.get('metadata', {}).get('app_id') == app_id and sub_dict.get('metadata', {}).get('uid') == uid:
                if latest_subscription is None or sub_dict.get('created', 0) > latest_subscription.get('created', 0):
                    latest_subscription = sub_dict

        return latest_subscription
    except Exception as e:
        print(f"Error finding app subscription by metadata: {e}")
        return None


def modify_subscription(subscription_id: str, **kwargs):
    """Modify a Stripe subscription with given parameters."""
    try:
        return stripe.Subscription.modify(subscription_id, **kwargs)
    except Exception as e:
        print(f"Error modifying subscription {subscription_id}: {e}")
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


def parse_event(payload, sig_header):
    """Parse the Stripe event."""
    return stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)


def parse_connect_event(payload, sig_header):
    """Parse the Stripe Connect event."""
    return stripe.Webhook.construct_event(payload, sig_header, connect_secret)


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
        refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account.id}"),
        return_url=urljoin(base_url, f"/v1/stripe/return/{account.id}"),
        type="account_onboarding",
    )

    return {"account_id": account.id, "url": account_links.url}


def refresh_connect_account_link(account_id: str):
    account_link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account_id}"),
        return_url=urljoin(base_url, f"/v1/stripe/return/{account_id}"),
        type="account_onboarding",
    )
    return {"account_id": account_id, "url": account_link.url}


def is_onboarding_complete(account_id: str):
    account = stripe.Account.retrieve(account_id)
    return account.charges_enabled and account.payouts_enabled and account.details_submitted


# Stripe does not have any official API to get a list of supported countries for connect
def get_supported_countries():
    if countries := redis_db.get_generic_cache('stripe_supported_countries'):
        return countries
    data = stripe.CountrySpec.list(limit=100)
    country_codes = [country['id'] for country in data.data]
    # Gibraltar is not supported by us since it does not allow transfers
    if "GI" in country_codes:
        country_codes.remove("GI")
    if "US" not in country_codes:
        country_codes.append("US")
    if "TR" not in country_codes:
        country_codes.append("TR")
    country_codes.sort()
    countries = [
        {"id": code, "name": pycountry.countries.get(alpha_2=code).name}
        for code in country_codes
        if pycountry.countries.get(alpha_2=code)
    ]
    # cache in redis for 7 days since it does not change that often. Maybe cache it for 30 days?
    redis_db.set_generic_cache('stripe_supported_countries', countries, 604800)
    return countries
