from fastapi import Request, Header, HTTPException, APIRouter, Depends
import stripe

from database.users import get_stripe_connect_account_id, set_stripe_connect_account_id
from utils import stripe as stripe_utils
from utils.apps import paid_app
from utils.other import endpoints as auth
from fastapi.responses import HTMLResponse

from utils.stripe import create_connect_account, refresh_connect_account_link, check_connect_account_onboarding_status, \
    is_onboarding_complete

router = APIRouter()


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
        session = event['data']['object']  # Contains session details
        print(f"Payment completed for session: {session['id']}")

        app_id = session['metadata']['app_id']
        client_reference_id = session['client_reference_id']
        if not client_reference_id or len(client_reference_id) < 4:
            raise HTTPException(status_code=400, detail="Invalid client")
        uid = client_reference_id[4:]

        # paid
        paid_app(app_id, uid)

    return {"status": "success"}


@router.post("/v1/stripe/create-connect-account")
async def create_connect_account_endpoint(request: Request, uid: str = Depends(auth.get_current_user_uid)):
    """
    Create a Stripe Connect account and return the account creation response
    """
    try:
        account_id = get_stripe_connect_account_id(uid)
        base_url = str(request.base_url).rstrip('/')

        if account_id:
            account = refresh_connect_account_link(account_id, base_url)
        else:
            account = create_connect_account(base_url)
            set_stripe_connect_account_id(uid, account['account_id'])

        return account

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
async def refresh_account_link_endpoint(request: Request, account_id: str,
                                        uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate a fresh account link if the previous one expired
    """
    try:
        base_url = str(request.base_url).rstrip('/')
        account = refresh_connect_account_link(account_id, base_url)
        return account
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/stripe/return/{account_id}", response_class=HTMLResponse)
async def stripe_return(account_id: str):
    """
    Handle the return flow from Stripe Connect account creation
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Return to App</title>
        <style>
            body {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            }
            .heading {
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 20px;
                color: #333;
                text-align: center;
            }
            .button {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 15px 32px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 16px;
                margin: 4px 2px;
                cursor: pointer;
                border-radius: 4px;
                transition: background-color 0.3s;
            }
            .button:hover {
                background-color: #45a049;
            }
        </style>
    </head>
    <body>
        <h1 class="heading">Stripe Account Setup Complete with Omi AI</h1>
        <a href="/" class="button">Return to App</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
