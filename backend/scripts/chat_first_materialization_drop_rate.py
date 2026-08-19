#!/usr/bin/env python3
"""Report how often a Chat-first proactive intent is never materialised.

Read-only. Performs no writes and creates no Firestore index.

Why this exists
---------------
``POST v2/chat/materialize-prompts`` hands a ready intent to whichever client is
foregrounded, and the *client's* kernel is the sole writer of the visible Chat
row; the server never writes one (see ``_materialize_prompts``). An intent is
retired account-wide the moment one client acknowledges it. Since #11844 a
client that receives an intent can persist the row and every other client sees
it, so cards no longer diverge *between* devices. The remaining failure mode is
narrower and account-wide: **no client ever materialised the intent at all**, so
the card exists nowhere.

That is what this script counts, and it is the number that decides whether
canonical server-side materialisation is worth building. If the drop rate is
negligible, that work buys very little. If cards are genuinely going missing,
this is the baseline to design against.

Why not the Prometheus counter
------------------------------
``CHAT_FIRST_PROACTIVE_TOTAL`` does label ``event='fetch'`` and
``event='kernel_receipt'``, which looks like the obvious source. It is not
readable in production: it is an in-process ``prometheus_client`` counter behind
a bearer-gated ``/metrics``, the API backend runs on Cloud Run with no scrape
annotation, and no dashboard or alert consumes it. Intent state, by contrast, is
durable in Firestore and survives instance churn -- so this reads the state.

What counts as a drop
---------------------
``delivered_at`` and ``materialization_receipt_id`` are written together, only on
acknowledgement (``acknowledge_materialization``), so "delivered but unreceipted"
is not a reachable state and is not what to look for. The signal is an intent
still sitting in ``ready`` or ``pending_kernel_receipt`` well past the age by
which a live client would have consumed it:

    dropped    delivery_state != 'delivered' and created_at older than --stale-after-hours
    in flight  delivery_state != 'delivered' and created_at newer than that
    delivered  delivery_state == 'delivered'

Drop rate is ``dropped / (dropped + delivered)``. Intents still in flight are
excluded from the denominator: their outcome is not yet decided.

Usage:
    python scripts/chat_first_materialization_drop_rate.py --uid <uid>
    python scripts/chat_first_materialization_drop_rate.py --limit 5000
    python scripts/chat_first_materialization_drop_rate.py --json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, cast

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database._client import db  # noqa: E402

INTENTS_COLLECTION = 'chat_first_proactive_intents'
DELIVERED = 'delivered'
DEFAULT_STALE_AFTER_HOURS = 48


def _documents(uid: str | None, limit: int | None) -> Iterator[Dict[str, Any]]:
    """Stream intent documents.

    A ``--uid`` run reads that user's subcollection directly. The account-wide
    run uses an unfiltered ``collection_group`` scan: age and delivery state are
    bucketed in Python precisely so this needs no composite index and no entry
    in ``firestore_index_registry``. Bound it with ``--limit`` on large projects.
    """

    if uid:
        query: Any = db.collection('users').document(uid).collection(INTENTS_COLLECTION)
    else:
        query = db.collection_group(INTENTS_COLLECTION)
    if limit is not None:
        query = query.limit(limit)
    for snapshot in query.stream():
        raw: object = snapshot.to_dict()
        if isinstance(raw, dict):
            yield cast(Dict[str, Any], raw)


def _created_at(document: Dict[str, Any]) -> datetime | None:
    value = document.get('created_at')
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _block_types(document: Dict[str, Any]) -> List[str]:
    blocks = document.get('blocks')
    if not isinstance(blocks, list):
        return []
    types: List[str] = []
    for block in cast(List[Any], blocks):
        if isinstance(block, dict):
            block_type = cast(Dict[str, Any], block).get('type')
            if isinstance(block_type, str):
                types.append(block_type)
    return types


def summarize(
    documents: Iterable[Dict[str, Any]],
    *,
    scope: str,
    stale_after_hours: int,
    now: datetime,
) -> Dict[str, Any]:
    """Bucket intent documents into delivered / dropped / in-flight.

    Kept free of Firestore so the classification is unit-testable on its own.
    """

    cutoff = now - timedelta(hours=stale_after_hours)
    delivered = 0
    in_flight = 0
    undated = 0
    dropped_by_source: collections.Counter[str] = collections.Counter()
    dropped_by_block: collections.Counter[str] = collections.Counter()
    delivered_by_source: collections.Counter[str] = collections.Counter()

    for document in documents:
        source = str(document.get('source') or 'unknown')
        if document.get('delivery_state') == DELIVERED:
            delivered += 1
            delivered_by_source[source] += 1
            continue
        created_at = _created_at(document)
        if created_at is None:
            # Never silently fold a malformed record into either outcome.
            undated += 1
            continue
        if created_at > cutoff:
            in_flight += 1
            continue
        dropped_by_source[source] += 1
        for block_type in set(_block_types(document)):
            dropped_by_block[block_type] += 1

    dropped = sum(dropped_by_source.values())
    decided = dropped + delivered
    return {
        'scope': scope,
        'stale_after_hours': stale_after_hours,
        'delivered': delivered,
        'dropped': dropped,
        'in_flight': in_flight,
        'undated': undated,
        'decided': decided,
        'drop_rate': (dropped / decided) if decided else None,
        'dropped_by_source': dict(dropped_by_source.most_common()),
        'delivered_by_source': dict(delivered_by_source.most_common()),
        'dropped_by_block_type': dict(dropped_by_block.most_common()),
    }


def collect(uid: str | None, limit: int | None, stale_after_hours: int, now: datetime) -> Dict[str, Any]:
    return summarize(
        _documents(uid, limit),
        scope=uid or 'all_accounts',
        stale_after_hours=stale_after_hours,
        now=now,
    )


def render(report: Dict[str, Any]) -> str:
    rate = report['drop_rate']
    lines = [
        f"scope                {report['scope']}",
        f"stale after          {report['stale_after_hours']}h",
        f"delivered            {report['delivered']}",
        f"dropped              {report['dropped']}",
        f"still in flight      {report['in_flight']} (excluded from the rate)",
        f"drop rate            {'n/a (no decided intents)' if rate is None else f'{rate:.2%}'}",
    ]
    if report['undated']:
        lines.append(f"undated records      {report['undated']} (no created_at; not counted either way)")
    for label, key in (('dropped by source', 'dropped_by_source'), ('dropped by block type', 'dropped_by_block_type')):
        if report[key]:
            lines.append(f"{label}:")
            lines.extend(f"  {name:<24} {count}" for name, count in cast(Dict[str, int], report[key]).items())
    return '\n'.join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid', help='Scope to one account. Omit to scan every account.')
    parser.add_argument('--limit', type=int, help='Maximum intent documents to read.')
    parser.add_argument(
        '--stale-after-hours',
        type=int,
        default=DEFAULT_STALE_AFTER_HOURS,
        help=f'Age past which an unacknowledged intent counts as dropped (default {DEFAULT_STALE_AFTER_HOURS}).',
    )
    parser.add_argument('--json', action='store_true', help='Emit the report as JSON.')
    parser.add_argument(
        '--fail-over-rate',
        type=float,
        help='Exit 1 when the drop rate exceeds this fraction, for use as a scheduled check.',
    )
    args = parser.parse_args(argv)

    report = collect(args.uid, args.limit, args.stale_after_hours, datetime.now(timezone.utc))
    print(json.dumps(report, indent=2) if args.json else render(report))

    rate = report['drop_rate']
    if args.fail_over_rate is not None and rate is not None and rate > args.fail_over_rate:
        print(f'drop rate {rate:.2%} exceeds {args.fail_over_rate:.2%}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
