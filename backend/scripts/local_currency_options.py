#!/usr/bin/env python3
"""Print the Stripe ``currency_options`` the local-currency table would add. Dry run by default.

The table is ``STOREFRONT_LOCAL_CURRENCY_TABLE`` (utils/local_currency.py), read from the
environment or ``--table FILE``. The two prices are Omi Pro's configured monthly and
annual prices (``STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID`` / ``..._ANNUAL_PRICE_ID``) unless
given with ``--monthly-price`` / ``--annual-price``.

Without ``--apply`` nothing reaches Stripe: the script prints the exact
``stripe.Price.modify`` calls. ``--apply`` performs them with ``STRIPE_API_KEY``; it is an
operator action for the price owner, never part of a code-change workflow.
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


def _table(path: str | None) -> local_currency.Table:
    if path:
        os.environ[local_currency.TABLE_ENV] = Path(path).read_text()
    return local_currency.load_table()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--table', help='JSON file in the STOREFRONT_LOCAL_CURRENCY_TABLE shape')
    parser.add_argument('--monthly-price', default=os.getenv(PRICE_ENVS['monthly']))
    parser.add_argument('--annual-price', default=os.getenv(PRICE_ENVS['annual']))
    parser.add_argument('--apply', action='store_true', help='write to Stripe (price owner only)')
    args = parser.parse_args(argv)

    calls = planned_calls(_table(args.table), {'monthly': args.monthly_price, 'annual': args.annual_price})
    print(json.dumps(calls, indent=2, sort_keys=True))
    if not args.apply:
        print('Dry run: nothing was sent to Stripe. Re-run with --apply to write.', file=sys.stderr)
        return 0

    import stripe

    stripe.api_key = os.environ['STRIPE_API_KEY']
    for call in calls:
        stripe.Price.modify(call['id'], currency_options=call['currency_options'])
        print(f"updated {call['id']}", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
