"""Owned local fixtures. No network, live code, order or subscription is created."""

import json
from datetime import datetime, timedelta, timezone

from database import referral_campaign as ledger
from utils.referral_campaign import CampaignPolicy, campaign_snapshot
from utils.referral_checkout import CheckoutSettings, signature, validate_checkout_receipt, verified_shopify_event

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
POLICY = CampaignPolicy(environment='local')
VARIANT = '53310207000868'  # existing Omi Silver variant, not a newly invented SKU
SETTINGS = CheckoutSettings(
    endpoint='https://fixture.invalid/checkout',
    bridge_secret='local-fixture-only-' * 3,
    webhook_secret='local-shopify-fixture-only-' * 3,
    shop='88f4ed-c3.myshopify.com',
    discount_code='LOCAL_FIXTURE_NOT_A_LIVE_CODE',
    variant_ids=(VARIANT,),
    discount_reviewed=True,
)


class LocalCheckoutAdapter:
    settings = SETTINGS
    ready = True

    def create(self, attribution, policy):
        uid = attribution['uid']
        result = {
            'attribution_id': attribution['id'],
            'uid': uid,
            'environment': policy.environment,
            'shop': SETTINGS.shop,
            'variant_id': VARIANT,
            'discount_code': SETTINGS.discount_code,
            'discount_percent': 10,
            'customer_id': 'local-customer-' + uid,
            'checkout_token': 'local-checkout-' + uid,
            'checkout_url': 'https://www.omi.me/checkouts/local-fixture-' + uid,
            'hardware_only': True,
            'combination_verified': True,
        }
        return validate_checkout_receipt(result, attribution, SETTINGS, policy)


def seed_user(client, uid):
    ref = client.collection('users').document(uid)
    # strict fixture supports seeding through a transaction as well as emulator.
    tx = client.transaction()
    tx.set(ref, {'name': uid, 'created_at': '2020-01-01', 'subscription': {'plan': 'basic', 'status': 'active'}})
    if hasattr(tx, 'commit'):
        tx.commit()


def prepare(client, uid, owner='owner', *, now=NOW):
    seed_user(client, uid)
    attribution = ledger.attribute(uid, owner, client=client, policy=POLICY, now=now)
    receipt = LocalCheckoutAdapter().create(attribution, POLICY)
    ledger.bind_checkout(uid, receipt, client=client, policy=POLICY, now=now)
    return receipt


def paid_payload(uid, order, *, now=NOW + timedelta(seconds=1)):
    return {
        'id': order,
        'test': True,
        'financial_status': 'paid',
        'cancelled_at': None,
        'refunds': [],
        'currency': 'USD',
        'total_price': '90.00',
        'created_at': now.isoformat(),
        'updated_at': now.isoformat(),
        'checkout_token': 'local-checkout-' + uid,
        'customer': {'id': 'local-customer-' + uid},
        'line_items': [
            {
                'variant_id': int(VARIANT),
                'quantity': 1,
                'price': '100.00',
                'discount_allocations': [{'discount_application_index': 0, 'amount': '10.00'}],
            }
        ],
        'discount_codes': [{'code': SETTINGS.discount_code, 'type': 'percentage', 'amount': '10.00'}],
        'discount_applications': [{'code': SETTINGS.discount_code, 'value_type': 'percentage', 'value': '10.0'}],
    }


def signed_event(payload, topic='orders/paid'):
    raw = json.dumps(payload, sort_keys=True).encode()
    headers = {
        'x-shopify-shop-domain': SETTINGS.shop,
        'x-shopify-topic': topic,
        'x-shopify-hmac-sha256': signature(raw, SETTINGS.webhook_secret),
    }
    return raw, headers


def settle(client, uid, order, *, payload=None, topic='orders/paid', now=NOW + timedelta(seconds=2)):
    raw, headers = signed_event(payload or paid_payload(uid, order), topic)
    evidence = verified_shopify_event(raw, headers, SETTINGS, POLICY)
    return ledger.settle_order(evidence, client=client, policy=POLICY, now=now)


def golden_states(client):
    seed_user(client, 'owner')
    result = {}

    def snapshot(name):
        state = ledger.read_campaign('owner', client=client, policy=POLICY)
        result[name] = campaign_snapshot(
            state,
            enabled=True,
            policy=POLICY,
            now=NOW,
            referral_url='https://omi.me/r/LOCAL_FIXTURE_LINK_NOT_FOR_SHARING',
        )

    snapshot('0-of-2')
    for i in range(5):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
        if i == 1:
            snapshot('2-of-2-claimable')
            ledger.claim_months('owner', client=client, policy=POLICY, now=NOW + timedelta(seconds=3))
            snapshot('2-of-5-first-claimed')
    snapshot('5-of-5-claimable')
    ledger.claim_months('owner', client=client, policy=POLICY, now=NOW + timedelta(seconds=4))
    snapshot('5-of-5-all-claimed')
    return result
