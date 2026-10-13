"""Fixture-only drift classification and a CLI with no repair authority."""

import json
from pathlib import Path
from datetime import datetime, timezone
import stripe
from google.cloud import firestore

from scripts import billing_reconcile as reconciliation_cli
from utils.observability import billing_reconciliation as reconciliation_metrics

import pytest

from utils.billing_reconciliation import reconcile, DRIFT_CATEGORIES
from utils.referrals import referral_claim_patch


def sub(status='active', price='price-plus', sub_id='sub-one', uid='u-one'):
    return {
        'id': sub_id,
        'status': status,
        'customer': 'cus-one',
        'metadata': {'uid': uid},
        'items': {'data': [{'price': {'id': price, 'currency': 'jpy', 'unit_amount': 4800}}]},
        'current_period_start': 10,
        'current_period_end': 200,
    }


def user(plan='plus', price='price-plus', sub_id='sub-one', end=200):
    return {
        'uid': 'u-one',
        'stripe_customer_id': 'cus-one',
        'subscription': {
            'plan': plan,
            'status': 'active',
            'stripe_subscription_id': sub_id,
            'current_price_id': price,
            'current_period_start': 10,
            'current_period_end': end,
        },
    }


def compare(subs, users):
    return reconcile(subs, users, {'price-plus': 'plus', 'price-operator': 'operator'}, as_of=100)


def test_matching_jpy_legacy_snapshot_has_no_drift_and_inputs_are_unchanged():
    subs, users = [sub()], [user()]
    before = json.dumps([subs, users], sort_keys=True)
    report = compare(subs, users)
    assert report.counts == dict.fromkeys(DRIFT_CATEGORIES, 0)
    assert report.compared_users == 1
    assert json.dumps([subs, users], sort_keys=True) == before


@pytest.mark.parametrize(
    'status,category',
    [('active', 'paid_in_stripe_basic_in_firestore'), ('trialing', 'trial_in_stripe_basic_in_firestore')],
)
def test_paid_and_trial_drift_are_separate(status, category):
    report = compare([sub(status)], [user('basic')])
    assert report.counts[category] == 1
    other = 'trial_in_stripe_basic_in_firestore' if status == 'active' else 'paid_in_stripe_basic_in_firestore'
    assert report.counts[other] == 0


@pytest.mark.parametrize('status', ['past_due', 'unpaid', 'canceled', 'incomplete', 'incomplete_expired', 'paused'])
def test_reverse_drift_all_non_entitled_statuses(status):
    assert compare([sub(status)], [user()]).counts['paid_in_firestore_no_stripe_entitlement'] == 1


def test_wrong_price_plan_and_stale_period_are_distinct():
    report = compare([sub(price='price-operator')], [user(end=150)])
    assert {key for key, value in report.counts.items() if value} == {'wrong_price', 'wrong_plan', 'stale_period'}


def test_absent_historical_price_is_missing_not_wrong():
    report = compare([sub()], [user(price=None)])
    assert report.counts['missing_price_identity'] == 1
    assert report.counts['wrong_price'] == 0


def test_multiple_subscriptions_are_not_arbitrarily_selected():
    report = compare([sub(), sub(price='price-operator', sub_id='sub-two')], [user(sub_id='sub-unrelated')])
    assert report.counts['multiple_entitled_subscriptions'] == 1
    assert report.counts['wrong_plan'] == 0
    assert report.counts['wrong_price'] == 0
    assert report.counts['subscription_id_mismatch'] == 0


def test_known_stored_id_is_compared_among_multiple_subscriptions():
    report = compare([sub(), sub(price='price-operator', sub_id='sub-two')], [user()])
    assert report.counts['multiple_entitled_subscriptions'] == 1
    assert report.counts['wrong_plan'] == 0


def test_unknown_price_owner_and_creator_app_are_visible_or_excluded():
    unknown = sub(price='unknown')
    unmapped = sub(uid='missing')
    app = sub()
    app['metadata']['app_id'] = 'creator-app'
    report = compare([unknown, unmapped, app], [user()])
    assert report.counts['unknown_price'] == 1
    assert report.counts['unmapped_owner'] == 1
    assert report.counts['multiple_entitled_subscriptions'] == 0
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0


def test_missing_metadata_matches_customer_only_if_unambiguous():
    payload = sub()
    payload['metadata'] = {}
    assert compare([payload], [user()]).counts['unmapped_owner'] == 0
    other = user()
    other['uid'] = 'u-two'
    report = compare([payload], [user(), other])
    assert report.counts['unmapped_owner'] == 1
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0


def cli_module():
    return reconciliation_cli


