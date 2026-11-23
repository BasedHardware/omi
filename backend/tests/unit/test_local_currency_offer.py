"""Local-currency offers for Google Play's Subscriptions policy (utils/local_currency.py).

Play rejected Android builds because a non-US reviewer saw the trial offer in US$. With
``STOREFRONT_LOCAL_CURRENCY`` on and an approved table, a buyer whose device region has
an approved price sees it in that currency on every surface and Checkout charges the
same Stripe ``currency_options`` entry; an Android buyer elsewhere sees no price. With
the switch off or the table empty every response is byte-identical to today, and a
build that sends no region keeps today's behaviour.
"""

import json
import time
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

    def on(mode='android', table=TABLE):
        monkeypatch.setenv(local_currency.MODE_ENV, mode)
        monkeypatch.setenv(local_currency.TABLE_ENV, json.dumps(table))

    return SimpleNamespace(on=on, monkeypatch=monkeypatch)


# --- the decision -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    'mode, platform, region, expected',
    [
        ('off', 'android', 'JP', local_currency.DEFAULT),
        ('android', 'android', 'JP', local_currency.Offer('local', 'jpy')),
        ('android', 'android', 'gb', local_currency.Offer('local', 'gbp')),
        ('android', 'android', 'US', local_currency.DEFAULT),
        ('android', 'android', 'EC', local_currency.DEFAULT),  # a USD country is the US price
        ('android', 'android', 'FR', local_currency.HIDDEN),  # no approved price on Android
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


def test_display_money_matches_the_app_and_checkout_locale():
    assert local_currency.display_money(4500, 'jpy') == '¥4,500'
    assert local_currency.display_money(20699, 'gbp') == '£206.99'
    assert local_currency.display_money(54900, 'mxn') == 'MX$549.00'
    assert local_currency.display_money(10999, 'aed') == 'AED 109.99'
    assert local_currency.display_money(26991, 'usd') == 'US$269.91'
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


def test_unknown_country_on_android_gets_no_price(env, plans_client):
    env.on()
    response = plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'FR'})
    assert response.status_code == 200
    assert response.json() == {'plans': []}


def test_stripe_without_the_option_hides_instead_of_mixing(env, plans_client):
    env.on()
    env.monkeypatch.setattr(stripe.Price, 'retrieve', _retrieve_factory({PRO_MONTH: OPTIONS[PRO_MONTH]}))
    response = plans_client.get('/v1/payments/available-plans', headers={**ANDROID, REGION: 'JP'})
    assert response.json() == {'plans': []}


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

    hidden = sheet_client.get('/v2/payments/plans', headers={**ANDROID, REGION: 'FR'}).json()
    assert hidden['show_subscription_ui'] is False and hidden['tiers'] == []


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


def test_user_subscription_price_strings_and_hide_flag(env):
    response = _subscription_response()
    users_route._apply_local_currency_offer(response, 'android', 'JP')
    assert response.model_dump() == _subscription_response().model_dump()  # switch off

    env.on()
    users_route._apply_local_currency_offer(response, 'android', None)
    assert response.model_dump() == _subscription_response().model_dump()  # old app
    users_route._apply_local_currency_offer(response, 'android', 'GB')
    assert [p.price_string for p in response.available_plans[0].prices] == ['£22.99/month', '£206.99/year']

    hidden = _subscription_response()
    users_route._apply_local_currency_offer(hidden, 'android', 'FR')
    assert hidden.show_subscription_ui is False and hidden.available_plans == []

    paid = _subscription_response()
    paid.subscription.plan = PlanType.unlimited_v2
    users_route._apply_local_currency_offer(paid, 'android', 'FR')
    assert paid.show_subscription_ui is True  # a subscriber keeps managing their plan


# --- checkout --------------------------------------------------------------------------------


def _checkout(env, region=None, platform='android', currency=None, trial_days=7):
    captured = {}

    def create_session(uid, price_id, idempotency_key, **kwargs):
        captured.update(kwargs, price_id=price_id)
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with (
        patch.object(payment, 'is_purchasable_price_id', return_value=True),
        patch.object(payment.subscription_utils, 'can_user_make_payment', return_value=(True, '')),
        patch.object(payment.subscription_utils, 'new_buyer_single_plan_violation', return_value=None),
        patch.object(payment, '_try_reactivate_subscription', return_value=None),
        patch.object(payment.users_db, 'get_stripe_customer_id', return_value=None),
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
    with pytest.raises(HTTPException) as unknown:
        _checkout(env, region='FR')
    assert unknown.value.status_code == 400  # the app shows a 400's detail; 409 means 'already subscribed'


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
    with patch.object(trial_reminder, 'get_plan_type_from_price_id', return_value=PlanType.unlimited_v2):
        before = trial_reminder.trial_ending_reminder_body('fixture', trial, int(time.time()))
        env.on()
        after = trial_reminder.trial_ending_reminder_body('fixture', trial, int(time.time()))
    assert 'US$269.91' in before  # table without gbp: today's text, byte for byte
    assert 'charged £206.99 a year' in after and 'US$' not in after


def test_promo_minimum_is_checked_in_the_subscription_currency(env):
    env.on()
    sub = _gbp_subscription()
    price = sub['items']['data'][0]['price']
    coupon = {'valid': True, 'percent_off': 50}
    usd_minimum = {'restrictions': {'minimum_amount': 2000, 'minimum_amount_currency': 'usd'}}
    with pytest.raises(promotion_redemption.RedemptionError):
        promotion_redemption._check_eligible(usd_minimum, coupon, sub)
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
    env.on()
    assert yearly_switch.refusal(_gbp_subscription()) == 'currency'


def test_retention_offer_shows_the_local_amount(env):
    env.on()
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
    return SimpleNamespace(client=client, schedule_modify=schedule_modify, sub=sub)


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
