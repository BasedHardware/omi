"""EXP-005 activates only after a positive initial paid invoice reaches the real webhook."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from config.plan_catalog import PlanType
from database import first_value_recovery as recovery
from routers import payment
from tests.unit.fixtures.generic_firestore_fake import FakeFirestore

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
START_AT = NOW - timedelta(hours=1)
PRICE_ID = 'fixture-monthly-price'


class _Request:
    @staticmethod
    async def body():
        return b'{}'


class _Subscription(dict):
    def to_dict(self):
        return dict(self)


def _event(amount_paid):
    return {
        'id': 'evt-first-paid',
        'created': int(NOW.timestamp()),
        'type': 'invoice.paid',
        'data': {
            'object': {
                'id': 'in-first-paid',
                'subscription': 'sub-first-paid',
                'paid': amount_paid > 0,
                'billing_reason': 'subscription_create',
                'amount_paid': amount_paid,
            }
        },
    }


def _subscription():
    return _Subscription(
        {
            'id': 'sub-first-paid',
            'created': int(START_AT.timestamp()),
            'status': 'active',
            'current_period_end': int((NOW + timedelta(days=30)).timestamp()),
            'metadata': {'uid': 'fixture-user'},
            'items': {
                'data': [{'price': {'id': PRICE_ID, 'recurring': {'interval': 'month'}}}],
            },
        }
    )


@pytest.fixture
def admission(monkeypatch):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    monkeypatch.setattr(recovery, 'intake_admitted', lambda *_args: True)
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    client = FakeFirestore()
    monkeypatch.setattr(recovery, 'get_firestore_client', lambda: client)
    emitted = []
    monkeypatch.setattr(recovery, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))
    return client, emitted


def _run(amount_paid, monkeypatch):
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda payload, sig: _event(amount_paid))
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', staticmethod(lambda _sub_id: _subscription()))
    return asyncio.run(payment.stripe_webhook(_Request(), 'sig'))


def test_positive_initial_invoice_reaches_paid_start_assignment(admission, monkeypatch):
    client, emitted = admission
    assert _run(3000, monkeypatch) == {'status': 'success'}
    assert len(client.docs) == 1
    start = next(iter(client.docs.values()))
    assert start['paid_start_at'] == START_AT
    assert start['variant'] in {'control', 'treatment'}
    assert len(emitted) == 1


def test_zero_initial_invoice_cannot_create_experiment_state(admission, monkeypatch):
    client, emitted = admission
    assert _run(0, monkeypatch) == {'status': 'success'}
    assert client.docs == {}
    assert emitted == []
