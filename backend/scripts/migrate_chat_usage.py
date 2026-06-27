"""Migrate current-month chat usage for existing users.

Scans each user's `messages` subcollection for human-sent messages in the
current UTC month and reconciles the total against the `llm_usage` collection
that `get_monthly_chat_usage()` reads.

If a user has more actual messages than what llm_usage reflects, the script
creates/updates an llm_usage doc for the current date with a synthetic
`chat.migrated.call_count` field set to the *difference*, so the sum
reported by `get_monthly_chat_usage()` becomes correct.

Usage:
    # Dry run (default) — report only, no writes
    python -m scripts.migrate_chat_usage

    # Apply writes
    python -m scripts.migrate_chat_usage --apply
"""

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from calendar import monthrange

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import db, get_users_uid
from database.user_usage import get_monthly_chat_usage


def _count_user_messages_this_month(uid: str, month_start: datetime, month_end: datetime) -> int:
    """Count human-sent chat messages in the current month from the messages collection."""
    messages_ref = db.collection('users').document(uid).collection('messages')
    query = (
        messages_ref.where(filter=FieldFilter('created_at', '>=', month_start))
        .where(filter=FieldFilter('created_at', '<=', month_end))
        .where(filter=FieldFilter('sender', '==', 'human'))
    )
    count_agg = query.count().get()
    return count_agg[0][0].value if count_agg else 0


def _process_user(uid: str, month_start: datetime, month_end: datetime, fixed_now: datetime, apply: bool) -> dict:
    """Process a single user: compare actual messages vs tracked llm_usage."""
    try:
        actual_count = _count_user_messages_this_month(uid, month_start, month_end)
        usage = get_monthly_chat_usage(uid, now=fixed_now)
        tracked_count = usage['questions']

        result = {
            'uid': uid,
            'actual_messages': actual_count,
            'tracked_questions': tracked_count,
            'delta': actual_count - tracked_count,
            'status': 'ok',
        }

        if actual_count > tracked_count and apply:
            delta = actual_count - tracked_count
            doc_id = f'{fixed_now.year}-{fixed_now.month:02d}-{fixed_now.day:02d}'
            usage_ref = db.collection('users').document(uid).collection('llm_usage').document(doc_id)
            usage_ref.set(
                {
                    'chat.migrated.call_count': firestore.Increment(delta),
                    'date': doc_id,
                    'last_updated': datetime.now(timezone.utc),
                },
                merge=True,
            )
            result['status'] = 'migrated'

        return result
    except Exception as e:
        return {
            'uid': uid,
            'actual_messages': -1,
            'tracked_questions': -1,
            'delta': 0,
            'status': f'error: {e}',
        }


def main():
    parser = argparse.ArgumentParser(description='Migrate current-month chat usage to llm_usage collection')
    parser.add_argument('--apply', action='store_true', help='Actually write to Firestore (default is dry-run)')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers (default 10)')
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    month_end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    print(f'Chat usage migration — {"APPLY" if args.apply else "DRY RUN"}')
    print(f'Month: {now.year}-{now.month:02d}')
    print(f'Range: {month_start.isoformat()} to {month_end.isoformat()}')
    print()

    uids = get_users_uid()
    print(f'Found {len(uids)} users')

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_process_user, uid, month_start, month_end, now, args.apply) for uid in uids]
        for i, future in enumerate(futures):
            result = future.result()
            results.append(result)
            if (i + 1) % 100 == 0:
                print(f'  Processed {i + 1}/{len(uids)} users...')

    # Summary
    total = len(results)
    ok_count = sum(1 for r in results if r['status'] == 'ok')
    migrated_count = sum(1 for r in results if r['status'] == 'migrated')
    error_count = sum(1 for r in results if r['status'].startswith('error'))
    needs_migration = [r for r in results if r['delta'] > 0]
    over_tracked = [r for r in results if r['delta'] < 0]

    print()
    print('=' * 60)
    print(f'Total users:           {total}')
    print(f'Already correct:       {ok_count}')
    if args.apply:
        print(f'Migrated:              {migrated_count}')
    else:
        print(f'Needs migration:       {len(needs_migration)}')
    print(f'Over-tracked (skip):   {len(over_tracked)}')
    print(f'Errors:                {error_count}')
    print('=' * 60)

    if needs_migration and not args.apply:
        print()
        print('Users needing migration (top 20):')
        print(f'{"UID":<40} {"Actual":>8} {"Tracked":>8} {"Delta":>8}')
        print('-' * 70)
        for r in sorted(needs_migration, key=lambda x: x['delta'], reverse=True)[:20]:
            print(f'{r["uid"]:<40} {r["actual_messages"]:>8} {r["tracked_questions"]:>8} {r["delta"]:>8}')
        print()
        print('Run with --apply to write corrections to Firestore.')

    if error_count > 0:
        print()
        print('Errors:')
        for r in results:
            if r['status'].startswith('error'):
                print(f'  {r["uid"]}: {r["status"]}')

    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
