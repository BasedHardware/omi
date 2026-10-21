#!/usr/bin/env python3
"""Re-home conversations stranded on ``legacy_final_pass_v1`` before legacy sync leaves ``on``.

The ``legacy_final_pass_rehomed`` draining precondition (lead ruling b209a5,
``scripts/rollout/ramp_controller.py``): a conversation whose
``record_lane_owner`` is still ``legacy_final_pass_v1`` with no live legacy job
is moved to ``batch_sync_v1`` through ``utils.sync.final_pass_rehome``, the
same revision-fenced CAS the upload path uses in ``draining``/``dark``. Run it
after the other draining preconditions are met (batch at 100, C8 provider-STT
live), repeat until the verdict is CLEAR, then confirm the precondition.

Dry run by default: counts only, never a uid or conversation id.

    source ~/.local/bin/gcp-agent-env.sh ro-prod            # or ro-dev for staging
    cd backend && .venv/bin/python -m scripts.legacy_dark.final_pass_rehome --env prod

    source ~/.local/bin/gcp-agent-env.sh prod-operator      # dev-operator for staging
    .venv/bin/python -m scripts.legacy_dark.final_pass_rehome --env prod --apply --output <receipt.json>

The live-job lease has no Redis from an operator shell, so it is read from the
uid's ``sync_content_ledger`` fresh for every conversation (the sweep runs at
``on`` beside live legacy admission): an ACTIVE legacy processing claim, a
retryable legacy row, or any ledger row created in the last QUIET_SECONDS
holds the uid (conservative; the upload path re-homes the held ones later,
from the exact Redis pending index). Needs the
``conversations.record_lane_owner`` collection-group field index
(``scripts/reconcile_firestore_indexes.py``).

Exit codes: 0 CLEAR (nothing eligible or held remains, whole stock scanned),
1 REMAINING or PARTIAL (a --limit run never clears),
2 usage, credential, tier or index error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from utils.sync import legacy_dark
from utils.sync.final_pass_rehome import LEGACY_FINAL_PASS_OWNER, RehomeOutcome, rehome_final_pass_owner

LEDGER_COLLECTION = 'sync_content_ledger'
LEDGER_LIVE_STATUSES = ('processing', 'retryable')
BATCH_PROTOCOLS = ('batch_v1', 'stt_cap_hold_v1')
CONVERSATION_PATH_DEPTH = 4  # users/{uid}/conversations/{id}
# A uid with any ledger row this recent may have a legacy job starting right now.
QUIET_SECONDS = 600


def ledger_live_jobs(
    client: Any, *, now: Optional[datetime] = None, quiet_seconds: int = QUIET_SECONDS
) -> Callable[[str], Optional[int]]:
    """A per-uid probe over the ledger, read fresh on every call; None on any read error (held).

    The sweep runs at ``on`` beside live legacy admission, so nothing is cached:
    a uid holds while it has an ACTIVE legacy processing claim, a retryable legacy
    row, or any ledger row created inside the quiet window.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    def probe(uid: str) -> Optional[int]:
        moment = now or datetime.now(timezone.utc)
        try:
            ledger = client.collection('users').document(uid).collection(LEDGER_COLLECTION)
            live = 0
            for status in LEDGER_LIVE_STATUSES:
                for snapshot in ledger.where(filter=FieldFilter('status', '==', status)).stream():
                    row = snapshot.to_dict() or {}
                    if row.get('dispatch_protocol') in BATCH_PROTOCOLS:
                        continue
                    ownership = legacy_dark.classify_ledger_row(row, now=moment)
                    if status == 'retryable' or ownership is legacy_dark.LegacyOwnership.ACTIVE:
                        live += 1
            since = moment - timedelta(seconds=quiet_seconds)
            recent = ledger.where(filter=FieldFilter('created_at', '>=', since)).limit(1)
            live += sum(1 for _ in recent.stream())
            return live
        except Exception:
            return None

    return probe


def stranded_conversations(client: Any, *, limit: int = 0):
    """Yield (uid, conversation_id) for every conversation still routed to legacy_final_pass_v1."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    query = client.collection_group('conversations').where(
        filter=FieldFilter('record_lane_owner', '==', LEGACY_FINAL_PASS_OWNER)
    )
    if limit:
        query = query.limit(limit)
    for snapshot in query.stream():
        segments = tuple(str(getattr(snapshot.reference, 'path', '')).split('/'))
        if len(segments) != CONVERSATION_PATH_DEPTH or segments[0] != 'users' or segments[2] != 'conversations':
            yield None, None
            continue
        yield segments[1], segments[3]


def sweep(
    client: Any,
    *,
    apply: bool,
    limit: int = 0,
    now: Optional[datetime] = None,
    probe: Optional[Callable[[str], Optional[int]]] = None,
) -> dict[str, Any]:
    probe = probe if probe is not None else ledger_live_jobs(client, now=now)
    counts: Counter[str] = Counter()
    scanned = 0
    for uid, conversation_id in stranded_conversations(client, limit=limit):
        scanned += 1
        if uid is None:
            counts['skipped_shape'] += 1
            continue
        outcome = rehome_final_pass_owner(uid, conversation_id, firestore_client=client, live_jobs=probe, apply=apply)
        counts[outcome.value] += 1
    remaining = counts[RehomeOutcome.HELD.value] + counts[RehomeOutcome.ELIGIBLE.value]
    # A capped scan says nothing about the rows it never reached: never CLEAR.
    truncated = bool(limit) and scanned >= limit
    verdict = 'PARTIAL' if truncated else ('CLEAR' if remaining == 0 else 'REMAINING')
    return {
        'apply': apply,
        'scanned': scanned,
        'truncated': truncated,
        'counts': dict(sorted(counts.items())),
        'remaining_stranded': remaining,
        'verdict': verdict,
    }


def main(argv: Optional[list[str]] = None) -> int:
    from scripts.legacy_dark.drain_census import ENVIRONMENTS

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=sorted(ENVIRONMENTS), required=True)
    parser.add_argument('--apply', action='store_true', help='write the owner change (default: dry run)')
    parser.add_argument('--limit', type=int, default=0, help='stop after this many conversations (0: all)')
    parser.add_argument('--output', help='write the receipt JSON here as well as stdout')
    args = parser.parse_args(argv)

    tier = os.environ.get('GCP_AGENT_TIER', 'unknown')
    if args.apply and tier.startswith('ro-'):
        print(f'--apply needs an operator tier, not {tier}', file=sys.stderr)
        return 2
    try:
        from google.cloud import firestore

        project, database, _location = ENVIRONMENTS[args.env]
        client = firestore.Client(project=project, database=database)
        now = datetime.now(timezone.utc)
        result = sweep(client, apply=args.apply, limit=args.limit)
    except Exception as error:
        print(f'sweep failed: {type(error).__name__}', file=sys.stderr)
        return 2
    receipt = {'env': args.env, 'tier': tier, 'observed_at': now.isoformat(), **result}
    text = json.dumps(receipt, sort_keys=True)
    if args.output:
        with open(args.output, 'w') as handle:
            handle.write(text + '\n')
    print(text)
    return 0 if result['verdict'] == 'CLEAR' else 1


if __name__ == '__main__':
    sys.exit(main())
