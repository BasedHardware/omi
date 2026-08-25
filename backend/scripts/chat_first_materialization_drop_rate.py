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

Windowing
---------
By default this reads every intent ever written -- unlike the weekly
scheduled check (``run_scheduled_check`` in the health module this wraps),
which windows itself to the last ``HEALTH_CHECK_WINDOW_DAYS`` so a single
drop cannot latch its verdict unhealthy forever and so its read cost does not
grow with the collection's all-time size. This script has neither problem: it
is operator-invoked, not a permanent signal, and "what is our all-time drop
rate" is exactly the question it exists to answer. Pass ``--window-days`` to
scope a run to a recent period instead, e.g. to reproduce what the scheduled
check just alarmed on.

Usage:
    python scripts/chat_first_materialization_drop_rate.py --uid <uid>
    python scripts/chat_first_materialization_drop_rate.py --limit 5000
    python scripts/chat_first_materialization_drop_rate.py --window-days 14
    python scripts/chat_first_materialization_drop_rate.py --json
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.task_intelligence.chat_first_materialization_health import (  # noqa: E402
    DEFAULT_STALE_AFTER_HOURS,
    collect,
    json_report,
    render,
)


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
    parser.add_argument(
        '--window-days',
        type=int,
        help=(
            'Only read intents created in the last N days (default: unwindowed, all-time). '
            'Pass the same value the scheduled check uses (HEALTH_CHECK_WINDOW_DAYS) to reproduce its scan.'
        ),
    )
    parser.add_argument('--json', action='store_true', help='Emit the report as JSON.')
    parser.add_argument(
        '--fail-over-rate',
        type=float,
        help='Exit 1 when the drop rate exceeds this fraction, for use as a scheduled check.',
    )
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    min_created_at = now - timedelta(days=args.window_days) if args.window_days is not None else None
    report = collect(args.uid, args.limit, args.stale_after_hours, now, min_created_at)
    print(json_report(report) if args.json else render(report))

    rate = report['drop_rate']
    if args.fail_over_rate is not None and rate is not None and rate > args.fail_over_rate:
        print(f'drop rate {rate:.2%} exceeds {args.fail_over_rate:.2%}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
