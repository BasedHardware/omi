"""Backfill people label evidence from manual-assignment receipts for one account.

Default is a dry run that reads and reports; ``--apply`` writes. Resumable: pages
conversations by document id and records the last id in ``--checkpoint`` so an
interrupted run continues where it stopped. Idempotent per conversation, so a rerun
or an overlap with live labeling never double counts.

    python scripts/backfill_person_label_evidence.py --uid <uid> [--apply] [--checkpoint path]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import conversations as conversations_db
from database._client import get_firestore_client
from utils.person_evidence_backfill import backfill_person, receipt_conversations_by_person

RECEIPT_FIELDS = ['manual_speaker_assignments', 'manual_speaker_assignments_compressed', 'deleted']
PAGE_SIZE = 200


def _pages(client, uid: str, start_after: str | None):
    collection = client.collection('users').document(uid).collection(conversations_db.conversations_collection)
    cursor = start_after
    while True:
        query = collection.select(RECEIPT_FIELDS).order_by('__name__').limit(PAGE_SIZE)
        if cursor:
            query = query.start_after(collection.document(cursor))
        page = [(doc.id, doc.to_dict() or {}) for doc in query.stream()]
        if not page:
            return
        yield page
        cursor = page[-1][0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--uid', required=True)
    parser.add_argument('--apply', action='store_true', help='write tallies (default: dry run)')
    parser.add_argument('--checkpoint', type=Path, default=None, help='resume file holding the last conversation id')
    args = parser.parse_args(argv)

    client = get_firestore_client()
    start_after = args.checkpoint.read_text().strip() if args.checkpoint and args.checkpoint.exists() else None

    def decode(data):
        return conversations_db.decode_manual_speaker_assignments(
            args.uid, data.get('manual_speaker_assignments'), bool(data.get('manual_speaker_assignments_compressed'))
        )

    scanned = changed = 0
    now = datetime.now(timezone.utc)
    for page in _pages(client, args.uid, start_after):
        scanned += len(page)
        # Each page is applied before the checkpoint moves; per-conversation keys make a replay harmless.
        for person_id, ids in sorted(receipt_conversations_by_person(page, decode).items()):
            if backfill_person(client, args.uid, person_id, ids, now, apply=args.apply) is not None:
                changed += 1
        if args.checkpoint and args.apply:
            args.checkpoint.write_text(page[-1][0])
    print(json.dumps({'uid': args.uid, 'apply': args.apply, 'conversations': scanned, 'person_updates': changed}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
