#!/usr/bin/env python3
"""Stamp discarded=True on existing sync donor redirect tombstones.

PR #15193 wrote deleted=True + sync_merged_into on absorbed conversations but
left discarded untouched. List/count paths that use the indexed
discarded==False filter therefore kept showing those fragments. New assignment
writes discarded=True atomically; this script remediates rows already in
production since 2026-09-21T03:17:42Z.

Dry-run is the default. Do not point this at production from an agent session.

Usage:
    python scripts/backfill_sync_donor_tombstone_discarded.py
    python scripts/backfill_sync_donor_tombstone_discarded.py --limit 50
    python scripts/backfill_sync_donor_tombstone_discarded.py --apply
    python scripts/backfill_sync_donor_tombstone_discarded.py --apply --start-after <uid>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from google.cloud.firestore_v1 import FieldFilter

_BATCH_LIMIT = 400
_DEFAULT_PAGE_SIZE = 200
_CONVERSATIONS = 'conversations'


def _conversation_id(snapshot: Any) -> str:
    return str(getattr(snapshot, 'id', '') or '')


def _uid_from_snapshot(snapshot: Any) -> str | None:
    reference = getattr(snapshot, 'reference', None)
    path = str(getattr(reference, 'path', '') or '')
    parts = [part for part in path.split('/') if part]
    if len(parts) >= 4 and parts[0] == 'users' and parts[2] == _CONVERSATIONS:
        return parts[1]
    parent = getattr(reference, 'parent', None)
    parent_parent = getattr(parent, 'parent', None)
    uid = getattr(parent_parent, 'id', None)
    return str(uid) if uid else None


def _needs_discard_stamp(data: dict[str, Any]) -> bool:
    if not data.get('deleted'):
        return False
    if not data.get('sync_merged_into'):
        return False
    return data.get('discarded') is not True


def run_backfill(
    client: Any,
    *,
    apply: bool,
    page_size: int,
    start_after: str | None,
    limit: int | None,
) -> dict[str, Any]:
    """Page users and stamp discarded=True on donor redirect tombstones.

    ``client`` is a Firestore-like object. Writes happen only when ``apply``
    is true. Typesense deletes are best-effort and skipped when the index
    helpers cannot be imported.
    """
    page_size = min(max(int(page_size), 1), _DEFAULT_PAGE_SIZE)
    remaining = None if limit is None or limit <= 0 else int(limit)

    scanned_users = 0
    scanned_tombstones = 0
    already_hidden = 0
    written = 0
    last_uid: str | None = None
    cursor: Any = {'__name__': start_after} if start_after else None

    delete_index = None
    try:
        from utils.conversations.typesense_index import delete_conversation_index_doc

        delete_index = delete_conversation_index_doc
    except Exception:
        delete_index = None

    batch = client.batch() if apply else None
    pending = 0

    while remaining is None or remaining > 0:
        take = page_size if remaining is None else min(page_size, remaining)
        query = client.collection('users').select([]).order_by('__name__').limit(take)
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        if not page:
            break

        for user_snapshot in page:
            last_uid = str(user_snapshot.id)
            scanned_users += 1
            conversations = (
                client.collection('users')
                .document(last_uid)
                .collection(_CONVERSATIONS)
                .where(filter=FieldFilter('deleted', '==', True))
            )
            for snapshot in conversations.stream():
                scanned_tombstones += 1
                data = snapshot.to_dict() or {}
                if not isinstance(data, dict):
                    data = {}
                if not _needs_discard_stamp(data):
                    already_hidden += 1
                    continue
                written += 1
                if apply and batch is not None:
                    batch.update(snapshot.reference, {'discarded': True})
                    pending += 1
                    if pending >= _BATCH_LIMIT:
                        batch.commit()
                        batch = client.batch()
                        pending = 0
                    if delete_index is not None:
                        uid = _uid_from_snapshot(snapshot) or last_uid
                        try:
                            delete_index(uid, _conversation_id(snapshot))
                        except Exception:
                            pass

        if remaining is not None:
            remaining -= len(page)
        cursor = page[-1]
        if len(page) < take:
            break

    if apply and batch is not None and pending > 0:
        batch.commit()

    return {
        'scanned_users': scanned_users,
        'scanned_tombstones': scanned_tombstones,
        'already_hidden': already_hidden,
        'written': written,
        'last_uid': last_uid,
        'apply': apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write discarded=True. Default is dry-run.')
    parser.add_argument(
        '--page-size',
        type=int,
        default=_DEFAULT_PAGE_SIZE,
        help=f'Users per page (default {_DEFAULT_PAGE_SIZE}, max {_DEFAULT_PAGE_SIZE}).',
    )
    parser.add_argument('--start-after', default=None, metavar='UID', help='Resume after this user document id.')
    parser.add_argument('--limit', type=int, default=None, help='Optional max users to scan (smoke runs).')
    args = parser.parse_args()

    from database._client import get_firestore_client

    summary = run_backfill(
        get_firestore_client(),
        apply=args.apply,
        page_size=args.page_size,
        start_after=args.start_after,
        limit=args.limit,
    )
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