def test_cli_fixture_mode_never_reads_live_or_credentials(tmp_path, monkeypatch, capsys):
    cli = cli_module()

    def forbidden(*args):
        raise AssertionError('fixture mode attempted live access')

    monkeypatch.setattr(cli, 'read_live', forbidden)
    for name, content in [
        ('stripe', {'complete': True, 'subscriptions': [sub()]}),
        ('users', {'complete': True, 'users': [user()]}),
        ('prices', {'price-plus': 'plus'}),
    ]:
        (tmp_path / f'{name}.json').write_text(json.dumps(content))
    assert (
        cli.main(
            [
                '--stripe-snapshot',
                str(tmp_path / 'stripe.json'),
                '--users-snapshot',
                str(tmp_path / 'users.json'),
                '--price-map',
                str(tmp_path / 'prices.json'),
                '--as-of',
                '100',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)['mode'] == 'read_only'


def test_incomplete_snapshot_fails_instead_of_claiming_reverse_drift(tmp_path):
    cli = cli_module()
    path = tmp_path / 'partial.json'
    path.write_text(json.dumps({'subscriptions': []}))
    with pytest.raises(ValueError, match='complete=true'):
        cli.load_snapshot(path, 'subscriptions')


def test_cli_has_no_write_or_repair_mode():
    cli = cli_module()
    with pytest.raises(SystemExit):
        cli.main(['--repair', '--as-of', '100'])


def test_operator_reader_only_paginates_stripe_and_projects_firestore(monkeypatch):
    cli = cli_module()
    monkeypatch.setenv('STRIPE_RECONCILE_READ_ONLY_KEY', 'rk_test_fixture_not_real')
    calls = []

    class StripePage:
        def auto_paging_iter(self):
            calls.append('paginate')
            return iter([stripe.Subscription.construct_from(sub(), 'fixture')])

    def listing(**kwargs):
        assert kwargs == {'status': 'all', 'limit': 100, 'api_key': 'rk_test_fixture_not_real'}
        return StripePage()

    class Projection:
        def select(self, fields):
            assert fields == ['subscription', 'stripe_customer_id', 'referral']
            calls.append('project')
            return self

        def stream(self):
            from types import SimpleNamespace

            return iter([SimpleNamespace(id='u-one', to_dict=referral_fixture)])

    class Client:
        def __init__(self, *, project):
            assert project == 'fixture-project'

        def collection(self, name):
            assert name == 'users'
            return Projection()

        def close(self):
            calls.append('close')

    monkeypatch.setattr(stripe.Subscription, 'list', listing)
    monkeypatch.setattr(firestore, 'Client', Client)
    subscriptions, users = cli.read_live('fixture-project')
    assert len(subscriptions) == len(users) == 1
    assert calls == ['paginate', 'project', 'close']
    report = compare([], users)
    assert report.counts['referral_trial_entitlement'] == 1
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0


def test_drift_metric_labels_are_closed_and_preinitialized():
    metrics = reconciliation_metrics
    metric = metrics.DRIFT
    children = {category: metric.labels(category=category)._value.get() for category in DRIFT_CATEGORIES}
    report = compare([sub()], [user('basic')])
    metrics.record_report(report)
    for category in DRIFT_CATEGORIES:
        assert metric.labels(category=category)._value.get() == children[category] + report.counts[category]


def test_organization_payment_intent_grant_is_not_false_reverse_drift():
    stored = user('unlimited')
    stored['subscription'].pop('stripe_subscription_id')
    stored['subscription']['subscription_id'] = 'pi_fixture_company_payment'
    report = compare([], [stored])
    assert report.counts['manual_payment_entitlement'] == 1
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0


def referral_fixture():
    patch, reason = referral_claim_patch(
        referred_uid='u-one',
        referrer_uid='u-referrer',
        is_new_user=True,
        user_data={},
        now=datetime.fromtimestamp(10, timezone.utc),
    )
    assert reason == 'granted'
    return dict(patch, uid='u-one')


def test_claimed_referral_is_not_reverse_drift():
    report = compare([], [referral_fixture()])
    assert report.counts['referral_trial_entitlement'] == 1
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0


@pytest.mark.parametrize('start', [None, 11])
def test_legacy_missing_start_is_not_stale_but_present_mismatch_is(start):
    stored = user()
    stored['subscription']['current_period_start'] = start
    assert compare([sub()], [stored]).counts['stale_period'] == (start is not None)


@pytest.mark.parametrize('end', [None, 99, 201])
def test_stripe_end_missing_expired_or_mismatched_is_stale(end):
    payload = sub()
    payload['current_period_end'] = end
    assert compare([payload], [user()]).counts['stale_period'] == 1


def test_future_paid_entitlement_does_not_require_active_status():
    stored = user()
    stored['subscription']['status'] = 'inactive'
    assert compare([], [stored]).counts['paid_in_firestore_no_stripe_entitlement'] == 1


def test_metrics_export_contains_only_billing_counters():
    payload = reconciliation_metrics.export_metrics().decode()
    assert 'omi_billing_reconciliation_drift_total' in payload
    assert 'omi_billing_reconciliation_runs_total' in payload
    assert 'python_info' not in payload
    assert 'process_' not in payload


def test_partial_price_map_extends_catalog(tmp_path, monkeypatch, capsys):
    catalog_price = next(iter(reconciliation_cli.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES))
    for name, content in [
        ('stripe', {'complete': True, 'subscriptions': [sub(price=catalog_price)]}),
        ('users', {'complete': True, 'users': [user()]}),
        ('prices', {'price-retained': 'operator'}),
    ]:
        (tmp_path / f'{name}.json').write_text(json.dumps(content))
    assert (
        reconciliation_cli.main(
            [
                '--stripe-snapshot',
                str(tmp_path / 'stripe.json'),
                '--users-snapshot',
                str(tmp_path / 'users.json'),
                '--price-map',
                str(tmp_path / 'prices.json'),
                '--as-of',
                '100',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)['counts']['unknown_price'] == 0
