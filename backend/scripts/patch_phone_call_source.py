"""One-time Firestore patch: change source='phone_call' to source='phone'.

Usage:
    python scripts/patch_phone_call_source.py [--dry-run]

Scans all conversations for the affected user and patches source field.
"""

import argparse
import sys

import firebase_admin
from firebase_admin import credentials, firestore


def main():
    parser = argparse.ArgumentParser(description='Patch phone_call source to phone in Firestore')
    parser.add_argument('--dry-run', action='store_true', help='Print affected docs without modifying')
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    db = firestore.client()

    uid = 'viUv7GtdoHXbK1UBCDlPuTDuPgJ2'
    conversations_ref = db.collection('users').document(uid).collection('conversations')
    query = conversations_ref.where('source', '==', 'phone_call')
    docs = list(query.stream())

    print(f'Found {len(docs)} conversations with source=phone_call for user {uid}')

    if not docs:
        print('Nothing to patch.')
        return

    for doc in docs:
        data = doc.to_dict()
        print(f'  {doc.id}: source={data.get("source")} title={data.get("structured", {}).get("title", "")[:60]}')
        if not args.dry_run:
            doc.reference.update({'source': 'phone'})
            print(f'    -> patched to source=phone')

    if args.dry_run:
        print('\nDry run — no changes made. Remove --dry-run to apply.')
    else:
        print(f'\nPatched {len(docs)} documents.')


if __name__ == '__main__':
    main()
