"""Regressions for money-code-review1: real production transitions and SDK boundaries."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from database import referral_campaign as ledger, users
from models.users import PlanType, Subscription
from routers import referrals
from tests.unit.fixtures.referral_campaign import (
    NOW,
    POLICY,
    SETTINGS,
    paid_payload,
    prepare,
    seed_user,
    settle,
    signed_event,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import referral_billing, subscription as commercial
from utils.other import endpoints as auth
from utils.referral_campaign import GRANT_FIELD, campaign_snapshot, effective_subscription_payload
from utils.referral_checkout import CheckoutError, verified_shopify_event


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    client = StrictFirestore()
    seed_user(client, 'owner')
    return client


def state(client):
    return ledger.read_campaign('owner', client=client, policy=POLICY)


def pay(client, buyer):
    prepare(client, buyer)
    return settle(client, buyer, 'order-' + buyer)


def claim(client, now=NOW + timedelta(seconds=3)):
    return ledger.claim_months('owner', client=client, policy=POLICY, now=now)


def refund_order(client, order):
    return settle(
        client, '', order, topic='refunds/create', payload={'order_id': order, 'refund_line_items': [{'quantity': 1}]}
    )


@pytest.mark.parametrize('initial_count', [2, 3, 4])
@pytest.mark.parametrize('refund_consumed', [True, False])
def test_claim_consumes_exact_slots_and_refund_cannot_strand_second_milestone(store, initial_count, refund_consumed):
    if initial_count == 2 and not refund_consumed:
        pytest.skip('two-purchase first claim has no unconsumed slot')
    for i in range(initial_count):
        pay(store, f'initial-{i}')
    assert claim(store)[0]['claimed_months'] == 2
    initial = state(store)
    assert len(initial['claimed_slots']) == 2
    candidates = (
        set(initial['claimed_slots'])
        if refund_consumed
        else set(initial['qualified_orders']) - set(initial['claimed_slots'])
    )
    order_key = initial['qualified_orders'][sorted(candidates)[0]]
    order = store.rows[('referral_orders', order_key)]['order_id']
    for _ in range(3):
        refund_order(store, order)
    assert len(state(store)['qualified_orders']) == initial_count - 1
    for i in range(5):
        if len(set(state(store)['claimed_slots']) | set(state(store)['qualified_orders'])) == 5:
            break
        assert pay(store, f'next-{i}')['state'] == 'qualified'
    snap = campaign_snapshot(state(store), enabled=True, policy=POLICY)
    assert snap['milestone_progress'] == 5 and snap['earned_months'] == 5
    assert snap['qualified_purchases'] == (4 if refund_consumed else 5)
    assert snap['claimed_months'] == 2 and snap['claimable_months'] == 3
    for _ in range(3):
        assert claim(store)[0]['claimed_months'] == 5
    assert len(state(store)['claimed_slots']) == 5
    assert pay(store, 'sixth')['state'] == 'cap_reached'
    awards = [data for path, data in store.rows.items() if path[0] == 'referral_awards']
    assert sorted(a['months'] for a in awards) == [2, 3]


def paid_period(start=NOW, days=90):
    return {
        'plan': 'operator',
        'status': 'active',
        'stripe_subscription_id': 'sub_known',
        'current_period_start': int(start.timestamp()),
        'current_period_end': int((start + timedelta(days=days)).timestamp()),
        'current_price_id': 'existing-price',
    }


def test_authoritative_delayed_renewal_blocks_claim_before_ledger_consumption(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')
    old = paid_period(NOW - timedelta(days=60), 30)
    store.rows[('users', 'owner')]['subscription'] = old
    observed = Mock(return_value=SimpleNamespace(to_dict=lambda: paid_period()))
    monkeypatch.setattr(referral_billing.stripe.Subscription, 'retrieve', observed)
    for _ in range(3):
        result, reason = claim(store)
        assert reason == 'pending_paid_subscription' and result.get('claimed_months', 0) == 0
    assert observed.call_count == 3
    assert GRANT_FIELD not in store.rows[('users', 'owner')]
    assert not [p for p in store.rows if p[0] == 'referral_awards']


def test_billing_outage_fails_closed_without_consuming_reward(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')
    store.rows[('users', 'owner')]['subscription'] = paid_period(NOW - timedelta(days=60), 30)
    monkeypatch.setattr(
        referral_billing.stripe.Subscription, 'retrieve', Mock(side_effect=RuntimeError('provider unavailable'))
    )
    before = dict(state(store))
    for _ in range(3):
        with pytest.raises(ledger.CampaignError, match='billing_authority_unavailable'):
            claim(store)
    assert state(store) == before and GRANT_FIELD not in store.rows[('users', 'owner')]


def test_claim_before_renewal_requeues_whole_reward_past_paid_period_and_dedupes(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')
    claimed, _ = claim(store)
    original = claimed['grant'].copy()
    duration = original['ends_at'] - original['starts_at']
    paid = paid_period(NOW, 90)  # covers the ENTIRE two-month promotional interval
    for _ in range(3):
        ledger.write_commercial_subscription('owner', paid, client=store, policy=POLICY, now=NOW + timedelta(seconds=4))
    stored = store.rows[('users', 'owner')]
    grant = stored[GRANT_FIELD]
    assert stored['subscription'] == paid
    assert grant['starts_at'] == paid['current_period_end']
    assert grant['ends_at'] - grant['starts_at'] == duration
    assert grant == state(store)['grant']
    assert effective_subscription_payload(paid, grant, now=NOW + timedelta(days=89)) == paid
    after = NOW + timedelta(days=91)
    assert effective_subscription_payload(paid, grant, now=after)['plan'] == 'unlimited_v2'
    monkeypatch.setattr(
        referral_billing.stripe.Subscription,
        'retrieve',
        lambda *_: SimpleNamespace(to_dict=lambda: {**paid, 'status': 'canceled'}),
    )
    for _ in range(3):
        assert claim(store, now=after)[0]['grant'] == grant
    assert len([p for p in store.rows if p[0] == 'referral_awards']) == 1


def test_renewal_before_claim_defers_then_full_months_start_after_paid_period(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')
    paid = paid_period(NOW, 90)
    ledger.write_commercial_subscription('owner', paid, client=store, policy=POLICY, now=NOW)
    assert claim(store)[1] == 'pending_paid_subscription'
    assert GRANT_FIELD not in store.rows[('users', 'owner')]
    after = NOW + timedelta(days=91)
    monkeypatch.setattr(
        referral_billing.stripe.Subscription,
        'retrieve',
        lambda *_: SimpleNamespace(to_dict=lambda: {**paid, 'status': 'canceled'}),
    )
    granted, _ = claim(store, now=after)
    assert granted['claimed_months'] == 2 and granted['grant']['starts_at'] == int(after.timestamp())
    assert granted['grant']['ends_at'] > int((after + timedelta(days=55)).timestamp())


def test_renewal_delivered_after_original_grant_expired_restores_paid_overlap(store):
    for i in range(2):
        pay(store, f'buyer-{i}')
    granted, _ = claim(store)
    duration = granted['grant']['ends_at'] - granted['grant']['starts_at']
    paid = paid_period(NOW, 90)
    delivered = NOW + timedelta(days=100)
    ledger.write_commercial_subscription('owner', paid, client=store, policy=POLICY, now=delivered)
    grant = state(store)['grant']
    assert grant['starts_at'] == int(delivered.timestamp())
    assert grant['ends_at'] - grant['starts_at'] == duration
    assert effective_subscription_payload(paid, grant, now=delivered + timedelta(seconds=1))['plan'] == 'unlimited_v2'


def test_commercial_checkout_uses_raw_period_valid_authority_not_promo(store, monkeypatch):
    basic = Subscription(plan=PlanType.basic, status='active')
    promo = Subscription(
        plan=PlanType.unlimited_v2,
        status='active',
        cancel_at_period_end=True,
        current_period_end=int((NOW + timedelta(days=60)).timestamp()),
    )
    calls = []

    def valid(uid, **kwargs):
        calls.append(kwargs)
        return basic if kwargs.get('include_promotions') is False else promo

    monkeypatch.setattr(users, 'get_user_valid_subscription', valid)
    monkeypatch.setattr(commercial, '_has_active_stripe_subscription', lambda *_: False)
    monkeypatch.setattr(commercial, 'find_active_paid_subscription_for_user', lambda *_: None)
    assert commercial.can_user_make_payment('owner', 'target-price')[0] is True
    assert calls[-1] == {'provision': False, 'include_promotions': False}
    monkeypatch.setattr(commercial, '_has_active_stripe_subscription', lambda *_: True)
    assert commercial.can_user_make_payment('owner', 'target-price')[0] is False
    monkeypatch.setattr(commercial, '_has_active_stripe_subscription', lambda *_: False)
    monkeypatch.setattr(commercial, 'find_active_paid_subscription_for_user', lambda *_: promo)
    assert commercial.can_user_make_payment('owner', 'target-price')[0] is False


def verify(payload):
    raw, headers = signed_event(payload)
    return verified_shopify_event(raw, headers, SETTINGS, POLICY)


def test_free_hardware_with_positive_shipping_or_accessory_never_qualifies():
    for positive_total in ('10.00', '50.00'):
        payload = paid_payload('buyer', 'order')
        payload['total_price'] = positive_total
        payload['discount_applications'].append({'type': 'automatic', 'value_type': 'fixed_amount', 'value': '90.00'})
        payload['line_items'][0]['discount_allocations'].append({'discount_application_index': 1, 'amount': '90.00'})
        with pytest.raises(CheckoutError, match='unqualified_order'):
            verify(payload)


def test_stacked_positive_net_hardware_and_quantity_rounding():
    payload = paid_payload('buyer', 'order')
    payload['line_items'][0]['quantity'] = 2
    payload['total_price'] = '120.00'
    payload['discount_codes'][0]['amount'] = '20.00'
    payload['line_items'][0]['discount_allocations'][0]['amount'] = '20.00'
    payload['discount_applications'].append({'type': 'automatic'})
    payload['line_items'][0]['discount_allocations'].append({'discount_application_index': 1, 'amount': '60.00'})
    payload['line_items'][0]['total_discount'] = '80.00'
    assert verify(payload)['net_hardware_minor'] == 12000


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-Infinity', '-1.00', '0.001', 'nonsense'])
def test_nonfinite_negative_or_fractional_money_is_rejected(bad):
    for field in ('price', 'allocation', 'total'):
        payload = paid_payload('buyer', 'order')
        if field == 'price':
            payload['line_items'][0]['price'] = bad
        elif field == 'allocation':
            payload['line_items'][0]['discount_allocations'][0]['amount'] = bad
        else:
            payload['total_price'] = bad
        with pytest.raises(CheckoutError):
            verify(payload)


@pytest.mark.parametrize('case', ['missing', 'amount', 'index', 'total', 'currency', 'quantity'])
def test_missing_or_mismatched_hardware_allocation_is_rejected(case):
    payload = paid_payload('buyer', 'order')
    line = payload['line_items'][0]
    if case == 'missing':
        line.pop('discount_allocations')
    elif case == 'amount':
        line['discount_allocations'][0]['amount'] = '9.99'
    elif case == 'index':
        line['discount_allocations'][0]['discount_application_index'] = 7
    elif case == 'total':
        line['total_discount'] = '5.00'
    elif case == 'currency':
        line['price_set'] = {'shop_money': {'amount': '100.00', 'currency_code': 'EUR'}}
    else:
        line['quantity'] = 1.5
    with pytest.raises(CheckoutError):
        verify(payload)


def test_disabled_actual_auth_with_native_headers_has_no_platform_device_or_recovery_writes(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'false')
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'false')
    verified = Mock(return_value={'uid': 'verified-owner'})
    monkeypatch.setattr(auth.auth, 'verify_id_token', verified)
    monkeypatch.setattr(auth, 'get_user_deletion_wipe_status', lambda *_: None)
    monkeypatch.setattr(auth, 'cutover_enforcement_enabled', lambda: True)
    cutover = Mock()
    byok = Mock()
    monkeypatch.setattr(auth, 'enforce_account_cutover_http_access', cutover)
    monkeypatch.setattr(auth, 'validate_byok_request', byok)
    # Both throttles would permit writes. The real readonly dependency must
    # avoid invoking telemetry entirely, rather than relying on those throttles.
    monkeypatch.setattr(users, 'try_acquire_user_platform_write_lock', lambda *a: True)
    monkeypatch.setattr(users, 'try_acquire_client_device_write_lock', lambda *a: True)
    platform, device, recovery = Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, 'record_user_platform', platform)
    monkeypatch.setattr(auth, 'record_client_device', device)
    monkeypatch.setattr(auth, '_recover_locked_content_if_request', recovery)
    monkeypatch.setattr(ledger, '_client', lambda *_: pytest.fail('disabled request touched campaign DB'))
    app = FastAPI()
    app.include_router(referrals.router)
    headers = {
        'Authorization': 'Bearer fixture.firebase.jwt',
        'X-App-Platform': 'ios',
        'X-Device-Id-Hash': 'd' * 64,
        'X-App-Version': '1.0.1',
    }
    with TestClient(app) as client:
        for method, path, body in [
            ('GET', '', None),
            ('POST', '/claim', {}),
            ('POST', '/attribution', {'code': 'ref2.invalid.signature'}),
        ]:
            response = client.request(method, '/v2/users/me/referral/campaign' + path, headers=headers, json=body)
            assert response.status_code == (503 if path == '/attribution' else 200)
    assert verified.call_count == cutover.call_count == byok.call_count == 3
    platform.assert_not_called()
    device.assert_not_called()
    recovery.assert_not_called()


@pytest.mark.parametrize('fence', ['deletion', 'cutover', 'byok'])
def test_readonly_dependency_still_enforces_security_fences(monkeypatch, fence):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'false')
    monkeypatch.setattr(auth.auth, 'verify_id_token', lambda *_: {'uid': 'owner'})
    monkeypatch.setattr(
        auth, 'get_user_deletion_wipe_status', lambda *_: 'pending_deletion' if fence == 'deletion' else None
    )
    monkeypatch.setattr(auth, 'cutover_enforcement_enabled', lambda: True)

    def cutover(*a, **k):
        if fence == 'cutover':
            raise HTTPException(403, detail='cutover')

    def byok(*a):
        if fence == 'byok':
            raise HTTPException(403, detail='byok')

    monkeypatch.setattr(auth, 'enforce_account_cutover_http_access', cutover)
    monkeypatch.setattr(auth, 'validate_byok_request', byok)
    app = FastAPI()
    app.include_router(referrals.router)
    with TestClient(app) as client:
        assert (
            client.get('/v2/users/me/referral/campaign', headers={'Authorization': 'Bearer fixture.jwt'}).status_code
            == 403
        )


def test_canonical_billing_writer_atomically_requeues_grant_and_ledger(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')
    claim(store)
    monkeypatch.setattr(users, 'db', store)
    monkeypatch.setattr(ledger, 'current_policy', lambda: POLICY)
    paid = paid_period()
    users.update_user_subscription('owner', paid)
    stored = store.rows[('users', 'owner')]
    assert stored['subscription'] == paid
    assert stored[GRANT_FIELD] == state(store)['grant']
    assert stored[GRANT_FIELD]['starts_at'] >= paid['current_period_end']


def test_billing_change_between_provider_check_and_transaction_refuses_claim(store, monkeypatch):
    for i in range(2):
        pay(store, f'buyer-{i}')

    def concurrent_billing(*_):
        ledger.write_commercial_subscription('owner', paid_period(), client=store, policy=POLICY, now=NOW)
        return True

    monkeypatch.setattr(ledger, 'billing_allows_claim', concurrent_billing)
    with pytest.raises(ledger.CampaignError, match='billing_state_changed'):
        claim(store)
    assert state(store).get('claimed_months', 0) == 0
    assert GRANT_FIELD not in store.rows[('users', 'owner')]
