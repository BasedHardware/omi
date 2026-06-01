"""One-time migration: rewrite ISO-string conversation timestamps back to Firestore Timestamps.

Between the deploy of PR #7101 and the fix in this PR, `process_conversation.py`
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

Usage:
    python scripts/migrate_conversation_timestamps.py --dry-run --limit 50
    python scripts/migrate_conversation_timestamps.py                 # full run
    python scripts/migrate_conversation_timestamps.py --full-scan     # no early stop
"""

import argparse
from datetime import datetime

import firebase_admin
from firebase_admin import firestore

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Only print what would change')
    parser.add_argument('--limit', type=int, default=0, help='Max users to process (0 = all)')
    parser.add_argument(
        '--full-scan',
        action='store_true',
        help='Scan every conversation per user instead of stopping at the first native timestamp',
    )
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    db = firestore.client()

    page_size = 500
    users_scanned = 0
    convs_fixed = 0
    users_with_fixes = 0
    last_doc = None

    while True:
        if args.limit and users_scanned >= args.limit:
            break
        query = db.collection('users').order_by('__name__').limit(page_size)
        if last_doc is not None:
            query = query.start_after(last_doc)
        batch = list(query.stream())
        if not batch:
            break

        for user_snapshot in batch:
            if args.limit and users_scanned >= args.limit:
                break
            users_scanned += 1
            uid = user_snapshot.id

            user_fixed = 0
            try:
                convs = (
                    user_snapshot.reference.collection('conversations')
                    .order_by('created_at', direction=firestore.Query.DESCENDING)
                    .stream()
                )
                for conv in convs:
                    data = conv.to_dict() or {}
                    updates = build_updates(data)
                    if not updates:
                        if not args.full_scan and isinstance(data.get('created_at'), datetime):
                            break
                        continue
                    if args.dry_run:
                        print(f'DRY {uid}/{conv.id}: {sorted(updates.keys())}')
                    else:
                        conv.reference.update(updates)
                    user_fixed += 1
            except Exception as e:  # noqa: BLE001 — one user shouldn't abort the run
                print(f'WARN conversations scan failed for {uid}: {e}')

            if user_fixed:
                users_with_fixes += 1
                convs_fixed += user_fixed

            if users_scanned % 1000 == 0:
                print(
                    f'users_scanned={users_scanned} users_with_fixes={users_with_fixes} convs_fixed={convs_fixed}',
                    flush=True,
                )

        last_doc = batch[-1]
        if len(batch) < page_size:
            break

    print(
        f'Done. users_scanned={users_scanned} users_with_fixes={users_with_fixes} convs_fixed={convs_fixed}'
        + (' (dry-run, no writes)' if args.dry_run else '')
    )


if __name__ == '__main__':
    main()
