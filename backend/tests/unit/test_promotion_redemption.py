"""A promotion code is redeemed onto the caller's subscription, once.

Stripe checks a code's minimum amount against what is due today, which is zero during a
free trial, so codes with a minimum fail at a trial checkout. Redemption checks the
code's restrictions against the plan price and attaches the coupon to the subscription.
"""

import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import utils.promotion_redemption as redemption  # noqa: E402
from utils.promotion_redemption import RedemptionError, redeem_promotion_code  # noqa: E402

YEARLY = {'id': 'price_year', 'product': 'prod_unlimited', 'currency': 'usd', 'unit_amount': 26991}
MONTHLY = {'id': 'price_month', 'product': 'prod_unlimited', 'currency': 'usd', 'unit_amount': 2999}


def _obj(d):
    return SimpleNamespace(to_dict=lambda: d)


def _subscription(price=YEARLY, status='trialing', **extra):
    return {
        'id': 'sub_1',
        'customer': 'cus_1',
        'status': status,
        'cancel_at_period_end': False,
        'metadata': {'uid': 'uid_1'},
        'discounts': [],
        'trial_end': 1_900_000_000,
        'items': {'data': [{'price': price}]},
        **extra,
    }


def _promo(**extra):
    return {
        'id': 'promo_1',
        'coupon': {'id': 'coupon_full'},
        'max_redemptions': 1,
        'times_redeemed': 0,
        'expires_at': None,
        'customer': None,
        'restrictions': {'minimum_amount': 26900, 'minimum_amount_currency': 'usd', 'first_time_transaction': False},
        **extra,
    }


COUPON = {'id': 'coupon_full', 'valid': True, 'percent_off': 100.0, 'applies_to': {'products': ['prod_unlimited']}}

ISSUANCE = {
    'attribution_schema': '1',
    'attribution_source': 'shopify_bundle_code',
    'shopify_shop': 'fixture-shop.myshopify.com',
    'shopify_order_id': 'gid://shopify/Order/12345',
    'bundle_order_line_item_id': 'gid://shopify/LineItem/67890',
    'bundle_redemption_role': 'gift',
}
ATTRIBUTION = {**ISSUANCE, 'bundle_promotion_code_id': 'promo_1'}


class _Env:
    def __init__(self, subscription=None, promos=None, coupon=None, claim=True):
        self.subscription = subscription or _subscription()
        self.promos = [_promo()] if promos is None else promos
        self.coupon = coupon or COUPON
        self.claim_result = claim
        self.promo_modify = MagicMock()
        self.sub_modify = MagicMock(side_effect=lambda sub_id, **kw: _obj({**self.subscription, **kw}))
        self.claim = MagicMock(return_value=claim)
        self.release = MagicMock()

    def __enter__(self):
        fake_stripe = SimpleNamespace(
            PromotionCode=SimpleNamespace(
                list=lambda **kw: SimpleNamespace(data=[_obj(p) for p in self.promos]),
                modify=self.promo_modify,
            ),
            Coupon=SimpleNamespace(retrieve=lambda coupon_id, **kw: _obj(self.coupon)),
            Subscription=SimpleNamespace(retrieve=lambda sub_id: _obj(self.subscription), modify=self.sub_modify),
            error=redemption.stripe.error,
            StripeError=redemption.stripe.StripeError,
        )
        self._patches = [
            patch.object(redemption, 'stripe', fake_stripe),
            patch.object(
                redemption.users_db,
                'get_user_subscription',
                return_value=SimpleNamespace(stripe_subscription_id=self.subscription and 'sub_1'),
            ),
            patch.object(redemption.redemptions_db, 'claim', self.claim),
            patch.object(redemption.redemptions_db, 'release', self.release),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


def test_trial_subscription_gets_the_coupon_and_the_code_is_used_up():
    with _Env() as env:
        result = redeem_promotion_code('uid_1', ' OMI-AAAA-BBBB ')
    assert result['status'] == 'applied'
    assert result['percent_off'] == 100.0
    assert result['applies_at'] == 1_900_000_000
    env.claim.assert_called_once_with(
        'promo_1', uid='uid_1', subscription_id='sub_1', coupon_id='coupon_full', attribution={}
    )
    assert env.promo_modify.call_args.kwargs['active'] is False
    assert env.sub_modify.call_args.kwargs['discounts'] == [{'coupon': 'coupon_full'}]


def test_monthly_plan_is_below_the_code_minimum():
    with _Env(subscription=_subscription(price=MONTHLY)) as env:
        with pytest.raises(RedemptionError) as excinfo:
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    assert excinfo.value.status_code == 400
    env.claim.assert_not_called()
    env.sub_modify.assert_not_called()


def test_code_for_another_product_is_refused():
    other = {**YEARLY, 'product': 'prod_other'}
    with _Env(subscription=_subscription(price=other)) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    env.sub_modify.assert_not_called()


def test_unknown_or_used_code_is_refused():
    with _Env(promos=[]) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'NOPE')
    env.claim.assert_not_called()
    with _Env(promos=[_promo(times_redeemed=1)]) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    with _Env(promos=[_promo(expires_at=int(time.time()) - 1)]) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')


def test_second_claim_of_the_same_code_loses():
    with _Env(claim=False) as env:
        with pytest.raises(RedemptionError) as excinfo:
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    assert excinfo.value.status_code == 409
    env.promo_modify.assert_not_called()
    env.sub_modify.assert_not_called()


def test_no_subscription_or_canceling_subscription_is_refused():
    with _Env(subscription=_subscription(status='canceled')) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    with _Env(subscription=_subscription(cancel_at_period_end=True)) as env:
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    env.claim.assert_not_called()


