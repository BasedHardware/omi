"""Local-currency offers for new buyers (Google Play Subscriptions policy). Default off.

Google Play rejected Android builds because a non-US reviewer saw the trial offer in
US$. This module decides, per request, whether a buyer with no paid subscription is
offered the plan price in a local currency, today's USD price, or no purchase price.

Two operator inputs, both empty by default, so every response stays as it is today:

- ``STOREFRONT_LOCAL_CURRENCY``: ``off`` (default), ``android`` or ``all``.
- ``STOREFRONT_LOCAL_CURRENCY_TABLE``: JSON ``{"countries": {"JP": "jpy"},
  "currencies": {"jpy": {"monthly": 4500, "annual": 40500}}}``. Amounts are Stripe
  minor units and are the operator's approval, not the display source.

Stripe stays the price authority (plan-source-of-truth.md): a local amount is the
Price's own ``currency_options`` entry, shown only when it equals the approved table
amount. Checkout charges that same entry, so the cart matches the offer page.

The country is the device region the app sends in ``X-Omi-Storefront-Region``. A
request without it (every released build) keeps today's behaviour.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Literal, Mapping, Optional

logger = logging.getLogger(__name__)

REGION_HEADER = 'X-Omi-Storefront-Region'
MODE_ENV = 'STOREFRONT_LOCAL_CURRENCY'
TABLE_ENV = 'STOREFRONT_LOCAL_CURRENCY_TABLE'
MODES = ('off', 'android', 'all')
INTERVAL_KEYS = {'month': 'monthly', 'year': 'annual'}

_REGION = re.compile(r'^[A-Z]{2}$')
_CURRENCY = re.compile(r'^[a-z]{3}$')

# Stripe charge units, as in utils.storefront_copy.
_ZERO_DECIMAL = frozenset(
    {'bif', 'clp', 'djf', 'gnf', 'jpy', 'kmf', 'krw', 'mga', 'pyg', 'rwf', 'vnd', 'vuv', 'xaf', 'xof', 'xpf'}
)
_THREE_DECIMAL = frozenset({'bhd', 'jod', 'kwd', 'omr', 'tnd'})

# The symbol Stripe Checkout renders for each currency at checkout_locale(currency):
# CLDR `en` for non-USD, `en-GB` for USD. The app (lib/utils/billing_price.dart) uses
# the same table, so offer page and cart show one string. Others use "CODE ".
_SYMBOLS = {
    'usd': 'US$',
    'jpy': '¥',
    'gbp': '£',
    'eur': '€',
    'aud': 'A$',
    'cad': 'CA$',
    'mxn': 'MX$',
    'brl': 'R$',
    'inr': '₹',
    'krw': '₩',
    'nzd': 'NZ$',
    'hkd': 'HK$',
}


@dataclass(frozen=True)
class Table:
    countries: dict[str, str]
    amounts: dict[str, dict[str, int]]


@dataclass(frozen=True)
class Offer:
    """``default``: today's behaviour. ``local``: price in ``currency``. ``hidden``: no purchase UI."""

    kind: Literal['default', 'local', 'hidden']
    currency: Optional[str] = None

    @property
    def is_default(self) -> bool:
        return self.kind == 'default'


DEFAULT = Offer('default')
HIDDEN = Offer('hidden')


def mode() -> str:
    raw = (os.getenv(MODE_ENV) or 'off').strip().lower()
    return raw if raw in MODES else 'off'


def load_table() -> Table:
    """Parse the operator table. Anything malformed is dropped, never guessed."""
    raw = (os.getenv(TABLE_ENV) or '').strip()
    if not raw:
        return Table({}, {})
    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning('%s is not JSON; local currency stays off', TABLE_ENV)
        return Table({}, {})
    if not isinstance(payload, dict):
        return Table({}, {})
    amounts: dict[str, dict[str, int]] = {}
    for currency, row in (payload.get('currencies') or {}).items():
        if not isinstance(currency, str) or not _CURRENCY.fullmatch(currency) or not isinstance(row, dict):
            continue
        values = {key: row.get(key) for key in INTERVAL_KEYS.values()}
        if all(type(value) is int and value > 0 for value in values.values()):
            amounts[currency] = values  # type: ignore[assignment]
    countries: dict[str, str] = {}
    for country, currency in (payload.get('countries') or {}).items():
        if not isinstance(country, str) or not _REGION.fullmatch(country) or not isinstance(currency, str):
            continue
        if currency == 'usd' or currency in amounts:
            countries[country] = currency
    return Table(countries, amounts)


