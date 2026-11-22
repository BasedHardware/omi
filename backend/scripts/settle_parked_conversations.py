#!/usr/bin/env python3
"""SCA-3590 bounded status backfill. Checkpoints are private operator state.

Dry-run uses ro-prod. Apply uses prod-operator on the reviewed serving revision.
Keep one checkpoint per pass in an operator-only directory. The canary and
the rest of the apply pass must share a checkpoint and cutoff.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.parked_conversations import parked_terminal_status_enabled
from database import conversation_parked_status as parked

MAX_SCAN = 450_000
PAGE = 200
TX_SIZE = 100
CANARY_SIZE = 50
MAX_BATCH_WRITES = 2_000
# Two full passes together, including the canary and its exact readback,
# must stay under the issue's 7M read limit even when every row is eligible.
MAX_PASS_READS = 3_500_000
PROJECT = 'based-hardware'


def _save(path: Path, state: dict) -> None:
    temp = path.with_suffix('.next')
    descriptor = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(state, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def _initial_state(args, now: datetime) -> dict:
    applying = args.phase != 'dry-run'
    if args.phase == 'apply':
        raise ValueError('apply requires a verified canary checkpoint')
    return {
        'cutoff': args.cutoff.isoformat(),
        'utc_day': now.date().isoformat(),
        'applying': applying,
        'cursor': None,
        'scanned': 0,
        'prior_dry_run_rows': 0,
        'reserved_reads': 0,
        'counts': {},
        'canary_verified': False,
        'unfinished_transaction': False,
        'exhausted': False,
    }


def _can_resume(state: dict, phase: str, cutoff: datetime) -> bool:
    return (
        phase in {'canary', 'apply'}
        and state['applying']
        and state['canary_verified'] == (phase == 'apply')
        and not state['unfinished_transaction']
        and state['cutoff'] == cutoff.isoformat()
    )


def _page(client, state: dict, limit: int):
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter('status', '==', 'processing'))
        .where(filter=FieldFilter('finished_at', '<=', datetime.fromisoformat(state['cutoff'])))
        .order_by('finished_at')
        .order_by('__name__')
        .select(parked.ROW_FIELDS)
        .limit(limit)
    )
    if state['cursor']:
        clock, path = state['cursor']
        query = query.start_after(
            {'finished_at': DatetimeWithNanoseconds.from_rfc3339(clock), '__name__': client.document(path)}
        )
    return query.get(retry=None, timeout=30)


def _cursor(snapshot) -> list[str]:
    clock = snapshot.get('finished_at')
    return [
        clock.rfc3339() if isinstance(clock, DatetimeWithNanoseconds) else clock.isoformat().replace('+00:00', 'Z'),
        snapshot.reference.path,
    ]


def _validate_canary(candidates, statuses) -> None:
    for snapshot, outcome in zip(candidates, statuses, strict=True):
        if outcome not in parked.CANDIDATES:
            continue
        current = snapshot.reference.get(field_paths=parked.ROW_FIELDS, retry=None, timeout=15).to_dict()
        if current != {**snapshot.to_dict(), 'status': 'completed'}:
            raise RuntimeError('canary readback differed from the expected status-only update')


def run_pass(client, path: Path, state: dict, phase: str) -> str:
    apply = phase != 'dry-run'
    canary = phase == 'canary'
    cutoff = datetime.fromisoformat(state['cutoff'])
    write_limit = CANARY_SIZE if canary else MAX_BATCH_WRITES
    processed = 0
    counts = Counter(state['counts'])
    written = counts['written'] if canary else 0
    while not state['exhausted'] and state['scanned'] < MAX_SCAN:
        if apply and (written >= write_limit or (not canary and processed >= MAX_BATCH_WRITES)):
            return 'canary_paused' if canary else 'batch_limit'
        limit = min(PAGE, MAX_SCAN - state['scanned'])
        if apply:
            # Reaching either write cap cannot leave part of a queried page
            # uncheckpointed, even if every projected row is eligible.
            batch_rows = MAX_BATCH_WRITES - processed
            if batch_rows <= 0:
                return 'canary_scan_cap' if canary else 'batch_limit'
            limit = min(limit, write_limit - written, batch_rows)
        if datetime.now(timezone.utc).date().isoformat() != state['utc_day']:
            return 'utc_day_ended'
        if state['reserved_reads'] + limit * (9 if canary else 8) > MAX_PASS_READS:
            return 'read_cap'
        state['unfinished_transaction'] = True
        state['reserved_reads'] += limit
        _save(path, state)
        page = _page(client, state, limit)
        # Reserve worst-case reads before issuing each chunk. Max attempts=1
        # avoids implicit transaction retries exceeding the reservation.
        state['scanned'] += len(page)
        processed += len(page)
        for start in range(0, len(page), TX_SIZE):
            chunk = page[start : start + TX_SIZE]
            candidates = []
            for snapshot in chunk:
                parts = snapshot.reference.path.split('/')
                if len(parts) != 4 or parts[0] != 'users':
                    counts['other_collection'] += 1
                    continue
                disposition = parked.classify(snapshot.to_dict(), cutoff=cutoff)
                if disposition in parked.CANDIDATES:
                    candidates.append(snapshot)
                else:
                    counts[disposition] += 1
            if not candidates:
                continue
            state['reserved_reads'] += len(candidates) * (8 if canary else 7)
            _save(path, state)
            transaction = client.transaction(max_attempts=1, read_only=not apply)
            statuses = firestore.transactional(parked.settle_in_transaction)(
                transaction, client, candidates, cutoff=cutoff, apply=apply
            )
            if canary:
                _validate_canary(candidates, statuses)
            counts.update(statuses)
            written_now = sum(outcome in parked.CANDIDATES for outcome in statuses) if apply else 0
            written += written_now
            counts['written'] += written_now
        if page:
            state['cursor'] = _cursor(page[-1])
        state['counts'] = dict(counts)
        state['exhausted'] = len(page) < limit
        state['unfinished_transaction'] = False
        _save(path, state)
    return 'exhausted' if state['exhausted'] else 'scan_cap'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['dry-run', 'canary', 'apply'])
    parser.add_argument('--cutoff', required=True, type=datetime.fromisoformat)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--accept-canary', action='store_true')
    parser.add_argument('--restart-dry-run', action='store_true', help='restart a failed dry-run, retaining its budget')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.cutoff.tzinfo is None or args.cutoff > now - timedelta(hours=6):
        parser.error('cutoff must be timezone-aware and at least six hours old')
    expected_tier = 'ro-prod' if args.phase == 'dry-run' else 'prod-operator'
    if os.getenv('GCP_AGENT_TIER') != expected_tier or os.getenv('FIRESTORE_EMULATOR_HOST'):
        parser.error(f'use the {expected_tier} credential environment')
    if args.phase != 'dry-run' and not parked_terminal_status_enabled():
        parser.error('parked terminal status is disabled')
    if args.phase == 'apply' and not args.accept_canary:
        parser.error('review the exact canary receipt and pass --accept-canary')
    if args.restart_dry_run and args.phase != 'dry-run':
        parser.error('only a read-only dry-run can be restarted')

    args.checkpoint.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if args.checkpoint.parent.stat().st_mode & 0o077:
        parser.error('checkpoint directory must be private (0700)')
    lock = args.checkpoint.with_suffix('.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, 'r+') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.checkpoint.exists():
            state = json.loads(args.checkpoint.read_text())
            if (
                args.restart_dry_run
                and not state['applying']
                and state['unfinished_transaction']
                and state['cutoff'] == args.cutoff.isoformat()
            ):
                # Discard unusable classification counts after a corrected
                # reader, while retaining every scanned row and reserved read.
                state['prior_dry_run_rows'] = state['scanned']
                state['cursor'] = None
                state['counts'] = {}
                state['unfinished_transaction'] = False
            elif not _can_resume(state, args.phase, args.cutoff):
                parser.error('checkpoint does not match a clean canary or verified apply pass')
        else:
            state = _initial_state(args, now)
        if state['utc_day'] != now.date().isoformat():
            parser.error('checkpoint is from another UTC day; review remaining range on SCA-3590')
        _save(args.checkpoint, state)
        client = firestore.Client(project=PROJECT)
        try:
            stop = run_pass(client, args.checkpoint, state, args.phase)
            canary_writes = state['counts'].get('written', 0)
            if args.phase == 'canary' and (canary_writes == CANARY_SIZE or (stop == 'exhausted' and canary_writes)):
                state['canary_verified'] = True
                _save(args.checkpoint, state)
        except Exception as error:
            # Cloud exceptions may include document paths. Retain only the
            # exception class in operator output and stop on uncertainty.
            stop = type(error).__name__
        print(
            json.dumps(
                {
                    'phase': args.phase,
                    'stop': stop,
                    'rows_scanned': state['scanned'],
                    'prior_dry_run_rows': state.get('prior_dry_run_rows', 0),
                    'reserved_reads': state['reserved_reads'],
                    'counts': state['counts'],
                    'canary_verified': state['canary_verified'],
                },
                sort_keys=True,
            )
        )
    return int(state['unfinished_transaction'])


if __name__ == '__main__':
    raise SystemExit(main())
