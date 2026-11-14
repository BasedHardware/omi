"""Declined yearly renewal to the same plan's monthly price: who is offered it, what is charged, and
that a decline, a replay or a failed void never charges twice or changes the plan."""

import os

import pytest
import stripe

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.users import PlanType  # noqa: E402
import utils.monthly_switch as ms  # noqa: E402

NOW = 1_793_000_000
DAY = 86400
UID = 'fixture-user'
NEO_YEARLY = 'price_1RtJQ71F8wnoWYvwKMPaGlGY'
NEO_MONTHLY = 'price_1RtJPm1F8wnoWYvwhVJ38kLb'
DEFINITIONS = [
    {'plan_type': PlanType.unlimited, 'monthly_price_id': NEO_MONTHLY, 'annual_price_id': NEO_YEARLY},
    {'plan_type': PlanType.unlimited_v2, 'monthly_price_id': 'price_um', 'annual_price_id': 'price_uy'},
    {'plan_type': PlanType.operator, 'monthly_price_id': 'price_om', 'annual_price_id': 'price_oy'},
]
MONTHLY_PRICE = {
    'id': NEO_MONTHLY,
    'active': True,
    'currency': 'usd',
    'unit_amount': 1999,
    'recurring': {'interval': 'month', 'interval_count': 1},
}


class _Obj(dict):
    def to_dict(self):
        return dict(self)


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(ms, '_plan_definitions', lambda: DEFINITIONS)


def _sub(price_id=NEO_YEARLY, **over):
    sub = {
        'id': 'sub_1',
        'customer': 'cus_1',
        'status': 'past_due',
        'currency': 'usd',
        'cancel_at_period_end': False,
        'cancel_at': None,
        'schedule': None,
        'pending_update': None,
        'discount': None,
        'discounts': [],
        'pause_collection': None,
        'collection_method': 'charge_automatically',
        'trial_end': None,
        'start_date': NOW - 367 * DAY,
        'current_period_start': NOW - 2 * DAY,
        'current_period_end': NOW + 363 * DAY,
        'latest_invoice': 'in_yearly',
        'metadata': {'uid': UID},
        'items': {
            'data': [
                {
                    'id': 'si_1',
                    'quantity': 1,
                    'price': {
                        'id': price_id,
                        'currency': 'usd',
                        'unit_amount': 19999,
                        'recurring': {'interval': 'year', 'interval_count': 1},
                    },
                }
            ]
        },
    }
    sub.update(over)
    return sub


def _invoice(**over):
    invoice = {
        'id': 'in_yearly',
        'customer': 'cus_1',
        'subscription': 'sub_1',
        'status': 'open',
        'attempted': True,
        'billing_reason': 'subscription_cycle',
        'currency': 'usd',
        'amount_remaining': 19999,
        'discounts': [],
        'total_discount_amounts': [],
    }
    invoice.update(over)
    return invoice


# --- who is offered the switch -------------------------------------------------------------------


def test_past_due_neo_yearly_renewal_is_offered_its_own_monthly_price():
    assert ms.refusal(_sub(), _invoice(), NOW) is None
    assert ms.target_for(NEO_YEARLY) == ms.Target(plan_id='unlimited', price_id=NEO_MONTHLY)


