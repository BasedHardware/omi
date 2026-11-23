"""Local-currency offers for Google Play's Subscriptions policy (utils/local_currency.py).

Play rejected Android builds because a non-US reviewer saw the trial offer in US$. With
``STOREFRONT_LOCAL_CURRENCY`` on and an approved table, a buyer whose device region has
an approved price sees it in that currency on every surface and Checkout charges the
same Stripe ``currency_options`` entry. Everyone else, a country outside the table or a
table currency the live Price lacks included, keeps today's USD, as Google Play does
where it has no local currency. With the switch off or the table empty every response is
byte-identical to today, and a build that sends no region keeps today's behaviour.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.storefront import StorefrontUsage
from models.users import PlanType, Subscription, SubscriptionStatus, UserSubscriptionResponse
from models.users import PricingOption as UserPricingOption, SubscriptionPlan
from routers import payment
from routers import storefront as storefront_route
from routers import users as users_route
from utils import local_currency, promotion_redemption, retention_offer, trial_reminder, yearly_switch
import utils.stripe as stripe_utils

PRO_MONTH = 'price_omi_pro_month_fixture'
PRO_YEAR = 'price_omi_pro_year_fixture'
REGION = local_currency.REGION_HEADER
TABLE = {
    'countries': {'JP': 'jpy', 'GB': 'gbp', 'DE': 'eur', 'EC': 'usd'},
    'currencies': {
        'jpy': {'monthly': 4500, 'annual': 40500},
        'gbp': {'monthly': 2299, 'annual': 20699},
        'eur': {'monthly': 2799, 'annual': 24999},
    },
}
OPTIONS = {
    PRO_MONTH: {'jpy': {'unit_amount': 4500}, 'gbp': {'unit_amount': 2299}, 'eur': {'unit_amount': 2799}},
    PRO_YEAR: {'jpy': {'unit_amount': 40500}, 'gbp': {'unit_amount': 20699}, 'eur': {'unit_amount': 24999}},
}


def _row(price_id, amount, interval, *, options=None):
    row = {
        'id': price_id,
        'object': 'price',
        'product': 'prod_omi_pro_fixture',
        'currency': 'usd',
        'unit_amount': amount,
        'active': True,
        'livemode': False,
        'recurring': {'interval': interval, 'interval_count': 1},
    }
    if options is not None:
        row['currency_options'] = options
    return row


BASE = {PRO_MONTH: _row(PRO_MONTH, 2999, 'month'), PRO_YEAR: _row(PRO_YEAR, 26991, 'year')}


def _retrieve_factory(options=OPTIONS):
    """Stripe returns currency_options only when expanded."""

    def retrieve(price_id, expand=None, **kwargs):
        row = dict(BASE[price_id])
        if expand and 'currency_options' in expand:
            row['currency_options'] = {'usd': {'unit_amount': row['unit_amount']}, **options.get(price_id, {})}
        return stripe.Price.construct_from(row, 'sk_test_fake')

    return retrieve


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', PRO_MONTH)
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID', PRO_YEAR)
    monkeypatch.delenv('NEW_BUYER_SINGLE_PLAN_ENABLED', raising=False)
    monkeypatch.delenv(local_currency.MODE_ENV, raising=False)
    monkeypatch.delenv(local_currency.TABLE_ENV, raising=False)
    monkeypatch.setattr(stripe.Price, 'retrieve', _retrieve_factory())
    # Uncached in tests: always the (fake) live Price with its options.
    monkeypatch.setattr(
        local_currency,
        'cached_price_with_options',
        lambda price_id: stripe.Price.retrieve(price_id, expand=['currency_options']).to_dict_recursive(),
    )
    monkeypatch.setattr(storefront_route.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(storefront_route.redis_db, 'set_generic_cache', lambda key, value, ttl: None)
    customer = SimpleNamespace(id=None, currency=None)
    monkeypatch.setattr(payment.users_db, 'get_stripe_customer_id', lambda uid: customer.id)
    monkeypatch.setattr(stripe.Customer, 'retrieve', lambda cid: SimpleNamespace(id=cid, currency=customer.currency))

    def on(mode='android', table=TABLE):
        monkeypatch.setenv(local_currency.MODE_ENV, mode)
        monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(table))

    def lapsed(currency):
        customer.id, customer.currency = 'cus_lapsed_fixture', currency

    return SimpleNamespace(on=on, lapsed=lapsed, monkeypatch=monkeypatch)


# --- the decision -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    'mode, platform, region, expected',
    [
        ('off', 'android', 'JP', local_currency.DEFAULT),
        ('android', 'android', 'JP', local_currency.Offer('local', 'jpy')),
        ('android', 'android', 'gb', local_currency.Offer('local', 'gbp')),
        ('android', 'android', 'US', local_currency.DEFAULT),
        ('android', 'android', 'EC', local_currency.DEFAULT),  # a USD country is the US price
        ('android', 'android', 'FR', local_currency.DEFAULT),  # outside the table: USD, as on Play
        ('android', 'android', None, local_currency.DEFAULT),  # released builds send no region
        ('android', 'android', 'not-a-region', local_currency.DEFAULT),
        ('android', 'ios', 'JP', local_currency.DEFAULT),
        ('all', 'ios', 'JP', local_currency.Offer('local', 'jpy')),
        ('all', 'ios', 'FR', local_currency.DEFAULT),  # outside Android, unknown keeps USD
        ('typo', 'android', 'JP', local_currency.DEFAULT),
    ],
)
def test_offer_decision(env, mode, platform, region, expected):
    env.on(mode)
    assert local_currency.offer_for(platform, region) == expected


@pytest.mark.parametrize('raw', ['', 'not json', '[]', json.dumps({'countries': {'JP': 'jpy'}})])
def test_empty_or_malformed_table_is_off(env, raw):
    env.monkeypatch.setenv(local_currency.MODE_ENV, 'android')
    env.monkeypatch.setenv(local_currency.TABLE_ENV, raw)
    assert local_currency.offer_for('android', 'JP') == local_currency.DEFAULT


def test_stripe_amount_must_equal_the_approved_table(env):
    env.on()
    year = _retrieve_factory()(PRO_YEAR, expand=['currency_options'])
    assert local_currency.approved_amount(year, 'jpy') == 40500
    stale = _retrieve_factory({PRO_YEAR: {'jpy': {'unit_amount': 39000}}})(PRO_YEAR, expand=['currency_options'])
    assert local_currency.approved_amount(stale, 'jpy') is None
    assert local_currency.approved_amount(BASE[PRO_YEAR], 'jpy') is None  # not expanded: never guessed


def test_display_money_is_the_checkout_render_for_every_stripe_currency():
    """Samples are ICU Intl.NumberFormat at the pinned locale (generate_checkout_currency_format.py)."""
    formats = local_currency.checkout_formats()
    assert len(formats) >= 135
    for code, row in formats.items():
        assert local_currency.display_money(row['sample_minor'], code) == row['sample'], code
        assert row['locale'] == local_currency.checkout_locale(code)
    assert local_currency.display_money(4800, 'jpy') == '¥4,800'
    assert local_currency.display_money(20699, 'gbp') == '£206.99'
    assert local_currency.display_money(56900, 'mxn') == 'MX$569.00'
    assert local_currency.display_money(10999, 'aed') == 'AED\u00a0109.99'
    assert local_currency.display_money(26991, 'usd') == 'US$269.91'
    assert local_currency.display_money(39000, 'krw') == '₩39,000'  # zero-decimal
    assert local_currency.display_money(749000, 'vnd') == '₫749,000'
    assert local_currency.display_money(27990, 'clp') == 'CLP\u00a027,990'
    assert local_currency.display_money(1099000, 'huf') == 'HUF\u00a010,990.00'  # whole hundreds, 2 decimals
    assert local_currency.display_money(99000, 'twd') == 'NT$990.00'
    assert local_currency.display_money(399900, 'isk') == 'ISK\u00a03,999'  # hundredths, no decimals
    assert local_currency.display_money(11000000, 'ugx') == 'UGX\u00a0110,000'


def test_table_rejects_amounts_stripe_or_the_cart_cannot_show(env):
    table = {
        'countries': {'HU': 'huf', 'IS': 'isk', 'TW': 'twd', 'UG': 'ugx', 'JP': 'jpy', 'XX': 'zzz'},
        'currencies': {
            'huf': {'monthly': 1099050, 'annual': 9891000},  # not whole hundreds
            'isk': {'monthly': 399900, 'annual': 3599100},
            'twd': {'monthly': 99000, 'annual': 891000},
            'ugx': {'monthly': 11000050, 'annual': 99000000},
            'jpy': {'monthly': 4800, 'annual': 43200},
            'zzz': {'monthly': 100, 'annual': 900},  # not a Stripe currency
        },
    }
    env.on(table=table)
    assert set(local_currency.load_table().amounts) == {'isk', 'twd', 'jpy'}
    assert local_currency.offer_for('android', 'HU') == local_currency.DEFAULT
    assert local_currency.offer_for('android', 'IS') == local_currency.Offer('local', 'isk')
    assert local_currency.checkout_locale('usd') == stripe_utils.CHECKOUT_LOCALE == 'en-GB'
    assert local_currency.checkout_locale('jpy') == 'en'


# --- available plans (trial paywall) ----------------------------------------------------------


@pytest.fixture
def plans_client(env, monkeypatch):
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: None)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: None)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture'
    return TestClient(app)


ANDROID = {'X-App-Platform': 'android', 'X-App-Version': '1.0.600'}


def test_switch_off_or_empty_table_is_byte_identical(env, plans_client):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    assert b'US$29.99' in baseline
    with_region = {**ANDROID, REGION: 'JP'}
    env.monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(TABLE))
    env.monkeypatch.setenv(local_currency.MODE_ENV, 'off')
    assert plans_client.get('/v1/payments/available-plans', headers=with_region).content == baseline
    env.monkeypatch.setenv(local_currency.MODE_ENV, 'android')
    env.monkeypatch.setenv(local_currency.TABLE_ENV, '')
    assert plans_client.get('/v1/payments/available-plans', headers=with_region).content == baseline


def test_old_app_and_us_buyer_get_todays_catalog(env, plans_client):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    env.on()
    assert plans_client.get('/v1/payments/available-plans', headers=ANDROID).content == baseline
    assert plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'US'}).content == baseline


@pytest.mark.parametrize(
    'region, currency, monthly, yearly',
    [('JP', 'jpy', '¥4,500', '¥40,500'), ('GB', 'gbp', '£22.99', '£206.99'), ('DE', 'eur', '€27.99', '€249.99')],
)
def test_configured_country_sees_its_currency(env, plans_client, region, currency, monthly, yearly):
    env.on()
    plans = plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: region}).json()['plans']
    rows = {row['interval']: row for row in plans}
    assert {row['currency'] for row in plans} == {currency}
    assert rows['month']['id'] == PRO_MONTH and rows['year']['id'] == PRO_YEAR
    assert rows['month']['unit_amount'] == TABLE['currencies'][currency]['monthly']
    assert rows['month']['billing_total'] == monthly
    assert rows['year']['billing_total'] == yearly
    assert 'US$' not in json.dumps(plans)


def test_country_outside_the_table_keeps_todays_usd(env, plans_client):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    env.on()
    assert plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'FR'}).content == baseline


def test_table_currency_missing_from_the_price_falls_back_to_usd_and_logs(env, plans_client, caplog):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    env.on()
    env.monkeypatch.setattr(stripe.Price, 'retrieve', _retrieve_factory({PRO_MONTH: OPTIONS[PRO_MONTH]}))
    with caplog.at_level('WARNING', logger='utils.local_currency'):
        response = plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'JP'})
    assert response.content == baseline  # never a mix, never a currency the Price lacks
    assert any('local currency jpy unavailable on ' + PRO_YEAR in r.getMessage() for r in caplog.records)


# --- the v2 plans sheet ----------------------------------------------------------------------


@pytest.fixture
def sheet_client(env, monkeypatch):
    monkeypatch.setattr(storefront_route.subscription_utils, 'get_usage_units', lambda uid: {})
    monkeypatch.setattr(storefront_route.auth, 'check_rate_limit', lambda *args: (True, 12, 0))
    monkeypatch.setattr(storefront_route.auth, 'RATE_LIMIT_SHADOW', False)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    monkeypatch.setattr(storefront_route, 'should_hide_subscription_ui', lambda *args: False)
    monkeypatch.setattr(storefront_route.users_db, 'get_user_valid_subscription', lambda uid, **kw: Subscription())
    monkeypatch.setattr(storefront_route, '_usage', lambda *args: StorefrontUsage())
    monkeypatch.setattr(storefront_route, '_retrieve_price', lambda price_id: BASE[price_id])
    app = FastAPI()
    app.include_router(storefront_route.router)
    app.dependency_overrides[storefront_route.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture'
    return TestClient(app)


def test_sheet_switch_off_identical_and_local_on(env, sheet_client):
    baseline = sheet_client.get('/v2/payments/plans', headers=ANDROID).content
    env.monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(TABLE))
    assert sheet_client.get('/v2/payments/plans', headers={**ANDROID, REGION: 'JP'}).content == baseline

    env.on()
    assert sheet_client.get('/v2/payments/plans', headers=ANDROID).content == baseline
    sheet = sheet_client.get('/v2/payments/plans', headers={**ANDROID, REGION: 'JP'}).json()
    offer, free = sheet['tiers']
    assert [(p['price_id'], p['currency'], p['amount_minor']) for p in offer['prices']] == [
        (PRO_MONTH, 'jpy', 4500),
        (PRO_YEAR, 'jpy', 40500),
    ]
    assert offer['prices'][0]['headline'] == '¥4,500/month'
    assert free['prices'][0]['currency'] == 'jpy' and free['prices'][0]['headline'] == '¥0'
    assert 'US$' not in json.dumps(sheet)

    assert sheet_client.get('/v2/payments/plans', headers={**ANDROID, REGION: 'FR'}).content == baseline


# --- /v1/users/me/subscription ---------------------------------------------------------------


def _subscription_response():
    return UserSubscriptionResponse(
        subscription=Subscription(),
        transcription_seconds_used=0,
        transcription_seconds_limit=0,
        words_transcribed_used=0,
        words_transcribed_limit=0,
        insights_gained_used=0,
        insights_gained_limit=0,
        available_plans=[
            SubscriptionPlan(
                id='unlimited_v2',
                title='Omi Pro',
                features=[],
                prices=[
                    UserPricingOption(id=PRO_MONTH, title='Monthly', price_string='US$29.99/month'),
                    UserPricingOption(id=PRO_YEAR, title='Annual', price_string='US$269.91/year'),
                ],
            )
        ],
    )


def test_user_subscription_price_strings(env):
    response = _subscription_response()
    users_route._apply_local_currency_offer(response, 'fixture', 'android', 'JP')
    assert response.model_dump() == _subscription_response().model_dump()  # switch off

    env.on()
    users_route._apply_local_currency_offer(response, 'fixture', 'android', None)
    assert response.model_dump() == _subscription_response().model_dump()  # old app
    users_route._apply_local_currency_offer(response, 'fixture', 'android', 'GB')
    assert [p.price_string for p in response.available_plans[0].prices] == ['£22.99/month', '£206.99/year']

    outside = _subscription_response()
    users_route._apply_local_currency_offer(outside, 'fixture', 'android', 'FR')
    assert outside.model_dump() == _subscription_response().model_dump()

    paid = _subscription_response()
    paid.subscription.plan = PlanType.unlimited_v2
    users_route._apply_local_currency_offer(paid, 'fixture', 'android', 'GB')
    assert paid.available_plans[0].prices[0].price_string == 'US$29.99/month'  # subscribers keep theirs


# --- checkout --------------------------------------------------------------------------------


def _checkout(env, region=None, platform='android', currency=None, trial_days=7, customer=None):
    captured = {}

    def create_session(uid, price_id, idempotency_key, **kwargs):
        captured.update(kwargs, price_id=price_id)
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with (
        patch.object(payment, 'is_purchasable_price_id', return_value=True),
        patch.object(payment.subscription_utils, 'can_user_make_payment', return_value=(True, '')),
        patch.object(payment.subscription_utils, 'new_buyer_single_plan_violation', return_value=None),
        patch.object(payment, '_try_reactivate_subscription', return_value=None),
        patch.object(payment.users_db, 'get_stripe_customer_id', return_value=customer),
        patch.object(payment.stripe_utils, 'create_subscription_checkout_session', side_effect=create_session),
    ):
        payment.create_checkout_session_endpoint(
            payment.CreateCheckoutRequest(price_id=PRO_YEAR, trial_days=trial_days, currency=currency),
            uid='fixture',
            x_app_platform=platform,
            x_storefront_region=region,
        )
    return captured


def test_checkout_currency_equals_the_displayed_currency(env):
    assert 'local_currency_code' not in _checkout(env, region='JP')  # switch off: today's call
    env.on()
    assert 'local_currency_code' not in _checkout(env)  # old app
    assert 'local_currency_code' not in _checkout(env, region='US', currency='usd')
    assert _checkout(env, region='JP', currency='jpy')['local_currency_code'] == 'jpy'
    assert _checkout(env, region='JP')['local_currency_code'] == 'jpy'
    with pytest.raises(HTTPException) as shown_usd:
        _checkout(env, region='JP', currency='usd')
    assert shown_usd.value.status_code == 400
    assert 'local_currency_code' not in _checkout(env, region='FR', currency='usd')  # outside the table: USD


def _session_params(env, currency, trial_days=7, promotion_code_id=None):
    captured = {}
    with patch.object(
        stripe_utils.stripe.checkout.Session,
        'create',
        side_effect=lambda **params: captured.update(params) or SimpleNamespace(url='u', id='cs'),
    ):
        stripe_utils.create_subscription_checkout_session(
            'fixture',
            PRO_YEAR,
            'idem',
            trial_period_days=trial_days,
            promotion_code_id=promotion_code_id,
            local_currency_code=currency,
        )
    return captured


def test_cart_is_pinned_to_the_offer_currency_and_amount(env):
    env.on()
    params = _session_params(env, 'jpy', promotion_code_id='promo_fixture')
    assert params['currency'] == 'jpy'
    assert params['locale'] == 'en'
    assert params['adaptive_pricing'] == {'enabled': False}
    assert params['line_items'] == [{'price': PRO_YEAR, 'quantity': 1}]
    assert params['discounts'] == [{'promotion_code': 'promo_fixture'}]
    message = params['custom_text']['submit']['message']
    assert 'charged ¥40,500 a year' in message and 'All amounts are in JPY.' in message
    assert 'US$' not in message

    usd = _session_params(env, None)
    assert usd['currency'] == 'usd' and usd['locale'] == 'en-GB'
    assert 'US$269.91 a year' in usd['custom_text']['submit']['message']

    env.monkeypatch.setattr(stripe.Price, 'retrieve', _retrieve_factory({}))
    with pytest.raises(ValueError):
        _session_params(env, 'jpy')


# --- subscribers billed in a local currency --------------------------------------------------


def _gbp_subscription(**changes):
    now = int(time.time())
    sub = {
        'id': 'sub_gbp_fixture',
        'customer': 'cus_fixture',
        'status': 'active',
        'currency': 'gbp',
        'collection_method': 'charge_automatically',
        'metadata': {'uid': 'fixture'},
        'start_date': now - 40 * 86400,
        'current_period_start': now - 10 * 86400,
        'current_period_end': now + 20 * 86400,
        'items': {'data': [{'id': 'si_fixture', 'quantity': 1, 'price': dict(BASE[PRO_MONTH])}]},
    }
    sub.update(changes)
    return sub


def test_trial_reminder_names_the_local_charge(env):
    trial = _gbp_subscription(status='trialing', trial_end=int(time.time()) + 3 * 86400)
    trial['items']['data'][0]['price'] = dict(BASE[PRO_YEAR])
    usd_trial = {**trial, 'currency': 'usd'}
    with patch.object(trial_reminder, 'get_plan_type_from_price_id', return_value=PlanType.unlimited_v2):
        gbp = trial_reminder.trial_ending_reminder_body('fixture', trial, int(time.time()))
        usd = trial_reminder.trial_ending_reminder_body('fixture', usd_trial, int(time.time()))
        env.monkeypatch.setattr(stripe.Price, 'retrieve', Mock(side_effect=stripe.APIConnectionError('offline')))
        unreadable = trial_reminder.trial_ending_reminder_body('fixture', trial, int(time.time()))
    assert 'charged £206.99 a year' in gbp and 'US$' not in gbp  # switch off, table empty
    assert 'charged US$269.91 a year' in usd  # a USD trial: today's text
    assert unreadable is None  # never a guessed amount


def test_promo_minimum_is_checked_in_the_subscription_currency(env):
    """A USD-only minimum (bundle and prepaid codes) is compared with the same Price's USD
    amount, so a local-currency trial is not charged because its code was refused."""
    sub = _gbp_subscription()
    price = sub['items']['data'][0]['price']
    coupon = {'valid': True, 'percent_off': 50}
    prepaid = {'valid': True, 'percent_off': 100}
    usd_minimum = {'restrictions': {'minimum_amount': 2999, 'minimum_amount_currency': 'usd'}}
    promotion_redemption._check_eligible(usd_minimum, prepaid, sub)  # same plan in USD: redeemable
    usd_too_high = {'restrictions': {'minimum_amount': 3000, 'minimum_amount_currency': 'usd'}}
    with pytest.raises(promotion_redemption.RedemptionError):
        promotion_redemption._check_eligible(usd_too_high, coupon, sub)
    eur_minimum = {'restrictions': {'minimum_amount': 100, 'minimum_amount_currency': 'eur'}}
    with pytest.raises(promotion_redemption.RedemptionError):
        promotion_redemption._check_eligible(eur_minimum, coupon, sub)
    gbp_ok = {
        'restrictions': {
            'minimum_amount': 2000,
            'minimum_amount_currency': 'usd',
            'currency_options': {'gbp': {'minimum_amount': 2000}},
        }
    }
    promotion_redemption._check_eligible(gbp_ok, coupon, sub)
    gbp_high = {'restrictions': {'minimum_amount': 2500, 'minimum_amount_currency': 'gbp'}}
    with pytest.raises(promotion_redemption.RedemptionError):
        promotion_redemption._check_eligible(gbp_high, coupon, sub)
    with pytest.raises(promotion_redemption.RedemptionError):
        promotion_redemption._check_eligible({}, {'valid': True, 'amount_off': 500, 'currency': 'usd'}, sub)
    assert price['currency'] == 'usd'  # the item still carries the base Price


def test_yearly_switch_refuses_a_non_usd_subscription(env):
    assert yearly_switch.refusal(_gbp_subscription()) == 'currency'


def test_retention_offer_shows_the_local_amount(env):  # switch off, table empty
    offer = retention_offer.evaluate(stripe.Subscription.construct_from(_gbp_subscription(), 'k'), {})
    assert (offer.currency, offer.regular_amount, offer.discounted_amount) == ('gbp', 2299, 1149)


@pytest.fixture
def gbp_case(env, monkeypatch):
    env.on()
    obj = _gbp_subscription()
    sub = Subscription(
        plan=PlanType.unlimited_v2,
        status=SubscriptionStatus.active,
        stripe_subscription_id=obj['id'],
        current_price_id=PRO_MONTH,
        current_period_start=obj['current_period_start'],
        current_period_end=obj['current_period_end'],
    )
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: sub)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: sub)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', Mock())
    monkeypatch.setattr(stripe.Subscription, 'retrieve', lambda sid, **kw: stripe.Subscription.construct_from(obj, 'k'))
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'list', lambda **kw: SimpleNamespace(data=[]))
    monkeypatch.setattr(payment, '_release_attached_schedules', Mock())
    schedule_modify = Mock()
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'create', Mock(return_value=SimpleNamespace(id='sched')))
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'modify', schedule_modify)
    monkeypatch.setattr(payment, '_validate_price_id', lambda price_id: None)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: 'fixture'
    app.dependency_overrides[payment.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture'
    client = TestClient(app)
    client.headers['X-Omi-Billing-Currency'] = '1'
    modify = Mock(side_effect=lambda sid, **kw: stripe.Subscription.construct_from({**obj, **_modified(kw)}, 'k'))
    monkeypatch.setattr(stripe.Subscription, 'modify', modify)
    for owner, name in [
        (payment, 'set_credits_invalidation_signal'),
        (payment, 'clear_fair_use_on_upgrade'),
        (payment.conversations_db, 'unlock_all_conversations'),
        (payment.memories_db, 'unlock_all_memories'),
        (payment.action_items_db, 'unlock_all_action_items'),
    ]:
        monkeypatch.setattr(owner, name, Mock())
    return SimpleNamespace(client=client, schedule_modify=schedule_modify, sub=sub, obj=obj, modify=modify)


def _modified(kw):
    price = kw['items'][0]['price']
    return {'items': {'data': [{'id': 'si_fixture', 'quantity': 1, 'price': dict(BASE[price])}]}}


def test_local_subscriber_manages_in_their_currency(gbp_case):
    plans = gbp_case.client.get('/v1/payments/available-plans', headers=ANDROID).json()['plans']
    assert {(row['interval'], row['currency'], row['unit_amount']) for row in plans} == {
        ('month', 'gbp', 2299),
        ('year', 'gbp', 20699),
    }
    response = gbp_case.client.post('/v1/payments/upgrade-subscription', json={'price_id': PRO_YEAR})
    assert response.status_code == 200, response.text
    phases = gbp_case.schedule_modify.call_args.kwargs['phases']
    assert [phase.get('currency') for phase in phases] == ['gbp', 'gbp']


def test_local_subscriber_sheet_shows_their_currency(env, gbp_case, sheet_client):
    env.monkeypatch.setattr(storefront_route.users_db, 'get_user_valid_subscription', lambda uid, **kw: gbp_case.sub)
    with patch.object(storefront_route, '_subscription_billing_currency', return_value='gbp'):
        sheet = sheet_client.get('/v2/payments/plans', headers={**ANDROID, REGION: 'GB'}).json()
    assert sheet['current']['currency'] == 'gbp' and sheet['current']['amount_minor'] == 2299
    assert '£22.99' in sheet['current']['line']
    assert 'US$' not in json.dumps(sheet)


def test_dry_run_script_prints_options_and_never_writes(env, monkeypatch, capsys):
    from scripts import local_currency_options as script

    modify = Mock(side_effect=AssertionError('dry run must not write'))
    monkeypatch.setattr(stripe.Price, 'modify', modify)
    monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(TABLE))
    assert script.main([]) == 0
    calls = json.loads(capsys.readouterr().out)
    assert calls[0]['id'] == PRO_MONTH and calls[1]['id'] == PRO_YEAR
    assert calls[1]['currency_options'] == {
        'eur': {'unit_amount': 24999},
        'gbp': {'unit_amount': 20699},
        'jpy': {'unit_amount': 40500},
    }
    modify.assert_not_called()


def test_legacy_jpy_subscriber_sheet_is_unchanged_when_jpy_is_approved(env):
    """A JPY-native Price is not a currency option: the existing JPY management sheet stays as is."""
    from utils.storefront import build_storefront, load_ladder

    jpy_row = {**_row('price_jpy_fixture', 4800, 'month'), 'currency': 'jpy'}

    def sheet(**extra):
        return build_storefront(
            catalog_revision=6,
            ladder=load_ladder(),
            bindings=[],
            recognized=[],
            subscription=Subscription(plan=PlanType.unlimited_v2, current_price_id='price_jpy_fixture'),
            retrieve_price=lambda key: jpy_row,
            purchasable=lambda key: True,
            usage=StorefrontUsage(),
            **extra,
        ).model_dump()

    baseline = sheet()
    env.on()
    assert sheet(subscription_currency='jpy') == baseline


def test_local_trial_is_charged_in_its_currency_at_trial_end_and_on_renewal(env, gbp_case):
    """A subscription's currency is fixed when Checkout creates it; Stripe bills every invoice
    (trial conversion, renewals) at that currency's option of the item's Price. So the proof is:
    the trial Checkout is created in the local currency, and nothing later changes it."""
    params = _session_params(env, 'gbp')
    assert params['currency'] == 'gbp' and params['subscription_data']['trial_period_days'] == 7
    assert 'currency' not in params['subscription_data'] and params['line_items'][0]['price'] == PRO_YEAR
    assert 'charged £206.99 a year' in params['custom_text']['submit']['message']

    # Interval change during the trial swaps the Price in place; the subscription currency is untouched.
    gbp_case.obj.update(status='trialing', trial_end=int(time.time()) + 5 * 86400)
    response = gbp_case.client.post('/v1/payments/upgrade-subscription', json={'price_id': PRO_YEAR})
    assert response.status_code == 200, response.text
    kwargs = gbp_case.modify.call_args.kwargs
    assert kwargs['items'] == [{'id': 'si_fixture', 'price': PRO_YEAR}] and 'currency' not in kwargs
    assert kwargs['trial_end'] == gbp_case.obj['trial_end']

    # The reminder before the trial ends names the GBP charge, never the base USD price.
    trial = {**gbp_case.obj, 'items': {'data': [{'quantity': 1, 'price': dict(BASE[PRO_YEAR])}]}}
    with patch.object(trial_reminder, 'get_plan_type_from_price_id', return_value=PlanType.unlimited_v2):
        body = trial_reminder.trial_ending_reminder_body('fixture', trial, int(time.time()))
    assert body is not None and '£206.99 a year' in body and 'US$' not in body


def test_rollback_keeps_every_subscriber_surface_in_the_subscription_currency(env, gbp_case, sheet_client):
    """Switch off and table emptied after a GBP subscription exists: Stripe still bills
    £, so every surface still says £ (the billed currency comes from Stripe alone)."""
    env.monkeypatch.delenv(local_currency.MODE_ENV)
    env.monkeypatch.delenv(local_currency.TABLE_ENV)
    plans = gbp_case.client.get('/v1/payments/available-plans', headers=ANDROID).json()['plans']
    assert {(row['currency'], row['unit_amount']) for row in plans} == {('gbp', 2299), ('gbp', 20699)}

    env.monkeypatch.setattr(storefront_route.users_db, 'get_user_valid_subscription', lambda uid, **kw: gbp_case.sub)
    sheet = sheet_client.get('/v2/payments/plans', headers=ANDROID).json()  # real currency lookup
    assert (sheet['current']['currency'], sheet['current']['amount_minor']) == ('gbp', 2299)
    assert 'US$' not in json.dumps(sheet)

    offer = retention_offer.evaluate(stripe.Subscription.construct_from(gbp_case.obj, 'k'), {})
    assert (offer.currency, offer.regular_amount) == ('gbp', 2299)
    with patch.object(trial_reminder, 'get_plan_type_from_price_id', return_value=PlanType.unlimited_v2):
        body = trial_reminder.trial_ending_reminder_body(
            'fixture', {**gbp_case.obj, 'status': 'trialing', 'trial_end': int(time.time()) + 86400}, int(time.time())
        )
    assert body is not None and '£22.99 a month' in body
    promotion_redemption._check_eligible({}, {'valid': True, 'percent_off': 100}, gbp_case.obj)

    env.monkeypatch.setattr(storefront_route.redis_db, 'get_generic_cache', Mock(side_effect=RuntimeError('down')))
    unreadable = sheet_client.get('/v2/payments/plans', headers=ANDROID).json()
    assert unreadable['current'].get('amount_minor') is None and 'US$' not in json.dumps(unreadable['current'])


def test_lapsed_usd_customer_in_a_table_country_stays_in_usd(env, plans_client):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    env.on()
    env.lapsed('usd')
    assert plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'GB'}).content == baseline
    assert 'local_currency_code' not in _checkout(
        env, region='GB', currency='usd', customer='cus_lapsed_fixture', trial_days=None
    )
    with pytest.raises(HTTPException):
        _checkout(env, region='GB', currency='gbp', customer='cus_lapsed_fixture', trial_days=None)  # a stale £ page


@pytest.mark.parametrize('mode', ['android', None])
def test_lapsed_gbp_customer_who_moved_to_the_us_keeps_gbp(env, plans_client, mode):
    if mode:
        env.on(mode)
    env.lapsed('gbp')
    plans = plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'US'}).json()['plans']
    assert {(row['currency'], row['billing_total']) for row in plans} == {('gbp', '£22.99'), ('gbp', '£206.99')}
    checkout = _checkout(env, region='US', currency='gbp', customer='cus_lapsed_fixture', trial_days=None)
    assert checkout['local_currency_code'] == 'gbp'


def test_customer_currency_the_price_lacks_falls_back_to_usd(env, plans_client):
    baseline = plans_client.get('/v1/payments/available-plans', headers=ANDROID).content
    env.lapsed('chf')  # not an option on these Prices: today's USD path, nothing Checkout would refuse first
    assert plans_client.get('/v1/payments/available-plans', headers=ANDROID).content == baseline


def test_released_currencies_reach_the_app_unchanged_with_the_switch_off():
    """With the switch off only USD and JPY Prices exist (catalog and management bindings),
    and both render exactly as before in the shared Checkout table."""
    from config.plan_catalog import MANAGEMENT_CURRENCY_PRICES

    catalog_currencies = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'currency' and isinstance(value, str):
                    catalog_currencies.add(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads((Path(__file__).resolve().parents[2] / 'config/plan_catalog.json').read_text()))
    assert catalog_currencies | {b['currency'] for b in MANAGEMENT_CURRENCY_PRICES.values()} <= {'usd', 'jpy'}
    assert local_currency.display_money(2999, 'usd') == 'US$29.99'
    assert local_currency.display_money(4800, 'jpy') == '¥4,800'


class _FakeStripe:
    """Records writes; serves Prices with given options and a subscription list."""

    def __init__(self, options, subscriptions=()):
        self.writes = []
        outer = self

        class Price:
            @staticmethod
            def retrieve(price_id, expand=None):
                row = {**BASE[price_id], 'currency_options': {'usd': {'unit_amount': BASE[price_id]['unit_amount']}}}
                row['currency_options'].update(options.get(price_id, {}))
                return stripe.Price.construct_from(row, 'k')

            @staticmethod
            def modify(price_id, **kwargs):
                outer.writes.append((price_id, kwargs))

        class Subscription:
            @staticmethod
            def list(price, status, limit):
                rows = [sub for sub in subscriptions if sub['price'] == price]
                return SimpleNamespace(auto_paging_iter=lambda: iter(rows))

        self.Price, self.Subscription = Price, Subscription


def test_apply_reads_both_prices_and_refuses_a_different_amount(env, monkeypatch, capsys):
    from scripts import local_currency_options as script

    monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(TABLE))
    assert script.main(['--apply'], stripe_module=_FakeStripe({})) == 2  # needs --confirm
    conflict = _FakeStripe({PRO_YEAR: {'gbp': {'unit_amount': 19999}}})
    assert script.main(['--apply', '--confirm'], stripe_module=conflict) == 2
    assert conflict.writes == []
    assert 'live 19999, table 20699' in capsys.readouterr().err

    partial = _FakeStripe({PRO_MONTH: {'gbp': {'unit_amount': 2299}}})
    assert script.main(['--apply', '--confirm'], stripe_module=partial) == 0
    out = capsys.readouterr().out
    assert 'existing currency_options' in out and '"gbp"' in out
    assert [(price_id, sorted(kw['currency_options'])) for price_id, kw in partial.writes] == [
        (PRO_MONTH, ['eur', 'jpy']),
        (PRO_YEAR, ['eur', 'gbp', 'jpy']),
    ]


def test_apply_refuses_a_table_with_dropped_entries(env, monkeypatch, capsys):
    from scripts import local_currency_options as script

    bad = {**TABLE, 'currencies': {**TABLE['currencies'], 'huf': {'monthly': 1099050, 'annual': 9891000}}}
    monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(bad))
    fake = _FakeStripe({})
    assert script.main(['--apply', '--confirm'], stripe_module=fake) == 2
    assert fake.writes == [] and 'currency huf' in capsys.readouterr().err


def test_count_non_usd_subscriptions_is_read_only(env, capsys):
    from scripts import local_currency_options as script

    subs = [
        {'price': PRO_MONTH, 'currency': 'eur', 'status': 'active'},
        {'price': PRO_MONTH, 'currency': 'usd', 'status': 'active'},
        {'price': PRO_MONTH, 'currency': 'eur', 'status': 'canceled'},
        {'price': PRO_YEAR, 'currency': 'gbp', 'status': 'trialing'},
    ]
    fake = _FakeStripe({}, subs)
    assert script.main(['--count-non-usd-subscriptions'], stripe_module=fake) == 0
    assert json.loads(capsys.readouterr().out) == {PRO_MONTH: {'eur': 1}, PRO_YEAR: {'gbp': 1}}
    assert fake.writes == []
