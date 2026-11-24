"""Advance local integration through paid/refund fixtures, not fake counters."""

import argparse
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import referral_campaign as ledger
from tests.unit.fixtures.referral_campaign import POLICY, paid_payload, prepare, seed_user, settle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('seed', 'purchase', 'refund', 'paid-owner', 'free-owner'))
    parser.add_argument('--buyer', default='buyer-1')
    args = parser.parse_args()
    if os.getenv('OMI_ENV_STAGE') not in ('local', 'offline') or urlparse(
        '//' + os.getenv('FIRESTORE_EMULATOR_HOST', '')
    ).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('local stage and loopback emulator required')
    os.environ['OMI_REFERRAL_CAMPAIGN_ENABLED'] = 'true'
    project = os.getenv('FIREBASE_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT') or 'demo-omi-local'
    if not project.startswith('demo-'):
        raise RuntimeError('demo emulator project required')
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    if args.action == 'seed':
        seed_user(client, 'owner')
    elif args.action == 'purchase':
        now = datetime.now(timezone.utc)
        prepare(client, args.buyer, now=now - timedelta(seconds=2))
        print(
            settle(
                client,
                args.buyer,
                'order-' + args.buyer,
                payload=paid_payload(args.buyer, 'order-' + args.buyer, now=now - timedelta(seconds=1)),
                now=now,
            )
        )
    elif args.action == 'refund':
        print(
            settle(
                client,
                args.buyer,
                'order-' + args.buyer,
                topic='refunds/create',
                payload={'order_id': 'order-' + args.buyer, 'refund_line_items': [{'quantity': 1}]},
            )
        )
    else:
        sub = {'plan': 'basic', 'status': 'active'}
        if args.action == 'paid-owner':
            sub = {
                'plan': 'operator',
                'status': 'active',
                'current_period_end': int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp()),
                'stripe_subscription_id': 'local-existing-paid-sub',
            }
        client.collection('users').document('owner').update({'subscription': sub})
    print(ledger.read_campaign('owner', client=client, policy=POLICY))
    client.close()


if __name__ == '__main__':
    main()
