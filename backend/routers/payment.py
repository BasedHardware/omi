from fastapi import Request, Header, HTTPException, APIRouter, Depends, Query
import stripe
from pydantic import BaseModel

from database import users as users_db, notifications as notifications_db
from utils.notifications import send_notification, send_subscription_paid_personalized_notification
from models.users import Subscription, PlanType, SubscriptionStatus, PlanLimits
from utils.subscription import get_basic_plan_limits, get_plan_type_from_price_id, get_plan_limits
from database.users import (
    get_stripe_connect_account_id,
    set_stripe_connect_account_id,
    set_paypal_payment_details,
    get_default_payment_method,
    set_default_payment_method,
    get_paypal_payment_details,
)
from utils import stripe as stripe_utils
from utils.apps import paid_app
from utils.other import endpoints as auth
from fastapi.responses import HTMLResponse

from utils.stripe import create_connect_account, refresh_connect_account_link, is_onboarding_complete

router = APIRouter()


class CreateCheckoutRequest(BaseModel):
    price_id: str


def _build_subscription_from_stripe_object(stripe_sub: dict) -> Subscription | None:
    """Builds a Subscription object from a Stripe Subscription object."""
    stripe_status = stripe_sub['status']

    # Get price ID from subscription items
    price_id = stripe_sub['items']['data'][0]['price']['id'] if stripe_sub['items']['data'] else None

    if not price_id:
        return None

    try:
        plan = get_plan_type_from_price_id(price_id)
    except ValueError:
        return None

    if stripe_status in ('active', 'trialing'):
        status = SubscriptionStatus.active
        limits = get_plan_limits(plan)
        cancel_at_period_end = stripe_sub.get('cancel_at_period_end', False)
    else:  # including 'canceled', 'unpaid', etc.
        plan = PlanType.basic
        status = SubscriptionStatus.inactive
        limits = get_basic_plan_limits()
        cancel_at_period_end = False  # If it's not active, it can't be pending cancellation

    return Subscription(
        plan=plan,
        status=status,
        current_period_end=stripe_sub.get('current_period_end'),
        stripe_subscription_id=stripe_sub['id'],
        cancel_at_period_end=cancel_at_period_end,
        limits=limits,
    )


def _update_subscription_from_session(uid: str, session: stripe.checkout.Session):
    customer_id = session.get('customer')
    subscription_id = session.get('subscription')

    if customer_id:
        users_db.set_stripe_customer_id(uid, customer_id)

    if subscription_id:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        if stripe_sub:
            new_subscription = _build_subscription_from_stripe_object(stripe_sub.to_dict())
            if new_subscription:
                users_db.update_user_subscription(uid, new_subscription.dict())
                print(f"Subscription for user {uid} updated from session {session.id}.")


@router.post('/v1/payments/checkout-session')
def create_checkout_session_endpoint(request: CreateCheckoutRequest, uid: str = Depends(auth.get_current_user_uid)):
    session = stripe_utils.create_subscription_checkout_session(uid, request.price_id)
    if not session:
        raise HTTPException(status_code=500, detail="Could not create checkout session.")
    return {"url": session.url, "session_id": session.id}


@router.delete('/v1/payments/subscription')
def cancel_subscription_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    subscription = users_db.get_user_subscription(uid)
    if not subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found.")

    updated_sub = stripe_utils.cancel_subscription(subscription.stripe_subscription_id)
    if not updated_sub:
        raise HTTPException(status_code=500, detail="Could not cancel subscription with Stripe.")

    subscription.cancel_at_period_end = updated_sub.cancel_at_period_end
    users_db.update_user_subscription(uid, subscription.dict())

    return {"status": "ok", "message": "Subscription scheduled for cancellation."}


