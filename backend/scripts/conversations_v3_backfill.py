#!/usr/bin/env python3
"""Per-owner conversations v3 repair: re-derive legacy pendant/phone history through live v3, or
(--mode rederive-live) replan the owner's finished live v3 windows after a planner fix.

Runtime: PYTHONPATH=backend backend/.venv/bin/python backend/scripts/conversations_v3_backfill.py ...
with the prod-operator tier (Firestore read/write; it needs no Cloud Tasks or LLM access: the
service's sweep starts a planned run once CONVERSATIONS_V3_BACKFILL=on, on its own queue).

Owners come from a file (one uid per line, '#' comments; mode 0600 recommended) and are printed
only as owner[N]. Output is counts, windows, run ids and outcomes; never content or uids.

  run --dry-run   plan and price the window; reads only, writes nothing
  run             write the run ledger + start marker, then (default) wait for it to finish
  status          the owner's runs and their partition progress
  resume --run ID re-arm a run whose step retries ran out, or a blocked run after its cause is fixed
  undo --run ID   restore the run's legacy rows exactly and remove its derived rows; for a
                  rederive-live run, restore every row it changed, created or retired

Runbook: backend/docs/runbooks/conversations-v3.md (Backfill and repair).
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.conversations_v3 import HISTORICAL_SITDOWN_TIMING
from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from utils.conversations.v3 import Conflict, backfill

# Live speech this recent may still be in an open window or an unsealed recording.
LIVE_SETTLE = timedelta(minutes=15)


def read_owners(path: str) -> list[str]:
    owners = []
    for line in Path(path).read_text().splitlines():
        value = line.split('#', 1)[0].strip()
        if value:
            if '/' in value or len(value) > 128:
                raise SystemExit(f'owners file line {len(owners) + 1}: not a uid')
            owners.append(value)
    if not owners:
        raise SystemExit('owners file has no uids')
    if len(set(owners)) != len(owners):
        raise SystemExit('owners file repeats an owner')
    return owners


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def window(args) -> tuple[datetime, datetime]:
    until = parse_time(args.until) if args.until else datetime.now(timezone.utc)
    since = parse_time(args.since) if args.since else until - timedelta(days=args.days)
    if not since < until:
        raise SystemExit('window: since must be before until')
    if until - since > timedelta(days=31):
        raise SystemExit('window: at most 31 days per run; run consecutive windows instead')
    return since, until


def code_sha() -> str:
    try:
        return subprocess.run(
            ['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
        ).stdout.strip()
    except Exception:
        return os.getenv('OMI_BACKEND_RELEASE_SHA', 'unknown')


def show(label: str, data: dict) -> None:
    print(label + ' ' + ' '.join(f'{k}={round(v, 4) if isinstance(v, float) else v}' for k, v in data.items()))


def plan_owner(uid: str, label: str, since: datetime, until: datetime, mode: str, *, historical_sitdown=False):
    meta = store.backfill_window_metadata(uid, since, until)
    live = mode == backfill.LIVE_MODE
    counts = backfill.classify_live_window(meta) if live else backfill.classify_window(meta)
    partitions = backfill.plan_partitions(
        meta,
        since,
        until,
        max_rows=backfill.LIVE_PARTITION_ROWS if live else backfill.PARTITION_ROWS,
        historical_sitdown=historical_sitdown,
    )
    show(label + ' window', {'since': since.isoformat(), 'until': until.isoformat(), 'mode': mode})
    show(label + ' rows', counts)
    totals: dict = {}
    if historical_sitdown:
        gap, lock = HISTORICAL_SITDOWN_TIMING
        show(label + ' timing', {'silence_seconds': gap, 'landing_lock_seconds': lock})
    now = datetime.now(timezone.utc) if historical_sitdown else None
    for index, partition in enumerate(partitions):
        if live:
            estimate = backfill.estimate_live_partition(
                uid,
                partition,
                run_id='dry-run',
                now=now,
                historical_sitdown=historical_sitdown,
                internal_end=index + 1 < len(partitions),
            )
        else:
            estimate = backfill.estimate_partition(uid, partition, run_id='dry-run', rederive=mode == 'rederive')
        for key, value in estimate.items():
            totals[key] = totals.get(key, 0) + value
        partition['estimate'] = {
            k: estimate[k]
            for k in ('sources', 'stretches', 'outline_calls', 'notes_calls', 'windows_after', 'rows_retired_est')
            if k in estimate
        }
    totals['usd'] = round(totals.get('usd', 0.0), 4)
    show(label + ' plan', {'partitions': len(partitions), 'forced_cuts': sum(p['forced_cut'] for p in partitions)})
    show(label + ' estimate', totals)
    if live:
        show(
            label + ' preview',
            {
                'windows': f"{totals.get('rows_eligible', 0)}->{totals.get('windows_after', 0)}",
                'visible': f"{totals.get('visible_before', 0)}->{totals.get('visible_after', 0)}",
                'rows_retired_est': totals.get('rows_retired_est', 0),
                # Sources too close to Firestore's 1 MiB document limit for a claims update: their rows stay.
                'sources_size_limit': totals.get('sources_blocked_size_limit', 0),
                # Live speech no window claimed: the run makes new cards of it.
                'sources_unclaimed': totals.get('sources_unclaimed', 0),
                # Windows the run would refuse to write (rederive_live_boundary): move since/until first.
                'windows_crossing_edge': totals.get('windows_crossing_edge', 0),
                'llm_calls': totals.get('outline_calls', 0)
                + totals.get('notes_calls', 0)
                + totals.get('short_task_calls', 0),
                'usd': totals['usd'],
            },
        )
    return counts, partitions, totals


def active_runs(uid: str) -> list[dict]:
    # A blocked run is still resumable: resume or undo it before planning another over the same rows.
    return [r for r in runs.list_runs(uid) if r.get('status') not in runs.FINISHED - {'blocked'}]


def wait_for(uid: str, label: str, run_id: str, minutes: int) -> str:
    deadline = time.monotonic() + minutes * 60
    last = None
    while True:
        run = runs.get_run(uid, run_id) or {}
        parts = run.get('partitions') or []
        state = (
            run.get('status'),
            sum(p.get('status') == 'committed' for p in parts),
            sum(int(p.get('notes_processed') or 0) for p in parts),
        )
        if state != last:
            show(
                label + ' progress',
                {
                    'status': state[0],
                    'partitions_committed': f'{state[1]}/{len(parts)}',
                    'notes_processed': state[2],
                    'notes_failed': sum(int(p.get('notes_failed') or 0) for p in parts),
                },
            )
            last = state
        if run.get('status') in runs.FINISHED:
            return run['status']
        if time.monotonic() >= deadline:
            return 'waiting_timed_out'
        time.sleep(30)


def cmd_run(args) -> int:
    owners = read_owners(args.owners_file)
    since, until = window(args)
    if args.historical_sitdown and (
        args.mode != backfill.LIVE_MODE or len(owners) != 1 or not (args.since and args.until)
    ):
        raise SystemExit('--historical-sitdown requires rederive-live, one owner and explicit --since and --until')
    settle = timedelta(seconds=HISTORICAL_SITDOWN_TIMING[1]) if args.historical_sitdown else LIVE_SETTLE
    if args.mode == backfill.LIVE_MODE and until > datetime.now(timezone.utc) - settle:
        # The live builder still owns the last minutes; a partition there would block as open.
        raise SystemExit(f'window: a rederive-live run must end at least {settle} ago (--until)')
    for number, uid in enumerate(owners, 1):
        label = f'owner[{number}]'
        if active_runs(uid):
            print(
                f'{label} skipped: a run is planned, running, blocked or undoing; resume or undo it first (see status)'
            )
            continue
        try:
            counts, partitions, estimate = plan_owner(
                uid, label, since, until, args.mode, historical_sitdown=args.historical_sitdown
            )
        except Conflict as error:
            if not args.historical_sitdown:
                raise
            show(label + ' blocked', {'reason': str(error)})
            return 1
        if args.dry_run:
            continue
        run_id = backfill.create_run(
            uid,
            since=since,
            until=until,
            mode=args.mode,
            operator=args.operator,
            code_sha=code_sha(),
            partitions=partitions,
            estimate=estimate,
            counts=counts,
            historical_sitdown=args.historical_sitdown,
        )
        print(f'{label} run={run_id} planned; the sweep starts it within ~5 minutes when CONVERSATIONS_V3_BACKFILL=on')
        if args.no_wait:
            if len(owners) > 1:
                print('owners run one at a time: stopping after the first planned run (--no-wait)')
                return 0
            continue
        outcome = wait_for(uid, label, run_id, args.wait_minutes)
        print(f'{label} run={run_id} outcome={outcome}')
        if outcome != 'committed':
            print('stopping: later owners wait until this run is committed, undone or resumed')
            return 1
        if number < len(owners):
            time.sleep(args.owner_gap_seconds)
    return 0


def cmd_status(args) -> int:
    for number, uid in enumerate(read_owners(args.owners_file), 1):
        for run in sorted(runs.list_runs(uid), key=lambda r: str(r.get('run_id'))):
            if args.run and run.get('run_id') != args.run:
                continue
            parts = run.get('partitions') or []
            show(
                f'owner[{number}] run={run.get("run_id")}',
                {
                    'mode': run.get('mode'),
                    'status': run.get('status'),
                    'since': str(run.get('since')),
                    'until': str(run.get('until')),
                    'partitions_committed': f'{sum(p.get("status") == "committed" for p in parts)}/{len(parts)}',
                    'blocked': ','.join(sorted({str(p.get('reason')) for p in parts if p.get('status') == 'blocked'}))
                    or '-',
                    'windows': sum(int(p.get('windows') or 0) for p in parts),
                    'home_visible': sum(int(p.get('home_visible') or 0) for p in parts),
                    'outline_calls': sum(int(p.get('outline_calls') or 0) for p in parts),
                    'notes_processed': sum(int(p.get('notes_processed') or 0) for p in parts),
                    'notes_failed': sum(int(p.get('notes_failed') or 0) for p in parts),
                    'estimate_usd': (run.get('estimate') or {}).get('usd'),
                },
            )
    return 0


def cmd_undo(args) -> int:
    status, found = 0, False
    for number, uid in enumerate(read_owners(args.owners_file), 1):
        label = f'owner[{number}]'
        run = runs.get_run(uid, args.run)
        if run is None:
            continue
        found = True
        if run.get('mode') == 'rederive':
            # Re-derived rows keep their original run's stamp; that run's undo removes them.
            print(f'{label} run={args.run} is a re-derive: undo the original run instead (see status)')
            status = 1
            continue
        if run.get('mode') == backfill.LIVE_MODE:
            priors = runs.list_priors(uid, args.run)
            show(
                label + ' undo scope',
                {
                    'run': args.run,
                    'rows_to_restore': sum(1 for p in priors if not p.get('created')),
                    'rows_to_remove': sum(1 for p in priors if p.get('created')),
                },
            )
            if not args.dry_run:
                result = backfill.undo_run(uid, args.run)
                show(label + ' undo', result)
                status |= result.get('outcome') != 'undone'
            continue
        docs = store.backfill_run_documents(uid, args.run)
        show(
            label + ' undo scope',
            {
                'run': args.run,
                'donors': sum(1 for d in docs if not d.get('v3_derived')),
                'derived_rows': sum(1 for d in docs if d.get('v3_derived')),
                # Donors whose copy the owner deleted stay converted with the copies they share.
                'donors_deleted_by_owner': sum(
                    1 for d in docs if not d.get('v3_derived') and store.deleted_after_backfill(d)
                ),
            },
        )
        if args.dry_run:
            continue
        result = backfill.undo_run(uid, args.run)
        show(label + ' undo', result)
        status |= result.get('outcome') != 'undone'
    if not found:
        print(f'run={args.run} not found for any listed owner')
        return 1
    return status


def cmd_resume(args) -> int:
    status, found = 0, False
    for number, uid in enumerate(read_owners(args.owners_file), 1):
        if runs.get_run(uid, args.run) is None:
            continue
        found = True
        result = backfill.resume_run(uid, args.run)
        show(f'owner[{number}] resume', {'run': args.run, **result})
        status |= result.get('outcome') != 'resumed'
    if not found:
        print(f'run={args.run} not found for any listed owner')
        return 1
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='plan (and with no --dry-run, start) a run per owner')
    run.add_argument('--owners-file', required=True)
    run.add_argument('--days', type=float, default=2.0, help='window length ending at --until (default 2)')
    run.add_argument('--since', help='ISO start; overrides --days')
    run.add_argument('--until', help='ISO end (default now)')
    run.add_argument('--mode', choices=('derive', 'rederive', 'rederive-live'), default='derive')
    run.add_argument(
        '--historical-sitdown', action='store_true', help='use the 900/3600 sit-down timing for live repair'
    )
    run.add_argument('--dry-run', action='store_true', help='counts and estimate only; writes nothing')
    run.add_argument('--operator', default=os.getenv('OMI_OPERATOR') or getpass.getuser())
    run.add_argument('--no-wait', action='store_true', help='plan one owner and return without waiting')
    run.add_argument('--wait-minutes', type=int, default=360)
    run.add_argument('--owner-gap-seconds', type=int, default=60)
    run.set_defaults(func=cmd_run)
    status = commands.add_parser('status', help="each owner's runs and progress")
    status.add_argument('--owners-file', required=True)
    status.add_argument('--run')
    status.set_defaults(func=cmd_status)
    resume = commands.add_parser('resume', help='re-arm a stalled or blocked run from its first unfinished partition')
    resume.add_argument('--owners-file', required=True)
    resume.add_argument('--run', required=True)
    resume.set_defaults(func=cmd_resume)
    undo = commands.add_parser('undo', help="restore a run's legacy rows and remove its derived rows")
    undo.add_argument('--owners-file', required=True)
    undo.add_argument('--run', required=True)
    undo.add_argument('--dry-run', action='store_true')
    undo.set_defaults(func=cmd_undo)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
