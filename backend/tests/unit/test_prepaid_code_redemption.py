"""No-card redemption of a fully prepaid Omi Pro code: which codes qualify, single use, idempotent
retries, live-plan refusals, rate limits, and identical responses with the switch off."""

import json
import os
import time
from types import SimpleNamespace

import pytest
import stripe as real_stripe

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config import prepaid_code_redeem as switch  # noqa: E402
from models.users import PlanType, Subscription, SubscriptionStatus  # noqa: E402
from utils import prepaid_code_redemption as redemption  # noqa: E402
from utils.prepaid_code_redemption import PrepaidCodeError, redeem_prepaid_code  # noqa: E402

UID = 'fixture-user'
OTHER = 'fixture-other'
NOW = int(time.time())
DAY = 86400
MONTHLY = {'id': 'price_pro_month', 'product': 'prod_pro', 'currency': 'usd', 'unit_amount': 2999}
YEARLY = {'id': 'price_pro_year', 'product': 'prod_pro', 'currency': 'usd', 'unit_amount': 26991}

BUNDLE = {'id': 'omi_shopify_pro_year', 'valid': True, 'percent_off': 100.0, 'amount_off': None, 'currency': None,
          'duration': 'repeating', 'duration_in_months': 12, 'redeem_by': None,
          'applies_to': {'products': ['prod_pro']}}  # fmt: skip
PREPAID_YEAR = {**BUNDLE, 'id': 'free_year', 'applies_to': None}
CREATOR = {**BUNDLE, 'id': 'rWZbg1Do', 'duration_in_months': 3, 'applies_to': None}
FIRST_MONTH = {'id': '31HHBoYp', 'valid': True, 'percent_off': None, 'amount_off': 2999, 'currency': 'usd',
               'duration': 'once', 'duration_in_months': None, 'redeem_by': None, 'applies_to': None}  # fmt: skip
PARTIAL = {**BUNDLE, 'id': 'omi-retention-50off-3mo', 'percent_off': 50.0, 'duration_in_months': 3, 'applies_to': None}


def promo(coupon, code='OMI-TRYBE-ABCD1234', **over):
    data = {'id': 'promo_1', 'code': code, 'active': True, 'coupon': coupon, 'max_redemptions': 1,
            'times_redeemed': 0, 'expires_at': None, 'customer': None, 'metadata': {}}  # fmt: skip
    data.update(over)
    return data


class FakeStripe:
    """Just enough of stripe-python: case-insensitive code lookup, single-use enforcement, idempotency."""

    StripeError = real_stripe.StripeError
    InvalidRequestError = real_stripe.InvalidRequestError

    def __init__(self, promos):
        self.promos = promos
        self.created = []
        self.customers = []
        self.idempotent = {}
        self.fail_create = None
        outer = self

        class _Obj(dict):
            def to_dict(self):
                return dict(self)

            @property
            def id(self):
                return self['id']

        self._Obj = _Obj

        class PromotionCode:
            @staticmethod
            def list(code, limit, expand):
                hits = [p for p in outer.promos if p['code'].lower() == code.lower()]
                return SimpleNamespace(data=[_Obj(h) for h in hits[:limit]])

        class Price:
            @staticmethod
            def retrieve(price_id):
                return _Obj({'price_pro_month': MONTHLY, 'price_pro_year': YEARLY}[price_id])

        class Customer:
            @staticmethod
            def create(metadata, idempotency_key):
                customer = _Obj(id=f'cus_{len(outer.customers) + 1}', metadata=metadata)
                outer.customers.append(customer)
                return customer

        class Subscription:
            @staticmethod
            def create(idempotency_key, **params):
                if outer.fail_create:
                    raise outer.fail_create
                if idempotency_key in outer.idempotent:
                    return outer.idempotent[idempotency_key]
                promo_id = params['discounts'][0]['promotion_code']
                stored = next(p for p in outer.promos if p['id'] == promo_id)
                if stored['times_redeemed'] >= (stored['max_redemptions'] or 10**9):
                    raise real_stripe.InvalidRequestError('This promotion code has been used up.', 'discounts')
                stored['times_redeemed'] += 1
                sub = _Obj(id=f'sub_{len(outer.created) + 1}', status='active', **params)
                outer.created.append(sub)
                outer.idempotent[idempotency_key] = sub
                return sub

        self.PromotionCode, self.Price, self.Customer, self.Subscription = PromotionCode, Price, Customer, Subscription


