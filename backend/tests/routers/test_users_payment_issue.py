"""GET /v1/users/me/subscription reports a payable declined renewal additively.

Real route, response model and billing_recovery decision; storage and Stripe are fakes.
The entitlement stays Basic (past_due→Basic is unchanged): only payment_issue is added.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users as users_router
from utils import billing_recovery, subscription as subscription_module

NOW = int(datetime.now(timezone.utc).timestamp())
OMI_PRO_MONTHLY = 'price_1TuIa81F8wnoWYvw0iX0j5M8'


class _Obj:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


def _client(monkeypatch, stripe_status='past_due', hide_subscription_ui=False, period_end=NOW + 29 * 86400):
    stored = users_router.Subscription(
        plan=users_router.PlanType.basic,
        status=users_router.SubscriptionStatus.active,
        stripe_subscription_id='sub_1',
        current_period_end=period_end,
    )
    stripe_calls = []

    def retrieve_sub(sub_id):
        stripe_calls.append(sub_id)
        return _Obj(
            {
                'id': sub_id,
                'status': stripe_status,
                'metadata': {'uid': 'fixture-user'},
                'current_period_start': NOW - 86400,
                'latest_invoice': 'in_1',
                'items': {'data': [{'price': {'id': OMI_PRO_MONTHLY}}]},
            }
        )

    def retrieve_invoice(invoice_id):
        stripe_calls.append(invoice_id)
        return _Obj({'id': invoice_id, 'status': 'open', 'attempted': True, 'amount_remaining': 2999})

    monkeypatch.setattr(billing_recovery.stripe.Subscription, 'retrieve', retrieve_sub)
    monkeypatch.setattr(billing_recovery.stripe.Invoice, 'retrieve', retrieve_invoice)
    monkeypatch.setattr(users_router.users_db, 'is_byok_active', lambda uid: False)
    monkeypatch.setattr(users_router.users_db, 'get_stripe_customer_id', lambda uid: 'cus_1')
    monkeypatch.setattr(users_router, 'get_user_subscription', lambda uid: stored.model_copy())
    monkeypatch.setattr(users_router, 'get_user_valid_subscription', lambda uid: stored.model_copy())
    monkeypatch.setattr(users_router, 'reconcile_basic_plan_with_stripe', lambda *args: None)
    monkeypatch.setattr(users_router, 'get_monthly_usage_for_subscription', lambda uid: {'transcription_seconds': 10})
    monkeypatch.setattr(users_router, 'get_paid_plan_definitions', lambda *args, **kwargs: [])
    monkeypatch.setattr(users_router, 'should_hide_subscription_ui', lambda *args: hide_subscription_ui)
    monkeypatch.setattr(
        users_router,
        'get_phone_call_quota_snapshot',
        lambda *args, **kwargs: MagicMock(to_client_dict=lambda: {'has_access': False, 'is_paid': False}),
    )
    monkeypatch.setattr(
        users_router,
        'get_chat_quota_snapshot',
        lambda *args, **kwargs: {'used': 0.0, 'limit': None, 'unit': 'questions', 'allowed': True, 'reset_at': None},
    )
    monkeypatch.setattr(
        users_router, 'resolve_transcription_allowance', subscription_module.resolve_transcription_allowance
    )
    monkeypatch.setattr(subscription_module, 'is_trial_paywalled', lambda *args, **kwargs: False)
    monkeypatch.setattr(subscription_module, 'get_byok_key', lambda provider: None)
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', '')
    app = FastAPI()
    app.add_api_route(
        '/v1/users/me/subscription',
        users_router.get_user_subscription_endpoint,
        response_model=users_router.UserSubscriptionResponse,
    )
    app.dependency_overrides[users_router.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture-user'
    headers = {'X-App-Platform': 'ios', 'X-App-Version': '1.0.600', 'X-Omi-Plan-Identity': '1'}
    with TestClient(app) as client:
        response = client.get('/v1/users/me/subscription', headers=headers)
    assert response.status_code == 200
    return response.json(), stripe_calls


def test_past_due_payer_gets_payment_issue_and_stays_basic(monkeypatch):
    body, stripe_calls = _client(monkeypatch)

    assert body['payment_issue'] == {'status': 'past_due', 'plan': 'unlimited_v2'}
    assert body['subscription']['plan'] == 'basic'
    assert stripe_calls == ['sub_1', 'in_1']


@pytest.mark.parametrize('stripe_status', ['past_due', 'unpaid'])
def test_open_failed_renewal_is_reported_after_the_stored_period_ended(monkeypatch, stripe_status):
    body, _ = _client(monkeypatch, stripe_status=stripe_status, period_end=NOW - 86400)

    assert body['payment_issue'] == {'status': stripe_status, 'plan': 'unlimited_v2'}
    assert body['subscription']['plan'] == 'basic'


@pytest.mark.parametrize('stripe_status', ['active', 'canceled'])
def test_no_payment_issue_unless_stripe_says_past_due_or_unpaid(monkeypatch, stripe_status):
    body, _ = _client(monkeypatch, stripe_status=stripe_status)

    assert 'payment_issue' not in body


def test_hidden_subscription_ui_never_reports_or_reads_stripe(monkeypatch):
    body, stripe_calls = _client(monkeypatch, hide_subscription_ui=True)

    assert 'payment_issue' not in body
    assert stripe_calls == []
