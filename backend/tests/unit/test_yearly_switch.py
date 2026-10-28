"""Monthly to yearly switch offer: who sees it, what it saves, and Stripe's preview of the charge."""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.users import PlanType, Subscription  # noqa: E402
import routers.yearly_switch as router  # noqa: E402
import utils.yearly_switch as ys  # noqa: E402

NOW = 1_793_000_000
DAY = 86400
DEFINITIONS = [
    {
        'plan_type': PlanType.unlimited_v2,
        'monthly_price_id': 'price_um',
        'annual_price_id': 'price_uy',
        'legacy': False,
    },
    {'plan_type': PlanType.plus, 'monthly_price_id': 'price_pm', 'annual_price_id': 'price_py', 'legacy': False},
    {
        'plan_type': PlanType.unlimited,
        'monthly_price_id': 'price_neo_m',
        'annual_price_id': 'price_neo_y',
        'legacy': False,
    },
    {'plan_type': PlanType.operator, 'monthly_price_id': 'price_om', 'annual_price_id': 'price_oy', 'legacy': False},
]
YEARLY = {
    'id': 'price_uy',
    'active': True,
    'currency': 'usd',
    'unit_amount': 26991,
    'recurring': {'interval': 'year', 'interval_count': 1},
}


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(ys, '_plan_definitions', lambda: DEFINITIONS)


def _sub(price_id='price_um', amount=2999, interval='month', **over):
    sub = {
        'id': 'sub_1',
        'customer': 'cus_1',
        'status': 'active',
        'cancel_at_period_end': False,
        'cancel_at': None,
        'schedule': None,
        'pending_update': None,
        'discount': None,
        'discounts': [],
        'trial_end': None,
        'start_date': NOW - 40 * DAY,
        'current_period_start': NOW - 5 * DAY,
        'current_period_end': NOW + 25 * DAY,
        'items': {
            'data': [
                {
                    'id': 'si_1',
                    'quantity': 1,
                    'price': {
                        'id': price_id,
                        'unit_amount': amount,
                        'currency': 'usd',
                        'recurring': {'interval': interval, 'interval_count': 1},
                    },
                }
            ]
        },
    }
    sub.update(over)
    return sub


def _invoice(amount_due=24492, currency='usd'):
    return {
        'currency': currency,
        'amount_due': amount_due,
        'lines': {
            'data': [
                {'proration': True, 'amount': -2499, 'period': {'start': NOW, 'end': NOW + 25 * DAY}},
                {'proration': False, 'amount': 26991, 'period': {'start': NOW, 'end': NOW + 365 * DAY}},
            ]
        },
    }


def test_omi_pro_monthly_is_offered_omi_pro_yearly_with_the_real_savings():
    offer = ys.evaluate(_sub(), YEARLY, NOW)
    assert offer.eligible
    assert (offer.plan_id, offer.price_id, offer.currency) == ('unlimited_v2', 'price_uy', 'usd')
    # 12 x $29.99 = $359.88 against $269.91 a year.
    assert (offer.monthly_amount, offer.yearly_amount, offer.savings_amount) == (2999, 26991, 8997)
    assert offer.first_billing_period is False


