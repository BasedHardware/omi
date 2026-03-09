"""One-time Firestore patch: change source='phone_call' to source='phone'.

Usage:
    python scripts/patch_phone_call_source.py --uid <UID> [--dry-run]

Scans all conversations for the specified user and patches source field.
"""

import argparse

import firebase_admin
from firebase_admin import firestore


def main():
    parser = argparse.ArgumentParser(description='Patch phone_call source to phone in Firestore')
    parser.add_argument('--uid', required=True, help='User UID to patch')
    parser.add_argument('--dry-run', action='store_true', help='Print affected doc IDs without modifying')
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    db = firestore.client()

    conversations_ref = db.collection('users').document(args.uid).collection('conversations')
    query = conversations_ref.where('source', '==', 'phone_call')
    docs = list(query.stream())

    print(f'Found {len(docs)} conversations with source=phone_call')

    if not docs:
        print('Nothing to patch.')
        return

    for doc in docs:
        print(f'  doc_id={doc.id}')
        if not args.dry_run:
            doc.reference.update({'source': 'phone'})
            print(f'    -> patched to source=phone')

    if args.dry_run:
        print('\nDry run — no changes made. Remove --dry-run to apply.')
    else:
        print(f'\nPatched {len(docs)} documents.')


if __name__ == '__main__':
    main()
