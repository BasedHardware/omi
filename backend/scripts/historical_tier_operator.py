#!/usr/bin/env python3
"""Owner-scoped, bounded operator for the historical tier (T1+). Dry-run is the default.

``convert`` turns rows stuck on "Writing notes" into historical rows: completed
sync-backfill or batch rows older than the tier age whose intake minimum still
owes a first summary (``summary_due_at`` armed) that the 72 h enrichment age gate
will never deliver. Each conversion drops the provisional title marker and the
due time, and stamps ``processing_tier='historical'``, the no-derived-effects
marker and ``summary_blocked_reason='historical_on_open'``. The owner then gets
the summary when they open the row. ``clear-marker`` is the rollback: it removes
those three fields from an owner's historical rows that have no summary yet.

Operator runs need David's explicit approval; never apply from an agent session.
Production apply also requires ``--confirm-production-project based-hardware``.
Only classifier fields are read (no transcript or summary text), each write is
fenced on the row's update time, and stdout carries counts only, never IDs.

Usage (from backend/):
    python scripts/historical_tier_operator.py convert --uid <uid> [--limit 200]
    python scripts/historical_tier_operator.py convert --uid <uid> --apply --confirm-production-project based-hardware
    python scripts/historical_tier_operator.py clear-marker --uid <uid> [--apply ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import FailedPrecondition, NotFound  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1 import FieldFilter, LastUpdateOption  # noqa: E402

from config import historical_tier  # noqa: E402
from utils.conversations.historical_minimum import BLOCKED_REASON, TERMINAL_NO_DERIVED_EFFECTS_FIELD  # noqa: E402

PRODUCTION_PROJECT = 'based-hardware'
MAX_LIMIT = 500
DEFAULT_LIMIT = 200
BACKFILL_LANES = frozenset({'backfill', 'batch'})
CLASSIFIER_FIELDS = (
    'status',
    'deleted',
    'discarded',
    'deferred',
    'is_locked',
    'processing_state',
    'processing_tier',
    'created_at',
    'structured.title_provenance',
    'structured.overview',
    'user_title',
    'user_overview',
    'summary_due_at',
    'summary_lane',
    'summary_output_present',
    'summary_completed_at',
    'summary_blocked_reason',
    'summary_title_provenance',
    'finalization_status',
    TERMINAL_NO_DERIVED_EFFECTS_FIELD,
    'capture_time_trust',
)


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def convert_refusal(row: dict[str, Any], *, now: float) -> str | None:
    """None when the row is stuck old backfill this operator may convert; else the kept reason."""
    if row.get('status') != 'completed' or row.get('deleted') or row.get('discarded'):
        return 'lifecycle'
    if row.get('deferred') or row.get('is_locked') or row.get('processing_state') == 'local_pending':
        return 'local_only'
    if historical_tier.is_historical(row):
        return 'already_historical'
    if row.get('user_title') is not None or row.get('user_overview') is not None:
        return 'manual'
    structured = row.get('structured') or {}
    if row.get('summary_output_present') or row.get('summary_completed_at') or structured.get('overview'):
        return 'already_enriched'
    if row.get('summary_due_at') is None:
        return 'not_owed'
    if 'server_minimum' not in (structured.get('title_provenance'), row.get('summary_title_provenance')):
        return 'unknown_provenance'
    if row.get('finalization_status') in {'queued', 'leased', 'blocked_byok'}:
        return 'generation_owned'
    if row.get('summary_lane') not in BACKFILL_LANES:
        return 'not_backfill'
    created = _epoch(row.get('created_at'))
    if created is None or now - created <= historical_tier.min_age_seconds():
        return 'too_recent'
    return None


def convert_update() -> dict[str, Any]:
    return {
        'processing_tier': historical_tier.TIER,
        TERMINAL_NO_DERIVED_EFFECTS_FIELD: True,
        'summary_blocked_reason': BLOCKED_REASON,
        'summary_due_at': None,
        'summary_title_provenance': firestore.DELETE_FIELD,
        'structured.title_provenance': firestore.DELETE_FIELD,
    }


def clear_refusal(row: dict[str, Any], *, now: float) -> str | None:
    if not historical_tier.is_historical(row):
        return 'not_historical'
    structured = row.get('structured') or {}
    if row.get('summary_output_present') or structured.get('overview'):
        return 'already_enriched'
    return None


def clear_update() -> dict[str, Any]:
    update: dict[str, Any] = {
        'processing_tier': firestore.DELETE_FIELD,
        TERMINAL_NO_DERIVED_EFFECTS_FIELD: firestore.DELETE_FIELD,
        'summary_blocked_reason': firestore.DELETE_FIELD,
    }
    return update


MODES = {
    'convert': (convert_refusal, convert_update),
    'clear-marker': (clear_refusal, clear_update),
}


def _candidates(client: Any, uid: str, mode: str, limit: int) -> Iterable[Any]:
    conversations = client.collection('users').document(uid).collection('conversations')
    if mode == 'clear-marker':
        queries = [conversations.where(filter=FieldFilter('processing_tier', '==', historical_tier.TIER))]
    else:
        # summary_due_at is a number on current rows and a timestamp on older ones: one pass per type.
        queries = [
            conversations.where(filter=FieldFilter('summary_due_at', '>', 0)),
            conversations.where(filter=FieldFilter('summary_due_at', '>', datetime(1970, 1, 2, tzinfo=timezone.utc))),
        ]
    remaining = limit
    for query in queries:
        if remaining <= 0:
            return
        for snapshot in query.select(CLASSIFIER_FIELDS).limit(remaining).stream():
            remaining -= 1
            yield snapshot


def run(
    client: Any, uid: str, *, mode: str = 'convert', apply: bool = False, limit: int = DEFAULT_LIMIT, now=None
) -> dict:
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode}')
    if not uid or '/' in uid:
        raise ValueError('one owner uid is required')
    if not 0 < limit <= MAX_LIMIT:
        raise ValueError(f'limit must be 1..{MAX_LIMIT}')
    refusal, update = MODES[mode]
    current = time.time() if now is None else now
    counts: Counter = Counter()
    for snapshot in _candidates(client, uid, mode, limit):
        row = snapshot.to_dict() or {}
        counts['scanned'] += 1
        reason = refusal(row, now=current)
        if reason is not None:
            counts[f'kept_{reason}'] += 1
            continue
        counts['eligible'] += 1
        if row.get('capture_time_trust') == 'untrusted':
            counts['eligible_untrusted_clock'] += 1
        if not apply:
            continue
        try:
            snapshot.reference.update(update(), option=LastUpdateOption(snapshot.update_time))
            counts['written'] += 1
        except (FailedPrecondition, NotFound):
            counts['conflicts'] += 1
    return {'mode': mode, 'apply': apply, 'counts': dict(sorted(counts.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=sorted(MODES))
    parser.add_argument('--uid', required=True, help='The one owner whose rows are scanned.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help=f'Rows scanned, 1..{MAX_LIMIT}.')
    parser.add_argument('--apply', action='store_true', help='Write. Default is dry-run.')
    parser.add_argument('--confirm-production-project', help='Required for --apply on based-hardware.')
    args = parser.parse_args(argv)
    from database._client import get_firestore_client

    client = get_firestore_client()
    project = getattr(client, 'project', None) or os.getenv('GOOGLE_CLOUD_PROJECT')
    if args.apply and project == PRODUCTION_PROJECT and args.confirm_production_project != PRODUCTION_PROJECT:
        parser.error('--apply on production requires --confirm-production-project based-hardware')
    print(json.dumps(run(client, args.uid, mode=args.mode, apply=args.apply, limit=args.limit), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
