#!/usr/bin/env python3
"""Fixture-only Stripe price proposal. No credentials, network, or write SDK.

Amounts are proposal inputs, never runtime display prices. An inventory fixture
is an offline export with products/prices arrays; this tool cannot fetch it.
"""

import argparse
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def proposal(ladder: dict, catalog: dict, inventory: dict) -> dict:
    products = {row['plan_id']: row['product_id'] for row in catalog['recognized_stripe_products']}
    calls = []
    registrations = []
    for tier in ladder['tiers']:
        for interval, amount in tier.get('proposed_prices', {}).items():
            plan = tier['plan_id']
            placeholder = f'<created_{plan}_{interval}_price_id>'
            calls.append(
                {
                    'call': 'stripe.Price.create',
                    'kwargs': {
                        'product': products[plan],
                        'unit_amount': amount,
                        'currency': ladder['currency'],
                        'recurring': {'interval': interval},
                        'metadata': {'plan_id': plan, 'entitlement_version': ladder['entitlement_version']},
                    },
                }
            )
            registrations.append(
                {
                    'price_id': placeholder,
                    'plan_id': plan,
                    'interval': interval,
                    'entitlement_version': ladder['entitlement_version'],
                    'environment': '<dev_or_prod>',
                }
            )
    return {
        'mode': 'fixture_only_dry_run',
        'inventory': inventory,
        'create_calls': calls,
        'catalog_diff': {
            'append_to_ladder_v1_stripe_prices': [row['price_id'] for row in registrations],
            'append_to_recognized_stripe_prices': registrations,
        },
        'warning': 'Proposal only. David must approve Stripe writes and catalog registration separately.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory-fixture', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        parser.error('Execution is disabled in this sprint. David\'s approval is required.')
    ladder = json.loads((BACKEND / 'config/storefront_ladder.json').read_text())
    catalog = json.loads((BACKEND / 'config/plan_catalog.json').read_text())
    inventory = (
        json.loads(args.inventory_fixture.read_text()) if args.inventory_fixture else {'products': [], 'prices': []}
    )
    print(json.dumps(proposal(ladder, catalog, inventory), indent=2))


if __name__ == '__main__':
    main()
