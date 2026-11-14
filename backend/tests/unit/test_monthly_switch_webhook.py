"""invoice.paid retries the void a monthly switch could not finish, so the unpaid yearly invoice
can never be collected after the reader moved to monthly. Real webhook handler; Stripe faked."""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import asyncio

import pytest
from fastapi import HTTPException

import routers.payment as payment
from utils import monthly_switch


class _Request:
    @staticmethod
    async def body():
        return b'{}'


SWITCHED = {
    'id': 'sub_1',
    'customer': 'cus_1',
    'status': 'active',
    'metadata': {'uid': 'user-1', monthly_switch.SUPERSEDED_INVOICE_KEY: 'in_yearly'},
}


@pytest.fixture
def stripe_fake(monkeypatch):
    state = {'invoice': {'id': 'in_yearly', 'subscription': 'sub_1', 'status': 'open'}, 'voids': [], 'fail': False}
    event = {'type': 'invoice.paid', 'data': {'object': {'subscription': 'sub_1'}}}
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda payload, sig: event)
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', staticmethod(lambda sub_id: dict(SWITCHED)))
    monkeypatch.setattr(monthly_switch.stripe.Invoice, 'retrieve', staticmethod(lambda invoice_id: state['invoice']))

    def void(invoice_id, **params):
        if state['fail']:
            raise RuntimeError('stripe unavailable')
        state['voids'].append((invoice_id, params.get('idempotency_key')))
        state['invoice'] = dict(state['invoice'], status='void')
        return state['invoice']

    monkeypatch.setattr(monthly_switch.stripe.Invoice, 'void_invoice', staticmethod(void))
    return state


def _run():
    return asyncio.run(payment.stripe_webhook(_Request(), 'sig'))


def test_paid_monthly_invoice_voids_a_still_open_yearly_invoice(stripe_fake):
    assert _run() == {"status": "success"}
    assert stripe_fake['voids'] == [('in_yearly', 'omi-monthly-switch-void-in_yearly')]


def test_an_already_void_yearly_invoice_is_left_alone(stripe_fake):
    stripe_fake['invoice'] = dict(stripe_fake['invoice'], status='void')

    assert _run() == {"status": "success"}
    assert stripe_fake['voids'] == []


def test_a_failed_void_asks_stripe_to_redeliver(stripe_fake):
    stripe_fake['fail'] = True

    with pytest.raises(HTTPException) as failed:
        _run()

    assert failed.value.status_code == 503