@pytest.mark.parametrize(
    'sub_over, invoice_over, reason',
    [
        ({'status': 'unpaid'}, {}, 'status'),
        ({'status': 'active'}, {}, 'status'),
        ({'trial_end': NOW + DAY}, {}, 'trial'),
        ({'cancel_at_period_end': True}, {}, 'cancel_scheduled'),
        ({'schedule': 'sub_sched_1'}, {}, 'scheduled_change'),
        ({'discount': {'coupon': {'id': 'c1'}}}, {}, 'discounted'),
        ({}, {'total_discount_amounts': [{'amount': 500}]}, 'discounted'),
        ({'pause_collection': {'behavior': 'void'}}, {}, 'paused'),
        ({'collection_method': 'send_invoice'}, {}, 'collection_method'),
        ({'currency': 'jpy'}, {}, 'currency'),
        ({}, {'currency': 'jpy'}, 'currency'),
        ({}, {'status': 'paid'}, 'no_open_invoice'),
        ({'latest_invoice': 'in_other'}, {}, 'not_latest_invoice'),
        ({}, {'billing_reason': 'subscription_update'}, 'not_renewal'),
        ({}, {'amount_remaining': 0}, 'nothing_due'),
    ],
)
def test_refused_for_everything_but_a_plain_declined_usd_yearly_renewal(sub_over, invoice_over, reason):
    assert ms.refusal(_sub(**sub_over), _invoice(**invoice_over), NOW) == reason


@pytest.mark.parametrize('price_id', ['price_om', 'price_oy', 'price_um', 'price_unknown'])
def test_monthly_desktop_and_unknown_prices_are_not_offered(price_id):
    assert ms.refusal(_sub(price_id=price_id), _invoice(), NOW) == 'not_offered'


def test_two_items_are_not_offered():
    sub = _sub()
    sub['items']['data'].append(dict(sub['items']['data'][0], id='si_2'))
    assert ms.refusal(sub, _invoice(), NOW) == 'items'


def test_offer_carries_the_catalog_monthly_amount_and_the_unpaid_yearly_amount(monkeypatch):
    monkeypatch.setattr(ms.stripe.Price, 'retrieve', lambda price_id: MONTHLY_PRICE)
    offer = ms.offer(_sub(), _invoice(), NOW)
    assert offer is not None
    assert offer.model_dump() == {'price_id': NEO_MONTHLY, 'amount': 1999, 'currency': 'usd', 'yearly_amount': 19999}


@pytest.mark.parametrize(
    'price',
    [
        dict(MONTHLY_PRICE, active=False),
        dict(MONTHLY_PRICE, currency='eur'),
        dict(MONTHLY_PRICE, recurring={'interval': 'year', 'interval_count': 1}),
        dict(MONTHLY_PRICE, unit_amount=0),
        dict(MONTHLY_PRICE, id='price_other'),
    ],
)
def test_no_offer_without_a_plain_monthly_usd_price(monkeypatch, price):
    monkeypatch.setattr(ms.stripe.Price, 'retrieve', lambda price_id: price)
    assert ms.offer(_sub(), _invoice(), NOW) is None


def test_offer_lookup_failure_hides_the_offer_and_never_raises(monkeypatch):
    def boom(price_id):
        raise stripe.error.APIConnectionError('down')

    monkeypatch.setattr(ms.stripe.Price, 'retrieve', boom)
    assert ms.offer(_sub(), _invoice(), NOW) is None


def test_refused_offer_makes_no_stripe_call(monkeypatch):
    def unexpected(price_id):
        raise AssertionError('no Stripe read for a refused offer')

    monkeypatch.setattr(ms.stripe.Price, 'retrieve', unexpected)
    assert ms.offer(_sub(status='active'), _invoice(), NOW) is None


# --- applying it ---------------------------------------------------------------------------------


