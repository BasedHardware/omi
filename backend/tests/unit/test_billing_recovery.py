"""A declined renewal the user can still pay is reported; nothing else is.

The webhook projects past_due to Basic on purpose, so the Home row depends on
this read: only past_due/unpaid with an open, attempted invoice, never for a
user who chose to cancel, never for a trial whose first charge failed.
"""

from datetime import datetime, timezone

import pytest

from models.users import PaymentIssue, PlanType, Subscription, SubscriptionStatus, UserSubscriptionResponse
from utils import billing_recovery

NOW = int(datetime.now(timezone.utc).timestamp())
DAY = 86400
OMI_PRO_MONTHLY = 'price_1TuIa81F8wnoWYvw0iX0j5M8'


def _stripe_sub(**overrides):
    sub = {
        'id': 'sub_1',
        'status': 'past_due',
        'customer': 'cus_1',
        'cancel_at_period_end': False,
        'cancel_at': None,
        'collection_method': 'charge_automatically',
        'metadata': {'uid': 'uid-1'},
        'trial_end': None,
        'current_period_start': NOW - DAY,
        'current_period_end': NOW + 29 * DAY,
        'latest_invoice': 'in_1',
        'items': {'data': [{'price': {'id': OMI_PRO_MONTHLY}}]},
    }
    sub.update(overrides)
    return sub


def _invoice(**overrides):
    invoice = {'id': 'in_1', 'status': 'open', 'attempted': True, 'amount_remaining': 2999}
    invoice.update(overrides)
    return invoice


def _stored(**overrides):
    fields = {
        'plan': PlanType.basic,
        'status': SubscriptionStatus.active,
        'stripe_subscription_id': 'sub_1',
        'current_period_end': NOW + 29 * DAY,
    }
    fields.update(overrides)
    return Subscription(**fields)


def test_past_due_with_open_invoice_is_a_payment_issue():
    issue = billing_recovery.payment_issue_from_stripe('uid-1', _stripe_sub(), _invoice())

    assert issue == PaymentIssue(status='past_due', plan=PlanType.unlimited_v2)


def test_unpaid_with_open_invoice_is_a_payment_issue():
    issue = billing_recovery.payment_issue_from_stripe('uid-1', _stripe_sub(status='unpaid'), _invoice())

    assert issue == PaymentIssue(status='unpaid', plan=PlanType.unlimited_v2)


@pytest.mark.parametrize('status', ['active', 'trialing', 'canceled', 'incomplete', 'incomplete_expired', 'paused'])
def test_other_statuses_are_not_payment_issues(status):
    assert billing_recovery.payment_issue_from_stripe('uid-1', _stripe_sub(status=status), _invoice()) is None


@pytest.mark.parametrize(
    'overrides',
    [
        {'cancel_at_period_end': True},
        {'cancel_at': NOW + 10 * DAY},
        {'collection_method': 'send_invoice'},
        {'metadata': {'uid': 'someone-else'}},
        {'items': {'data': [{'price': {'id': 'price_not_in_the_catalog'}}]}},
        {'items': {'data': []}},
    ],
)
def test_chosen_cancellations_and_foreign_subscriptions_are_not_payment_issues(overrides):
    assert billing_recovery.payment_issue_from_stripe('uid-1', _stripe_sub(**overrides), _invoice()) is None


def test_trial_whose_first_charge_failed_simply_ended():
    trial_ended = _stripe_sub(trial_end=NOW - DAY, current_period_start=NOW - DAY)

    assert billing_recovery.payment_issue_from_stripe('uid-1', trial_ended, _invoice()) is None


def test_failed_renewal_after_a_converted_trial_is_a_payment_issue():
    renewed = _stripe_sub(trial_end=NOW - 40 * DAY, current_period_start=NOW - DAY)

    assert billing_recovery.payment_issue_from_stripe('uid-1', renewed, _invoice()) is not None


def test_trial_check_reads_the_item_period_when_the_subscription_has_none():
    sub = _stripe_sub(trial_end=NOW - DAY, current_period_start=None)
    sub['items']['data'][0]['current_period_start'] = NOW - DAY

    assert billing_recovery.payment_issue_from_stripe('uid-1', sub, _invoice()) is None


