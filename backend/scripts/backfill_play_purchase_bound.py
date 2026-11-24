"""Set ``users/{uid}.play_purchase_bound`` for every uid that owns a Play purchase document.

Checkout only looks for Google Play purchases when the user document carries a Play history field
(``database.play_subscriptions.HISTORY_FIELDS``). Purchases bound before that marker existed may lack it.
Idempotent. Dry-run by default; ``--apply`` writes. Prints counts only, never uids or tokens.

    python scripts/backfill_play_purchase_bound.py            # dry run
    python scripts/backfill_play_purchase_bound.py --apply    # write the missing markers
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import play_subscriptions as play_db  # noqa: E402
from database._client import get_firestore_client  # noqa: E402


def backfill(client, *, apply: bool) -> dict[str, int]:
    counts = {'purchases': 0, 'owners': 0, 'already_marked': 0, 'missing_user': 0, 'to_mark': 0, 'marked': 0}
    owners: set[str] = set()
    for snapshot in client.collection(play_db.COLLECTION).select(['uid']).stream():
        counts['purchases'] += 1
        uid = (snapshot.to_dict() or {}).get('uid')
        if isinstance(uid, str) and uid:
            owners.add(uid)
    counts['owners'] = len(owners)
    for uid in sorted(owners):
        user = client.collection('users').document(uid).get([play_db.BOUND_FIELD])
        if not user.exists:
            counts['missing_user'] += 1
            continue
        if (user.to_dict() or {}).get(play_db.BOUND_FIELD):
            counts['already_marked'] += 1
            continue
        counts['to_mark'] += 1
        if apply:
            play_db.mark_play_history(uid, firestore_client=client)
            counts['marked'] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Set the Play history marker for every Play purchase owner.')
    parser.add_argument('--apply', action='store_true', help='write the missing markers (default: dry run)')
    args = parser.parse_args(argv)
    counts = backfill(get_firestore_client(), apply=args.apply)
    print(('applied ' if args.apply else 'dry run ') + ' '.join(f'{key}={value}' for key, value in counts.items()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
