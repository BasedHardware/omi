"""Unit tests verifying that GET /v1/stripe/return/{account_id} does not leak

account onboarding status to unauthenticated callers and does not crash on invalid accounts.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import payment as payment_router

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(payment_router.router)
    with TestClient(app) as test_client:
        yield test_client


def test_stripe_return_source_does_not_invoke_is_onboarding_complete():
    """Verify that stripe_return does not call is_onboarding_complete, preventing unauthenticated status disclosure."""
    source = PAYMENT_SOURCE.read_text(encoding="utf-8")
    start = source.index("def stripe_return(account_id: str):")
    end = source.index("\ndef ", start + 1)
    endpoint_code = source[start:end]

    assert "is_onboarding_complete(" not in endpoint_code, (
        "stripe_return must not invoke is_onboarding_complete to avoid disclosing onboarding status to unauthenticated callers."
    )


def test_stripe_return_does_not_leak_onboarding_status_in_html(monkeypatch, client):
    """Verify that stripe_return returns a generic landing response without specific account status disclosure."""
    mock_status = MagicMock(return_value=True)
    monkeypatch.setattr(payment_router, "is_onboarding_complete", mock_status)

    response = client.get("/v1/stripe/return/acct_target123")
    assert response.status_code == 200
    html = response.text

    # The unauthenticated return page must not report specific account setup outcomes
    assert "Stripe Account Setup Complete" not in html
    assert "Stripe Account Setup Incomplete" not in html
    assert "Your Stripe account has been successfully set up with Omi AI" not in html
    assert "The account setup process was not completed" not in html

    # It must provide generic, safe guidance to return to the app
    assert "Stripe Account Setup" in html
    assert "return to the app" in html.lower()

    # is_onboarding_complete must not be called
    mock_status.assert_not_called()


def test_stripe_return_handles_arbitrary_account_id_safely(client):
    """Verify that arbitrary or non-existent account IDs safely return the generic landing page without 500 error."""
    response = client.get("/v1/stripe/return/acct_nonexistent_or_malformed")
    assert response.status_code == 200
    assert "Stripe Account Setup" in response.text
