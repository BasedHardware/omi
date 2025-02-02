from urllib.parse import urljoin

from fastapi import Request, Header, HTTPException, APIRouter, Depends
import stripe
from utils import stripe as stripe_utils
from utils.apps import paid_app
from utils.other import endpoints as auth
from fastapi.responses import HTMLResponse

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
async def create_connect_account(request: Request):
    """
    Create a Stripe Connect account and return the account creation response
    """
    try:
        base_url = str(request.base_url).rstrip('/')

        account = stripe.Account.create(
            controller={
                "stripe_dashboard": {
                    "type": "express",
                },
                "fees": {
                    "payer": "application"
                },
                "losses": {
                    "payments": "application"
                },
            },
            settings={
                "payouts": {
                    "schedule": {
                        "interval": "monthly",
                        "monthly_anchor": 2
                    },
                },
            }
        )

        # Generate the onboarding URL with dynamic return and refresh URLs
        account_links = stripe.AccountLink.create(
            account=account.id,
            refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account.id}"),
            return_url=urljoin(base_url, f"/v1/stripe/return/{account.id}"),
            type="account_onboarding",
        )

        return {
            "account_id": account.id,
            "url": account_links.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/stripe/onboarding-status/{account_id}")
async def check_onboarding_status(account_id: str):
    """
    Check the onboarding status of a Connect account
    """
    try:
        account = stripe.Account.retrieve(account_id)
        return {
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
            "capabilities": account.capabilities
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/v1/stripe/refresh/{account_id}")
async def refresh_account_link(account_id: str):
    """
    Generate a fresh account link if the previous one expired
    """
    try:
        base_url = str(request.base_url).rstrip('/')
        account_link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=urljoin(base_url, f"/v1/stripe/refresh/{account.id}"),
            return_url=urljoin(base_url, f"/v1/stripe/return/{account.id}"),
            type="account_onboarding",
        )
        return {
            "account_id": account.id,
            "url": account_links.url
        }
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
