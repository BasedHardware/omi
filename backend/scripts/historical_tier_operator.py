#!/usr/bin/env python3
"""Owner-scoped, bounded operator for the historical tier (T1+). Dry-run is the default.

``convert`` turns rows stuck on "Writing notes" into historical rows: completed
sync-backfill or batch rows older than the tier age whose intake minimum still
owes a first summary (``summary_due_at`` armed) that the enrichment age gate will
never deliver. Each conversion stamps ``processing_tier='historical'``, the
no-derived-effects marker, ``summary_blocked_reason='historical_on_open'`` and the
``historical_minimum`` title stand-in, drops the due time and the row-level
provisional marker, ends the row's open sync processing hold, and retires its
parked enrichment outbox row. The owner then gets the summary when they open it.

``clear-marker`` removes the tier, the no-derived-effects marker and the block from
an owner's historical rows that have no summary yet. It is not an exact inverse of
``convert``: the due time and the provisional marker stay gone, so the row owes no
automatic summary and the owner's Reprocess runs the full pipeline. Pass
``--from-receipt`` to clear exactly the rows one ``convert`` receipt wrote.

Operator runs need David's explicit approval; never apply from an agent session.
``--apply`` requires ``--approval-ref`` and writes a dated JSON receipt (mode, owner
hash, approval reference, counts and the written row IDs, for replay) under
``--receipt-dir``. Production apply also requires ``--confirm-production-project
based-hardware``. Only classifier fields are read (no transcript or summary
text), each write is fenced on the row's update time, and stdout carries counts
only, never IDs.

Usage (from backend/):
    python scripts/historical_tier_operator.py convert --uid <uid> [--limit 200]
    python scripts/historical_tier_operator.py convert --uid <uid> --apply --approval-ref <ref> \\
        --confirm-production-project based-hardware
    python scripts/historical_tier_operator.py clear-marker --uid <uid> [--from-receipt PATH] [--apply ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import FailedPrecondition, NotFound  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1 import FieldFilter, LastUpdateOption  # noqa: E402

from config import historical_tier  # noqa: E402
from config.historical_tier import BLOCKED_REASON, TERMINAL_NO_DERIVED_EFFECTS_FIELD  # noqa: E402

PRODUCTION_PROJECT = 'based-hardware'
MAX_LIMIT = 500
DEFAULT_LIMIT = 200
MAX_SCAN = 5000
DEFAULT_SCAN = 2000
PAGE_SIZE = 100
BACKFILL_LANES = frozenset({'backfill', 'batch'})
HOLD_FIELD = 'sync_processing_hold'
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
    f'{HOLD_FIELD}.pending_since',
    f'{HOLD_FIELD}.held',
)


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _summarized(row: dict[str, Any]) -> bool:
    # Presence receipts only: the summary text itself is never read.
    return row.get('summary_output_present') is not False or bool(row.get('summary_completed_at'))


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
    if _summarized(row):
        return 'already_enriched'
    if row.get('summary_due_at') is None:
        return 'not_owed'
    structured = row.get('structured') or {}
    if 'server_minimum' not in (structured.get('title_provenance'), row.get('summary_title_provenance')):
        return 'unknown_provenance'
    if row.get('finalization_status') in {'queued', 'leased', 'blocked_byok'}:
        return 'generation_owned'
    if row.get('summary_lane') not in BACKFILL_LANES:
        return 'not_backfill'
    created = _epoch(row.get('created_at'))
    boundary = historical_tier.min_age_seconds()
    if boundary <= 0 or created is None or now - created <= boundary:
        return 'too_recent'
    return None


def convert_update(row: dict[str, Any]) -> dict[str, Any]:
    update: dict[str, Any] = {
        'processing_tier': historical_tier.TIER,
        TERMINAL_NO_DERIVED_EFFECTS_FIELD: True,
        'summary_blocked_reason': BLOCKED_REASON,
        'summary_due_at': None,
        'summary_title_provenance': firestore.DELETE_FIELD,
        'structured.title_provenance': historical_tier.TITLE_PROVENANCE,
    }
    hold = row.get(HOLD_FIELD) or {}
    if hold.get('pending_since') is not None or hold.get('held'):
        # The hold epoch would otherwise stay open behind a wake that never runs.
        update.update(
            {f'{HOLD_FIELD}.pending_since': None, f'{HOLD_FIELD}.held': False, f'{HOLD_FIELD}.unprocessed_donor': False}
        )
    return update


def clear_refusal(row: dict[str, Any], *, now: float) -> str | None:
    if not historical_tier.is_historical(row):
        return 'not_historical'
    if _summarized(row):
        return 'already_enriched'
    return None


def clear_update(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'processing_tier': firestore.DELETE_FIELD,
        TERMINAL_NO_DERIVED_EFFECTS_FIELD: firestore.DELETE_FIELD,
        'summary_blocked_reason': firestore.DELETE_FIELD,
    }


MODES = {
    'convert': (convert_refusal, convert_update),
    'clear-marker': (clear_refusal, clear_update),
}


def _pages(query: Any, budget: int) -> Iterable[Any]:
    """Every row of ``query`` up to ``budget`` reads, paged by cursor so kept rows never stall a run."""
    last = None
    while budget > 0:
        page = query.limit(min(PAGE_SIZE, budget))
        if last is not None:
            page = page.start_after(last)
        snapshots = list(page.stream())
        for snapshot in snapshots:
            budget -= 1
            last = snapshot
            yield snapshot
        if len(snapshots) < PAGE_SIZE:
            return


def _candidates(client: Any, uid: str, mode: str, scan: int, ids: list[str] | None) -> Iterable[Any]:
    conversations = client.collection('users').document(uid).collection('conversations')
    if ids is not None:
        for conversation_id in ids[:scan]:
            snapshot = conversations.document(conversation_id).get(field_paths=CLASSIFIER_FIELDS)
            if snapshot.exists:
                yield snapshot
        return
    if mode == 'clear-marker':
        queries = [conversations.where(filter=FieldFilter('processing_tier', '==', historical_tier.TIER))]
    else:
        # summary_due_at is a number on current rows and a timestamp on older ones: one pass per type.
        queries = [
            conversations.where(filter=FieldFilter('summary_due_at', '>', 0)).order_by('summary_due_at'),
            conversations.where(
                filter=FieldFilter('summary_due_at', '>', datetime(1970, 1, 2, tzinfo=timezone.utc))
            ).order_by('summary_due_at'),
        ]
    remaining = scan
    for query in queries:
        for snapshot in _pages(query.select(CLASSIFIER_FIELDS), remaining):
            remaining -= 1
            yield snapshot
        if remaining <= 0:
            return


def _retire_parked_outbox(client: Any, uid: str, conversation_id: str) -> bool:
    """Retire the row's parked enrichment wake the way a completed wake ends: the CAS deletes it."""
    from utils.enrichment import age_gate, outbox

    def update(old):
        if old is None or not age_gate.parked(old) or old.get('lease_until', 0) > time.time():
            return old, False
        return None, True

    return bool(outbox.mutate_row(outbox.key(uid, conversation_id), update, client=client))


