#!/usr/bin/env python3
"""Add the local-currency table's ``currency_options`` to Omi Pro's two Prices. Dry run by default.

The table is ``STOREFRONT_LOCAL_CURRENCY_TABLE`` (utils/local_currency.py), read from the
environment or ``--table FILE``. The two Prices are Omi Pro's monthly and annual prices
(``STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID`` / ``..._ANNUAL_PRICE_ID``) unless given with
``--monthly-price`` / ``--annual-price``.

Modes:
- default (dry run): offline. Prints the exact ``stripe.Price.modify`` calls; no key, no network.
- ``--count-non-usd-subscriptions``: read-only, ``STRIPE_READ_API_KEY``. Counts live subscriptions
  on the two Prices whose currency is not USD (older Adaptive Pricing conversions), by currency.
  A manually added option overrides Adaptive Pricing for that currency, so run this first.
- ``--apply --confirm``: ``STRIPE_API_KEY``. Reads both Prices and prints their existing
  ``currency_options``; refuses (exit 2) before any write if the table dropped an entry or a
  table currency already exists on a Price with a different amount; then adds only the
  missing currencies. An operator action for the price owner, never a code-change workflow.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import local_currency  # noqa: E402

PRICE_ENVS = {
    'monthly': 'STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID',
    'annual': 'STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID',
}
READ_KEY_ENV = 'STRIPE_READ_API_KEY'
WRITE_KEY_ENV = 'STRIPE_API_KEY'
LIVE_STATUSES = frozenset({'active', 'trialing', 'past_due', 'unpaid', 'paused'})


class Refused(Exception):
    pass


def dropped_entries(raw: dict, table: local_currency.Table) -> list[str]:
    """Table entries the parser refused (logged there); any of them blocks --apply."""
    countries = raw.get('countries') or {}
    currencies = raw.get('currencies') or {}
    dropped = [f'currency {code}' for code in currencies if code not in table.amounts]
    dropped += [f'country {code}' for code in countries if code not in table.countries]
    return dropped


def planned_calls(table: local_currency.Table, prices: dict[str, str]) -> list[dict]:
    """One ``stripe.Price.modify`` call per price, adding every table currency."""
    if not table.amounts:
        raise ValueError('the local-currency table has no currencies')
    calls = []
    for key in ('monthly', 'annual'):
        price_id = prices.get(key)
        if not price_id:
            raise ValueError(f'{key} price id is missing')
        options = {currency: {'unit_amount': row[key]} for currency, row in sorted(table.amounts.items())}
        calls.append({'call': 'stripe.Price.modify', 'id': price_id, 'currency_options': options})
    return calls


def guarded_calls(calls: list[dict], existing: dict[str, dict]) -> list[dict]:
    """Only currencies missing on each Price; Refused if one exists with a different amount."""
    conflicts, guarded = [], []
    for call in calls:
        current = existing.get(call['id']) or {}
        missing = {}
        for currency, option in call['currency_options'].items():
            have = (current.get(currency) or {}).get('unit_amount')
            if have is None:
                missing[currency] = option
            elif have != option['unit_amount']:
                conflicts.append(f"{call['id']} {currency}: live {have}, table {option['unit_amount']}")
        if missing:
            guarded.append({**call, 'currency_options': missing})
    if conflicts:
        raise Refused('existing currency_options differ from the table: ' + '; '.join(conflicts))
    return guarded


def existing_options(stripe_module, price_ids: list[str]) -> dict[str, dict]:
    out = {}
    for price_id in price_ids:
        price = stripe_module.Price.retrieve(price_id, expand=['currency_options']).to_dict_recursive()
        out[price_id] = {
            code: {'unit_amount': option.get('unit_amount')}
            for code, option in (price.get('currency_options') or {}).items()
        }
    return out


def count_non_usd(stripe_module, price_ids: list[str]) -> dict[str, dict[str, int]]:
    """Live subscriptions on each Price whose currency is not USD, by currency. Read-only."""
    counts: dict[str, dict[str, int]] = {}
    for price_id in price_ids:
        per_currency: dict[str, int] = {}
        for sub in stripe_module.Subscription.list(price=price_id, status='all', limit=100).auto_paging_iter():
            currency = (sub.get('currency') or '').lower()
            if sub.get('status') in LIVE_STATUSES and currency != 'usd':
                per_currency[currency] = per_currency.get(currency, 0) + 1
        counts[price_id] = per_currency
    return counts


def main(argv: list[str] | None = None, stripe_module=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--table', help='JSON file in the STOREFRONT_LOCAL_CURRENCY_TABLE shape')
    parser.add_argument('--monthly-price', default=os.getenv(PRICE_ENVS['monthly']))
    parser.add_argument('--annual-price', default=os.getenv(PRICE_ENVS['annual']))
    parser.add_argument('--count-non-usd-subscriptions', action='store_true', help=f'read-only, {READ_KEY_ENV}')
    parser.add_argument('--apply', action='store_true', help=f'write to Stripe with {WRITE_KEY_ENV} (price owner only)')
    parser.add_argument('--confirm', action='store_true', help='required with --apply')
    args = parser.parse_args(argv)
    prices = {'monthly': args.monthly_price, 'annual': args.annual_price}
    price_ids = [price_id for price_id in prices.values() if price_id]

    if args.count_non_usd_subscriptions:
        stripe_module = stripe_module or _stripe(READ_KEY_ENV)
        print(json.dumps(count_non_usd(stripe_module, price_ids), indent=2, sort_keys=True))
        return 0

    raw = json.loads(Path(args.table).read_text()) if args.table else json.loads(os.environ[local_currency.TABLE_ENV])
    os.environ[local_currency.TABLE_ENV] = json.dumps(raw)
    table = local_currency.load_table()
    dropped = dropped_entries(raw, table)
    calls = planned_calls(table, prices)
    if not args.apply:
        print(json.dumps(calls, indent=2, sort_keys=True))
        print(f'dropped entries: {dropped or "none"}', file=sys.stderr)
        print('Dry run: nothing was sent to Stripe. Re-run with --apply --confirm to write.', file=sys.stderr)
        return 0
    if not args.confirm:
        print('--apply needs --confirm', file=sys.stderr)
        return 2
    try:
        if dropped:
            raise Refused(f'the table dropped entries: {dropped}')
        stripe_module = stripe_module or _stripe(WRITE_KEY_ENV)
        existing = existing_options(stripe_module, price_ids)
        print('existing currency_options: ' + json.dumps(existing, indent=2, sort_keys=True))
        guarded = guarded_calls(calls, existing)
    except Refused as refused:
        print(f'refused: {refused}', file=sys.stderr)
        return 2
    for call in guarded:
        stripe_module.Price.modify(call['id'], currency_options=call['currency_options'])
        print(f"updated {call['id']}: added {sorted(call['currency_options'])}", file=sys.stderr)
    if not guarded:
        print('nothing to add', file=sys.stderr)
    return 0


def _stripe(key_env: str):
    import stripe

    stripe.api_key = os.environ[key_env]
    return stripe


if __name__ == '__main__':
    sys.exit(main())
