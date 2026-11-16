"""One-time migration: set the default language for conversations to 'en'.

This walks each user's conversations and updates any conversation where
'language' is missing or None to 'en'.

Usage (run as a module from backend/):
    python -m scripts.migrate_conversation_language --dry-run --uid <UID>
    python -m scripts.migrate_conversation_language --uid <UID>
    python -m scripts.migrate_conversation_language --dry-run
    python -m scripts.migrate_conversation_language
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from database._client import db, get_users_uid


def process_user(uid: str, dry_run: bool) -> Dict[str, Any]:
    """Fix missing language field for one user's conversations."""
    fixed = 0
    try:
        convs = db.collection('users').document(uid).collection('conversations').stream()
        for conv in convs:
            data: Dict[str, Any] = conv.to_dict() or {}
            if data.get('language') is None:
                if not dry_run:
                    conv.reference.update({'language': 'en'})
                fixed += 1
        return {'uid': uid, 'fixed': fixed, 'status': 'ok'}
    except Exception as e:  # noqa: BLE001
        return {'uid': uid, 'fixed': fixed, 'status': f'error: {e}'}


def main() -> int:
    parser = argparse.ArgumentParser(description='Set default conversation language to "en"')
    parser.add_argument('--dry-run', action='store_true', help='Only print what would change')
    parser.add_argument('--uid', help='Process a single user by uid instead of all users')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers (default 10)')
    parser.add_argument('--limit', type=int, default=0, help='Max users to process (0 = all)')
    args = parser.parse_args()

    print(f'Conversation language migration — {"DRY RUN" if args.dry_run else "APPLY"}')

    if args.uid:
        uids = [args.uid]
    else:
        uids = get_users_uid()
        if args.limit:
            uids = uids[: args.limit]
    print(f'Processing {len(uids)} user(s) with {args.workers} workers')

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_user, uid, args.dry_run) for uid in uids]
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
