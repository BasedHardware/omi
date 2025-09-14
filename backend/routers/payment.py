from fastapi import Request, Header, HTTPException, APIRouter, Depends, Query
import stripe
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time

from database import (
    users as users_db,
    notifications as notifications_db,
    conversations as conversations_db,
    memories as memories_db,
    action_items as action_items_db,
)
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
from utils.apps import find_app_subscription, get_is_user_paid_app, paid_app, set_user_app_sub_customer_id
from utils.other import endpoints as auth
from fastapi.responses import HTMLResponse

from utils.stripe import create_connect_account, refresh_connect_account_link, is_onboarding_complete
from utils import subscription as subscription_utils
import os

router = APIRouter()


class CreateCheckoutRequest(BaseModel):
    price_id: str


class UpgradeSubscriptionRequest(BaseModel):
    price_id: str


class PricingOption(BaseModel):
    id: str  # price_id
    title: str  # "Monthly" or "Annual"
    price_string: str  # "$19/month" or "$199/year"
    description: Optional[str] = None
    interval: str  # "month" or "year"
    unit_amount: int  # amount in cents
    is_active: bool = False # Added for active status


class AvailablePlansResponse(BaseModel):
    plans: List[PricingOption]


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
                

@router.get('/v1/payments/available-plans', response_model=AvailablePlansResponse)
def get_available_plans_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Get available subscription plans with their price IDs and billing intervals."""
    try:

        monthly_price_id = os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID')
        annual_price_id = os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID')
        
        if not monthly_price_id or not annual_price_id:
            raise HTTPException(status_code=500, detail="Price configuration not found")
        
        # Fetch price details from Stripe
        monthly_price = stripe.Price.retrieve(monthly_price_id)
        annual_price = stripe.Price.retrieve(annual_price_id)
        
        # Get user's current subscription to determine which plan is active
        current_subscription = users_db.get_user_subscription(uid)
        current_price_id = None
        scheduled_price_id = None
        
        if current_subscription and current_subscription.status == SubscriptionStatus.active:
            try:
                stripe_sub = stripe.Subscription.retrieve(current_subscription.stripe_subscription_id).to_dict()
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
                            print(f"Error checking subscription schedules: {e}")
                            
            except Exception as e:
                print(f"Error retrieving current subscription: {e}")
        else:
            print(f"No active subscription found for user {uid}")
        
        # Create pricing options
        monthly_option = PricingOption(
            id=monthly_price.id,
            title="Monthly",
            price_string=f"${monthly_price.unit_amount / 100:.2f}/mo",
            description=None,
            interval=monthly_price.recurring.interval,
            unit_amount=monthly_price.unit_amount,
            is_active=current_price_id == monthly_price.id or scheduled_price_id == monthly_price.id
        )

        
        annual_option = PricingOption(
            id=annual_price.id,
            title="Annual", 
            price_string=f"${int(annual_price.unit_amount / 100 / 12)}/mo",
            description="Save 20% with annual billing.",
            interval=annual_price.recurring.interval,
            unit_amount=annual_price.unit_amount,
            is_active=current_price_id == annual_price.id or scheduled_price_id == annual_price.id
        )
        
        return AvailablePlansResponse(plans=[monthly_option, annual_option])
        
    except Exception as e:
        print(f"Error fetching available plans: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch available plans")


@router.post('/v1/payments/checkout-session')
def create_checkout_session_endpoint(request: CreateCheckoutRequest, uid: str = Depends(auth.get_current_user_uid)):
    # Check if user can make a new payment
    can_pay, reason = subscription_utils.can_user_make_payment(uid, request.price_id)
    if not can_pay:
        raise HTTPException(status_code=400, detail=reason)
    
    # idempotency key to prevent duplicate payments
    idempotency_key = str(uuid.uuid4())
    
    session = stripe_utils.create_subscription_checkout_session(uid, request.price_id, idempotency_key)
    if not session:
        raise HTTPException(status_code=500, detail="Could not create checkout session.")
    return {"url": session.url, "session_id": session.id}


@router.post('/v1/payments/upgrade-subscription')
def upgrade_subscription_endpoint(request: UpgradeSubscriptionRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Schedule an upgrade/downgrade to take effect at the end of the current billing period."""
    current_subscription = users_db.get_user_subscription(uid)
    
    if not current_subscription or not current_subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found to upgrade.")
    
    if current_subscription.plan != PlanType.unlimited:
        raise HTTPException(status_code=400, detail="Can only upgrade unlimited plan subscriptions.")
    
    try:
        # Retrieve current subscription to get current price ID
        stripe_sub = stripe.Subscription.retrieve(current_subscription.stripe_subscription_id).to_dict()
        current_price_id = stripe_sub['items']['data'][0]['price']['id']
        
        # Check if user is trying to upgrade to the same plan
        if current_price_id == request.price_id:
            raise HTTPException(
                status_code=400, 
                detail="You are already subscribed to this plan. Please select a different plan to upgrade or downgrade."
            )
        
        # Create a subscription schedule from the existing subscription
        schedule = stripe.SubscriptionSchedule.create(
            from_subscription=stripe_sub['id'], 
        )

        # Update the schedule with the new phase (annual plan)
        updated_schedule = stripe.SubscriptionSchedule.modify(
            schedule.id,
            phases=[
                {
                    'items': [{
                        'price': current_price_id,  # Keep current monthly plan
                        'quantity': 1,
                    }],
                    'start_date': stripe_sub['current_period_start'],
                    'end_date': stripe_sub['current_period_end'],
                },
                {
                    'items': [{
                        'price': request.price_id,  # New annual plan
                    }],
                },
            ],
            metadata={'uid': uid, 'upgrade_type': 'monthly_to_annual'}
        )

        print(f"updated_schedule: {updated_schedule}")
        
        # Update the subscription in our database to reflect the scheduled change
        # The current_period_end will be extended to include the annual period
        monthly_period_end = stripe_sub['current_period_end']
        annual_end_timestamp = monthly_period_end + 31536000  # 12 months after monthly ends
        current_subscription.current_period_end = annual_end_timestamp

        print(f"Updated subscription: {current_subscription.dict()}")
        
        users_db.update_user_subscription(uid, current_subscription.dict())
        
        # Calculate remaining days
        remaining_seconds = stripe_sub['current_period_end'] - int(time.time())
        remaining_days = max(0, remaining_seconds // 86400)  # Convert seconds to days
        
        return {
            "status": "success", 
            "message": f"Upgrade scheduled successfully! Your monthly plan continues until {remaining_days} days from now, then automatically switches to annual. You'll get 13 months of coverage total.",
            "subscription": current_subscription.dict(),
            "days_remaining": remaining_days,
            "schedule_id": schedule.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error scheduling subscription upgrade: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule subscription upgrade. Please try again.")


@router.delete('/v1/payments/subscription')
def cancel_subscription_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    subscription = users_db.get_user_subscription(uid)
    if not subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found.")

    try:
        # First, check if the subscription is managed by a subscription schedule
        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
        
        # Look for active subscription schedules for this customer
        customer_id = stripe_sub.get('customer')
        if not customer_id:
            raise HTTPException(status_code=400, detail="No customer ID found for subscription.")
            
        schedules = stripe.SubscriptionSchedule.list(
            customer=customer_id,
            limit=10
        )
        
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
            print(f"Canceling subscription schedule {active_schedule.id} for subscription {subscription.stripe_subscription_id}")
            stripe.SubscriptionSchedule.release(active_schedule.id)
            
            # Also cancel the current subscription at period end
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            
            # Update our database to reflect the scheduled cancellation
            subscription.cancel_at_period_end = True
            users_db.update_user_subscription(uid, subscription.dict())
            
            return {"status": "ok", "message": "Subscription scheduled for cancellation."}
        else:
            # No active schedule, cancel the subscription directly
            updated_sub = stripe_utils.cancel_subscription(subscription.stripe_subscription_id)
            if not updated_sub:
                raise HTTPException(status_code=500, detail="Could not cancel subscription with Stripe.")

            subscription.cancel_at_period_end = updated_sub.cancel_at_period_end
            users_db.update_user_subscription(uid, subscription.dict())

            return {"status": "ok", "message": "Subscription scheduled for cancellation."}
            
    except stripe.error.StripeError as e:
        print(f"Stripe error canceling subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Could not cancel subscription: {str(e)}")
    except Exception as e:
        print(f"Error canceling subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription. Please try again.")


@router.post('/v1/stripe/webhook', tags=['v1', 'stripe', 'webhook'])
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe_utils.parse_event(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

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
                stripe_utils.modify_subscription(subscription_id, metadata={"uid": uid, "app_id": app_id})
                # Store the customer ID for app subscription so that it is easy to cancel the subscription
                customer_id = session.get("customer")
                if customer_id:
                    set_user_app_sub_customer_id(app_id, uid, customer_id)
            paid_app(app_id, uid)

        # Regular user subscription
        elif client_reference_id:
            # Check if user already has an active subscription to prevent duplicates
            existing_subscription = users_db.get_user_valid_subscription(client_reference_id)
            if existing_subscription and existing_subscription.stripe_subscription_id:
                # If user already has a Stripe subscription, verify it's not the same one
                if existing_subscription.stripe_subscription_id == session.get('subscription'):
                    print(f"Duplicate webhook event for existing subscription: {session.get('subscription')}")
                    return {"status": "success", "message": "Subscription already processed."}
                else:
                    print(f"User {client_reference_id} has existing subscription {existing_subscription.stripe_subscription_id}, processing new subscription {session.get('subscription')}")
            
            _update_subscription_from_session(client_reference_id, session)
            subscription = users_db.get_user_subscription(client_reference_id)
            if subscription and subscription.plan == PlanType.unlimited:
                conversations_db.unlock_all_conversations(client_reference_id)
                memories_db.unlock_all_memories(client_reference_id)
                action_items_db.unlock_all_action_items(client_reference_id)
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
                if new_subscription.status == SubscriptionStatus.active and new_subscription.plan == PlanType.unlimited:
                    conversations_db.unlock_all_conversations(uid)
                    memories_db.unlock_all_memories(uid)
                    action_items_db.unlock_all_action_items(uid)
                users_db.update_user_subscription(uid, new_subscription.dict())
                print(f"Subscription for user {uid} updated from webhook event: {event['type']}.")

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
                        new_stripe_sub = stripe.Subscription.retrieve(new_subscription_id)
                        new_subscription = _build_subscription_from_stripe_object(new_stripe_sub.to_dict())
                        users_db.update_user_subscription(uid, new_subscription.dict())
                        print(f"Scheduled upgrade completed for user {uid}. New subscription: {new_subscription_id}")
                except Exception as e:
                    print(f"Error updating subscription after scheduled upgrade: {e}")
            elif schedule_obj.get('status') == 'canceled':
                try:
                    # When a schedule is canceled, update the subscription to reflect cancellation
                    if schedule_obj.get('subscription'):
                        subscription_id = schedule_obj['subscription']
                        stripe_sub = stripe.Subscription.retrieve(subscription_id)
                        subscription_obj = stripe_sub.to_dict()
                        
                        # Build subscription object with cancellation status
                        new_subscription = _build_subscription_from_stripe_object(subscription_obj)
                        new_subscription.cancel_at_period_end = True
                        
                        users_db.update_user_subscription(uid, new_subscription.dict())
                        print(f"Subscription schedule canceled for user {uid}. Subscription: {subscription_id}")
                except Exception as e:
                    print(f"Error updating subscription after schedule cancellation: {e}")

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


@router.get("/v1/apps/{app_id}/subscription")
def get_app_subscription(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get user's subscription for a specific app"""
    try:

        paid_app_check = get_is_user_paid_app(app_id, uid)
        if not paid_app_check:
            return {"subscription": None}

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
        print(f"Error getting app subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve subscription information")


@router.delete("/v1/apps/{app_id}/subscription")
def cancel_app_subscription(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Cancel user's subscription for a specific app"""
    try:

        paid_app_check = get_is_user_paid_app(app_id, uid)
        if not paid_app_check:
            raise HTTPException(status_code=404, detail="No active subscription found for this app")

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
    except stripe.error.StripeError as e:
        print(f"Stripe error canceling app subscription: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error canceling app subscription: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription")
