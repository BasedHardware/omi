#!/usr/bin/env python3
"""One-time migration: set default 'en' language for conversations from the Friend source.

The Friend source will now use 'en' as the default language. This script updates
any existing conversations with source 'friend' or 'friend_com' that have a null or missing language.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterator, List

from google.cloud import firestore

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database._client import get_firestore_client

USER_PAGE_SIZE = 1000


def _iter_user_pages(firestore_client: Any, page_size: int = USER_PAGE_SIZE) -> Iterator[List[str]]:
    users_query = firestore_client.collection('users').order_by('__name__')
    cursor = None
    while True:
        page_query = users_query.start_after(cursor) if cursor is not None else users_query
        documents = list(page_query.limit(page_size).stream())
        if not documents:
            return
        yield [str(document.id) for document in documents]
        if len(documents) < page_size:
            return
        cursor = documents[-1]


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
        firestore_client = get_firestore_client()
        user_pages = iter([[args.uid.strip()]])
    else:
        firestore_client = get_firestore_client()
        user_pages = _iter_user_pages(firestore_client)
    total_label = '1' if args.uid is not None else (str(args.limit) if args.limit else 'all')
    print(f'Processing {total_label} user(s) with {args.workers} workers')

    users_scanned = 0
    convs_fixed = 0
    users_with_fixes = 0
    errors: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for page in user_pages:
            if args.limit:
                remaining = args.limit - users_scanned
                if remaining <= 0:
                    break
                page = page[:remaining]
            futures = [executor.submit(process_user, uid, args.dry_run, firestore_client) for uid in page]
            for future in futures:
                result = future.result()
                users_scanned += 1
                convs_fixed += result['fixed']
                users_with_fixes += bool(result['fixed'])
                if result['status'].startswith('error'):
                    errors.append(result)
                if users_scanned % 1000 == 0:
                    print(f'  processed {users_scanned}/{total_label} users, convs_fixed={convs_fixed}...', flush=True)

    print('=' * 60)
    print(f'users_scanned={users_scanned} users_with_fixes={users_with_fixes} convs_fixed={convs_fixed}', end='')
    print(' (dry-run, no writes)' if args.dry_run else '')
    print(f'errors={len(errors)}')
    for r in errors:
        print(f'  {r["uid"]}: {r["status"]}')

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