def run(
    client: Any,
    uid: str,
    *,
    mode: str = 'convert',
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    scan: int = DEFAULT_SCAN,
    ids: list[str] | None = None,
    now=None,
    retire_outbox: Callable[[Any, str, str], bool] = _retire_parked_outbox,
) -> dict:
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode}')
    if not uid or '/' in uid:
        raise ValueError('one owner uid is required')
    if not 0 < limit <= MAX_LIMIT:
        raise ValueError(f'limit must be 1..{MAX_LIMIT}')
    if not 0 < scan <= MAX_SCAN:
        raise ValueError(f'scan must be 1..{MAX_SCAN}')
    refusal, update = MODES[mode]
    current = time.time() if now is None else now
    counts: Counter = Counter()
    written: list[str] = []
    for snapshot in _candidates(client, uid, mode, scan, ids):
        if counts['eligible'] >= limit:
            break
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
            snapshot.reference.update(update(row), option=LastUpdateOption(snapshot.update_time))
        except (FailedPrecondition, NotFound):
            counts['conflicts'] += 1
            continue
        counts['written'] += 1
        written.append(snapshot.id)
        if mode == 'convert' and retire_outbox(client, uid, snapshot.id):
            counts['outbox_retired'] += 1
    return {'mode': mode, 'apply': apply, 'counts': dict(sorted(counts.items())), 'written_ids': written}


def owner_hash(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def write_receipt(directory: Path, uid: str, result: dict, approval_ref: str, *, now: datetime) -> Path:
    """The durable record of one applied run; its IDs let ``clear-marker --from-receipt`` replay it."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    path = directory / f'{stamp}-{result["mode"]}-{owner_hash(uid)}.json'
    receipt = {
        'mode': result['mode'],
        'owner_hash': owner_hash(uid),
        'approval_ref': approval_ref,
        'at': now.isoformat(),
        'counts': result['counts'],
        'written_ids': result['written_ids'],
    }
    with path.open('x') as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
    return path


def _receipt_ids(path: str, uid: str) -> list[str]:
    receipt = json.loads(Path(path).read_text())
    if receipt.get('mode') != 'convert' or receipt.get('owner_hash') != owner_hash(uid):
        raise ValueError('the receipt must be a convert receipt for this owner')
    return list(receipt.get('written_ids') or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=sorted(MODES))
    parser.add_argument('--uid', required=True, help='The one owner whose rows are scanned.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help=f'Eligible rows per run, 1..{MAX_LIMIT}.')
    parser.add_argument('--scan', type=int, default=DEFAULT_SCAN, help=f'Rows read per run, 1..{MAX_SCAN}.')
    parser.add_argument('--apply', action='store_true', help='Write. Default is dry-run.')
    parser.add_argument('--approval-ref', help="Required with --apply: where David's approval is recorded.")
    parser.add_argument('--receipt-dir', default='historical-tier-receipts', help='Where --apply writes its receipt.')
    parser.add_argument('--from-receipt', help='clear-marker only: clear exactly the rows this convert receipt wrote.')
    parser.add_argument('--confirm-production-project', help='Required for --apply on based-hardware.')
    args = parser.parse_args(argv)
    if args.apply and not (args.approval_ref or '').strip():
        parser.error('--apply requires --approval-ref naming the recorded approval')
    if args.from_receipt and args.mode != 'clear-marker':
        parser.error('--from-receipt replays a convert receipt with clear-marker')
    from database._client import get_firestore_client

    client = get_firestore_client()
    project = getattr(client, 'project', None) or os.getenv('GOOGLE_CLOUD_PROJECT')
    if args.apply and project == PRODUCTION_PROJECT and args.confirm_production_project != PRODUCTION_PROJECT:
        parser.error('--apply on production requires --confirm-production-project based-hardware')
    ids = _receipt_ids(args.from_receipt, args.uid) if args.from_receipt else None
    result = run(client, args.uid, mode=args.mode, apply=args.apply, limit=args.limit, scan=args.scan, ids=ids)
    output = {key: result[key] for key in ('mode', 'apply', 'counts')}
    if args.apply:
        receipt = write_receipt(
            Path(args.receipt_dir), args.uid, result, args.approval_ref.strip(), now=datetime.now(timezone.utc)
        )
        output['receipt'] = receipt.name
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
