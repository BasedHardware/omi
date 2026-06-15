"""One-time migration: rewrite ISO-string conversation timestamps back to Firestore Timestamps.

Between the deploy of PR #7101 (2026-05-26) and the fix in #7580, `process_conversation.py`
wrote `created_at` / `started_at` / `finished_at` as ISO-8601 strings (via
`Conversation.as_dict_cleaned_dates()`) instead of native Firestore Timestamps.
A field that holds both strings and timestamps sorts strings above timestamps and
is excluded from timestamp range queries, so affected conversations vanish from the
default `created_at DESC` list and from date-range filters.

This walks each user's conversations and converts any string-typed timestamp field
back to a native datetime. Conversations written before the regression (and via merge)
are already Timestamps and are left untouched.

Scan strategy: Firestore's total type order places every string-typed value above
every timestamp-typed value. Iterating a user's conversations by `created_at DESC`
therefore yields the string cluster first, then the timestamp cluster — so once a
native-datetime `created_at` is seen, the rest of that user are already correct and
the scan can stop early. Pass `--full-scan` to disable the early stop.

Usage (run as a module from backend/):
    python -m scripts.migrate_conversation_timestamps --dry-run --uid <UID>   # one user, no writes
    python -m scripts.migrate_conversation_timestamps --uid <UID>             # one user, apply
    python -m scripts.migrate_conversation_timestamps --dry-run               # all users, no writes
    python -m scripts.migrate_conversation_timestamps                         # full run
    python -m scripts.migrate_conversation_timestamps --workers 20            # tune parallelism
    python -m scripts.migrate_conversation_timestamps --full-scan             # no early stop
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from google.cloud import firestore

from database._client import db, get_users_uid

TIMESTAMP_FIELDS = ('created_at', 'started_at', 'finished_at')


def parse_iso(value: str):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def build_updates(data: dict) -> dict:
    updates = {}
    for field in TIMESTAMP_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            parsed = parse_iso(value)
            if parsed is not None:
                updates[field] = parsed
    return updates


def process_user(uid: str, dry_run: bool, full_scan: bool) -> dict:
    """Fix string-typed timestamps for one user's conversations."""
    fixed = 0
    try:
        convs = (
            db.collection('users')
            .document(uid)
            .collection('conversations')
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .stream()
        )
        for conv in convs:
            data = conv.to_dict() or {}
            updates = build_updates(data)
            if not updates:
                if not full_scan and isinstance(data.get('created_at'), datetime):
                    break
                continue
            if dry_run:
                print(f'DRY {uid}/{conv.id}: {sorted(updates.keys())}')
            else:
                conv.reference.update(updates)
            fixed += 1
        return {'uid': uid, 'fixed': fixed, 'status': 'ok'}
    except Exception as e:  # noqa: BLE001 — one user shouldn't abort the run
        return {'uid': uid, 'fixed': fixed, 'status': f'error: {e}'}


def main():
    parser = argparse.ArgumentParser(description='Rewrite ISO-string conversation timestamps to Firestore Timestamps')
    parser.add_argument('--dry-run', action='store_true', help='Only print what would change')
    parser.add_argument('--uid', help='Process a single user by uid instead of all users')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers (default 10)')
    parser.add_argument('--limit', type=int, default=0, help='Max users to process (0 = all)')
    parser.add_argument(
        '--full-scan',
        action='store_true',
        help='Scan every conversation per user instead of stopping at the first native timestamp',
    )
    args = parser.parse_args()

    print(f'Conversation timestamp migration — {"DRY RUN" if args.dry_run else "APPLY"}')

    if args.uid:
        uids = [args.uid]
    else:
        uids = get_users_uid()
        if args.limit:
            uids = uids[: args.limit]
    print(f'Processing {len(uids)} user(s) with {args.workers} workers')

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_user, uid, args.dry_run, args.full_scan) for uid in uids]
        for i, future in enumerate(futures):
            results.append(future.result())
            if (i + 1) % 1000 == 0:
                done = sum(r['fixed'] for r in results)
                print(f'  processed {i + 1}/{len(uids)} users, convs_fixed={done}...', flush=True)

    convs_fixed = sum(r['fixed'] for r in results)
    users_with_fixes = sum(1 for r in results if r['fixed'])
    errors = [r for r in results if r['status'].startswith('error')]

    print('=' * 60)
    print(f'users_scanned={len(results)} users_with_fixes={users_with_fixes} convs_fixed={convs_fixed}', end='')
    print(' (dry-run, no writes)' if args.dry_run else '')
    print(f'errors={len(errors)}')
    for r in errors:
        print(f'  {r["uid"]}: {r["status"]}')

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