@pytest.mark.parametrize(
    'sub,reason',
    [
        (None, 'no_subscription'),
        # #23298: a trial must never be switched (Stripe ended it and charged the yearly price).
        (_sub(status='trialing'), 'status'),
        (_sub(trial_end=NOW + 3 * DAY), 'trial'),
        # #23301 territory: a past_due reader is not charged a bigger invoice.
        (_sub(status='past_due'), 'status'),
        (_sub(status='incomplete'), 'status'),
        (_sub(cancel_at_period_end=True), 'cancel_scheduled'),
        (_sub(cancel_at=NOW + 25 * DAY), 'cancel_scheduled'),
        (_sub(schedule='sub_sched_1'), 'scheduled_change'),
        (_sub(pending_update={'expires_at': NOW + DAY}), 'pending_update'),
        # A coupon (the stay offer's 50% off) would carry onto the yearly invoice.
        (_sub(discounts=['di_1']), 'discounted'),
        (_sub(discount={'coupon': {'id': 'omi-retention-50off-3mo'}}), 'discounted'),
        (_sub(pause_collection={'behavior': 'void'}), 'paused'),
        (_sub(collection_method='send_invoice'), 'collection_method'),
        (_sub(price_id='price_uy', amount=26991, interval='year'), 'not_monthly'),
        # Retired plans (2026-10-26) are not offered a new yearly term, even their own.
        (_sub(price_id='price_pm', amount=1799), 'not_offered'),
        (_sub(price_id='price_neo_m', amount=1999), 'not_offered'),
        (_sub(price_id='price_om', amount=4999), 'not_offered'),
        # A JPY subscription manages through its own prices (#23584); the offer is USD only.
        (_sub(currency='jpy'), 'currency'),
        (_sub(price_id='price_retained', amount=2999), 'not_offered'),
        (_sub(amount=0), 'free_price'),
    ],
)
def test_only_an_active_renewing_undiscounted_monthly_plan_is_offered(sub, reason):
    assert ys.refusal(sub, NOW) == reason
    offer = ys.evaluate(sub, YEARLY, NOW)
    assert not offer.eligible and offer.reason == reason


def test_a_price_billed_in_another_currency_is_not_offered():
    sub = _sub()
    sub['items']['data'][0]['price']['currency'] = 'eur'
    assert ys.refusal(sub, NOW) == 'currency'


def test_two_items_or_a_quantity_are_not_offered():
    two = _sub()
    two['items']['data'].append(dict(two['items']['data'][0], id='si_2'))
    assert ys.refusal(two, NOW) == 'items'
    seats = _sub()
    seats['items']['data'][0]['quantity'] = 3
    assert ys.refusal(seats, NOW) == 'items'


@pytest.mark.parametrize(
    'yearly,reason',
    [
        (None, 'no_yearly_price'),
        (dict(YEARLY, active=False), 'no_yearly_price'),
        (dict(YEARLY, id='price_other'), 'no_yearly_price'),
        (dict(YEARLY, recurring={'interval': 'month', 'interval_count': 1}), 'no_yearly_price'),
        (dict(YEARLY, currency='jpy'), 'currency'),
        (dict(YEARLY, unit_amount=35988), 'no_savings'),
    ],
)
def test_the_yearly_price_must_be_the_plans_own_and_cheaper(yearly, reason):
    offer = ys.evaluate(_sub(), yearly, NOW)
    assert not offer.eligible and offer.reason == reason


@pytest.mark.parametrize(
    'over,first',
    [
        ({'start_date': NOW - 5 * DAY}, True),  # still in the month they signed up
        ({'start_date': NOW - 40 * DAY}, False),
        # A 7-day trial then the first paid month: the paid month starts at trial_end.
        ({'start_date': NOW - 12 * DAY, 'trial_end': NOW - 5 * DAY}, True),
        ({'start_date': NOW - 42 * DAY, 'trial_end': NOW - 35 * DAY}, False),
    ],
)
def test_first_billing_period_marks_readers_still_in_their_first_paid_month(over, first):
    assert ys.evaluate(_sub(**over), YEARLY, NOW).first_billing_period is first


def test_switch_refusal_uses_the_offer_rules_and_only_the_plans_yearly_price():
    assert ys.switch_refusal(_sub(), 'price_uy', NOW) is None
    assert ys.switch_refusal(_sub(), 'price_py', NOW) == 'not_yearly_of_plan'
    assert ys.switch_refusal(_sub(status='trialing'), 'price_uy', NOW) == 'status'
    assert ys.switch_refusal(_sub(discounts=['di_1']), 'price_uy', NOW) == 'discounted'


