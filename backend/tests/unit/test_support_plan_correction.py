"""Tests for owner-scoped billing evidence, privacy and the transactional plan audit."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES, resolve_subscription_entitlements
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
        ('customers/search', None): [],
        ('invoices', None): [],
        ('charges', None): [],
        ('checkout/sessions', 'open'): [],
        ('checkout/sessions', 'complete'): [],
        **(overrides or {}),
    }

    def handle(request):
        assert request.method == 'GET'
        path = request.url.path.removeprefix('/v1/')
        if path.endswith('/search'):
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


def test_stale_price_must_belong_to_the_verified_canceled_subscription():
    subscription = {
        'id': SUBSCRIPTION,
        'status': 'canceled',
        'metadata': {'uid': OWNER},
        'ended_at': 180,
        'items': {'data': [{'price': {'id': 'price_fixture'}}]},
    }
    with stripe_fixture({('subscriptions', 'all'): [subscription]}) as billing:
        assert billing.guard(OWNER, CUSTOMER, SUBSCRIPTION, SINCE, NOW, price='price_fixture') is None
        assert billing.guard(OWNER, CUSTOMER, SUBSCRIPTION, SINCE, NOW, price='price_other') == 'billing_unknown'


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
        ({('charges', None): [{'status': 'pending'}]}, 'pending_checkout'),
        (
            {('charges', None): [{'status': 'succeeded', 'paid': True, 'captured': False}]},
            'pending_checkout',
        ),
        ({('checkout/sessions', 'open'): [{'mode': 'subscription'}]}, 'pending_checkout'),
        (
            {
                ('customers/search', None): [{'id': 'cus_other', 'metadata': {'uid': OWNER}}],
                ('subscriptions', 'all', 'cus_other'): [],
                ('checkout/sessions', 'complete', 'cus_other'): [{'mode': 'payment', 'payment_status': 'unpaid'}],
            },
            'pending_checkout',
        ),
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

    def guard(*_, **_kwargs):
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


@pytest.mark.parametrize('with_stale_price', [False, True])
def test_apply_and_rollback_write_only_the_verified_subscription_fields(monkeypatch, with_stale_price):
    price = next(iter(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES))
    before = dict(PROFILE['subscription'])
    if with_stale_price:
        before['current_price_id'] = price
        assert resolve_subscription_entitlements({**before, 'plan': 'basic'}, {})['plan_id'] != 'basic'
    profile = {**PROFILE, 'subscription': before, 'language': 'en'}
    store = StrictFirestore({('users', OWNER): profile})
    txn = store.transaction(max_attempts=1)
    version = SimpleNamespace(rfc3339=lambda: 'version')
    txn.write_results = [SimpleNamespace(update_time=version)]
    monkeypatch.setattr(store, 'transaction', lambda **kwargs: txn)
    context = support_actions.ActionContext('TICKET', 'operator', 'repair projection', 'host', True)
    operator = repair.PlanCorrection(store, SimpleNamespace(guard=lambda *args, **kwargs: None), SINCE, context)

    def read(ref, transaction=None, field_paths=None):
        snapshot = ref.get(transaction)
        snapshot.update_time = version
        return snapshot

    monkeypatch.setattr(operator, '_read', read)
    monkeypatch.setattr(repair, 'append_receipt', lambda *_: None)
    result = operator.process(OWNER, None, None, rollback=False)
    assert result['outcome'] == 'corrected'
    patch = {'subscription.plan': 'basic'}
    if with_stale_price:
        patch['subscription.current_price_id'] = None
    assert txn.updates == [(('users', OWNER), patch)]
    stored = store.rows[('users', OWNER)]
    assert stored['language'] == 'en'
    assert stored['subscription']['stripe_subscription_id'] == SUBSCRIPTION
    assert resolve_subscription_entitlements(stored['subscription'], {})['plan_id'] == 'basic'
    assert result['before_price_present'] is with_stale_price
    assert result['before_price_id'] == (price if with_stale_price else None)
    ((path, audit),) = txn.creates
    assert path == ('support_actions', result['action'])
    assert audit['ticket'] == 'TICKET' and audit['summary']['before_plan'] == 'plus'
    assert all(value not in repr(audit) for value in (OWNER, CUSTOMER, SUBSCRIPTION, price))

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

    txn = StrictFirestore.transaction(store, max_attempts=1)
    monkeypatch.setattr(operator, '_read', read)
    with monkeypatch.context() as preview:
        preview.setattr(operator, 'ctx', replace(context, apply=False))

        def preview_transaction(*, max_attempts, read_only):
            assert read_only and max_attempts == 1
            return txn

        preview.setattr(store, 'transaction', preview_transaction)
        assert operator.process(OWNER, None, result, rollback=True)['outcome'] == 'ready'
    assert not txn.updates and not txn.creates

    txn = StrictFirestore.transaction(store, max_attempts=1)
    txn.write_results = [SimpleNamespace(update_time=version)]
    assert operator.process(OWNER, None, result, rollback=True)['outcome'] == 'rolled_back'
    assert store.rows[('users', OWNER)] == profile
    ((_, rollback_audit),) = txn.creates
    assert rollback_audit['summary']['rollback_of'] == result['action']


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


@pytest.mark.parametrize('off', ['false', ' OFF ', '0', 'no'])
def test_apply_kill_switch_blocks_before_credentials_or_packet(monkeypatch, off):
    monkeypatch.setenv('OMI_SUPPORT_CORRECT_PLAN_ENABLED', off)
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host', True)
    result, code = repair.run(argparse.Namespace(), ctx)
    assert (result, code) == ({'document_reads': 0, 'counts': {}, 'error': 'disabled'}, 1)


@pytest.mark.parametrize(
    'invalid', [None, 'schema', 'mode', 'ticket', 'since', 'stale', 'incomplete', 'failed', 'unknown', 'owner']
)
def test_apply_obeys_committed_dry_run_proof(invalid):
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    since = date(2026, 11, 21)
    header = {
        'schema': repair.RECEIPT_SCHEMA,
        'mode': 'dry_run',
        'ticket': 'TICKET',
        'since': since.isoformat(),
        'created_at': now.isoformat(),
    }
    row = {'owner': OWNER, 'outcome': 'ready'}
    trailer = {'complete': True, 'counts': {}}
    if invalid in {'schema', 'mode', 'ticket', 'since'}:
        header[invalid] = 'unexpected'
    if invalid == 'stale':
        header['created_at'] = (now - timedelta(hours=25)).isoformat()
    if invalid == 'incomplete':
        trailer['complete'] = False
    if invalid in {'failed', 'unknown'}:
        trailer['counts']['failed' if invalid == 'failed' else 'billing_unknown'] = 1
    args = argparse.Namespace(
        owner='out-of-scope' if invalid == 'owner' else OWNER,
        owners_file=None,
        since=since,
        rollback_receipt=None,
        dry_run_receipt='packets/fixture.jsonl',
    )
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host', True)
    packet = SimpleNamespace(receipt=lambda _: [header, row, trailer])
    if invalid is not None:
        with pytest.raises(repair.EvidenceUnavailable):
            repair._inputs(args, ctx, packet, now)
    else:
        assert repair._inputs(args, ctx, packet, now) == ([OWNER], 'apply', {OWNER: row})


def test_document_reads_use_the_bounded_firestore_boundary():
    store = StrictFirestore()
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host')
    operator = repair.PlanCorrection(store, SimpleNamespace(), SINCE, ctx)
    assert not operator._read(store.document('users/fixture-owner')).exists
    assert operator.reads == 1


@pytest.mark.parametrize('outcome', ['billing_unknown', 'basic_with_price', 'failed'])
def test_unresolved_dry_run_returns_nonzero_and_counts_only(monkeypatch, outcome):
    monkeypatch.setenv('STRIPE_PLAN_CORRECTION_READ_KEY', 'rk_live_fixture')
    monkeypatch.setenv('OMI_SUPPORT_TRIAGE_ORIGIN', 'ssh://git@fixture.invalid/triage.git')
    packet = SimpleNamespace(new_receipt=lambda _: nullcontext())
    monkeypatch.setattr(repair, 'PrivatePacket', lambda *_: packet)
    monkeypatch.setattr(repair, '_inputs', lambda *_: ([OWNER], 'dry_run', {}))
    monkeypatch.setattr(repair, 'append_receipt', lambda *_: None)

    def process(*_, **_kwargs):
        if outcome == 'failed':
            raise RuntimeError(OWNER)
        if outcome == 'billing_unknown':
            raise repair.EvidenceUnavailable()
        return {'outcome': outcome}

    monkeypatch.setattr(repair, 'PlanCorrection', lambda *_: SimpleNamespace(process=process, reads=3))
    args = argparse.Namespace(private_checkout=None, receipt='packets/fixture.jsonl', since=date(2026, 11, 21))
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host')
    result, code = repair.run(args, ctx, firestore_client=object())
    assert (result, code) == ({'document_reads': 3, 'counts': {outcome: 1, 'unprocessed': 0}}, 1)
    assert OWNER not in repr(result)


@pytest.mark.parametrize(('price', 'outcome'), [(None, 'already_basic'), ('price_fixture', 'basic_with_price')])
def test_basic_with_price_needs_review_instead_of_silent_skip(monkeypatch, price, outcome):
    profile = {**PROFILE, 'subscription': {**PROFILE['subscription'], 'plan': 'basic', 'current_price_id': price}}
    store = StrictFirestore({('users', OWNER): profile})
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host')
    operator = repair.PlanCorrection(store, SimpleNamespace(), SINCE, ctx)
    monkeypatch.setattr(operator, '_read', lambda ref, transaction=None, field_paths=None: ref.get(transaction))
    assert operator.process(OWNER, None, None, rollback=False) == {'outcome': outcome}
    assert not store.transactions


def test_rollback_requires_committed_apply_receipt():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    since = date(2026, 11, 21)
    header = {'schema': repair.RECEIPT_SCHEMA, 'mode': 'apply', 'ticket': 'TICKET', 'since': since.isoformat()}
    row = {'owner': OWNER, 'outcome': 'corrected'}
    args = argparse.Namespace(
        owner=OWNER,
        owners_file=None,
        since=since,
        rollback_receipt='packets/apply.jsonl',
        dry_run_receipt=None,
    )
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host')
    packet = SimpleNamespace(receipt=lambda _: [header, row, {'complete': True}])
    assert repair._inputs(args, ctx, packet, now) == ([OWNER], 'rollback', {OWNER: row})
    header['mode'] = 'dry_run'
    with pytest.raises(repair.InvalidReceipt):
        repair._inputs(args, ctx, packet, now)


def test_missing_commit_version_preserves_apply_action_for_reconciliation(monkeypatch):
    store = StrictFirestore({('users', OWNER): PROFILE})
    txn = store.transaction(max_attempts=1)
    txn.write_results = []
    monkeypatch.setattr(store, 'transaction', lambda **kwargs: txn)
    ctx = support_actions.ActionContext('TICKET', 'operator', 'fixture', 'host', True)
    operator = repair.PlanCorrection(store, SimpleNamespace(guard=lambda *args, **kwargs: None), SINCE, ctx)
    monkeypatch.setattr(operator, '_read', lambda ref, transaction=None, field_paths=None: ref.get(transaction))
    monkeypatch.setattr(repair, 'append_receipt', lambda *_: None)

    result = operator.process(OWNER, None, None, rollback=False)
    assert result['outcome'] == 'readback_failed'
    assert 'version' not in result
    assert store.rows[('support_actions', result['action'])]['outcome'] == 'succeeded'
