#!/usr/bin/env python3
"""Rewrite the stored default emoji on notes served by the v2 notes contract.

Between the 2026-10-22 notes-v2 rollout and its fix, every v2 serve path asked
for structured notes without asking for an emoji, so the pydantic default
``🧠`` was stored on real conversations. This script finds the affected rows
for one owner — conversations with ``structured.emoji == '🧠'``, not discarded,
created at or after a given UTC time — and rewrites only ``structured.emoji``
with the same category fallback the serving path now applies. Under that
mapping every category yields a concrete stand-in — ``other`` maps to ``💬`` —
so each affected row is rewritten, none keeps ``🧠``, and everything else on
the document is left untouched.

Dry-run is the default and reads only. ``--apply`` writes through a transaction
that re-checks the stored emoji, so a concurrent reprocess cannot be clobbered.
The uid is read from a file — never argv — so it cannot leak through shell
history or process listings. Whether and where to run this is the rollout
lead's decision; do not point it at production without that approval.

Usage:
    python scripts/backfill_notes_v2_default_emoji.py --uid-file /path/uid.txt --since 2026-10-22T00:00:00Z
    python scripts/backfill_notes_v2_default_emoji.py --uid-file /path/uid.txt --since 2026-10-22T00:00:00Z --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from utils.llm.notes_output import DEFAULT_EMOJI, fallback_emoji

PAGE_SIZE = 300


def read_uid(path: Path) -> str:
    """The owner's uid: first nonempty line of the file, never an argv value."""
    uid = (path.read_text(encoding='utf-8').splitlines() or [''])[0].strip()
    if not uid:
        raise SystemExit(f'no uid found in {path}')
    return uid


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def created_at_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif hasattr(value, 'to_datetime'):
        parsed = value.to_datetime()
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def candidate_emoji(conversation: dict[str, Any]) -> Optional[str]:
    """The emoji this row should carry, or None when nothing better than the default exists."""
    structured = conversation.get('structured')
    if not isinstance(structured, dict) or structured.get('emoji') != DEFAULT_EMOJI:
        return None
    emoji = fallback_emoji(DEFAULT_EMOJI, structured.get('category'))
    return emoji if emoji != DEFAULT_EMOJI else None


def rewrite_emoji(client: Any, ref: Any, emoji: str) -> bool:
    from google.cloud import firestore

    from database._client import run_transactional

    @firestore.transactional
    def _rewrite(transaction: Any, ref: Any, emoji: str) -> bool:
        data = ref.get(transaction=transaction).to_dict() or {}
        if candidate_emoji(data) is None:
            return False
        transaction.update(ref, {'structured.emoji': emoji})
        return True

    return bool(run_transactional(client, _rewrite, ref, emoji))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid-file', required=True, type=Path, help='File whose first line is the owner uid.')
    parser.add_argument('--since', required=True, help='UTC ISO 8601 time; only conversations created at/after it.')
    parser.add_argument(
        '--apply', action='store_true', help='Rewrite structured.emoji. Default is a read-only dry run.'
    )
    parser.add_argument('--page-size', type=int, default=PAGE_SIZE, help='Conversations per page.')
    args = parser.parse_args()

    uid = read_uid(args.uid_file)
    since = parse_utc(args.since)

    from database._client import get_firestore_client
    from database.conversations import is_visible_conversation
    from google.cloud.firestore_v1 import FieldFilter

    client = get_firestore_client()
    outcomes: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    cursor: Optional[Any] = None
    while True:
        take = max(int(args.page_size), 1)
        query = (
            client.collection('users')
            .document(uid)
            .collection('conversations')
            .where(filter=FieldFilter('structured.emoji', '==', DEFAULT_EMOJI))
            .order_by('__name__')
            .limit(take)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        for doc in page:
            outcomes['scanned'] += 1
            conversation = doc.to_dict() or {}
            created_at = created_at_utc(conversation.get('created_at'))
            if created_at is None or created_at < since:
                outcomes['skipped_before_since'] += 1
                continue
            if not is_visible_conversation(conversation, include_discarded=False):
                outcomes['skipped_not_visible'] += 1
                continue
            emoji = candidate_emoji(conversation)
            if emoji is None:
                outcomes['skipped_no_category_fallback'] += 1
                continue
            if not args.apply:
                outcomes['planned'] += 1
                by_category[str((conversation.get('structured') or {}).get('category'))] += 1
                continue
            outcomes['rewritten' if rewrite_emoji(client, doc.reference, emoji) else 'refused_at_write'] += 1
        if len(page) < take:
            break
        cursor = page[-1]

    summary = dict(outcomes)
    summary.update(apply=args.apply, since=since.isoformat())
    if not args.apply:
        summary['planned_by_category'] = dict(by_category)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
