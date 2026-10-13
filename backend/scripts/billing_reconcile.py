#!/usr/bin/env python3
"""Report billing drift only. This command has no repair/write mode."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from utils.billing_reconciliation import reconcile


def load_snapshot(path: Path, kind: str) -> list[dict]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get('complete') is not True or not isinstance(payload.get(kind), list):
        raise ValueError(f'{kind} snapshot must certify complete=true and contain an array')
    return payload[kind]


def read_live(project: str) -> tuple[list[dict], list[dict]]:
    # Imports and credential reads happen only in explicitly selected operator mode.
    # Do not import database/users: its subscription getter can create/migrate rows.
    key = os.environ.get('STRIPE_RECONCILE_READ_ONLY_KEY', '')
    if not key.startswith(('rk_live_', 'rk_test_')):
        raise ValueError('operator mode requires a restricted Stripe key in STRIPE_RECONCILE_READ_ONLY_KEY')
    import stripe
    from google.cloud import firestore

    subscriptions = [
        s.to_dict() for s in stripe.Subscription.list(status='all', limit=100, api_key=key).auto_paging_iter()
    ]
    client = firestore.Client(project=project)
    try:
        users = [
            dict(doc.to_dict(), uid=doc.id)
            for doc in client.collection('users').select(['subscription', 'stripe_customer_id']).stream()
        ]
    finally:
        client.close()
    return subscriptions, users


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stripe-snapshot', type=Path)
    parser.add_argument('--users-snapshot', type=Path)
    parser.add_argument(
        '--price-map', type=Path, help='optional JSON price id → plan id map for fixtures/retained bindings'
    )
    parser.add_argument('--as-of', type=int, required=True, help='comparison Unix timestamp (explicit/reproducible)')
    parser.add_argument('--live', action='store_true', help='operator-only read mode; never used by tests')
    parser.add_argument('--prometheus-output', type=Path, help='optional local metrics artifact; no network export')
    parser.add_argument('--project', help='explicit Firestore project for operator read mode')
    args = parser.parse_args(argv)
    if args.live:
        if not args.project or args.stripe_snapshot or args.users_snapshot:
            parser.error('--live requires --project and forbids snapshot arguments')
    elif not args.stripe_snapshot or not args.users_snapshot or args.project:
        parser.error('snapshot mode requires both snapshot paths and forbids --project')
    try:
        subscriptions, users = (
            read_live(args.project)
            if args.live
            else (
                load_snapshot(args.stripe_snapshot, 'subscriptions'),
                load_snapshot(args.users_snapshot, 'users'),
            )
        )
        price_plans = (
            json.loads(args.price_map.read_text())
            if args.price_map
            else {price: plan.value for price, plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items()}
        )
        report = reconcile(subscriptions, users, price_plans, as_of=args.as_of)
        from utils.observability.billing_reconciliation import record_report

        record_report(report)
        if args.prometheus_output:
            from prometheus_client import generate_latest

            args.prometheus_output.write_bytes(generate_latest())
    except Exception as error:
        # Never stringify provider exceptions or key values into operator logs.
        print(f'billing reconciliation failed: {type(error).__name__}', file=sys.stderr)
        return 2
    print(json.dumps({'mode': 'read_only', 'as_of': args.as_of, **asdict(report)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