class _Stripe:
    """Records the Stripe calls of one switch; ``decline`` makes the monthly charge fail."""

    def __init__(
        self,
        monkeypatch,
        sub=None,
        invoice=None,
        preview_amount=1999,
        decline=False,
        void_error=None,
        modify_error=None,
        modify_lands=False,
        collection_errors=(),
    ):
        self.calls = []
        self.modify_error = modify_error  # raised by Subscription.modify (after applying it when modify_lands)
        self.modify_lands = modify_lands
        self.collection_errors = list(collection_errors)  # raised by the next Invoice.modify calls, in order
        self.sub = sub or _sub()
        self.invoices = {'in_yearly': invoice or _invoice()}
        self.preview_amount = preview_amount
        self.decline = decline
        self.void_error = void_error
        monkeypatch.setattr(ms.stripe.Subscription, 'retrieve', self.retrieve_sub)
        monkeypatch.setattr(ms.stripe.Subscription, 'modify', self.modify)
        monkeypatch.setattr(ms.stripe.Invoice, 'retrieve', self.retrieve_invoice)
        monkeypatch.setattr(ms.stripe.Invoice, 'create_preview', self.preview)
        monkeypatch.setattr(ms.stripe.Invoice, 'void_invoice', self.void)
        monkeypatch.setattr(ms.stripe.Invoice, 'modify', self.modify_invoice)
        monkeypatch.setattr(ms.stripe.Price, 'retrieve', lambda price_id: MONTHLY_PRICE)

    def retrieve_sub(self, sub_id):
        self.calls.append(('retrieve_sub', sub_id))
        return _Obj(self.sub)

    def retrieve_invoice(self, invoice_id):
        self.calls.append(('retrieve_invoice', invoice_id))
        return _Obj(self.invoices[invoice_id])

    def preview(self, **params):
        self.calls.append(('preview', params['subscription_details']))
        return {'currency': 'usd', 'amount_due': self.preview_amount, 'discounts': [], 'total_discount_amounts': []}

    def modify_invoice(self, invoice_id, **params):
        self.calls.append(('collection', invoice_id, params['auto_advance']))
        if self.collection_errors:
            error = self.collection_errors.pop(0)
            if error:
                raise error
        self.invoices[invoice_id] = dict(self.invoices[invoice_id], auto_advance=params['auto_advance'])
        return _Obj(self.invoices[invoice_id])

    def auto_advance(self):
        return self.invoices['in_yearly'].get('auto_advance', True)

    def modify(self, sub_id, **params):
        self.calls.append(('modify', params))
        if self.decline:
            raise stripe.error.CardError('Your card was declined.', None, 'card_declined')
        if self.modify_error and not self.modify_lands:
            raise self.modify_error
        items = [dict(self.sub['items']['data'][0], price=dict(MONTHLY_PRICE))]
        self.sub = dict(
            self.sub,
            status='active',
            latest_invoice='in_monthly',
            items={'data': items},
            metadata=dict(self.sub['metadata'], **params['metadata']),
        )
        if self.modify_error:
            raise self.modify_error  # applied by Stripe, but the answer was lost
        return _Obj(self.sub)

    def void(self, invoice_id, **params):
        self.calls.append(('void', invoice_id, params.get('idempotency_key')))
        if self.void_error:
            raise self.void_error
        self.invoices[invoice_id] = dict(self.invoices[invoice_id], status='void')
        return _Obj(self.invoices[invoice_id])

    def names(self):
        return [call[0] for call in self.calls]


