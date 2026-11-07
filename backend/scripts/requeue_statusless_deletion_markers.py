#!/usr/bin/env python3
"""Re-drive account-deletion markers that have no wipe_status, one approved uid list at a time.

Default is a dry run that prints counts only. It never prints or logs uids.
A real run needs both ``--apply`` and ``ACCOUNT_DELETION_STATUSLESS_REDRIVE=on``,
plus a uid list that David approved. The uid list is operator input and must not
be committed.

For each uid, the script refuses unless the Firebase Auth user is already gone.
Only then does it move the marker to ``pending`` and enqueue the normal wipe task.
That wipe is destructive and irreversible, so the script never runs unattended.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin  # noqa: E402
import firebase_admin.credentials  # noqa: E402,F401
from firebase_admin import auth as firebase_auth  # noqa: E402

from database import users as users_db  # noqa: E402
from database.account_deletion_statusless import is_statusless_marker  # noqa: E402
from utils.cloud_tasks import enqueue_account_deletion_wipe  # noqa: E402

ENV_GATE = 'ACCOUNT_DELETION_STATUSLESS_REDRIVE'
SERVICE_ACCOUNT_ENV = 'SERVICE_ACCOUNT_JSON'


def _init_firebase() -> None:
    """Initialize the default Admin app with the customer service account.

    Mirrors the non-emulator path in main.py. It requires SERVICE_ACCOUNT_JSON and
    never falls back to ambient ADC, which can point at another project.
    """
    if firebase_admin._apps:  # type: ignore[attr-defined]
        return
    raw = os.environ.get(SERVICE_ACCOUNT_ENV, '').strip()
    if not raw:
        raise SystemExit(f'{SERVICE_ACCOUNT_ENV} must hold the customer service account; refusing to use ambient ADC')
    certificate = firebase_admin.credentials.Certificate(json.loads(raw))  # type: ignore[reportUnknownMemberType]
    firebase_admin.initialize_app(certificate)  # type: ignore[reportUnknownMemberType]


def _auth_user_gone(uid: str) -> bool:
    try:
        firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        return True
    return False


def _marker_is_statusless(uid: str) -> tuple[bool, bool]:
    """Read-only: (marker_exists, is_statusless). Mirrors the apply-time transaction."""
    client = users_db.account_deletion_firestore_client()
    snapshot = users_db.account_deletion_document(uid, firestore_client=client).get()
    if not snapshot.exists:
        return False, False
    return True, is_statusless_marker(snapshot.to_dict())


def _read_uids(path: str) -> list[str]:
    with open(path, encoding='utf-8') as handle:
        return sorted({line.strip() for line in handle if line.strip()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid-file', required=True, help='David-approved uid list, one per line. Not committed.')
    parser.add_argument('--apply', action='store_true', help='Re-drive the wipes. Requires the env gate.')
    args = parser.parse_args()

    apply = args.apply and os.environ.get(ENV_GATE, '').strip().lower() == 'on'
    if args.apply and not apply:
        print(f'refusing to apply: {ENV_GATE} is not "on"; running as dry run')
    _init_firebase()

    counts: Counter[str] = Counter()
    for uid in _read_uids(args.uid_file):
        counts['listed'] += 1
        if not _auth_user_gone(uid):
            counts['skipped_auth_present'] += 1
            continue
        if not apply:
            exists, statusless = _marker_is_statusless(uid)
            if not exists:
                counts['dry_run_missing_marker'] += 1
            elif not statusless:
                counts['dry_run_not_statusless'] += 1
            else:
                counts['dry_run_would_requeue'] += 1
            continue
        job_id = users_db.requeue_statusless_deletion_marker(uid)
        if not job_id:
            counts['skipped_not_statusless'] += 1
            continue
        enqueue_account_deletion_wipe(job_id)
        counts['requeued'] += 1

    mode = 'apply' if apply else 'dry_run'
    print(f'mode={mode}', ' '.join(f'{key}={value}' for key, value in sorted(counts.items())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