@pytest.mark.parametrize(
    'invoice',
    [
        None,
        {'status': 'paid', 'attempted': True, 'amount_remaining': 0},
        {'status': 'draft', 'attempted': False, 'amount_remaining': 2999},
        {'status': 'open', 'attempted': False, 'amount_remaining': 2999},
        {'status': 'open', 'attempted': True, 'amount_remaining': 0},
        {'status': 'void', 'attempted': True, 'amount_remaining': 2999},
        {'status': 'uncollectible', 'attempted': True, 'amount_remaining': 2999},
    ],
)
def test_without_an_open_attempted_invoice_there_is_nothing_to_pay(invoice):
    assert billing_recovery.payment_issue_from_stripe('uid-1', _stripe_sub(), invoice) is None


class _Obj:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


def _stripe(monkeypatch, sub=None, invoice=None, error=None):
    calls = []

    def retrieve_sub(sub_id):
        calls.append(('subscription', sub_id))
        if error:
            raise error
        return _Obj(sub)

    def retrieve_invoice(invoice_id):
        calls.append(('invoice', invoice_id))
        return _Obj(invoice)

    monkeypatch.setattr(billing_recovery.stripe.Subscription, 'retrieve', retrieve_sub)
    monkeypatch.setattr(billing_recovery.stripe.Invoice, 'retrieve', retrieve_invoice)
    return calls


def test_lookup_reads_the_stored_subscription_and_its_latest_invoice(monkeypatch):
    calls = _stripe(monkeypatch, _stripe_sub(), _invoice())

    issue = billing_recovery.payment_issue_for('uid-1', _stored(), now=NOW)

    assert issue == PaymentIssue(status='past_due', plan=PlanType.unlimited_v2)
    assert calls == [('subscription', 'sub_1'), ('invoice', 'in_1')]


def test_active_subscription_never_reads_an_invoice(monkeypatch):
    calls = _stripe(monkeypatch, _stripe_sub(status='active'), _invoice())

    assert billing_recovery.payment_issue_for('uid-1', _stored(), now=NOW) is None
    assert calls == [('subscription', 'sub_1')]


@pytest.mark.parametrize(
    'stored',
    [
        None,
        _stored(plan=PlanType.unlimited_v2),
        _stored(stripe_subscription_id=None),
        _stored(stripe_subscription_id='pi_org_grant'),
        # Canceled by choice: the webhook stores the period that already ended.
        _stored(current_period_end=NOW - DAY),
    ],
)
def test_paid_free_and_former_subscribers_cost_no_stripe_call(monkeypatch, stored):
    calls = _stripe(monkeypatch, _stripe_sub(), _invoice())

    assert billing_recovery.payment_issue_for('uid-1', stored, now=NOW) is None
    assert calls == []


def test_unknown_stored_period_still_asks_stripe(monkeypatch):
    calls = _stripe(monkeypatch, _stripe_sub(), _invoice())

    assert billing_recovery.payment_issue_for('uid-1', _stored(current_period_end=None), now=NOW) is not None
    assert calls[0] == ('subscription', 'sub_1')


def test_stripe_failure_answers_no_issue_and_records_the_fallback(monkeypatch):
    _stripe(monkeypatch, error=RuntimeError('stripe down'))
    recorded = []
    monkeypatch.setattr(billing_recovery, 'record_fallback', lambda **labels: recorded.append(labels))

    assert billing_recovery.payment_issue_for('uid-1', _stored(), now=NOW) is None
    assert recorded == [
        {
            'component': 'other',
            'from_mode': 'stripe_payment_issue',
            'to_mode': 'none',
            'reason': 'unavailable',
            'outcome': 'degraded',
        }
    ]


def _response(**fields):
    return UserSubscriptionResponse(
        subscription=Subscription(),
        transcription_seconds_used=0,
        transcription_seconds_limit=0,
        words_transcribed_used=0,
        words_transcribed_limit=0,
        insights_gained_used=0,
        insights_gained_limit=0,
        **fields,
    )


def test_response_omits_payment_issue_when_there_is_none():
    assert 'payment_issue' not in _response().model_dump(mode='json')


def test_response_carries_status_and_plan_wire_ids():
    data = _response(payment_issue=PaymentIssue(status='past_due', plan=PlanType.unlimited_v2)).model_dump(mode='json')

    assert data['payment_issue'] == {'status': 'past_due', 'plan': 'unlimited_v2'}