def test_switch_charges_monthly_first_then_voids_the_unpaid_yearly_invoice(monkeypatch):
    fake = _Stripe(monkeypatch)

    updated = ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert updated['status'] == 'active'
    modify = next(call[1] for call in fake.calls if call[0] == 'modify')
    assert modify == {
        'items': [{'id': 'si_1', 'price': NEO_MONTHLY}],
        'proration_behavior': 'none',
        'billing_cycle_anchor': 'now',
        'payment_behavior': 'error_if_incomplete',
        'metadata': {'uid': UID, 'sub_type': 'unlimited', ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'},
        'idempotency_key': 'omi-monthly-switch-sub_1-in_yearly-attempt-1',
    }
    preview = next(call[1] for call in fake.calls if call[0] == 'preview')
    assert preview == {
        'items': [{'id': 'si_1', 'price': NEO_MONTHLY}],
        'proration_behavior': 'none',
        'billing_cycle_anchor': 'now',
    }
    names = fake.names()
    assert names.index('preview') < names.index('collection') < names.index('modify') < names.index('void')
    # Collection was paused before the charge and never resumed: Stripe can no longer retry the yearly invoice.
    assert [call for call in fake.calls if call[0] == 'collection'] == [('collection', 'in_yearly', False)]
    assert ('void', 'in_yearly', 'omi-monthly-switch-void-in_yearly') in fake.calls
    assert fake.invoices['in_yearly']['status'] == 'void'


def test_declined_monthly_charge_changes_nothing_and_never_voids(monkeypatch):
    fake = _Stripe(monkeypatch, decline=True)

    with pytest.raises(stripe.error.CardError):
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert 'void' not in fake.names()
    assert fake.sub['status'] == 'past_due'
    assert fake.invoices['in_yearly']['status'] == 'open'
    # Paused for the attempt, then resumed: dunning and Update work exactly as before.
    assert [call for call in fake.calls if call[0] == 'collection'] == [
        ('collection', 'in_yearly', False),
        ('collection', 'in_yearly', True),
    ]
    assert fake.auto_advance() is True


@pytest.mark.parametrize(
    'kwargs, expected_amount, reason',
    [
        ({}, 2999, 'price_changed'),
        ({'preview_amount': 2500}, 1999, 'preview_changed'),
        ({'sub': _sub(status='active')}, 1999, 'no_payment_issue'),
        ({'sub': _sub(cancel_at_period_end=True)}, 1999, 'no_payment_issue'),
        ({'sub': _sub(metadata={'uid': 'someone-else'})}, 1999, 'no_payment_issue'),
        ({'sub': _sub(discount={'coupon': {'id': 'c1'}})}, 1999, 'discounted'),
    ],
)
def test_refusals_happen_before_any_charge(monkeypatch, kwargs, expected_amount, reason):
    fake = _Stripe(monkeypatch, **kwargs)

    with pytest.raises(ms.Refused) as refused:
        ms.switch(UID, 'sub_1', NEO_MONTHLY, expected_amount, 'attempt-1')

    assert refused.value.reason == reason
    assert 'modify' not in fake.names() and 'void' not in fake.names() and 'collection' not in fake.names()


def test_another_price_than_the_plans_monthly_is_refused(monkeypatch):
    fake = _Stripe(monkeypatch)

    with pytest.raises(ms.Refused) as refused:
        ms.switch(UID, 'sub_1', 'price_um', 1999, 'attempt-1')

    assert refused.value.reason == 'not_monthly_of_plan'
    assert 'modify' not in fake.names()


def test_a_repeated_request_replays_without_a_second_charge(monkeypatch):
    fake = _Stripe(monkeypatch)
    ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    for attempt in ('attempt-2', 'attempt-3'):
        replay = ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, attempt)
        assert replay['status'] == 'active'

    assert fake.names().count('modify') == 1
    assert fake.names().count('void') == 1  # the voided invoice is left alone afterwards


def test_a_failed_void_still_reports_the_switch_and_the_replay_voids_it(monkeypatch):
    fake = _Stripe(monkeypatch, void_error=stripe.error.APIConnectionError('down'))

    updated = ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')
    assert updated['status'] == 'active'
    assert fake.invoices['in_yearly']['status'] == 'open'

    fake.void_error = None
    ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-2')
    assert fake.invoices['in_yearly']['status'] == 'void'
    assert fake.names().count('modify') == 1


