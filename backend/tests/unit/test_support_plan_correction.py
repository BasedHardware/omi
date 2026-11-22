"""Tests for owner-scoped billing evidence, privacy and the transactional plan audit."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from database import support_actions
from scripts.support import ops
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.support import plan_correction as repair

OWNER = 'fixture-owner'
CUSTOMER = 'cus_fixture'
SUBSCRIPTION = 'sub_fixture'
SINCE = 200
NOW = 300
PROFILE = {
    'stripe_customer_id': CUSTOMER,
    'subscription': {'plan': 'plus', 'status': 'active', 'stripe_subscription_id': SUBSCRIPTION},
}


@contextmanager
def stripe_fixture(overrides=None):
    responses = {
        ('subscriptions', 'all'): [
            {'id': SUBSCRIPTION, 'status': 'canceled', 'metadata': {'uid': OWNER}, 'ended_at': 180}
        ],
        ('subscriptions/search', None): [{'metadata': {'uid': OWNER}}],
        ('invoices', None): [],
        ('charges', None): [],
        ('checkout/sessions', 'open'): [],
        ('checkout/sessions', 'complete'): [],
        **(overrides or {}),
    }

    def handle(request):
        assert request.method == 'GET'
        path = request.url.path.removeprefix('/v1/')
        if path == 'subscriptions/search':
            assert request.url.params['query'] == "metadata['uid']:'fixture-owner'"
            object_type = 'search_result'
        else:
            object_type = 'list'
        customer = request.url.params.get('customer', CUSTOMER)
        assert customer in {CUSTOMER, 'cus_other'}
        status = request.url.params.get('status')
        rows = responses.get((path, status, customer), responses[(path, status)])
        return httpx.Response(
            200,
            json={
                'object': object_type,
                'data': [{'customer': customer, 'livemode': True, **r} for r in rows],
                'has_more': False,
            },
        )

    with httpx.Client(base_url='https://api.stripe.com/v1/', transport=httpx.MockTransport(handle)) as client:
        yield repair.StripeBilling(client)


def test_canceled_owner_with_no_other_billing_evidence_is_eligible():
    with stripe_fixture() as billing:
        assert billing.guard(OWNER, CUSTOMER, SUBSCRIPTION, SINCE, NOW) is None


def test_historical_customer_without_current_entitlement_is_eligible():
    overrides = {
        ('subscriptions/search', None): [{'metadata': {'uid': OWNER}, 'customer': 'cus_other'}],
        ('subscriptions', 'all', 'cus_other'): [{'status': 'incomplete_expired'}],
    }
    with stripe_fixture(overrides) as billing:
        assert billing.guard(OWNER, CUSTOMER, SUBSCRIPTION, SINCE, NOW) is None


@pytest.mark.parametrize(
    ('override', 'reason'),
    [
        ({('subscriptions', 'all'): [{'id': 'sub_replacement', 'status': 'active'}]}, 'active_subscription'),
        ({('subscriptions', 'all'): [{'id': 'sub_replacement', 'status': 'incomplete'}]}, 'pending_checkout'),
        (
            {
                ('subscriptions/search', None): [{'metadata': {'uid': OWNER}, 'customer': 'cus_other'}],
                ('subscriptions', 'all', 'cus_other'): [{'status': 'incomplete_expired'}],
                ('checkout/sessions', 'open', 'cus_other'): [{'mode': 'subscription'}],
            },
            'pending_checkout',
        ),
        ({('invoices', None): [{'amount_paid': 50, 'status_transitions': {'paid_at': 220}}]}, 'recent_payment'),
        (
            {
                ('invoices', None): [
                    {
                        'amount_paid': 50,
                        'status_transitions': {'paid_at': 160},
                        'lines': {'has_more': False, 'data': [{'type': 'subscription', 'period': {'end': 330}}]},
                    }
                ]
            },
            'paid_subscription',
        ),
        (
            {
                ('charges', None): [
                    {
                        'paid': True,
                        'captured': True,
                        'status': 'succeeded',
                        'created': 170,
                        'balance_transaction': {'created': 210},
                    }
                ]
            },
            'recent_payment',
        ),
        ({('checkout/sessions', 'open'): [{'mode': 'subscription'}]}, 'pending_checkout'),
        (
            {('checkout/sessions', 'complete'): [{'mode': 'subscription', 'payment_status': 'unpaid'}]},
            'pending_checkout',
        ),
    ],
)
def test_billing_vetoes(override, reason):
    with stripe_fixture(override) as billing:
        assert billing.guard(OWNER, CUSTOMER, SUBSCRIPTION, SINCE, NOW) == reason


@pytest.mark.parametrize('apply', [False, True])
def test_hold_before_write_is_checked_again_in_transaction(monkeypatch, apply):
    store = StrictFirestore({('users', OWNER): PROFILE})
    hold = {'active': True, 'schema_version': 'legal_hold.v1', 'issuer': 'admin'}

    def guard(*_):
        store.rows[('legal_holds', OWNER)] = hold
        return None

    def transaction(max_attempts=None, read_only=False):
        assert not read_only
        return StrictFirestore.transaction(store, max_attempts)

    context = support_actions.ActionContext('TICKET', 'operator', 'repair projection', 'host', apply)
    operator = repair.PlanCorrection(store, SimpleNamespace(guard=guard), SINCE, context)
    monkeypatch.setattr(operator, '_read', lambda ref, transaction=None, field_paths=None: ref.get(transaction))
    monkeypatch.setattr(store, 'transaction', transaction)
    prepared = []
    monkeypatch.setattr(repair, 'append_receipt', lambda f, row: prepared.append(row))

    result = operator.process(OWNER, None, None, rollback=False)
    assert result['outcome'] == ('legal_hold' if apply else 'ready')
    assert store.rows[('users', OWNER)] == PROFILE
    assert not any(ref[0] == 'support_actions' for ref in store.rows)
    assert len(prepared) == int(apply)


def test_audit_fields_are_content_free_and_plan_write_is_narrow(monkeypatch):
    store = StrictFirestore({('users', OWNER): PROFILE})
    txn = store.transaction(max_attempts=1)
    version = SimpleNamespace(rfc3339=lambda: 'version')
    txn.write_results = [SimpleNamespace(update_time=version)]
    monkeypatch.setattr(store, 'transaction', lambda **kwargs: txn)
    context = support_actions.ActionContext('TICKET', 'operator', 'repair projection', 'host', True)
    operator = repair.PlanCorrection(store, SimpleNamespace(guard=lambda *args: None), SINCE, context)

    def read(ref, transaction=None, field_paths=None):
        snapshot = ref.get(transaction)
        snapshot.update_time = version
        return snapshot

    monkeypatch.setattr(operator, '_read', read)
    monkeypatch.setattr(repair, 'append_receipt', lambda *_: None)
    result = operator.process(OWNER, None, None, rollback=False)
    assert result['outcome'] == 'corrected'
    assert txn.updates == [(('users', OWNER), {'subscription.plan': 'basic'})]
    ((path, audit),) = txn.creates
    assert path == ('support_actions', result['action'])
    assert audit['ticket'] == 'TICKET' and audit['summary']['before_plan'] == 'plus'
    assert all(value not in repr(audit) for value in (OWNER, CUSTOMER, SUBSCRIPTION))

    # A later owner document version must fence off the rollback, even with a
    # matching plan and otherwise valid audit.
    txn = StrictFirestore.transaction(store, max_attempts=1)

    def changed_version(ref, transaction=None, field_paths=None):
        snapshot = read(ref, transaction, field_paths)
        snapshot.update_time = SimpleNamespace(rfc3339=lambda: 'later-version')
        return snapshot

    monkeypatch.setattr(operator, '_read', changed_version)
    assert operator.process(OWNER, None, result, rollback=True)['outcome'] == 'rollback_conflict'
    assert not txn.updates and not txn.creates


def test_parser_errors_do_not_echo_owner_arguments(capsys):
    with pytest.raises(SystemExit):
        ops.main(
            [
                '--ticket',
                'TICKET',
                '--actor',
                'operator',
                '--reason',
                'repair',
                'account',
                'correct-plan',
                '--owner',
                OWNER,
                '--since',
                OWNER,
            ]
        )
    assert OWNER not in capsys.readouterr().err
