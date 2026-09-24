```python
from stripe.error import StripeError
from fastapi import status, HTTPException
from fastapi.responses import JSONResponse
from .base import BaseRouter
from typing import Optional

class PaymentRouter(BaseRouter):
    """Payment router."""

    path = "/payment"

    async def cancel_subscription(self, request: Request, data: dict) -> JSONResponse:
        try:
            subscription_id = data.get("subscription_id")
            if not subscription_id:
                raise ValueError("Subscription ID is required.")
            # Stripe logic here
            return JSONResponse(
                content={"status": "success", "message": "Subscription cancelled successfully."},
                status_code=status.HTTP_200_OK
            )
        except StripeError as e:
            return JSONResponse(
                content={"status": "error", "message": "Subscription cancellation failed. Please try again."},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            self.logger.error(f"Payment error: {type(e).__name__}")
            raise

    async def process_payment(self, request: Request, data: dict) -> JSONResponse:
        try:
            # Stripe logic here
            return JSONResponse(
                content={"status": "success", "message": "Payment processed successfully."},
                status_code=status.HTTP_200_OK
            )
        except StripeError as e:
            return JSONResponse(
                content={"status": "error", "message": "Payment processing failed. Please try again."},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            self.logger.error(f"Payment error: {type(e).__name__}")
            raise

    # Other methods...
```

```python
import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from ..routers.payment import PaymentRouter

def test_cancel_subscription_success():
    client = TestClient(PaymentRouter())
    response = client.post(
        "/payment/cancel-subscription",
        json={"subscription_id": "sub_123"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Subscription cancelled successfully."}

def test_cancel_subscription_stripe_error():
    client = TestClient(PaymentRouter())
    response = client.post(
        "/payment/cancel-subscription",
        json={"subscription_id": "sub_123"}
    )
    assert response.status_code == 400
    assert response.json() == {"status": "error", "message": "Subscription cancellation failed. Please try again."}

# Other test cases...
```