def test_void_never_touches_an_invoice_of_another_subscription(monkeypatch):
    fake = _Stripe(monkeypatch, invoice=_invoice(subscription='sub_other'))
    switched = _sub(status='active', metadata={'uid': UID, ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'})

    assert ms.void_superseded(switched) is False
    assert 'void' not in fake.names()


def test_void_reads_the_new_api_parent_subscription(monkeypatch):
    invoice = _invoice(subscription=None, parent={'subscription_details': {'subscription': 'sub_1'}})
    fake = _Stripe(monkeypatch, invoice=invoice)
    switched = _sub(status='active', metadata={'uid': UID, ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'})

    assert ms.void_superseded(switched) is True
    assert 'void' in fake.names()


def test_void_waits_until_the_subscription_is_active(monkeypatch):
    fake = _Stripe(monkeypatch)
    pending = _sub(metadata={'uid': UID, ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'})

    assert ms.void_superseded(pending) is False
    assert fake.calls == []


def test_kill_switch_hides_the_offer_and_refuses_the_switch(monkeypatch):
    fake = _Stripe(monkeypatch)
    monkeypatch.setenv('PAYMENT_ISSUE_MONTHLY_SWITCH_ENABLED', 'false')

    assert ms.offer(_sub(), _invoice(), NOW) is None
    with pytest.raises(ms.Refused) as refused:
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')
    assert refused.value.reason == 'disabled'
    assert fake.calls == []


class _Fallbacks:
    def __init__(self, monkeypatch):
        self.events = []
        monkeypatch.setattr(ms, 'record_fallback', lambda **kwargs: self.events.append(kwargs))

    def to_modes(self):
        return [event['to_mode'] for event in self.events]


def test_unknown_failure_that_did_not_switch_resumes_collection(monkeypatch):
    fake = _Stripe(monkeypatch, modify_error=stripe.error.APIConnectionError('timeout'))

    with pytest.raises(stripe.error.APIConnectionError):
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert fake.sub['status'] == 'past_due'
    assert fake.auto_advance() is True
    assert 'void' not in fake.names()


def test_unknown_failure_after_the_switch_landed_keeps_collection_paused(monkeypatch):
    fake = _Stripe(monkeypatch, modify_error=stripe.error.APIConnectionError('timeout'), modify_lands=True)

    with pytest.raises(stripe.error.APIConnectionError):
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert fake.sub['status'] == 'active'  # charged
    assert fake.auto_advance() is False  # so no retry can collect the yearly invoice as well
    fake.modify_error = None
    ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-2')  # the retry replays and voids
    assert fake.invoices['in_yearly']['status'] == 'void'
    assert fake.names().count('modify') == 1


def test_a_failed_pause_never_charges(monkeypatch):
    fake = _Stripe(monkeypatch, collection_errors=[stripe.error.APIConnectionError('down')])

    with pytest.raises(stripe.error.APIConnectionError):
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert 'modify' not in fake.names()
    assert fake.auto_advance() is True  # a pause that may have landed is undone


def test_a_failed_resume_is_reported(monkeypatch):
    fallbacks = _Fallbacks(monkeypatch)
    fake = _Stripe(monkeypatch, decline=True, collection_errors=[None, stripe.error.APIConnectionError('down')])

    with pytest.raises(stripe.error.CardError):
        ms.switch(UID, 'sub_1', NEO_MONTHLY, 1999, 'attempt-1')

    assert fake.auto_advance() is False
    assert fallbacks.to_modes() == ['paused']


def test_a_paid_superseded_yearly_invoice_is_reported_for_a_refund(monkeypatch, caplog):
    fallbacks = _Fallbacks(monkeypatch)
    fake = _Stripe(monkeypatch, invoice=_invoice(status='paid', amount_paid=19999, amount_remaining=0))
    switched = _sub(status='active', metadata={'uid': UID, ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'})

    with caplog.at_level('ERROR', logger=ms.logger.name):
        assert ms.void_superseded(switched) is True

    assert 'void' not in fake.names()
    assert fallbacks.events == [
        {
            'component': 'other',
            'from_mode': 'monthly_switch_superseded_invoice',
            'to_mode': 'paid_twice',
            'reason': 'other',
            'outcome': 'exhausted',
        }
    ]
    assert any('refund needed' in record.getMessage() for record in caplog.records)


def test_a_voided_superseded_invoice_raises_no_alarm(monkeypatch):
    fallbacks = _Fallbacks(monkeypatch)
    _Stripe(monkeypatch, invoice=_invoice(status='void', amount_remaining=0))
    switched = _sub(status='active', metadata={'uid': UID, ms.SUPERSEDED_INVOICE_KEY: 'in_yearly'})

    assert ms.void_superseded(switched) is True
    assert fallbacks.events == []
