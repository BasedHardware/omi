from __future__ import annotations

from utils.observability import subscription_events
from utils import product_telemetry


def test_paid_start_emits_bounded_owner_bound_event(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'unlimited')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-start-1',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.created',
        subscription_obj={'status': 'active', 'id': 'sub-secret'},
        previous_paid_subscription_id=None,
        resulting_paid_subscription_id='sub-secret',
    )

    assert emitted[0]['uid'] == 'uid-1'
    assert emitted[0]['event'] == 'Billing Subscription Started'
    assert emitted[0]['properties']['billing_event_id'] == 'evt-start-1'
    assert emitted[0]['properties']['plan'] == 'unlimited'
    assert 'sub-secret' not in emitted[0]['properties']
    assert 'customer' not in emitted[0]['properties']


def test_churn_requires_matching_paid_owner_and_scheduled_cancel_is_not_churn(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'unlimited')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(subscription_events, '_resolve_cancellation_reason', lambda _: 'cancellation_requested')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-update',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.updated',
        subscription_obj={'status': 'active', 'id': 'sub-1'},
        resulting_paid_subscription_id='sub-1',
        previous_paid_subscription_id='sub-1',
    )
    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-delete',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.deleted',
        subscription_obj={'status': 'canceled', 'id': 'sub-1'},
        resulting_paid_subscription_id=None,
        previous_paid_subscription_id='sub-1',
    )
    assert len(emitted) == 1
    assert emitted[0]['event'] == 'Billing Subscription Churned'
    assert emitted[0]['properties']['reason'] == 'cancellation_requested'


def test_paid_start_is_emitted_on_authoritative_updated_transition_after_incomplete_created(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'unlimited')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-created-incomplete',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.created',
        subscription_obj={'status': 'incomplete', 'id': 'sub-1'},
        resulting_paid_subscription_id=None,
        previous_paid_subscription_id=None,
    )
    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-updated-active',
        stripe_event_created=1_758_700_801,
        stripe_event_type='customer.subscription.updated',
        subscription_obj={'status': 'active', 'id': 'sub-1'},
        resulting_paid_subscription_id='sub-1',
        previous_paid_subscription_id=None,
    )

    assert [event['event'] for event in emitted] == ['Billing Subscription Started']


def test_stale_deleted_paid_subscription_does_not_emit_churn_for_different_current_paid_id(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'unlimited')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-delete-old',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.deleted',
        subscription_obj={'status': 'canceled', 'id': 'sub-old'},
        resulting_paid_subscription_id='sub-new',
        previous_paid_subscription_id='sub-old',
    )

    assert emitted == []


def test_paid_entitlement_loss_is_counted_on_update_and_not_again_on_delete(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'unlimited')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))
    for event_type, status, prior in [
        ('customer.subscription.updated', 'past_due', 'sub-1'),
        ('customer.subscription.deleted', 'canceled', None),
    ]:
        subscription_events.emit_billing_product_event(
            uid='uid-1',
            stripe_event_id=f'evt-{status}',
            stripe_event_created=1_758_700_800,
            stripe_event_type=event_type,
            subscription_obj={'status': status, 'id': 'sub-1'},
            previous_paid_subscription_id=prior,
            resulting_paid_subscription_id=None,
        )
    assert len(emitted) == 1
    assert emitted[0]['event'] == 'Billing Subscription Churned'
    assert emitted[0]['properties']['reason'] == 'payment_failure'


_PLUS_MONTHLY = 'price_1TuH6z1F8wnoWYvw7Siv61SX'


def test_scheduled_cancellation_carries_price_mrr_and_legacy_marker(monkeypatch):
    emitted = []
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-schedule',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.updated',
        subscription_obj={
            'status': 'active',
            'id': 'sub-secret',
            'cancel_at_period_end': True,
            'items': {
                'data': [
                    {
                        'price': {
                            'id': _PLUS_MONTHLY,
                            'unit_amount': 1999,
                            'recurring': {'interval': 'month'},
                        }
                    }
                ]
            },
        },
        previous_paid_subscription_id='sub-secret',
        resulting_paid_subscription_id='sub-secret',
        previous_attributes={'cancel_at_period_end': False},
    )

    assert [event['event'] for event in emitted] == ['Billing Subscription Cancellation Scheduled']
    properties = emitted[0]['properties']
    assert properties['plan'] == 'plus'
    assert properties['interval'] == 'month'
    assert properties['price_id'] == _PLUS_MONTHLY
    assert properties['mrr_cents'] == 1999
    assert properties['price_generation'] == 'legacy'
    assert properties['reason'] == 'none'
    assert 'sub-secret' not in properties.values()


def test_yearly_mrr_is_unit_amount_divided_by_twelve(monkeypatch):
    emitted = []
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-start-year',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.created',
        subscription_obj={
            'status': 'active',
            'id': 'sub-secret',
            'items': {
                'data': [
                    {
                        'price': {
                            'id': 'price_not_in_catalog',
                            'unit_amount': 19990,
                            'recurring': {'interval': 'year'},
                        }
                    }
                ]
            },
        },
        previous_paid_subscription_id=None,
        resulting_paid_subscription_id='sub-secret',
    )

    properties = emitted[0]['properties']
    assert properties['interval'] == 'year'
    assert properties['mrr_cents'] == 19990 // 12
    assert properties['price_generation'] == 'unknown'
    assert subscription_events.price_catalog_generation(_PLUS_MONTHLY) == 'legacy'
    assert subscription_events.price_catalog_generation('price_not_in_catalog') == 'unknown'


def test_update_without_cancel_transition_does_not_emit_scheduled_cancellation(monkeypatch):
    emitted = []
    monkeypatch.setattr(subscription_events, '_resolve_plan', lambda _: 'plus')
    monkeypatch.setattr(subscription_events, '_resolve_interval', lambda _: 'month')
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    subscription_events.emit_billing_product_event(
        uid='uid-1',
        stripe_event_id='evt-update',
        stripe_event_created=1_758_700_800,
        stripe_event_type='customer.subscription.updated',
        subscription_obj={'status': 'active', 'id': 'sub-1', 'cancel_at_period_end': True},
        previous_paid_subscription_id='sub-1',
        resulting_paid_subscription_id='sub-1',
        previous_attributes={'status': 'trialing'},
    )

    assert emitted == []