@router.post('/v1/stripe/webhook', tags=['v1', 'stripe', 'webhook'])
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe_utils.parse_event(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    print("stripe_webhook event", event['type'])

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_reference_id = session.get('client_reference_id')

        # App payments for creators
        if session.get('metadata', {}).get('app_id'):
            print(f"Payment completed for session: {session['id']}")
            app_id = session['metadata']['app_id']
            uid = session['client_reference_id']
            if not uid or len(uid) < 4:
                raise HTTPException(status_code=400, detail="Invalid client")
            uid = uid[4:]

            if session.get("subscription"):
                subscription_id = session["subscription"]
                stripe.Subscription.modify(subscription_id, metadata={"uid": uid, "app_id": app_id})
            paid_app(app_id, uid)

        # Regular user subscription
        elif client_reference_id:
            _update_subscription_from_session(client_reference_id, session)
            subscription_id = session.get('subscription')
            if subscription_id:
                try:
                    stripe.Subscription.modify(subscription_id, metadata={"uid": client_reference_id})
                except Exception as e:
                    print(f"Error updating subscription metadata: {e}")

                # Get subscription details
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                if stripe_sub:
                    subscription_obj = stripe_sub.to_dict()
                    if subscription_obj and subscription_obj['items']['data']:
                        price_id = subscription_obj['items']['data'][0]['price']['id']
                        try:
                            plan_type = get_plan_type_from_price_id(price_id)
                            # Only send notification for unlimited plan subscriptions
                            if plan_type == PlanType.unlimited:
                                await send_subscription_paid_personalized_notification(client_reference_id)
                        except ValueError:
                            print(f"Ignoring checkout session for subscription with unknown price_id: {price_id}")

    if event['type'] in [
        'customer.subscription.updated',
        'customer.subscription.deleted',
        'customer.subscription.created',
    ]:
        subscription_obj = event['data']['object']
        uid = subscription_obj.get('metadata', {}).get('uid')

        if not uid:
            customer_id = subscription_obj.get('customer')
            if not customer_id:
                return {"status": "success", "message": "No customer ID or UID in subscription event."}

            user = users_db.get_user_by_stripe_customer_id(customer_id)
            if user and user.get('uid'):
                uid = user['uid']

        if uid:
            new_subscription = _build_subscription_from_stripe_object(subscription_obj)
            if new_subscription:
                users_db.update_user_subscription(uid, new_subscription.dict())
                print(f"Subscription for user {uid} updated from webhook event: {event['type']}.")

    return {"status": "success"}


@router.post('/v1/stripe/connect/webhook', tags=['v1', 'stripe', 'webhook'])
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
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
            uid = account['metadata']['uid']
            if get_default_payment_method(uid) is None:
                set_default_payment_method(uid, 'stripe')

    # TODO: handle this event to link transfers?
    # if event['type'] == 'transfer.created':
    #     transfer = event['data']['object']

    return {"status": "success"}


@router.post("/v1/stripe/connect-accounts")
async def create_connect_account_endpoint(
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
            if country is None or country.strip() == "":
                raise HTTPException(status_code=400, detail="Country is required")
            account = create_connect_account(uid, country)
            set_stripe_connect_account_id(uid, account['account_id'])

        return account
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/v1/stripe/supported-countries')
def get_supported_countries():
    return stripe_utils.get_supported_countries()


@router.get("/v1/stripe/onboarded", tags=['v1', 'stripe'])
async def check_onboarding_status(uid: str = Depends(auth.get_current_user_uid)):
    """
    Check the onboarding status of a Connect account
    """
    try:
        account_id = get_stripe_connect_account_id(uid)
        if not account_id:
            return {"onboarding_complete": False}
        return {"onboarding_complete": is_onboarding_complete(account_id)}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/v1/stripe/refresh/{account_id}")
async def refresh_account_link_endpoint(
    request: Request, account_id: str, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Generate a fresh account link if the previous one expired
    """
    try:
        account = refresh_connect_account_link(account_id)
        return account
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/stripe/return/{account_id}", response_class=HTMLResponse)
async def stripe_return(account_id: str):
    """
    Handle the return flow from Stripe Connect account creation
    """
    onboarding_complete = is_onboarding_complete(account_id)
    title = "Stripe Account Setup Complete" if onboarding_complete else "Stripe Account Setup Incomplete"
    message_class = "" if onboarding_complete else "error"
    message = (
        "Your Stripe account has been successfully set up with Omi AI. You can now start receiving payments."
        if onboarding_complete
        else "The account setup process was not completed. Please try again in a few minutes. If the issue persists, contact support."
    )

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
            .error {{
                color: #d32f2f;
            }}
        </style>
    </head>
    <body>
        <h1 class="heading">{title}</h1>
        <p class="message {message_class}">{message}</p>
        <p class="close-instruction">You can now close this window and return to the app</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/v1/paypal/payment-details")
def save_paypal_payment_details(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """
    Save PayPal payment details (email and paypal.me link)
    """
    try:
        if 'email' not in data or 'paypalme_url' not in data:
            raise HTTPException(status_code=400, detail="Email and PayPal.me URL are required")
        paypalme_url = data.get('paypalme_url').lower()
        data['email'] = data.get('email').lower()
        if paypalme_url and not paypalme_url.startswith('http'):
            paypalme_url = 'https://' + paypalme_url
        data['paypalme_url'] = paypalme_url
        set_paypal_payment_details(uid, data)
        if get_default_payment_method(uid) is None:
            set_default_payment_method(uid, 'paypal')
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/paypal/payment-details")
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
async def stripe_success(session_id: str = Query(...)):
    # The subscription is updated via webhook. This page is just for user feedback.
    return HTMLResponse(
        content="""
        <html>
            <head><title>Success</title></head>
            <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
                <h1>Payment Successful!</h1>
                <p>Your subscription is now active. You can close this window and return to the app.</p>
            </body>
        </html>
    """
    )


@router.get("/v1/payments/cancel", response_class=HTMLResponse)
async def stripe_cancel():
    return HTMLResponse(
        content="""
        <html>
            <head><title>Cancelled</title></head>
            <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
                <h1>Payment Cancelled</h1>
                <p>Your payment process was cancelled. You can return to the app.</p>
            </body>
        </html>
    """
    )


@router.get("/v1/payment-methods/status")
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


@router.post("/v1/payment-methods/default")
def set_default_payment_method_endpoint(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """Set the default payment method for the user"""
    method = data.get('method')
    if method not in ['stripe', 'paypal']:
        raise HTTPException(status_code=400, detail="Invalid method")
    set_default_payment_method(uid, method)
    return {"status": "success"}
