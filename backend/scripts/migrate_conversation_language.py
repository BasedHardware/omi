"""One-time migration: set default 'en' language for conversations from the Friend source.

The Friend source will now use 'en' as the default language. This script updates
any existing conversations with source 'friend' or 'friend_com' that have a null or missing language.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from google.cloud import firestore

from database._client import get_firestore_client, get_users_uid


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError('must be non-negative')
    return parsed


def process_user(uid: str, dry_run: bool, firestore_client: Any = None) -> Dict[str, Any]:
    """Fix language for one user's conversations."""
    fixed = 0
    try:
        client = firestore_client or get_firestore_client()
        convs = (
            client.collection('users')
            .document(uid)
            .collection('conversations')
            .where(filter=firestore.FieldFilter('source', 'in', ['friend', 'friend_com']))
            .stream()
        )
        for conv in convs:
            data: Dict[str, Any] = conv.to_dict() or {}

            # Check if source is 'friend' or 'friend_com' and language is missing or None
            source = data.get('source')
            if source not in ('friend', 'friend_com'):
                continue

            language = data.get('language')
            if language is not None and (not isinstance(language, str) or language.strip()):
                continue

            updates = {'language': 'en'}

            if dry_run:
                print(f'DRY {uid}/{conv.id}: {updates}')
            else:
                conv.reference.update(updates)
            fixed += 1
        return {'uid': uid, 'fixed': fixed, 'status': 'ok'}
    except Exception as e:  # noqa: BLE001 — one user shouldn't abort the run
        return {'uid': uid, 'fixed': fixed, 'status': f'error: {e}'}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Set default "en" language for Friend conversations')
    parser.add_argument('--dry-run', action='store_true', help='Only print what would change')
    parser.add_argument('--uid', help='Process a single user by uid instead of all users')
    parser.add_argument('--workers', type=_positive_int, default=10, help='Number of parallel workers (default 10)')
    parser.add_argument('--limit', type=_nonnegative_int, default=0, help='Max users to process (0 = all)')
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    print(f'Conversation language migration — {"DRY RUN" if args.dry_run else "APPLY"}')

    if args.uid is not None:
        if not args.uid.strip():
            parser.error('--uid must not be empty')
        uids = [args.uid.strip()]
    else:
        uids = get_users_uid()
        if args.limit:
            uids = uids[: args.limit]
    print(f'Processing {len(uids)} user(s) with {args.workers} workers')

    results: List[Dict[str, Any]] = []
    firestore_client = get_firestore_client()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_user, uid, args.dry_run, firestore_client) for uid in uids]
        for i, future in enumerate(futures):
            results.append(future.result())
            if (i + 1) % 1000 == 0:
                done = sum(r['fixed'] for r in results)
                print(f'  processed {i + 1}/{len(uids)} users, convs_fixed={done}...', flush=True)

    convs_fixed = sum(r['fixed'] for r in results)
    users_with_fixes = sum(1 for r in results if r['fixed'])
    errors: List[Dict[str, Any]] = [r for r in results if r['status'].startswith('error')]

    print('=' * 60)
    print(f'users_scanned={len(results)} users_with_fixes={users_with_fixes} convs_fixed={convs_fixed}', end='')
    print(' (dry-run, no writes)' if args.dry_run else '')
    print(f'errors={len(errors)}')
    for r in errors:
        print(f'  {r["uid"]}: {r["status"]}')

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