@pytest.mark.parametrize(
    'proration_date,reason',
    [
        (None, 'preview_required'),
        (NOW - 60, None),
        (NOW + 60, 'preview_expired'),
        (NOW - 2 * 3600, 'preview_expired'),
        (NOW - 6 * DAY, 'preview_expired'),  # before the current period started
    ],
)
def test_a_previewed_proration_date_is_honored_for_an_hour_inside_the_period(proration_date, reason):
    assert ys.proration_date_refusal(_sub(), proration_date, NOW) == reason


def test_the_switch_charges_only_a_previewed_amount_and_never_a_promotion_code():
    assert ys.request_refusal(_sub(), 'price_uy', None, NOW - 60, 24492, NOW) is None
    assert ys.request_refusal(_sub(), 'price_uy', 'SAVE20', NOW - 60, 24492, NOW) == 'promotion_code'
    assert ys.request_refusal(_sub(), 'price_uy', None, None, 24492, NOW) == 'preview_required'
    assert ys.request_refusal(_sub(), 'price_uy', None, NOW - 60, None, NOW) == 'preview_required'
    assert ys.request_refusal(_sub(status='past_due'), 'price_uy', None, NOW - 60, 24492, NOW) == 'status'


@pytest.mark.parametrize(
    'preview,expected,reason',
    [
        ({'return_value': _invoice()}, 24492, None),
        # The amount moved since the reader saw it (balance, tax): refuse, the app re-previews.
        ({'return_value': _invoice(amount_due=24000)}, 24492, 'preview_changed'),
        ({'return_value': dict(_invoice(), total_discount_amounts=[{'amount': 13496}])}, 24492, 'discounted'),
        ({'return_value': dict(_invoice(), discounts=['di_customer'])}, 24492, 'discounted'),
        ({'return_value': _invoice(currency='jpy')}, 24492, 'preview_unavailable'),
        ({'side_effect': ys.stripe.error.APIConnectionError('down')}, 24492, 'preview_unavailable'),
    ],
)
def test_charge_refusal_reruns_the_preview_at_the_readers_proration_date(preview, expected, reason):
    with patch.object(ys.stripe.Invoice, 'create_preview', **preview) as create_preview:
        assert ys.charge_refusal(_sub(), 'price_uy', NOW - 60, expected) == reason
    create_preview.assert_called_once_with(
        customer='cus_1',
        subscription='sub_1',
        subscription_details={
            'items': [{'id': 'si_1', 'price': 'price_uy'}],
            'proration_behavior': 'always_invoice',
            'proration_date': NOW - 60,
        },
    )


def test_charge_refusal_without_a_preview_never_calls_stripe():
    with patch.object(ys.stripe.Invoice, 'create_preview') as create_preview:
        assert ys.charge_refusal(_sub(), 'price_uy', None, 24492) == 'preview_required'
        assert ys.charge_refusal(_sub(), 'price_uy', NOW, None) == 'preview_required'
    create_preview.assert_not_called()


def test_idempotency_key_is_one_per_subscription_and_preview():
    assert ys.idempotency_key('sub_1', NOW) == ys.idempotency_key('sub_1', NOW)
    assert ys.idempotency_key('sub_1', NOW) != ys.idempotency_key('sub_1', NOW + 1)
    assert ys.idempotency_key('sub_1', NOW) != ys.idempotency_key('sub_2', NOW)


def test_preview_asks_stripe_for_the_immediate_prorated_switch_and_reads_its_invoice():
    with (
        patch.object(ys.stripe.Subscription, 'retrieve', return_value=_sub()) as retrieve,
        patch.object(ys.stripe.Price, 'retrieve', return_value=YEARLY) as price,
        patch.object(ys.stripe.Invoice, 'create_preview', return_value=_invoice()) as preview,
    ):
        offer = ys.get_offer('sub_1', preview=True, now=NOW)

    retrieve.assert_called_once_with('sub_1', expand=['items.data.price'])
    price.assert_called_once_with('price_uy')
    preview.assert_called_once_with(
        customer='cus_1',
        subscription='sub_1',
        subscription_details={
            'items': [{'id': 'si_1', 'price': 'price_uy'}],
            'proration_behavior': 'always_invoice',
            'proration_date': NOW,
        },
    )
    assert offer.eligible
    assert (offer.amount_due_today, offer.renews_at, offer.proration_date) == (24492, NOW + 365 * DAY, NOW)