class FakeLedger:
    def __init__(self):
        self.docs = {}

    def claim(self, promotion_code_id, *, uid, subscription_id, coupon_id, attribution=None, extra=None):
        if promotion_code_id in self.docs:
            return False
        self.docs[promotion_code_id] = {'uid': uid, 'subscription_id': subscription_id, **(extra or {})}
        return True

    def get(self, promotion_code_id):
        return self.docs.get(promotion_code_id)

    def release(self, promotion_code_id):
        self.docs.pop(promotion_code_id, None)

    def set_subscription(self, promotion_code_id, subscription_id):
        self.docs[promotion_code_id]['subscription_id'] = subscription_id


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(
        stripe=FakeStripe([promo(BUNDLE)]),
        ledger=FakeLedger(),
        row=None,
        stripe_active_paid=None,
        customer_id=None,
    )
    monkeypatch.setattr(redemption, 'stripe', state.stripe)
    for name in ('claim', 'get', 'release', 'set_subscription'):
        monkeypatch.setattr(redemption.redemptions_db, name, getattr(state.ledger, name))
    monkeypatch.setattr(redemption.users_db, 'get_existing_user_subscription', lambda uid: state.row)
    monkeypatch.setattr(redemption.users_db, 'get_stripe_customer_id', lambda uid: state.customer_id)

    def set_customer(uid, customer_id):
        state.customer_id = customer_id

    monkeypatch.setattr(redemption.users_db, 'set_stripe_customer_id', set_customer)
    monkeypatch.setattr(redemption, 'find_active_paid_subscription_for_user', lambda uid: state.stripe_active_paid)
    monkeypatch.setattr(
        redemption,
        '_pro_prices',
        lambda: (MONTHLY['id'], YEARLY['id']),
    )
    return state


def _reason(uid, code):
    with pytest.raises(PrepaidCodeError) as error:
        redeem_prepaid_code(uid, code)
    return error.value.status_code, error.value.reason


def _assert_no_card_subscription(sub, months):
    assert sub['items'] == [{'price': MONTHLY['id']}]
    assert sub['discounts'] == [{'promotion_code': 'promo_1'}]
    assert sub['payment_behavior'] == 'error_if_incomplete'
    assert sub['proration_behavior'] == 'none'
    assert 'default_payment_method' not in sub and 'trial_period_days' not in sub
    assert sub['metadata']['uid'] == UID and sub['metadata']['redeemed_promotion_code_id'] == 'promo_1'
    expected_end = redemption.add_months(NOW, months) - redemption.END_MARGIN_SECONDS
    assert abs(sub['cancel_at'] - expected_end) <= 5


# ---- in-scope code kinds -----------------------------------------------------------------------


@pytest.mark.parametrize(
    'coupon,months',
    [(BUNDLE, 12), (PREPAID_YEAR, 12), (CREATOR, 3), (FIRST_MONTH, 1)],
    ids=['bundle_12_months_included', 'prepaid_year', 'creator_code', 'first_month_included'],
)
def test_fully_prepaid_codes_create_a_no_card_subscription_that_ends_with_the_term(world, coupon, months):
    world.stripe.promos = [promo(coupon)]
    result = redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')
    assert result['status'] == 'redeemed' and result['plan'] == 'Omi Pro' and result['months'] == months
    [sub] = world.stripe.created
    _assert_no_card_subscription(sub, months)
    assert result['ends_at'] == sub['cancel_at']
    assert world.stripe.customers[0]['metadata'] == {'uid': UID} and world.customer_id == 'cus_1'
    assert world.ledger.docs['promo_1']['subscription_id'] == sub['id']
    assert world.ledger.docs['promo_1']['uid'] == UID


