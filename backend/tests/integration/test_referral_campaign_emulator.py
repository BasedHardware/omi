"""Run only against a loopback Firestore emulator; never application credentials.

FIRESTORE_EMULATOR_HOST=127.0.0.1:18085 PYTHONPATH=backend backend/.venv/bin/pytest -q <this file>
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlparse

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import referral_campaign as ledger
from tests.unit.fixtures.referral_campaign import NOW, POLICY, paid_payload, prepare, seed_user, settle
from utils.referral_campaign import GRANT_FIELD, campaign_snapshot, effective_subscription_payload


@pytest.fixture
def client(monkeypatch):
    if urlparse('//' + os.getenv('FIRESTORE_EMULATOR_HOST', '')).hostname not in ('127.0.0.1', 'localhost', '::1'):
        pytest.fail('loopback Firestore emulator required')
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    result = firestore.Client(project='demo-referral-' + uuid.uuid4().hex[:12], credentials=AnonymousCredentials())
    seed_user(result, 'owner')
    yield result
    result.close()


def state(client):
    return ledger.read_campaign('owner', client=client, policy=POLICY)


def claim(client):
    return ledger.claim_months('owner', client=client, policy=POLICY, now=NOW + timedelta(seconds=3))


def test_final_slot_race_duplicate_deliveries_and_parallel_claims(client):
    for i in range(4):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    for i in (4, 5):
        prepare(client, f'buyer-{i}')
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: settle(client, f'buyer-{i}', f'order-{i}'), [4, 5, 4, 5, 4, 5]))
    assert {r['state'] for r in results} == {'qualified', 'cap_reached'}
    assert len(state(client)['qualified_orders']) == 5
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: claim(client), range(6)))
    assert all(s['claimed_months'] == 5 and r is None for s, r in claims)
    stored = client.collection('users').document('owner').get().to_dict()
    assert stored['subscription'] == {'plan': 'basic', 'status': 'active'}
    assert (
        effective_subscription_payload(stored['subscription'], stored[GRANT_FIELD], now=NOW + timedelta(seconds=4))[
            'plan'
        ]
        == 'unlimited_v2'
    )
    awards = list(client.collection('referral_awards').stream())
    assert len(awards) == 1 and awards[0].to_dict()['months'] == 5


def test_competing_referrers_are_first_writer_only(client):
    seed_user(client, 'other-owner')
    seed_user(client, 'buyer')

    def attribute(owner):
        try:
            return ledger.attribute('buyer', owner, client=client, policy=POLICY, now=NOW)['referrer_uid']
        except ledger.CampaignError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attribute, ['owner', 'other-owner']))
    assert outcomes.count('attribution_conflict') == 1
    assert sum(x in ('owner', 'other-owner') for x in outcomes) == 1


def test_refund_paid_order_race_then_retry_never_resurrects(client):
    prepare(client, 'buyer')
    refund = {'order_id': 'order', 'refund_line_items': [{'quantity': 1}]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(settle, client, 'buyer', 'order'),
            pool.submit(settle, client, 'buyer', 'order', payload=refund, topic='refunds/create'),
        ]
        [f.result() for f in futures]
    for _ in range(3):
        assert settle(client, 'buyer', 'order')['state'] == 'reversed'
        assert settle(client, 'buyer', 'order', payload=refund, topic='refunds/create')['state'] == 'reversed'
    assert not state(client).get('qualified_orders')
    assert not claim(client)[0].get('claimed_months')
    assert GRANT_FIELD not in client.collection('users').document('owner').get().to_dict()


def test_claim_refund_race_is_serializable_and_never_double_grants(client):
    for i in range(2):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    refund = {'order_id': 'order-1', 'refund_line_items': [{'quantity': 1}]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(claim, client),
            pool.submit(settle, client, 'buyer-1', 'order-1', payload=refund, topic='refunds/create'),
        ]
        [f.result() for f in jobs]
    snapshot = campaign_snapshot(state(client), enabled=True, policy=POLICY)
    assert snapshot['qualified_purchases'] == 1
    assert snapshot['claimed_months'] in (0, 2)  # whichever transaction serialized first
    for _ in range(3):
        assert claim(client)[0].get('claimed_months', 0) == snapshot['claimed_months']
    assert len(list(client.collection('referral_awards').stream())) == (1 if snapshot['claimed_months'] else 0)


def test_paid_billing_write_racing_claim_is_preserved(client, monkeypatch):
    for i in range(2):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    paid = {
        'plan': 'operator',
        'status': 'active',
        'current_price_id': 'existing-price',
        'stripe_subscription_id': 'existing-sub',
        'current_period_start': int(NOW.timestamp()),
        'current_period_end': int((NOW + timedelta(days=90)).timestamp()),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:

        def race_claim():
            try:
                return claim(client)
            except ledger.CampaignError as error:
                assert str(error) == 'billing_state_changed'
                return None

        jobs = [
            pool.submit(race_claim),
            pool.submit(
                ledger.write_commercial_subscription,
                'owner',
                paid,
                client=client,
                policy=POLICY,
                now=NOW + timedelta(seconds=4),
            ),
        ]
        [f.result() for f in jobs]
    stored = client.collection('users').document('owner').get().to_dict()
    assert stored['subscription'] == paid
    assert effective_subscription_payload(paid, stored.get(GRANT_FIELD), now=NOW) == paid
    if stored.get(GRANT_FIELD):
        assert stored[GRANT_FIELD]['starts_at'] >= paid['current_period_end']
        assert stored[GRANT_FIELD]['ends_at'] > paid['current_period_end'] + 55 * 86400
    else:
        monkeypatch.setattr(ledger, 'billing_allows_claim', lambda *a: True)
        result, reason = ledger.claim_months('owner', client=client, policy=POLICY, now=NOW + timedelta(days=91))
        assert result['grant']['ends_at'] > int((NOW + timedelta(days=146)).timestamp())
        assert reason is None


def test_refund_before_claim_old_account_preorder_self_and_expiry(client):
    with pytest.raises(ledger.CampaignError, match='self_referral'):
        ledger.attribute('owner', 'owner', client=client, policy=POLICY, now=NOW)
    prepare(client, 'old-account')
    with pytest.raises(ledger.CampaignError, match='unqualified_order'):
        settle(
            client, 'old-account', 'before', payload=paid_payload('old-account', 'before', now=NOW - timedelta(days=1))
        )
    assert settle(client, 'old-account', 'after')['state'] == 'qualified'
    prepare(client, 'second')
    settle(client, 'second', 'second-order')
    refund = {'order_id': 'second-order', 'refund_line_items': [{'quantity': 1}]}
    settle(client, 'second', 'second-order', payload=refund, topic='refunds/create')
    assert claim(client)[0].get('claimed_months', 0) == 0
    prepare(client, 'replacement')
    settle(client, 'replacement', 'replacement-order')
    assert claim(client)[0]['claimed_months'] == 2
    stored = client.collection('users').document('owner').get().to_dict()
    assert (
        effective_subscription_payload(stored['subscription'], stored[GRANT_FIELD], now=NOW + timedelta(days=80))
        == stored['subscription']
    )


def test_consumed_refund_then_final_cap_contention_completes_second_milestone(client):
    for i in range(2):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    assert claim(client)[0]['claimed_months'] == 2
    refund = {'order_id': 'order-0', 'refund_line_items': [{'quantity': 1}]}
    settle(client, 'buyer-0', 'order-0', payload=refund, topic='refunds/create')
    for i in (2, 3):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    for i in (4, 5):
        prepare(client, f'buyer-{i}')
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda i: settle(client, f'buyer-{i}', f'order-{i}'), (4, 5)))
    assert {r['state'] for r in result} == {'qualified', 'cap_reached'}
    snapshot = campaign_snapshot(state(client), enabled=True, policy=POLICY)
    assert snapshot['qualified_purchases'] == 4
    assert snapshot['milestone_progress'] == snapshot['earned_months'] == 5
    assert snapshot['claimable_months'] == 3
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: claim(client), range(3)))
    assert all(s['claimed_months'] == 5 for s, _ in results)
    awards = list(client.collection('referral_awards').stream())
    assert sorted(a.to_dict()['months'] for a in awards) == [2, 3]


@pytest.mark.parametrize(
    'ranges,delivered,remaining_days',
    [
        (((0, 30), (30, 61)), 62, 61),
        (((0, 30), (20, 50)), 62, 50),
        (((0, 30), (30, 61)), 100, 61),
    ],
)
def test_canonical_writer_distinct_paid_delivery_orders_preserve_same_obligation(
    client, monkeypatch, ranges, delivered, remaining_days
):
    from database import users
    from datetime import datetime

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(days=delivered)

    monkeypatch.setattr(users, 'db', client)
    monkeypatch.setattr(ledger, 'current_policy', lambda: POLICY)
    monkeypatch.setattr(ledger, 'datetime', Clock)
    outcomes = []
    for owner, ordering in [('owner-ab', (0, 1)), ('owner-ba', (1, 0))]:
        seed_user(client, owner)
        for i in range(2):
            buyer = owner + f'-buyer-{i}'
            prepare(client, buyer, owner=owner)
            settle(client, buyer, owner + f'-order-{i}')
        first, _ = ledger.claim_months(owner, client=client, policy=POLICY, now=NOW)
        assert first['grant']['budget_seconds'] == 61 * 86400
        for index in ordering:
            start, end = ranges[index]
            paid = {
                'plan': 'operator',
                'status': 'active',
                'stripe_subscription_id': 'sub_' + owner,
                'current_period_start': int((NOW + timedelta(days=start)).timestamp()),
                'current_period_end': int((NOW + timedelta(days=end)).timestamp()),
            }
            users.update_user_subscription(owner, paid)
            snapshot = client.collection('users').document(owner).get().to_dict()[GRANT_FIELD]
            for _ in range(3):
                users.update_user_subscription(owner, paid)
            stored = client.collection('users').document(owner).get().to_dict()
            assert stored['subscription'] == paid
            assert stored[GRANT_FIELD] == snapshot
        grant = stored[GRANT_FIELD]
        assert grant == ledger.read_campaign(owner, client=client, policy=POLICY)['grant']
        assert grant['ends_at'] == int((NOW + timedelta(days=delivered + remaining_days)).timestamp())
        assert grant['ends_at'] - grant['starts_at'] == remaining_days * 86400
        assert (
            effective_subscription_payload(
                stored['subscription'], grant, now=NOW + timedelta(days=delivered, seconds=1)
            )['plan']
            == 'unlimited_v2'
        )
        outcomes.append(grant)
    assert outcomes[0] == outcomes[1]
