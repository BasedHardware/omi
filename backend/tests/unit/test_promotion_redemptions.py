"""The per-promotion redemption claim retains optional verified order provenance."""

from datetime import timezone

from google.api_core.exceptions import AlreadyExists

from database import promotion_redemptions as redemptions


class _Document:
    def __init__(self, rows, key):
        self.rows = rows
        self.key = key

    def create(self, value):
        if self.key in self.rows:
            raise AlreadyExists('synthetic duplicate claim')
        self.rows[self.key] = value


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def document(self, key):
        return _Document(self.rows, key)


class _Firestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        assert name == redemptions.COLLECTION
        return _Collection(self.rows)


def _claim(client, **extra):
    return redemptions.claim(
        'promo_fixture',
        uid='uid_fixture',
        subscription_id='sub_fixture',
        coupon_id='coupon_fixture',
        firestore_client=client,
        **extra,
    )


def test_claim_persists_allowlisted_order_provenance():
    client = _Firestore()
    attribution = {
        'attribution_schema': '1',
        'attribution_source': 'shopify_bundle_code',
        'shopify_shop': 'fixture-shop.myshopify.com',
        'shopify_order_id': '12345',
        'bundle_order_line_item_id': '67890',
        'bundle_redemption_role': 'gift',
        'bundle_promotion_code_id': 'promo_fixture',
    }
    assert _claim(client, attribution=attribution) is True
    stored = client.rows['promo_fixture']
    assert stored == {
        'uid': 'uid_fixture',
        'subscription_id': 'sub_fixture',
        'coupon_id': 'coupon_fixture',
        'redeemed_at': stored['redeemed_at'],
        **attribution,
    }
    assert stored['redeemed_at'].tzinfo == timezone.utc


def test_missing_attribution_remains_optional_and_claim_is_create_once():
    client = _Firestore()
    assert _claim(client) is True
    stored = client.rows['promo_fixture']
    assert set(stored) == {'uid', 'subscription_id', 'coupon_id', 'redeemed_at'}
    assert _claim(client, attribution={'shopify_order_id': 'different'}) is False
    assert client.rows['promo_fixture'] == stored
