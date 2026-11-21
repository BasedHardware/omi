"""Fail-closed trusted checkout bridge and Shopify raw-body verification.

The bridge must verify Firebase UID -> Shopify customer ownership server-side,
apply an approved hardware-only 10% discount, and return a signed receipt. Merely
putting a UID/referral token in cart attributes is never an ownership proof.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

import httpx

from utils.referral_campaign import CampaignPolicy


class CheckoutError(ValueError):
    pass


def _usd_amount(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0 or amount.quantize(Decimal('0.01')) != amount:
        raise ValueError('invalid USD amount')
    return amount


def _retained_hardware_value(payload, line, application_index, discount, settings):
    quantity = line['quantity']
    if type(quantity) is not int or quantity <= 0:
        raise ValueError('invalid hardware quantity')
    unit_price = _usd_amount(line['price'])
    shop_money = (line.get('price_set') or {}).get('shop_money')
    if shop_money and (
        shop_money['currency_code'] != settings.currency or _usd_amount(shop_money['amount']) != unit_price
    ):
        raise ValueError('hardware currency/amount mismatch')
    gross = unit_price * quantity
    total_discount = Decimal(0)
    referral_discount = Decimal(0)
    seen = set()
    for allocation in line['discount_allocations']:
        index = allocation['discount_application_index']
        if type(index) is not int or index < 0 or index >= len(payload['discount_applications']) or index in seen:
            raise ValueError('invalid discount allocation')
        seen.add(index)
        amount = _usd_amount(allocation['amount'])
        allocation_money = (allocation.get('amount_set') or {}).get('shop_money')
        if allocation_money and (
            allocation_money['currency_code'] != settings.currency or _usd_amount(allocation_money['amount']) != amount
        ):
            raise ValueError('allocation currency/amount mismatch')
        total_discount += amount
        if index == application_index:
            referral_discount += amount
    if 'total_discount' in line and _usd_amount(line['total_discount']) != total_discount:
        raise ValueError('hardware discount total mismatch')
    if (
        referral_discount <= 0
        or referral_discount != _usd_amount(discount['amount'])
        or referral_discount > (gross * Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    ):
        raise ValueError('hardware referral allocation mismatch')
    retained = gross - total_discount
    if retained <= 0 or retained > _usd_amount(payload['total_price']):
        raise ValueError('no positive paid hardware value')
    return int(retained * 100)


def signature(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


@dataclass(frozen=True)
class CheckoutSettings:
    endpoint: str = ''
    bridge_secret: str = ''
    webhook_secret: str = ''
    shop: str = ''
    discount_code: str = ''
    variant_ids: tuple[str, ...] = ()
    currency: str = 'USD'
    # Explicit operator attestation after contextual checkout/stacking verification.
    discount_reviewed: bool = False

    @property
    def ready(self):
        parsed = urlparse(self.endpoint)
        return bool(
            parsed.scheme == 'https'
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and len(self.bridge_secret) >= 32
            and len(self.webhook_secret) >= 32
            and self.shop == '88f4ed-c3.myshopify.com'
            and self.discount_code
            and self.variant_ids
            and all(v.isdigit() for v in self.variant_ids)
            and self.discount_reviewed
        )


def checkout_settings() -> CheckoutSettings:
    return CheckoutSettings(
        endpoint=os.getenv('OMI_REFERRAL_CHECKOUT_ENDPOINT', ''),
        bridge_secret=os.getenv('OMI_REFERRAL_CHECKOUT_SECRET', ''),
        webhook_secret=os.getenv('OMI_REFERRAL_SHOPIFY_WEBHOOK_SECRET', ''),
        shop=os.getenv('OMI_REFERRAL_SHOPIFY_SHOP', ''),
        discount_code=os.getenv('OMI_REFERRAL_DISCOUNT_CODE', ''),
        variant_ids=tuple(filter(None, os.getenv('OMI_REFERRAL_HARDWARE_VARIANTS', '').split(','))),
        discount_reviewed=os.getenv('OMI_REFERRAL_DISCOUNT_REVIEWED', '') == 'true',
    )


def validate_checkout_receipt(
    data: dict, attribution: dict, settings: CheckoutSettings, policy: CampaignPolicy
) -> dict:
    try:
        url = urlparse(data['checkout_url'])
        if (
            url.scheme != 'https'
            or url.hostname not in {'www.omi.me', '88f4ed-c3.myshopify.com'}
            or url.username
            or url.password
            or url.port not in (None, 443)
            or not url.path.startswith(('/checkouts/', '/cart/'))
            or data['attribution_id'] != attribution['id']
            or data['uid'] != attribution['uid']
            or data['environment'] != policy.environment
            or data['shop'] != settings.shop
            or data['variant_id'] not in settings.variant_ids
            or data['discount_code'] != settings.discount_code
            or data['discount_percent'] != 10
            or data['hardware_only'] is not True
            or data['combination_verified'] is not True
            or not data['customer_id']
            or not data['checkout_token']
        ):
            raise ValueError('invalid receipt')
        return {
            k: data[k]
            for k in (
                'attribution_id',
                'uid',
                'environment',
                'shop',
                'variant_id',
                'discount_code',
                'discount_percent',
                'customer_id',
                'checkout_token',
                'checkout_url',
                'hardware_only',
                'combination_verified',
            )
        }
    except (KeyError, ValueError, TypeError) as error:
        raise CheckoutError('invalid_checkout_receipt') from error


class TrustedCheckoutAdapter:
    def __init__(self, settings: CheckoutSettings | None = None):
        self.settings = settings or checkout_settings()

    @property
    def ready(self):
        return self.settings.ready

    def create(self, attribution: dict, policy: CampaignPolicy) -> dict:
        if not self.ready:
            raise CheckoutError('checkout_activation_required')
        payload = {
            'attribution_id': attribution['id'],
            'uid': attribution['uid'],
            'campaign_id': policy.campaign_id,
            'environment': policy.environment,
            'discount_percent': 10,
            'discount_code': self.settings.discount_code,
            'shop': self.settings.shop,
            'variant_ids': self.settings.variant_ids,
        }
        body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        try:
            # This method is called only by a synchronous route, never the event loop.
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(
                    self.settings.endpoint,
                    content=body,
                    headers={
                        'Content-Type': 'application/json',
                        'Idempotency-Key': attribution['id'],
                        'X-Omi-Signature': signature(body, self.settings.bridge_secret),
                    },
                )
            response.raise_for_status()
            expected = signature(attribution['id'].encode() + b'.' + response.content, self.settings.bridge_secret)
            if not hmac.compare_digest(expected, response.headers.get('X-Omi-Signature', '')):
                raise CheckoutError('invalid_checkout_receipt')
            return validate_checkout_receipt(response.json(), attribution, self.settings, policy)
        except (httpx.HTTPError, ValueError) as error:
            raise CheckoutError('checkout_unavailable') from error


def verified_shopify_event(raw: bytes, headers, settings: CheckoutSettings, policy: CampaignPolicy) -> dict:
    if not settings.ready:
        raise CheckoutError('checkout_activation_required')
    if (
        headers.get('x-shopify-shop-domain') != settings.shop
        or len(raw) > 1_000_000
        or not hmac.compare_digest(signature(raw, settings.webhook_secret), headers.get('x-shopify-hmac-sha256', ''))
    ):
        raise CheckoutError('invalid_shopify_signature')
    try:
        payload = json.loads(raw)
        topic = headers.get('x-shopify-topic')
        if topic == 'refunds/create':
            # Shopify refund payload has order_id; paid payload's id cannot be reinterpreted as a refund.
            if not payload['order_id'] or not payload.get('refund_line_items'):
                raise ValueError('no line refund')
            return {
                'kind': 'refund',
                'shop': settings.shop,
                'order_id': str(payload['order_id']),
                'digest': hashlib.sha256(raw).hexdigest(),
            }
        if (
            topic != 'orders/paid'
            or payload.get('test') is not (policy.environment != 'prod')
            or payload.get('financial_status') != 'paid'
            or payload.get('cancelled_at')
            or payload.get('refunds')
            or payload.get('currency') != settings.currency
            or _usd_amount(payload['total_price']) <= 0
        ):
            raise ValueError('unqualified order')
        lines = [
            line
            for line in payload['line_items']
            if str(line['variant_id']) in settings.variant_ids
            and type(line['quantity']) is int
            and line['quantity'] > 0
            and _usd_amount(line['price']) > 0
        ]
        discounts = [
            d
            for d in payload['discount_codes']
            if d['code'] == settings.discount_code and d['type'] == 'percentage' and _usd_amount(d['amount']) > 0
        ]
        applications = [
            (i, d)
            for i, d in enumerate(payload['discount_applications'])
            if d.get('code') == settings.discount_code
            and d.get('value_type') == 'percentage'
            and Decimal(str(d['value'])) == 10
        ]
        if len(lines) != 1 or len(discounts) != 1 or len(applications) != 1:
            raise ValueError('hardware discount missing')
        index, _ = applications[0]
        net_hardware_minor = _retained_hardware_value(payload, lines[0], index, discounts[0], settings)
        ordered = datetime.fromisoformat(payload['created_at'].replace('Z', '+00:00'))
        paid = datetime.fromisoformat(payload['updated_at'].replace('Z', '+00:00'))
        if ordered.tzinfo is None or paid.tzinfo is None:
            raise ValueError('timezone required')
        return {
            'kind': 'paid',
            'shop': settings.shop,
            'order_id': str(payload['id']),
            'checkout_token': str(payload['checkout_token']),
            'customer_id': str(payload['customer']['id']),
            'variant_id': str(lines[0]['variant_id']),
            'discount_code': settings.discount_code,
            'net_hardware_minor': net_hardware_minor,
            'ordered_at': int(ordered.timestamp()),
            'paid_at': int(paid.timestamp()),
            'digest': hashlib.sha256(raw).hexdigest(),
        }
    except (ValueError, TypeError, KeyError, InvalidOperation) as error:
        raise CheckoutError('unqualified_order') from error