def test_the_term_ends_before_the_first_undiscounted_renewal():
    start = int(time.mktime((2026, 1, 31, 12, 0, 0, 0, 0, 0)))
    assert redemption.add_months(start, 1) - start < 31 * DAY  # Feb clamps to the 28th
    assert redemption.add_months(start, 12) > start + 364 * DAY


def test_wrong_case_and_whitespace_find_the_same_code(world):
    result = redeem_prepaid_code(UID, '  omi-trybe-\tabcd 1234\n')
    assert result['months'] == 12 and len(world.stripe.created) == 1


# ---- refusals that leave the code unused -------------------------------------------------------


@pytest.mark.parametrize(
    'coupon',
    [
        PARTIAL,
        {**FIRST_MONTH, 'amount_off': 1000},  # $10 off a $29.99 month
        {**FIRST_MONTH, 'amount_off': 2999, 'currency': 'eur'},
        {**BUNDLE, 'duration': 'forever', 'duration_in_months': None},  # no fixed term
        {**BUNDLE, 'duration': 'once', 'duration_in_months': None},  # would also zero a year
        {**BUNDLE, 'applies_to': {'products': ['prod_other']}},
    ],
    ids=['percent_off', 'amount_below_price', 'other_currency', 'forever', 'once_full', 'other_product'],
)
def test_a_partial_or_open_ended_code_is_refused_and_not_consumed(world, coupon):
    world.stripe.promos = [promo(coupon)]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'not_prepaid')
    assert world.stripe.created == [] and world.ledger.docs == {} and world.stripe.promos[0]['times_redeemed'] == 0


def test_a_shared_code_is_a_discount_not_a_prepaid_code(world):
    world.stripe.promos = [promo(BUNDLE, max_redemptions=None)]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'not_prepaid')
    assert world.stripe.created == []


def test_unknown_code_is_invalid(world):
    assert _reason(UID, 'NOPE-0000') == (400, 'invalid_code')
    assert _reason(UID, '   ') == (400, 'invalid_code')


def test_expired_code(world):
    world.stripe.promos = [promo(BUNDLE, expires_at=NOW - DAY)]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'code_expired')
    world.stripe.promos = [promo({**BUNDLE, 'redeem_by': NOW - 1})]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'code_expired')
    assert world.stripe.created == [] and world.ledger.docs == {}


def test_code_used_at_checkout_or_by_someone_else(world):
    world.stripe.promos = [promo(BUNDLE, times_redeemed=1, active=False)]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (409, 'code_used')
    world.stripe.promos = [promo(BUNDLE)]
    redeem_prepaid_code(OTHER, 'OMI-TRYBE-ABCD1234')
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (409, 'code_used')
    assert len(world.stripe.created) == 1 and world.stripe.created[0]['metadata']['uid'] == OTHER


def test_code_locked_to_another_customer_is_invalid(world):
    world.stripe.promos = [promo(BUNDLE, customer='cus_someone_else')]
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'invalid_code')


def test_stripe_refusing_the_code_releases_the_claim(world):
    world.stripe.fail_create = real_stripe.InvalidRequestError(
        'This promotion code cannot be redeemed because the associated customer has prior transactions.', 'x'
    )
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (400, 'not_eligible')
    assert world.ledger.docs == {}


def test_unknown_stripe_outcome_keeps_the_claim_for_an_idempotent_retry(world):
    world.stripe.fail_create = real_stripe.APIConnectionError('timeout')
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (503, 'try_again')
    assert world.ledger.docs['promo_1']['uid'] == UID
    world.stripe.fail_create = None
    result = redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')
    assert result['status'] == 'redeemed' and len(world.stripe.created) == 1


