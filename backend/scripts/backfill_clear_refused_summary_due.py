#!/usr/bin/env python3
"""Clear overdue summary indexes on durably refused conversations, with a classifier-only projection.

Dry-run is the default. Do not point this at production from an agent session.
cl2-deploy runs dry-run, then a 5k apply canary, then the full apply.

Usage (from backend/):
    python scripts/backfill_clear_refused_summary_due.py --limit 5000
    python scripts/backfill_clear_refused_summary_due.py --apply --limit 5000 --cursor-file /private/tmp/summary-cursor.json
    python scripts/backfill_clear_refused_summary_due.py --apply --start-after /private/tmp/summary-cursor.json

--start-after reads a private JSON file containing {"due": <number>, "__name__":
<document path>}. --cursor-file checkpoints that pair after each committed page;
keep dry-run and apply cursor files separate. Stdout/stderr contain counts only,
never document paths. A conflict skips the changed row; a later sweep can revisit
it. Owed rows at every age, processing rows, generation-owned rows and local-only
rows are left alone. summary_first_pending_at is never changed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud.firestore_v1 import FieldFilter, LastUpdateOption
from utils.conversations import summary_delivery

_BATCH_LIMIT = 400
_DEFAULT_PAGE_SIZE = 400
# Project classifier fields only; nested provenance excludes generated summary
# text. Manual title/overview fields are needed solely for their nullness.
CLASSIFIER_FIELDS = (
    'summary_due_at',
    'status',
    'deleted',
    'discarded',
    'deferred',
    'is_locked',
    'processing_state',
    'structured.title_provenance',
    'relevance_decision.verdict',
    'relevance_decision.decided_by',
    'relevance_decision.reason',
    'data_protection_level',
    'terminal_no_derived_effects',
    'client_processing',
    'user_title',
    'user_overview',
    'summary_completed_at',
    'summary_output_present',
    'summary_blocked_reason',
    'summary_title_provenance',
    'finalization_job_id',
    'finalization_status',
)
DURABLE_REFUSALS = frozenset(
    {
        'lifecycle',
        'manual',
        'already_enriched',
        'unknown_provenance',
        'privacy',
        'content_below_floor',
        *summary_delivery.EMPTY_BLOCKED_REASONS,
    }
)


def durable_refusal(row: dict[str, Any]) -> str | None:
    """Use the serving classifier, with explicit exclusions for transient owners.

    refusal() prioritizes lifecycle/manual/etc. over generation ownership, so
    these exclusions must precede it even when another refusal flag is present.
    """
    if (
        row.get('status') != 'completed'
        or row.get('finalization_job_id')
        or row.get('finalization_status') == 'blocked_byok'
    ):
        return None
    reason = summary_delivery.refusal(row)
    return reason if reason in DURABLE_REFUSALS else None


def _commit(client: Any, snapshots: list[Any]) -> tuple[int, int]:
    batch = client.batch()
    for snapshot in snapshots:
        batch.update(snapshot.reference, {'summary_due_at': None}, option=LastUpdateOption(snapshot.update_time))
    try:
        batch.commit()
        return len(snapshots), 0
    except (FailedPrecondition, NotFound):
        # A Firestore batch is atomic: one changed/deleted row aborts the whole
        # batch. Retry each original precondition, never retry against new state.
        written = conflicts = 0
        for snapshot in snapshots:
            try:
                snapshot.reference.update({'summary_due_at': None}, option=LastUpdateOption(snapshot.update_time))
                written += 1
            except (FailedPrecondition, NotFound):
                conflicts += 1
        return written, conflicts


def _checkpoint(path: Path, cursor: dict[str, Any]) -> None:
    # Resume paths can identify accounts; write privately and never print them.
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(cursor, output)
    temporary.replace(path)


def run_backfill(
    client: Any,
    *,
    apply: bool = False,
    page_size: int = _DEFAULT_PAGE_SIZE,
    start_after: dict[str, Any] | None = None,
    limit: int | None = None,
    now: float | None = None,
    cursor_file: Path | None = None,
) -> dict[str, Any]:
    """Bounded collection-group pages, with an update-time fence on every clear.

    limit bounds scanned rows (not just writes), so a canary is bounded even
    when most of its page is owed. Restart a full sweep without its cursor to
    reconsider conflicts. The fixed cutoff and (due, name) cursor survive clears.
    """
    if limit is not None and limit <= 0:
        raise ValueError('limit must be positive')
    page_size = min(max(int(page_size), 1), _BATCH_LIMIT)
    cutoff = time.time() if now is None else now
    scanned = written = conflicts = 0
    classified: Counter[str] = Counter()
    cursor = None
    if start_after is not None:
        cursor = {'summary_due_at': start_after['due'], '__name__': client.document(start_after['__name__'])}
    while limit is None or scanned < limit:
        take = page_size if limit is None else min(page_size, limit - scanned)
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('summary_due_at', '<=', cutoff))
            .order_by('summary_due_at')
            .order_by('__name__')
            .select(CLASSIFIER_FIELDS)
            .limit(take)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        if not page:
            break
        pending = []
        for snapshot in page:
            row = snapshot.to_dict() or {}
            scanned += 1
            reason = durable_refusal(row)
            classified[reason or 'retained'] += 1
            if reason is not None and apply:
                if snapshot.update_time is None:
                    raise ValueError('update_time required')
                pending.append(snapshot)
        if pending:
            page_written, page_conflicts = _commit(client, pending)
            written += page_written
            conflicts += page_conflicts
        last = page[-1]
        due = last.to_dict()['summary_due_at']
        cursor = {'summary_due_at': due, '__name__': last.reference}
        if cursor_file is not None:
            _checkpoint(cursor_file, {'due': due, '__name__': last.reference.path})
        if len(page) < take:
            break
    return {
        'scanned': scanned,
        'eligible': sum(count for reason, count in classified.items() if reason != 'retained'),
        'classes': dict(sorted(classified.items())),
        'written': written,
        'conflicts': conflicts,
        'apply': apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Clear due. Default is dry-run.')
    parser.add_argument('--page-size', type=int, default=_DEFAULT_PAGE_SIZE, help='Rows per page (max 400).')
    parser.add_argument('--limit', type=int, default=None, help='Maximum rows scanned, including retained rows.')
    parser.add_argument('--start-after', type=Path, help='Resume from a private JSON (due + __name__) cursor file.')
    parser.add_argument(
        '--cursor-file', type=Path, help='Checkpoint after each successful page; contains document paths.'
    )
    args = parser.parse_args()
    try:
        from database._client import get_firestore_client

        cursor = json.loads(args.start_after.read_text()) if args.start_after else None
        result = run_backfill(
            get_firestore_client(),
            apply=args.apply,
            page_size=args.page_size,
            start_after=cursor,
            cursor_file=args.cursor_file,
            limit=args.limit,
        )
    except Exception:
        # SDK exception messages may contain document paths. Fail closed without
        # exposing them; resume from the last successful page's private cursor.
        print(json.dumps({'failed': 1}), file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