def test_offer_without_preview_never_calls_the_invoice_preview():
    with (
        patch.object(ys.stripe.Subscription, 'retrieve', return_value=_sub()),
        patch.object(ys.stripe.Price, 'retrieve', return_value=YEARLY),
        patch.object(ys.stripe.Invoice, 'create_preview') as preview,
    ):
        offer = ys.get_offer('sub_1', now=NOW)
    preview.assert_not_called()
    assert offer.eligible and offer.amount_due_today is None


def test_ineligible_subscription_reads_no_prices_or_preview():
    with (
        patch.object(ys.stripe.Subscription, 'retrieve', return_value=_sub(status='trialing')),
        patch.object(ys.stripe.Price, 'retrieve') as price,
        patch.object(ys.stripe.Invoice, 'create_preview') as preview,
    ):
        offer = ys.get_offer('sub_1', preview=True, now=NOW)
    assert (offer.eligible, offer.reason) == (False, 'status')
    price.assert_not_called()
    preview.assert_not_called()


@pytest.mark.parametrize(
    'invoice',
    [
        _invoice(currency='eur'),
        _invoice(amount_due=None),
        dict(_invoice(), lines={'data': [{'proration': True, 'period': {'end': NOW + 25 * DAY}}]}),
    ],
)
def test_a_preview_that_does_not_describe_the_switch_hides_it(invoice):
    with (
        patch.object(ys.stripe.Subscription, 'retrieve', return_value=_sub()),
        patch.object(ys.stripe.Price, 'retrieve', return_value=YEARLY),
        patch.object(ys.stripe.Invoice, 'create_preview', return_value=invoice),
    ):
        offer = ys.get_offer('sub_1', preview=True, now=NOW)
    assert (offer.eligible, offer.reason) == (False, 'unavailable')


def test_a_customer_coupon_on_the_preview_refuses_the_offer():
    with (
        patch.object(ys.stripe.Subscription, 'retrieve', return_value=_sub()),
        patch.object(ys.stripe.Price, 'retrieve', return_value=YEARLY),
        patch.object(
            ys.stripe.Invoice, 'create_preview', return_value=dict(_invoice(), total_discount_amounts=[{'amount': 500}])
        ),
    ):
        offer = ys.get_offer('sub_1', preview=True, now=NOW)
    assert (offer.eligible, offer.reason) == (False, 'discounted')


def test_stripe_failure_hides_the_offer_instead_of_raising():
    with patch.object(ys.stripe.Subscription, 'retrieve', side_effect=ys.stripe.error.APIConnectionError('down')):
        offer = ys.get_offer('sub_1', preview=True, now=NOW)
    assert (offer.eligible, offer.reason) == (False, 'unavailable')
    assert ys.get_offer(None).reason == 'no_subscription'


def test_endpoint_returns_the_offer_for_the_readers_subscription(monkeypatch):
    stored = Subscription(plan=PlanType.unlimited_v2, stripe_subscription_id='sub_1')
    monkeypatch.setattr(router.users_db, 'get_user_subscription', lambda uid: stored)
    seen = {}

    def fake_offer(subscription_id, preview=False):
        seen['args'] = (subscription_id, preview)
        return ys.evaluate(_sub(), YEARLY, NOW)

    monkeypatch.setattr(router.yearly_switch, 'get_offer', fake_offer)
    body = router.get_yearly_switch_endpoint(preview=True, uid='u1')
    assert seen['args'] == ('sub_1', True)
    assert body.eligible and body.savings_amount == 8997 and body.price_id == 'price_uy'


def test_endpoint_for_a_reader_without_a_subscription_is_ineligible(monkeypatch):
    monkeypatch.setattr(router.users_db, 'get_user_subscription', lambda uid: None)
    body = router.get_yearly_switch_endpoint(preview=False, uid='u1')
    assert (body.eligible, body.reason) == (False, 'no_subscription')
