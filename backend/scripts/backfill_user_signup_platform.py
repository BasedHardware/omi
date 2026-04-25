"""One-time backfill for `signup_platform` / `platforms_used` on users.

Triage signals used (any match adds to `platforms_used`; earliest-seen wins
for `signup_platform`):

  1. `users/{uid}/fcm_tokens/{device_key}` — doc id prefix encodes platform
     (`ios_…`, `android_…`, `macos_…`, `web_…`) and carries a `created_at`
     timestamp on the doc.

  2. `users/{uid}/conversations.source` — ConversationSource enum. Values
     map to coarse platforms:
        desktop                     → desktop
        omi, friend, openglass,
        apple_watch, phone,
        phone_call                  → mobile
        fieldy, bee, plaud, frame,
        friend_com                  → mobile (paired devices go via mobile)
        screenpipe, workflow,
        sdcard, external_integration → skipped (programmatic / not user-platform)
     Timestamp is the conversation's `created_at`.

After this runs, live traffic takes over via the `get_current_user_uid`
dependency that calls `record_user_platform` on every authenticated request.

Users with zero usable signals are skipped — they'll get populated the next
time they hit the backend with `X-App-Platform` set.

Usage:
    python scripts/backfill_user_signup_platform.py --dry-run --limit 50
    python scripts/backfill_user_signup_platform.py                 # full run
    python scripts/backfill_user_signup_platform.py --force         # overwrite
"""

import argparse
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import firestore

_PLATFORM_FROM_TOKEN_PREFIX = {
    'macos': ('desktop', 'macos'),
    'ios': ('mobile', 'ios'),
    'android': ('mobile', 'android'),
    'web': ('web', 'web'),
}

_PLATFORM_FROM_CONVERSATION_SOURCE = {
    'desktop': ('desktop', 'desktop'),
    'omi': ('mobile', 'mobile'),
    'friend': ('mobile', 'mobile'),
    'openglass': ('mobile', 'mobile'),
    'apple_watch': ('mobile', 'mobile'),
    'phone': ('mobile', 'mobile'),
    'phone_call': ('mobile', 'mobile'),
    'fieldy': ('mobile', 'mobile'),
    'bee': ('mobile', 'mobile'),
    'plaud': ('mobile', 'mobile'),
    'frame': ('mobile', 'mobile'),
    'friend_com': ('mobile', 'mobile'),
}


def classify_token(doc_id: str):
    prefix = doc_id.split('_', 1)[0].lower() if doc_id else ''
    return _PLATFORM_FROM_TOKEN_PREFIX.get(prefix)


def classify_source(source: str):
    if not source:
        return None
    return _PLATFORM_FROM_CONVERSATION_SOURCE.get(str(source).lower())


def consider(candidate, timestamp, earliest):
    """Merge a (coarse, os, ts) signal into a (ts, coarse, os) earliest tuple."""
    coarse, os_value = candidate
    if earliest is None:
        return (timestamp, coarse, os_value)
    cur_ts = earliest[0]
    if timestamp is not None and cur_ts is not None and timestamp < cur_ts:
        return (timestamp, coarse, os_value)
    if cur_ts is None and timestamp is not None:
        return (timestamp, coarse, os_value)
    return earliest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Only print what would change')
    parser.add_argument('--limit', type=int, default=0, help='Max users to process (0 = all)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing signup_platform even if set')
    parser.add_argument(
        '--scan-conversations',
        action='store_true',
        default=True,
        help='Also scan users/{uid}/conversations.source (default on)',
    )
    parser.add_argument(
        '--no-scan-conversations',
        action='store_false',
        dest='scan_conversations',
    )
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    db = firestore.client()

    # The users collection has 100K+ docs; a single `stream()` blows through
    # the gRPC deadline. Paginate via `order_by(__name__).limit().start_after`
    # so each RPC is bounded.
    page_size = 500
    scanned = 0
    updated = 0
    skipped_no_signal = 0
    skipped_already_set = 0
    last_doc = None

    while True:
        if args.limit and scanned >= args.limit:
            break
        query = db.collection('users').order_by('__name__').limit(page_size)
        if last_doc is not None:
            query = query.start_after(last_doc)
        batch = list(query.stream())
        if not batch:
            break

        for user_snapshot in batch:
            if args.limit and scanned >= args.limit:
                break
            scanned += 1

            uid = user_snapshot.id
            existing = user_snapshot.to_dict() or {}

            if existing.get('signup_platform') and not args.force:
                skipped_already_set += 1
                continue

            earliest = None
            platforms_used = set()

            try:
                for token in user_snapshot.reference.collection('fcm_tokens').stream():
                    klass = classify_token(token.id)
                    if not klass:
                        continue
                    platforms_used.add(klass[0])
                    created = (token.to_dict() or {}).get('created_at')
                    earliest = consider(klass, created, earliest)
            except Exception as e:  # noqa: BLE001 — one user's subcollection shouldn't abort the run
                print(f'WARN fcm_tokens scan failed for {uid}: {e}')

            if args.scan_conversations:
                try:
                    # Cap the per-user scan to keep runtime bounded; 50
                    # earliest conversations is enough to find a platform
                    # signal.
                    convs = (
                        user_snapshot.reference.collection('conversations').order_by('created_at').limit(50).stream()
                    )
                    for conv in convs:
                        data = conv.to_dict() or {}
                        klass = classify_source(data.get('source'))
                        if not klass:
                            continue
                        platforms_used.add(klass[0])
                        created = data.get('created_at')
                        earliest = consider(klass, created, earliest)
                except Exception as e:  # noqa: BLE001
                    print(f'WARN conversations scan failed for {uid}: {e}')

            if not earliest:
                skipped_no_signal += 1
                continue

            signup_at, coarse, os_value = earliest
            update = {
                'signup_platform': coarse,
                'signup_os': os_value,
                'signup_platform_at': signup_at or datetime.now(timezone.utc),
                'platforms_used': firestore.ArrayUnion(sorted(platforms_used)),
            }

            if args.dry_run:
                print(f'DRY {uid}: signup={coarse}/{os_value} used={sorted(platforms_used)}')
            else:
                try:
                    user_snapshot.reference.set(update, merge=True)
                except Exception as e:  # noqa: BLE001
                    print(f'WARN write failed for {uid}: {e}')
                    continue
            updated += 1

            if scanned % 1000 == 0:
                print(
                    f'scanned={scanned} updated={updated} '
                    f'no_signal={skipped_no_signal} already_set={skipped_already_set}',
                    flush=True,
                )

        last_doc = batch[-1]
        if len(batch) < page_size:
            break

    print(
        f'Done. scanned={scanned} updated={updated} '
        f'skipped_no_signal={skipped_no_signal} skipped_already_set={skipped_already_set}'
    )


if __name__ == '__main__':
    main()