# ---- idempotency -------------------------------------------------------------------------------


def test_second_tap_returns_the_same_redemption_and_creates_nothing_new(world):
    first = redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')
    # The webhook has now granted Pro; a retry must still answer success, not "you already have a plan".
    world.row = Subscription(
        plan=PlanType.unlimited_v2, status=SubscriptionStatus.active, current_period_end=NOW + 30 * DAY
    )
    second = redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')
    assert second == first
    assert len(world.stripe.created) == 1 and len(world.stripe.customers) == 1


def test_retry_after_stripe_forgot_the_idempotency_key_still_answers_success(world):
    first = redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')
    world.stripe.idempotent.clear()  # Stripe keeps idempotency keys for 24 hours
    world.row = Subscription(
        plan=PlanType.unlimited_v2, status=SubscriptionStatus.active, current_period_end=NOW + 30 * DAY
    )
    assert redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234') == first
    assert len(world.stripe.created) == 1


# ---- users who already have a plan -------------------------------------------------------------


def test_user_with_a_live_stripe_subscription_is_told_and_the_code_is_untouched(world):
    world.row = Subscription(plan=PlanType.unlimited_v2, status=SubscriptionStatus.active, current_period_end=NOW + DAY)
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (409, 'has_plan')
    world.row = None
    world.stripe_active_paid = Subscription(plan=PlanType.unlimited_v2, stripe_subscription_id='sub_live')
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (409, 'has_plan')
    assert world.stripe.created == [] and world.ledger.docs == {} and world.stripe.promos[0]['times_redeemed'] == 0


def test_user_with_a_live_play_subscription_is_told_and_the_code_is_untouched(world):
    world.row = Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + DAY, provider='play')
    assert _reason(UID, 'OMI-TRYBE-ABCD1234') == (409, 'has_plan')
    assert world.stripe.created == [] and world.ledger.docs == {}


def test_lapsed_plan_can_redeem(world):
    world.row = Subscription(plan=PlanType.unlimited_v2, status=SubscriptionStatus.active, current_period_end=NOW - 1)
    assert redeem_prepaid_code(UID, 'OMI-TRYBE-ABCD1234')['status'] == 'redeemed'


# ---- switch, route and rate limits -------------------------------------------------------------


def test_switch_defaults_off_and_admits_only_on_or_the_cohort(monkeypatch):
    from config import rollout_cohorts

    monkeypatch.delenv(switch.ENV, raising=False)
    monkeypatch.setattr(
        rollout_cohorts, 'in_rollout_cohort', lambda uid, name: uid == UID and name == 'prepaid-code-redeem'
    )
    assert switch.enabled_for(UID, {}) is True  # test account through the cohort document
    assert switch.enabled_for(OTHER, {}) is False
    assert switch.enabled_for(OTHER, {'PREPAID_CODE_REDEEM': 'off'}) is False
    assert switch.enabled_for(OTHER, {'PREPAID_CODE_REDEEM': 'yes'}) is False
    assert switch.enabled_for(OTHER, {'PREPAID_CODE_REDEEM': ' ON '}) is True
    monkeypatch.setattr(rollout_cohorts, 'in_rollout_cohort', lambda uid, name: (_ for _ in ()).throw(RuntimeError()))
    assert switch.enabled_for(UID, {}) is False  # unknown membership keeps today's behaviour


@pytest.fixture
def route(monkeypatch):
    from routers import redeem_code

    calls = []
    monkeypatch.setattr(redeem_code.auth, 'check_rate_limit_inline', lambda key, policy: calls.append((key, policy)))
    monkeypatch.setattr(
        redeem_code,
        'redeem_prepaid_code',
        lambda uid, code: {'status': 'redeemed', 'plan': 'Omi Pro', 'ends_at': 1, 'months': 12},
    )
    return SimpleNamespace(module=redeem_code, calls=calls)


