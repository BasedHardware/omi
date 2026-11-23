#!/usr/bin/env python3
"""One-shot ghost-hold repair. Defaults to read-only counts; --apply enables writes.

Only results whose discovery hint is quarantine_held, summary receipt is ready,
and parts contain no quarantine are eligible. Each write uses the observed
update_time as an atomic precondition, so concurrent projection/privacy changes
cannot be overwritten. Jobs, receipts, ledger, and audio are never changed.

Run from backend/ with an explicitly selected project and namespace. This tool
is not a serving worker and must be run separately by an authorized operator.
"""

import argparse
import json
import math
import re
import sys
import time

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore

from database.batch_pipeline_projection_finish import projection_finish_state_fields

NAMESPACE_RE = re.compile(r'batch_pipeline_(prod|dev|test_[a-z0-9_]{1,40})\Z')
MAX_BATCH_SIZE = 250


def is_ghost_hold(entry: dict) -> bool:
    receipt = entry.get('projection')
    parts = entry.get('projection_parts', {})
    return bool(
        entry.get('projection_state') == 'quarantine_held'
        and isinstance(receipt, dict)
        and receipt.get('state') == 'ready'
        and isinstance(parts, dict)
        and all(isinstance(part, dict) and part.get('state') != 'quarantined' for part in parts.values())
    )


def reconcile(client, namespace, *, apply=False, batch_size=100, max_rows=10000, deadline_seconds=60.0):
    """Bound memory, rows and RPC time; emit only aggregate integer counts."""
    if not NAMESPACE_RE.fullmatch(namespace):
        raise ValueError('invalid namespace')
    if not 1 <= batch_size <= MAX_BATCH_SIZE or not 1 <= max_rows <= 1000000:
        raise ValueError('invalid row budget')
    if not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 3600:
        raise ValueError('invalid deadline')
    deadline = time.monotonic() + deadline_seconds
    counts = dict(scanned=0, matched=0, updated=0, conflicts=0, errors=0, deadline_reached=0)
    collection = client.collection(f'{namespace}_results')
    after = None
    while counts['scanned'] < max_rows:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            counts['deadline_reached'] = 1
            break
        size = min(batch_size, max_rows - counts['scanned'])
        query = collection.where('projection_state', '==', 'quarantine_held').order_by('__name__').limit(size)
        if after is not None:
            query = query.start_after({'__name__': after})
        # No implicit SDK retries can extend this one-shot's deadline.
        page = list(query.stream(timeout=min(3.0, remaining), retry=None))
        for snapshot in page:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                counts['deadline_reached'] = 1
                return counts
            counts['scanned'] += 1
            after = snapshot.reference
            if not is_ghost_hold(snapshot.to_dict() or {}):
                continue
            counts['matched'] += 1
            if not apply:
                continue
            try:
                # A finish-state write must carry the clock: with the backoff
                # lever on, a row without one is outside the filtered page.
                snapshot.reference.update(
                    {'projection_state': 'ready', **projection_finish_state_fields('ready', time.time())},
                    option=firestore.LastUpdateOption(snapshot.update_time),
                    timeout=min(3.0, remaining),
                    retry=None,
                )
                counts['updated'] += 1
            except (FailedPrecondition, NotFound):
                counts['conflicts'] += 1
        if len(page) < size:
            break
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--namespace', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Read aggregate counts only (default)')
    mode.add_argument('--apply', action='store_true', help='Explicitly enable conditional hint-only writes')
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--max-rows', type=int, default=10000)
    parser.add_argument('--deadline', type=float, default=60.0)
    args = parser.parse_args(argv)
    # Validate before constructing a client. Never surface SDK exception messages
    # or row identities, including on failure.
    if not NAMESPACE_RE.fullmatch(args.namespace):
        parser.error('invalid namespace')
    if not 1 <= args.batch_size <= MAX_BATCH_SIZE or not 1 <= args.max_rows <= 1000000:
        parser.error('invalid row budget')
    if not math.isfinite(args.deadline) or not 0 < args.deadline <= 3600:
        parser.error('invalid deadline')
    try:
        counts = reconcile(
            firestore.Client(project=args.project),
            args.namespace,
            apply=args.apply,
            batch_size=args.batch_size,
            max_rows=args.max_rows,
            deadline_seconds=args.deadline,
        )
    except Exception:
        print(json.dumps({'errors': 1}))
        return 1
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