def test_subscription_with_a_discount_already_is_refused():
    with _Env(subscription=_subscription(discounts=['di_1'])) as env:
        with pytest.raises(RedemptionError) as excinfo:
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    assert excinfo.value.status_code == 409
    env.claim.assert_not_called()


def test_failed_stripe_update_gives_the_code_back():
    with _Env() as env:
        env.sub_modify.side_effect = redemption.stripe.error.InvalidRequestError('nope', None)
        with pytest.raises(RedemptionError):
            redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    assert env.promo_modify.call_args_list[-1].kwargs == {'active': True}
    env.release.assert_called_once_with('promo_1')


def test_redemption_retains_issuance_provenance_without_coupling_it_to_code_benefit():
    subscription = _subscription(metadata={'uid': 'uid_1', 'sub_type': 'unlimited', 'unrelated': 'kept'})
    with _Env(subscription=subscription, promos=[_promo(metadata=ISSUANCE)]) as env:
        result = redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')

    assert result['status'] == 'applied'
    assert env.claim.call_args.kwargs['attribution'] == ATTRIBUTION
    promo_params = env.promo_modify.call_args.kwargs
    assert promo_params['active'] is False
    assert promo_params['metadata'] == {
        'redeemed_by_uid': 'uid_1',
        'redeemed_subscription_id': 'sub_1',
    }
    assert env.sub_modify.call_args_list[0].kwargs == {
        'discounts': [{'coupon': 'coupon_full'}],
        'metadata': {'redeemed_promotion_code_id': 'promo_1'},
    }
    # Stripe merges this optional allowlist without rewriting unrelated fields or uid.
    assert env.sub_modify.call_args_list[1].kwargs == {'metadata': ATTRIBUTION}
    assert set(promo_params) == {'active', 'metadata'}


@pytest.mark.parametrize('role', ['self', 'gift', 'unknown'])
def test_redemption_preserves_verified_redemption_role(role):
    with _Env(promos=[_promo(metadata={**ISSUANCE, 'bundle_redemption_role': role})]) as env:
        redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')
    assert env.claim.call_args.kwargs['attribution']['bundle_redemption_role'] == role
    assert env.sub_modify.call_args.kwargs['metadata']['bundle_redemption_role'] == role


def test_redemption_preserves_conflicting_existing_order_provenance():
    original = {
        **ISSUANCE,
        'shopify_order_id': 'gid://shopify/Order/99999',
        'bundle_redemption_role': 'unknown',
        'bundle_promotion_code_id': 'promo_original',
    }
    subscription = _subscription(metadata={'uid': 'uid_1', 'sub_type': 'unlimited', **original})
    with _Env(subscription=subscription, promos=[_promo(metadata=ISSUANCE)]) as env:
        result = redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')

    assert result['status'] == 'applied'
    metadata = env.sub_modify.call_args.kwargs['metadata']
    assert metadata['shopify_order_id'] == original['shopify_order_id']
    assert metadata['bundle_promotion_code_id'] == 'promo_original'
    assert metadata['bundle_redemption_role'] == 'unknown'
    assert 'uid' not in metadata
    assert 'sub_type' not in metadata
    assert env.sub_modify.call_args_list[0].kwargs['metadata']['redeemed_promotion_code_id'] == 'promo_1'


@pytest.mark.parametrize(
    'metadata,coupon',
    [
        ({**ISSUANCE, 'shopify_order_id': 'malformed'}, None),
        (ISSUANCE, {'id': 'coupon_full', 'metadata': {**ISSUANCE, 'shopify_shop': 'other'}}),
    ],
)
def test_invalid_or_conflicting_provenance_does_not_change_redemption_result(metadata, coupon):
    promo = _promo(metadata=metadata)
    if coupon is not None:
        promo['coupon'] = coupon
    with _Env(promos=[promo]) as env:
        result = redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')

    assert result == {
        'status': 'applied',
        'percent_off': 100.0,
        'amount_off': None,
        'currency': None,
        'applies_at': 1_900_000_000,
    }
    assert env.claim.call_args.kwargs['attribution'] == {}
    subscription_metadata = env.sub_modify.call_args.kwargs['metadata']
    assert subscription_metadata == {'redeemed_promotion_code_id': 'promo_1'}


def test_endpoint_returns_the_refusal_as_a_client_error():
    from fastapi import HTTPException

    import routers.redeem_code as payment

    with patch.object(payment, 'redeem_promotion_code', side_effect=RedemptionError(409, 'used')):
        with pytest.raises(HTTPException) as excinfo:
            payment.redeem_code_endpoint(payment.RedeemCodeRequest(code='OMI-AAAA-BBBB'), uid='uid_1')
    assert (excinfo.value.status_code, excinfo.value.detail) == (409, 'used')


@pytest.mark.parametrize(
    'failure', [RuntimeError('optional metadata unavailable'), redemption.stripe.StripeError('metadata')]
)
def test_optional_attribution_write_failure_does_not_undo_code_benefit(failure):
    with _Env(promos=[_promo(metadata=ISSUANCE)]) as env:

        def apply_or_fail_metadata(subscription_id, **kwargs):
            if kwargs.get('metadata', {}).get('attribution_schema'):
                raise failure
            return _obj({**env.subscription, **kwargs})

        env.sub_modify.side_effect = apply_or_fail_metadata
        result = redeem_promotion_code('uid_1', 'OMI-AAAA-BBBB')

    assert result['status'] == 'applied'
    assert env.sub_modify.call_args_list[0].kwargs == {
        'discounts': [{'coupon': 'coupon_full'}],
        'metadata': {'redeemed_promotion_code_id': 'promo_1'},
    }
    assert env.sub_modify.call_count == 2
    env.release.assert_not_called()
    assert env.promo_modify.call_count == 1
    assert env.promo_modify.call_args.kwargs['active'] is False
