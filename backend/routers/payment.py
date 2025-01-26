from fastapi import FastAPI, Request, Header, HTTPException, APIRouter
import stripe
from utils import stripe as stripe_utils
from utils.apps import paid_app

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
