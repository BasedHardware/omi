#!/usr/bin/env python3
"""Regenerate one user's completed conversation summary vectors (Pinecone ns1).

Repairs the JIT/finalization gap: folder/apps obligations never owned summary
vectors. Deterministic IDs make reruns overwrite safely with fresh embeddings.
Dry-run (default) reads only conversation metadata/summary fields, never
transcripts, embeddings or Pinecone. --apply costs one fresh embedding per row.
Selection and Firestore reads are capped at 10 * --limit scanned documents,
including ineligible rows.
See backend/docs/runbooks/backfill-summary-vectors.md for operator sign-off.

Usage:
    python scripts/backfill_summary_vectors.py --uid <uid>
    python scripts/backfill_summary_vectors.py --uid <uid> --since 2026-08-01T00:00:00Z --limit 50 --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from itertools import islice
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logger = logging.getLogger(__name__)
DEFAULT_SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)


def iso_timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise argparse.ArgumentTypeError('Expected an ISO timestamp') from error
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def eligible(row: Mapping[str, Any], since: datetime) -> bool:
    created = row.get('created_at')
    if isinstance(created, str):
        try:
            created = iso_timestamp(created)
        except argparse.ArgumentTypeError:
            return False
    if not isinstance(created, datetime):
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    structured = row.get('structured')
    # Empty stubs have no summary worth embedding; do not fetch transcript/audio to check them.
    has_summary = isinstance(structured, Mapping) and any(
        str(structured.get(key) or '').strip() for key in ('title', 'overview')
    )
    return bool(
        created >= since
        and getattr(row.get('status'), 'value', row.get('status')) == 'completed'
        and not row.get('discarded')
        and not row.get('deleted')
        and has_summary
    )


@dataclass
class Summary:
    apply: bool
    scanned: int = 0
    selected: int = 0
    created: int = 0
    updated: int = 0
    error: int = 0
    stopped_error_budget: bool = False


def backfill_user(
    uid: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    since: datetime = DEFAULT_SINCE,
    limit: int = 500,
    apply: bool = False,
    write: Callable[[str, Mapping[str, Any]], str] | None = None,
) -> Summary:
    """Consume newest-first metadata rows. Stop above 10% of the selected batch's error budget."""
    summary = Summary(apply=apply)
    selected: list[Mapping[str, Any]] = []
    for row in islice(rows, limit * 10):
        summary.scanned += 1
        if eligible(row, since):
            selected.append(row)
            if len(selected) >= limit:
                break
    summary.selected = len(selected)
    if not apply:
        return summary
    if write is None:
        raise ValueError('--apply requires a writer')
    error_budget = math.floor(summary.selected * 0.1)
    for row in selected:
        try:
            outcome = write(uid, row)
            if outcome == 'created':
                summary.created += 1
            elif outcome == 'updated':
                summary.updated += 1
            else:
                raise RuntimeError('summary vector was not written')
        except Exception as error:
            summary.error += 1
            logger.warning('summary vector backfill failed: %s', type(error).__name__)
            if summary.error > error_budget:
                summary.stopped_error_budget = True
                break
    return summary


def metadata_rows(uid: str, since: datetime, scan_limit: int = 5000) -> Iterable[Mapping[str, Any]]:
    from database._client import get_firestore_client
    from database.conversations import conversations_collection
    from google.cloud.firestore_v1.base_query import FieldFilter

    # One range/order field avoids a new composite index. Visibility/status are filtered locally.
    query = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection(conversations_collection)
        .where(filter=FieldFilter('created_at', '>=', since))
        .order_by('created_at', direction='DESCENDING')
        .select(['id', 'created_at', 'status', 'discarded', 'deleted', 'structured'])
    )
    cursor = None
    remaining = scan_limit
    while remaining > 0:
        page_size = min(400, remaining)
        page = query.limit(page_size)
        if cursor is not None:
            page = page.start_after(cursor)
        snapshots = list(page.stream())
        for snapshot in snapshots:
            row = snapshot.to_dict()
            row['id'] = snapshot.id
            yield row
        remaining -= len(snapshots)
        if len(snapshots) < page_size:
            break
        cursor = snapshots[-1]


def write_summary(uid: str, metadata: Mapping[str, Any]) -> str:
    from database import conversations as conversations_db, vector_db
    from utils.conversations.factory import deserialize_conversation
    from utils.conversations.process_conversation import save_structured_vector

    # Re-read at write time: never index a row removed/discarded since selection.
    row = conversations_db.get_conversation(uid, str(metadata['id']))
    if not row or not eligible(row, datetime.min.replace(tzinfo=timezone.utc)):
        raise RuntimeError('selected conversation is no longer eligible')
    vector_id = f"{uid}-{metadata['id']}"
    existing = vector_db.index.fetch(ids=[vector_id], namespace='ns1')
    existed = bool(existing.vectors)
    if not save_structured_vector(uid, deserialize_conversation(row)):
        raise RuntimeError('summary vector upsert failed')
    # Same deletion race safeguard as the transcript-chunk analog.
    current = conversations_db.get_conversation(uid, str(metadata['id']))
    if not current or current.get('deleted') or current.get('discarded'):
        vector_db.delete_vector(uid, str(metadata['id']))
        raise RuntimeError('conversation removed during indexing')
    return 'updated' if existed else 'created'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--since', type=iso_timestamp, default=DEFAULT_SINCE)
    parser.add_argument('--limit', type=int, default=500)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true', help='Metadata-only preview (the default).')
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error('--limit must be positive')
    if args.apply:
        from database import vector_db

        if vector_db.index is None:
            print('Refusing --apply: no vector index configured.', file=sys.stderr)
            return 2
    summary = backfill_user(
        args.uid,
        metadata_rows(args.uid, args.since, scan_limit=args.limit * 10),
        since=args.since,
        limit=args.limit,
        apply=args.apply,
        write=write_summary if args.apply else None,
    )
    print(json.dumps(asdict(summary)))
    return 1 if summary.error else 0


if __name__ == '__main__':
    sys.exit(main())