def _request(xff=None):
    from fastapi import Request

    headers = [(b'x-forwarded-for', xff.encode())] if xff else []
    return Request({'type': 'http', 'headers': headers, 'client': ('10.0.0.1', 1)})


def test_switch_off_route_is_not_found_and_touches_nothing(monkeypatch, route):
    from fastapi import HTTPException

    monkeypatch.setattr(route.module.prepaid_code_config, 'enabled_for', lambda uid: False)
    with pytest.raises(HTTPException) as error:
        route.module.redeem_prepaid_code_endpoint(route.module.RedeemCodeRequest(code='X'), _request(), uid=UID)
    assert (error.value.status_code, error.value.detail) == (404, 'Not Found')
    assert route.calls == []


def test_route_rate_limits_per_user_and_per_client_ip(monkeypatch, route):
    monkeypatch.setattr(route.module.prepaid_code_config, 'enabled_for', lambda uid: True)
    body = route.module.RedeemCodeRequest(code='OMI-1')
    route.module.redeem_prepaid_code_endpoint(body, _request('1.1.1.1, 203.0.113.9'), uid=UID)
    route.module.redeem_prepaid_code_endpoint(body, _request('9.9.9.9, 203.0.113.9'), uid=OTHER)
    assert [policy for _, policy in route.calls] == ['payments:prepaid_code', 'payments:prepaid_code_ip'] * 2
    assert route.calls[0][0] == UID
    # A spoofed leading hop does not change the IP bucket: the front end appends the real one.
    assert route.calls[1][0] == route.calls[3][0] and route.calls[1][0].startswith('ip:')
    assert '203.0.113.9' not in route.calls[1][0]


def test_route_rate_limit_rejection_stops_before_any_lookup(monkeypatch, route):
    from fastapi import HTTPException

    monkeypatch.setattr(route.module.prepaid_code_config, 'enabled_for', lambda uid: True)

    def limited(key, policy):
        raise HTTPException(status_code=429, detail='Rate limit exceeded. Try again in 60s.')

    monkeypatch.setattr(route.module.auth, 'check_rate_limit_inline', limited)
    monkeypatch.setattr(route.module, 'redeem_prepaid_code', lambda uid, code: pytest.fail('looked up a code'))
    with pytest.raises(HTTPException) as error:
        route.module.redeem_prepaid_code_endpoint(route.module.RedeemCodeRequest(code='X'), _request(), uid=UID)
    assert error.value.status_code == 429


def test_route_maps_errors_to_reason_codes(monkeypatch, route):
    from fastapi import HTTPException

    monkeypatch.setattr(route.module.prepaid_code_config, 'enabled_for', lambda uid: True)

    def refuse(uid, code):
        raise PrepaidCodeError(409, 'has_plan')

    monkeypatch.setattr(route.module, 'redeem_prepaid_code', refuse)
    with pytest.raises(HTTPException) as error:
        route.module.redeem_prepaid_code_endpoint(route.module.RedeemCodeRequest(code='X'), _request(), uid=UID)
    assert (error.value.status_code, error.value.detail) == (409, 'has_plan')


def test_rate_limit_policies_exist():
    from utils.rate_limit_config import RATE_POLICIES

    assert RATE_POLICIES['payments:prepaid_code'] == (10, 3600)
    assert RATE_POLICIES['payments:prepaid_code_ip'] == (30, 3600)


def test_subscription_response_is_byte_identical_with_the_switch_off(monkeypatch):
    from fastapi import Request
    from routers import users

    monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
    monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: True)
    monkeypatch.setattr(users.users_db, 'get_user_valid_subscription', lambda *a, **k: None)
    monkeypatch.setattr(users.play_subscriptions_db, 'remember_account_once', lambda *a: None)

    def body():
        return users.get_user_subscription_endpoint(
            request=Request({'type': 'http', 'headers': []}),
            uid=UID,
            x_app_platform='android',
            x_app_version='1.0.600',
            x_app_build='1700',
        ).model_dump_json()

    monkeypatch.setattr(users.prepaid_code_config, 'enabled_for', lambda uid: False)
    baseline = body()
    assert 'prepaid_code_redeem' not in baseline
    monkeypatch.setattr(users.prepaid_code_config, 'enabled_for', lambda uid: True)
    on = json.loads(body())
    assert on.pop('prepaid_code_redeem') is True
    assert on == json.loads(baseline)


