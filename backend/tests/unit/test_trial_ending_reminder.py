"""A free trial's first charge is announced before it happens.

Support saw readers surprised by the full-price charge when a 7-day trial ended, and the in-app
30-day trial offer promises "We'll remind you before anything is charged". Stripe's
`customer.subscription.trial_will_end` (three days before the end) now sends that reminder once,
only to the account that owns the trial, and Checkout states the charge above its button.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from models.users import PlanType, Subscription
from routers import payment
from utils import trial_reminder
import utils.stripe as stripe_utils

NOW = 1_794_000_000
DAY = 86_400
PAID_PRICE = next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.unlimited)


def _trial(**changes):
    sub = {
        'id': 'sub-trial',
        'status': 'trialing',
        'trial_end': NOW + 3 * DAY,
        'cancel_at_period_end': False,
        'metadata': {'uid': 'user-trial'},
        'items': {
            'data': [
                {
                    'quantity': 1,
                    'price': {
                        'id': PAID_PRICE,
                        'currency': 'usd',
                        'unit_amount': 26991,
                        'recurring': {'interval': 'year'},
                    },
                }
            ]
        },
    }
    sub.update(changes)
    return sub


def test_trialing_paid_plan_names_the_charge_and_when():
    body = trial_reminder.trial_ending_reminder_body('user-trial', _trial(), NOW)
    assert body == (
        'It ends in 3 days, then your card is charged US$269.91 a year. '
        'To pay nothing, cancel before then in Settings.'
    )


def test_monthly_and_last_day_wording():
    monthly = _trial(trial_end=NOW + DAY // 2)
    monthly['items']['data'][0]['price'].update({'unit_amount': 2999, 'recurring': {'interval': 'month'}})
    body = trial_reminder.trial_ending_reminder_body('user-trial', monthly, NOW)
    assert body.startswith('It ends tomorrow, then your card is charged US$29.99 a month.')


@pytest.mark.parametrize(
    'changes',
    [
        {'status': 'active'},
        {'cancel_at_period_end': True},
        {'cancel_at': NOW + 3 * DAY},
        {'trial_end': NOW - 1},
        {'metadata': {'uid': 'someone-else'}},
        # An included-year code makes the next charge something other than the list price.
        {'discounts': ['di_123']},
        {'discount': {'id': 'di_123'}},
        {'collection_method': 'send_invoice'},
    ],
    ids=['not-trialing', 'cancelling', 'cancel-at', 'ended', 'foreign', 'discounts', 'discount', 'invoiced'],
)
def test_no_reminder_when_nothing_unexpected_will_be_charged(changes):
    assert trial_reminder.trial_ending_reminder_body('user-trial', _trial(**changes), NOW) is None


def test_unknown_price_sends_nothing():
    sub = _trial()
    sub['items']['data'][0]['price']['id'] = 'price_not_omi'
    assert trial_reminder.trial_ending_reminder_body('user-trial', sub, NOW) is None


def test_checkout_terms_state_amount_and_interval():
    assert trial_reminder.checkout_trial_terms(7, 26991, 'usd', 'year') == (
        'No charge today. When your 7-day free trial ends, your card is charged US$269.91 a year, '
        'less any code you apply, until you cancel. Cancel in the Omi app before the trial ends and you pay nothing.'
    )
    assert trial_reminder.checkout_trial_terms(7, None, 'usd', None).startswith('No charge today.')


def test_trial_checkout_session_carries_the_terms(monkeypatch):
    captured = {}
    price = SimpleNamespace(currency='usd', unit_amount=2999, recurring={'interval': 'month'})
    monkeypatch.setattr(stripe_utils.stripe.Price, 'retrieve', lambda price_id: price)
    monkeypatch.setattr(
        stripe_utils.stripe.checkout.Session,
        'create',
        lambda **params: captured.update(params) or SimpleNamespace(url='u', id='cs'),
    )
    stripe_utils.create_subscription_checkout_session('uid', PAID_PRICE, 'idem', trial_period_days=7)
    assert captured['subscription_data']['trial_period_days'] == 7
    assert captured['custom_text']['submit']['message'] == (
        'No charge today. When your 7-day free trial ends, your card is charged US$29.99 a month, '
        'less any code you apply, until you cancel. Cancel in the Omi app before the trial ends and you pay nothing. '
        'All amounts are in USD (US dollars).'
    )

    captured.clear()
    stripe_utils.create_subscription_checkout_session('uid', PAID_PRICE, 'idem')
    assert captured['custom_text']['submit']['message'] == 'All amounts are in USD (US dollars).'


@pytest.fixture
def lane(monkeypatch):
    state = SimpleNamespace(
        stored=Subscription(plan=PlanType.unlimited, stripe_subscription_id='sub-trial'),
        claims=set(),
        notifications=[],
        claim_error=None,
    )

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def claim(uid, subscription_id, trial_end):
        if state.claim_error:
            raise state.claim_error
        marker = (uid, subscription_id, trial_end)
        if marker in state.claims:
            return False
        state.claims.add(marker)
        return True

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: state.stored)
    monkeypatch.setattr(payment, 'claim_trial_ending_notification', claim)
    monkeypatch.setattr(payment.time, 'time', lambda: NOW)
    monkeypatch.setattr(
        payment,
        'dispatch_notification',
        lambda intent: state.notifications.append((intent.user_id, intent.title, intent.body, intent.data)),
    )
    return state


def _event(sub=None):
    return {
        'id': 'evt-trial',
        'type': 'customer.subscription.trial_will_end',
        'data': {'object': sub or _trial()},
    }


def _deliver(event):
    async def run():
        tasks = BackgroundTasks()
        result = await payment._handle_stripe_event(event, tasks)
        await tasks()
        return result

    return asyncio.run(run())


def test_trial_will_end_sends_one_reminder_across_redeliveries(lane):
    assert _deliver(_event())['status'] == 'success'
    _deliver(_event())
    assert lane.notifications == [
        (
            'user-trial',
            'Your Omi Pro free trial ends soon',
            'It ends in 3 days, then your card is charged US$269.91 a year. '
            'To pay nothing, cancel before then in Settings.',
            {'type': 'trial_ending', 'navigate_to': '/settings'},
        )
    ]


def test_stale_subscription_or_missing_owner_sends_nothing(lane):
    lane.stored = Subscription(plan=PlanType.unlimited, stripe_subscription_id='sub-newer')
    _deliver(_event())
    _deliver(_event(_trial(metadata={})))
    assert lane.notifications == []


def test_claim_failure_stays_retryable(lane):
    lane.claim_error = ConnectionError('redis down')
    with pytest.raises(ConnectionError):
        _deliver(_event())
    assert lane.notifications == []