def normalize_region(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    value = raw.strip().upper()
    return value if _REGION.fullmatch(value) else None


def offer_for(platform: Any, region: Any) -> Offer:
    """Which offer a buyer with no paid subscription gets, before checking Stripe."""
    selected = mode()
    if selected == 'off':
        return DEFAULT
    normalized_platform = platform.strip().lower() if isinstance(platform, str) else ''
    if selected == 'android' and normalized_platform != 'android':
        return DEFAULT
    country = normalize_region(region)
    if country is None:
        return DEFAULT
    table = load_table()
    if not table.countries or country == 'US':
        return DEFAULT
    currency = table.countries.get(country)
    if currency == 'usd':
        return DEFAULT
    if currency:
        return Offer('local', currency)
    return unconfigured(normalized_platform)


def unconfigured(platform: Any) -> Offer:
    """No approved local price: Android shows no price at all; other platforms keep today's USD."""
    normalized = platform.strip().lower() if isinstance(platform, str) else ''
    return HIDDEN if normalized == 'android' else DEFAULT


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def option_amount(price: Any, currency: str) -> Optional[int]:
    """Stripe's ``currency_options[currency].unit_amount``; None when absent."""
    if _get(price, 'currency') == currency:
        amount = _get(price, 'unit_amount')
        return amount if type(amount) is int and amount > 0 else None
    options = _get(price, 'currency_options')
    option = _get(options, currency) if options is not None else None
    amount = _get(option, 'unit_amount') if option is not None else None
    return amount if type(amount) is int and amount > 0 else None


def approved_amount(price: Any, currency: str) -> Optional[int]:
    """The local amount for a new buyer: Stripe's option, only when it equals the table."""
    recurring = _get(price, 'recurring')
    interval = _get(recurring, 'interval') if recurring is not None else None
    key = INTERVAL_KEYS.get(interval) if isinstance(interval, str) else None
    if key is None or _get(price, 'currency') == currency:
        return None
    expected = load_table().amounts.get(currency, {}).get(key)
    amount = option_amount(price, currency)
    if expected is None or amount != expected:
        return None
    return amount


def localize_rows(rows: Iterable[dict[str, Any]], currency: str) -> Optional[list[dict[str, Any]]]:
    """Copies of Stripe price rows re-expressed in ``currency``, or None when any row lacks it.

    The price id stays the same: Checkout selects the currency option on that Price.
    """
    localized = []
    for row in rows:
        amount = approved_amount(row, currency)
        if amount is None:
            return None
        localized.append({**row, 'currency': currency, 'unit_amount': amount})
    return localized


def table_currency(currency: Any) -> bool:
    """A currency the operator approved, for managing a subscription already billed in it."""
    return isinstance(currency, str) and currency in load_table().amounts


def billed_in_option(price: Any, subscription_currency: Any) -> bool:
    """True when a subscription is billed through a table currency option of ``price``.

    A subscription on a multi-currency Price carries the base Price (USD) on its item;
    Stripe bills the ``currency_options`` entry for the subscription currency. Other
    currency mismatches (older Adaptive Pricing conversions) keep today's handling.
    """
    return (
        isinstance(subscription_currency, str)
        and _get(price, 'currency') != subscription_currency
        and table_currency(subscription_currency)
    )


def option_amount_for(price: Any, currency: str, retrieve: Optional[Callable[[str], Any]] = None) -> Optional[int]:
    """``option_amount``, expanding the Price when the caller's copy lacks currency_options."""
    amount = option_amount(price, currency)
    price_id = _get(price, 'id')
    if amount is None and isinstance(price_id, str):
        try:
            amount = option_amount((retrieve or retrieve_with_options)(price_id), currency)
        except Exception as exc:  # noqa: BLE001 - unknown amount, caller refuses
            logger.warning('currency option lookup failed: %s', type(exc).__name__)
            return None
    return amount


def retrieve_with_options(price_id: str) -> Any:
    """A Stripe Price with its ``currency_options`` (not returned unless expanded)."""
    import stripe

    return stripe.Price.retrieve(price_id, expand=['currency_options'])


def checkout_locale(currency: str) -> str:
    """Checkout locale whose currency glyph matches the app for ``currency``.

    `en-GB` renders USD as US$ (#25494). For other currencies `en` renders the CLDR
    `en` symbol in _SYMBOLS; `en-GB` would render JPY as JP¥ instead of ¥.
    """
    return 'en-GB' if currency.lower() == 'usd' else 'en'


def display_money(amount_minor: int, currency: str) -> str:
    """The app's billing price string (formatBillingPrice): symbol, en grouping, full decimals."""
    code = currency.strip().lower()
    exponent = 0 if code in _ZERO_DECIMAL else (3 if code in _THREE_DECIMAL else 2)
    quantizer = Decimal('1') if exponent == 0 else Decimal(10) ** -exponent
    amount = (Decimal(amount_minor) / (Decimal(10) ** exponent)).quantize(quantizer, rounding=ROUND_HALF_UP)
    rendered = f'{amount:,.{exponent}f}' if exponent else f'{int(amount):,}'
    return f'{_SYMBOLS.get(code, code.upper() + " ")}{rendered}'