# ---- a prepaid subscription is never changed or un-cancelled -----------------------------------


def _prepaid_stripe_sub(**over):
    return {
        'id': 'sub_prepaid',
        'status': 'active',
        'customer': 'cus_1',
        'cancel_at': NOW + 90 * DAY,
        'cancel_at_period_end': False,
        'current_period_end': NOW + 30 * DAY,
        'metadata': {'uid': UID, 'prepaid_code_redemption': '1'},
        'items': {'data': [{'id': 'si_1', 'price': {'id': MONTHLY['id'], 'recurring': {'interval': 'month'}}}]},
        **over,
    }


def test_is_prepaid_subscription_reads_only_the_redemption_marker():
    assert switch.is_prepaid_subscription(_prepaid_stripe_sub()) is True
    assert switch.is_prepaid_subscription({'metadata': {'uid': UID}}) is False
    assert switch.is_prepaid_subscription({}) is False


@pytest.fixture
def payment_router(monkeypatch):
    from routers import payment

    row = Subscription(
        plan=PlanType.unlimited_v2,
        status=SubscriptionStatus.active,
        stripe_subscription_id='sub_prepaid',
        current_period_end=NOW + 30 * DAY,
    )
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: row)
    modified = []
    fake = SimpleNamespace(
        retrieve=lambda sub_id, **kw: SimpleNamespace(to_dict=lambda: _prepaid_stripe_sub(**payment_router_over)),
        modify=lambda *a, **kw: modified.append((a, kw)),
    )
    payment_router_over = {}
    monkeypatch.setattr(payment.stripe, 'Subscription', fake)
    return SimpleNamespace(module=payment, modified=modified, over=payment_router_over)


def test_upgrade_refuses_a_prepaid_subscription_before_any_stripe_change(monkeypatch, payment_router):
    from fastapi import HTTPException

    monkeypatch.setattr(payment_router.module, '_validate_price_id', lambda price_id: None)
    request = payment_router.module.UpgradeSubscriptionRequest(price_id=YEARLY['id'])
    with pytest.raises(HTTPException) as error:
        payment_router.module.upgrade_subscription_endpoint.__wrapped__(request, uid=UID)
    assert error.value.status_code == 409 and 'prepaid' in error.value.detail
    assert payment_router.modified == []


def test_reactivation_never_uncancels_a_prepaid_subscription(payment_router):
    from fastapi import HTTPException

    payment_router.over.update(cancel_at_period_end=True)
    with pytest.raises(HTTPException) as error:
        payment_router.module._try_reactivate_subscription.__wrapped__(UID, MONTHLY['id'])
    assert error.value.status_code == 409
    assert payment_router.modified == []


def test_a_prepaid_subscription_is_shown_ending_at_its_term_not_renewing():
    from utils.subscription_state_machine import project_subscription
    from utils.subscription import get_plan_limits

    prepaid = _prepaid_stripe_sub()
    row = project_subscription(prepaid, PlanType.unlimited_v2, get_plan_limits(PlanType.unlimited_v2))
    assert row.current_period_end == prepaid['cancel_at'] and row.cancel_at_period_end is True
    ordinary = {**prepaid, 'metadata': {'uid': UID}}
    row = project_subscription(ordinary, PlanType.unlimited_v2, get_plan_limits(PlanType.unlimited_v2))
    assert row.current_period_end == ordinary['current_period_end'] and row.cancel_at_period_end is False
    ended = {**prepaid, 'status': 'canceled'}
    assert project_subscription(ended, None, get_plan_limits(PlanType.basic)).plan == PlanType.basic
