from dataclasses import replace
from datetime import timedelta

import pytest

from database import referral_campaign as ledger
from tests.unit.fixtures.referral_campaign import (
    NOW,
    POLICY,
    SETTINGS,
    golden_states,
    paid_payload,
    prepare,
    seed_user,
    settle,
    signed_event,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.referral_campaign import (
    GRANT_FIELD,
    CampaignPolicy,
    campaign_code,
    campaign_snapshot,
    decode_campaign_code,
    effective_subscription_payload,
)
from utils.referral_checkout import (
    CheckoutError,
    TrustedCheckoutAdapter,
    validate_checkout_receipt,
    verified_shopify_event,
)
from utils.referrals import ReferralCodeError, create_referral_code, referrer_uid_from_code


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    client = StrictFirestore()
    seed_user(client, 'owner')
    return client


def state(client):
    return ledger.read_campaign('owner', client=client, policy=POLICY)


def claim(client, **kwargs):
    return ledger.claim_months('owner', client=client, policy=POLICY, now=NOW + timedelta(seconds=3), **kwargs)


def test_actual_ledger_golden_states_and_five_month_total(store):
    results = golden_states(store)
    assert [(r['qualified_purchases'], r['claimed_months'], r['claimable_months']) for r in results.values()] == [
        (0, 0, 0),
        (2, 0, 2),
        (2, 2, 0),
        (5, 2, 3),
        (5, 5, 0),
    ]
    awards = [v for path, v in store.rows.items() if path[0] == 'referral_awards']
    assert sorted(a['months'] for a in awards) == [2, 3]
    for _ in range(3):
        assert claim(store)[0]['claimed_months'] == 5
    assert len([p for p in store.rows if p[0] == 'referral_awards']) == 2


def test_default_off_including_write_requests_never_instantiates_client(monkeypatch):
    monkeypatch.delenv('OMI_REFERRAL_CAMPAIGN_ENABLED', raising=False)
    monkeypatch.setattr(ledger, 'get_customer_firestore_client', lambda: pytest.fail('disabled path touched DB'))
    assert ledger.read_campaign('owner') == {}
    for action in (
        lambda: ledger.attribute('buyer', 'owner'),
        lambda: ledger.claim_months('owner'),
        lambda: ledger.settle_order({}),
        lambda: ledger.bind_checkout('buyer', {}),
    ):
        with pytest.raises(ledger.CampaignError, match='campaign_disabled'):
            action()
    assert TrustedCheckoutAdapter().ready is False


def test_versioned_token_environment_tampering_expiry_and_legacy_compatibility(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'local-test-signing-key-' * 3)
    code = campaign_code('owner', policy=POLICY)
    assert decode_campaign_code(code, policy=POLICY, now=NOW) == 'owner'
    for bad, policy in ((code + 'x', POLICY), (code, CampaignPolicy()), (create_referral_code('owner'), POLICY)):
        with pytest.raises(ReferralCodeError):
            decode_campaign_code(bad, policy=policy)
    expiring = replace(POLICY, expires_at=int(NOW.timestamp()))
    with pytest.raises(ReferralCodeError):
        decode_campaign_code(campaign_code('owner', policy=expiring), policy=expiring, now=NOW)
    assert referrer_uid_from_code(create_referral_code('owner')) == 'owner'


def test_distinct_orders_buyers_cap_and_repeated_transport_deliveries(store):
    for i in range(6):
        uid = f'buyer-{i}'
        prepare(store, uid)
        for _ in range(3):
            result = settle(store, uid, f'order-{i}')
            assert result['state'] == ('qualified' if i < 5 else 'cap_reached')
    assert len(state(store)['qualified_orders']) == 5
    assert settle(store, 'buyer-0', 'another-order')['state'] == 'duplicate_buyer'
    assert len(state(store)['qualified_orders']) == 5
    assert claim(store)[0]['claimed_months'] == 5


def test_no_15_minute_gate_old_accounts_allowed_but_pre_attribution_orders_rejected(store):
    receipt = prepare(store, 'old-account')
    assert receipt['uid'] == 'old-account'
    payload = paid_payload('old-account', 'old-order', now=NOW - timedelta(seconds=1))
    with pytest.raises(ledger.CampaignError, match='unqualified_order'):
        settle(store, 'old-account', 'old-order', payload=payload)
    assert not state(store)
    assert settle(store, 'old-account', 'new-order')['state'] == 'qualified'


def test_first_attribution_ownership_self_referral_deleted_owner(store):
    with pytest.raises(ledger.CampaignError, match='self_referral'):
        ledger.attribute('owner', 'owner', client=store, policy=POLICY, now=NOW)
    prepare(store, 'buyer')
    seed_user(store, 'other')
    for _ in range(3):
        ledger.attribute('buyer', 'owner', client=store, policy=POLICY, now=NOW + timedelta(days=2))
        with pytest.raises(ledger.CampaignError, match='attribution_conflict'):
            ledger.attribute('buyer', 'other', client=store, policy=POLICY, now=NOW)
    store.rows[('account_deletions', 'owner')] = {'wipe_status': 'pending_deletion'}
    with pytest.raises(ledger.CampaignError, match='account_unavailable'):
        settle(store, 'buyer', 'order')
    assert not state(store)


def test_refund_before_paid_is_permanent_business_tombstone(store):
    prepare(store, 'buyer')
    refund = {'id': 'refund-1', 'order_id': 'order', 'refund_line_items': [{'quantity': 1}]}
    for _ in range(3):
        assert settle(store, 'buyer', 'order', payload=refund, topic='refunds/create')['state'] == 'reversed'
        assert settle(store, 'buyer', 'order')['state'] == 'reversed'
    assert not state(store)
    assert claim(store)[0] == {}


def test_refund_reverses_progress_before_claim_without_clawing_commercial_subscription(store):
    for i in range(2):
        prepare(store, f'buyer-{i}')
        settle(store, f'buyer-{i}', f'order-{i}')
    assert campaign_snapshot(state(store), enabled=True, policy=POLICY)['claimable_months'] == 2
    refund = {'order_id': 'order-1', 'refund_line_items': [{'quantity': 1}]}
    for _ in range(3):
        settle(store, 'buyer-1', 'order-1', payload=refund, topic='refunds/create')
    assert len(state(store)['qualified_orders']) == 1
    assert claim(store)[0]['claimed_months'] == 0
    prepare(store, 'replacement')
    settle(store, 'replacement', 'replacement-order')
    assert claim(store)[0]['claimed_months'] == 2
    assert store.rows[('users', 'owner')]['subscription']['plan'] == 'basic'


def test_paid_subscription_claim_defers_then_grants_without_overwriting_stripe(store, monkeypatch):
    for i in range(2):
        prepare(store, f'buyer-{i}')
        settle(store, f'buyer-{i}', f'order-{i}')
    paid = {
        'plan': 'operator',
        'status': 'active',
        'current_price_id': 'existing-historical-price',
        'stripe_subscription_id': 'existing-sub',
        'current_period_end': int((NOW + timedelta(days=3)).timestamp()),
    }
    store.rows[('users', 'owner')]['subscription'] = paid.copy()
    for _ in range(3):
        result, reason = claim(store)
        assert reason == 'pending_paid_subscription'
        assert not result.get('claimed_months')
        assert GRANT_FIELD not in store.rows[('users', 'owner')]
    from utils import referral_billing
    from types import SimpleNamespace

    monkeypatch.setattr(
        referral_billing.stripe.Subscription,
        'retrieve',
        lambda *_: SimpleNamespace(
            to_dict=lambda: {'status': 'canceled', 'current_period_end': int((NOW + timedelta(days=3)).timestamp())}
        ),
    )
    result, reason = ledger.claim_months('owner', client=store, policy=POLICY, now=NOW + timedelta(days=4))
    assert reason is None and result['claimed_months'] == 2
    assert store.rows[('users', 'owner')]['subscription'] == paid
    grant = store.rows[('users', 'owner')][GRANT_FIELD]
    assert effective_subscription_payload(paid, grant, now=NOW)['current_price_id'] == paid['current_price_id']
    assert effective_subscription_payload(paid, grant, now=NOW + timedelta(days=4))['plan'] == 'unlimited_v2'
    assert effective_subscription_payload(paid, grant, now=NOW + timedelta(days=100)) == paid


def test_immutable_pinned_policy_and_expiry(store):
    prepare(store, 'buyer')
    changed = replace(POLICY, expires_at=int((NOW + timedelta(days=1)).timestamp()))
    with pytest.raises(ledger.CampaignError, match='policy_version_conflict'):
        ledger.attribute('buyer', 'owner', client=store, policy=changed, now=NOW)
    with pytest.raises(ledger.CampaignError, match='campaign_expired'):
        ledger.claim_months('owner', client=store, policy=changed, now=NOW + timedelta(days=1))


@pytest.mark.parametrize(
    'change',
    [
        {'test': False},
        {'financial_status': 'pending'},
        {'currency': 'EUR'},
        {'customer': {'id': 'forged-uid'}},
        {'checkout_token': 'unsigned-cart-attribute'},
        {'discount_codes': []},
    ],
)
def test_unsigned_or_unqualified_payment_claims_never_increment(store, change):
    prepare(store, 'buyer')
    payload = {**paid_payload('buyer', 'order'), **change}
    with pytest.raises((CheckoutError, ledger.CampaignError)):
        settle(store, 'buyer', 'order', payload=payload)
    assert not state(store)


def test_hmac_invalid_shop_and_raw_body_rejected(store):
    raw, headers = signed_event(paid_payload('buyer', 'order'))
    for body, hdr in ((raw + b' ', headers), (raw, {**headers, 'x-shopify-shop-domain': 'another.myshopify.com'})):
        with pytest.raises(CheckoutError, match='invalid_shopify_signature'):
            verified_shopify_event(body, hdr, SETTINGS, POLICY)


def test_trusted_customer_binding_cannot_move_to_second_uid(store):
    receipt = prepare(store, 'buyer')
    prepare(store, 'second')
    receipt = {
        **receipt,
        'uid': 'second',
        'checkout_token': 'different-token',
        'attribution_id': ledger.attribute('second', 'owner', client=store, policy=POLICY, now=NOW)['id'],
    }
    with pytest.raises(ledger.CampaignError, match='buyer_already_bound'):
        ledger.bind_checkout('second', receipt, client=store, policy=POLICY, now=NOW)
