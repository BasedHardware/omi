"""Regression: a paid-app update with a missing or non-numeric price must not 500.

routers.apps.update_app passes the raw request price straight into
utils.apps.upsert_app_payment_link, which does int(price * 100) to build a Stripe recurring
price. A null price (is_paid toggled on without a price) or a non-numeric value used to raise
TypeError/ValueError. The guard treats any non-positive or non-numeric price like the existing
price==0 case: it skips link creation and returns without crashing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import utils.apps as apps_mod
from utils.apps import upsert_app_payment_link


def _app_data(**over):
    data = {
        'id': 'app1',
        'name': 'Test App',
        'category': 'productivity',
        'author': 'Zach',
        'description': 'desc',
        'image': 'https://storage.googleapis.com/x/y.png',
        'capabilities': [],
        'uid': 'u1',
        'is_paid': True,
        'payment_plan': 'monthly_recurring',
        'price': 5.0,
    }
    data.update(over)
    return data


@pytest.fixture
def stripe_mock(monkeypatch):
    monkeypatch.setattr(apps_mod, 'get_app_by_id_db', lambda app_id: _app_data())
    monkeypatch.setattr(apps_mod, 'get_stripe_connect_account_id', lambda uid: 'acct_1')
    monkeypatch.setattr(apps_mod, 'update_app_in_db', lambda *a, **k: None)
    stripe = MagicMock()
    stripe.create_product.return_value = SimpleNamespace(id='prod_1')
    stripe.create_app_monthly_recurring_price.return_value = SimpleNamespace(id='price_1')
    stripe.create_app_payment_link.return_value = SimpleNamespace(id='link_1', url='https://pay/x')
    monkeypatch.setattr(apps_mod, 'stripe', stripe)
    return stripe


@pytest.mark.parametrize('bad_price', [None, '5.0', 'abc', -1, 0, True])
def test_invalid_price_skips_link_without_crashing(stripe_mock, bad_price):
    # Must not raise, and must not attempt to build a Stripe price from a bad value.
    upsert_app_payment_link('app1', True, bad_price, 'monthly_recurring', 'u1')
    stripe_mock.create_app_monthly_recurring_price.assert_not_called()


def test_valid_price_creates_the_recurring_price(stripe_mock):
    upsert_app_payment_link('app1', True, 5.0, 'monthly_recurring', 'u1')
    stripe_mock.create_app_monthly_recurring_price.assert_called_once()
    # int(5.0 * 100) == 500 cents, the exact value that used to crash on a bad price.
    assert stripe_mock.create_app_monthly_recurring_price.call_args[0][1] == 500


@pytest.mark.parametrize(
    'price, expected_cents',
    [(5.0, 500), (10.0, 1000), (0.99, 99), (9.99, 999), (29.99, 2999), (1.5, 150), (100.0, 10000)],
)
def test_price_is_billed_in_whole_cents(stripe_mock, price, expected_cents):
    """The amount handed to Stripe is the price in cents."""
    upsert_app_payment_link('app1', True, price, 'monthly_recurring', 'u1')
    assert stripe_mock.create_app_monthly_recurring_price.call_args[0][1] == expected_cents


@pytest.mark.parametrize(
    'price, expected_cents',
    [(19.99, 1999), (8.29, 829), (0.29, 29), (1.13, 113), (2.01, 201), (43.15, 4315)],
)
def test_binary_float_prices_are_not_underbilled_by_a_cent(stripe_mock, price, expected_cents):
    """Prices whose cent value is not exactly representable must round, not truncate.

    int(19.99 * 100) is 1998, so an app listed at $19.99 had a Stripe price created at
    $19.98 while App.price kept saying 19.99 — the database and Stripe disagreed
    permanently and every buyer was undercharged a cent.
    """
    upsert_app_payment_link('app1', True, price, 'monthly_recurring', 'u1')
    assert stripe_mock.create_app_monthly_recurring_price.call_args[0][1] == expected_cents


def test_no_price_in_the_common_range_is_underbilled(stripe_mock):
    """No price in $0.01..$100.00 may be billed fewer cents than it is worth."""
    wrong = []
    for cents in range(1, 10001):
        price = cents / 100
        upsert_app_payment_link('app1', True, price, 'monthly_recurring', 'u1')
        if stripe_mock.create_app_monthly_recurring_price.call_args[0][1] != cents:
            wrong.append(price)
    assert wrong == []
