#!/usr/bin/env python3
"""Fixture-only Stripe price proposal. No credentials, network, or write SDK.

Amounts are proposal inputs, never runtime display prices. An inventory fixture
is an offline export with products/prices arrays; this tool cannot fetch it.
"""

import argparse
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def proposal(ladder: dict, catalog: dict, inventory: dict, environment: str = 'dev') -> dict:
    if environment not in {'dev', 'prod'}:
        raise ValueError('environment must be dev or prod')
    tiers = ladder['tiers']
    plan_ids = [tier['plan_id'] for tier in tiers]
    if len(set(plan_ids)) != len(plan_ids):
        raise ValueError('duplicate plan_id in ladder tiers')
    products = {}
    for tier in tiers:
        if not tier.get('proposed_prices'):
            continue
        plan = tier['plan_id']
        matches = [row for row in catalog['recognized_stripe_products'] if row['plan_id'] == plan]
        if len(matches) != 1:
            raise ValueError(f'{plan}: expected one product row; found {len(matches)} (duplicate or missing plan_id)')
        products[plan] = matches[0]['product_id']
    calls = []
    registrations = []
    for tier in ladder['tiers']:
        for interval, amount in tier.get('proposed_prices', {}).items():
            plan = tier['plan_id']
            placeholder = f'price_W5PLACEHOLDER{plan}{interval}'
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
                    'environment': environment,
                }
            )
    expected = inventory.get('expected_create_calls')
    if expected is not None and expected != calls:
        raise ValueError('fixture expected_create_calls does not match proposed creates')
    return {
        'mode': 'fixture_only_dry_run',
        'inventory': inventory,
        'placeholder_ids': {
            row['price_id']: 'REPLACE with the returned Stripe price ID before registration' for row in registrations
        },
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
    parser.add_argument('--environment', choices=('dev', 'prod'), default='dev')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        parser.error('Execution is disabled in this sprint. David\'s approval is required.')
    ladder = json.loads((BACKEND / 'config/storefront_ladder.json').read_text())
    catalog = json.loads((BACKEND / 'config/plan_catalog.json').read_text())
    inventory = (
        json.loads(args.inventory_fixture.read_text()) if args.inventory_fixture else {'products': [], 'prices': []}
    )
    try:
        output = proposal(ladder, catalog, inventory, args.environment)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
