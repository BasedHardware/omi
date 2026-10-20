# LIFECYCLE: permanent
"""Operator CLI for `rollout_cohorts/_ramp` (contracts (f), (h)). Never prints uids or SDK errors.

Writes are CAS on --expected-revision (read it with --show). Authority (contract (g)):
- during the ladder the controller is the only percent writer, so percent writes here are refused
  unless the env is unseeded (seed) or the operator holds locked_by (set it first with --lock);
- legacy_sync (on|draining|dark) and locked_by are the lead's writes;
- --clear-lock writes locked_by=null with reason `lock_cleared`, which also acknowledges the
  controller's two-rollbacks stop;
- a quality-floor percent (first-summary) below its floor needs --allow-quality-decrease. Seed
  `_ramp` with first-summary=100, or leave it out so serving keeps the env value.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database import rollout_cohorts as store  # noqa: E402
from scripts.rollout.ramp_controller import DRAINING_PRECONDITIONS, QUALITY_FLOOR  # noqa: E402
from utils.rollout.runtime_percent import write_ramp  # noqa: E402

EXPECTED_TIER = {'prod': 'prod-operator', 'staging': 'dev-operator'}
DEFAULT_TARGET = {'prod': ('based-hardware', '(default)'), 'staging': ('based-hardware-dev', 'staging')}
CONTROLLER_ACTOR = 'ramp-controller'


def parse_percent(text: str) -> tuple[str, float]:
    name, sep, value = text.partition('=')
    if not sep or name not in store.RAMP_NAMES:
        raise argparse.ArgumentTypeError('expected NAME=VALUE with NAME in ' + ','.join(store.RAMP_NAMES))
    try:
        return name, float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('percent must be a number') from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=sorted(EXPECTED_TIER), required=True)
    parser.add_argument('--project')
    parser.add_argument('--database')
    op = parser.add_mutually_exclusive_group(required=True)
    op.add_argument('--show', action='store_true', help='Print the env entry and document revision (read-only)')
    op.add_argument('--percent', type=parse_percent, action='append', help='NAME=VALUE (repeatable)')
    op.add_argument('--legacy-sync', choices=store.LEGACY_SYNC_MODES)
    op.add_argument('--lock', metavar='WHO', help='Set locked_by (the controller refuses while set)')
    op.add_argument('--clear-lock', action='store_true', help='Set locked_by=null (acknowledges a controller stop)')
    parser.add_argument('--expected-revision', type=int)
    parser.add_argument('--actor', help='Who is writing, e.g. lead or david (never ramp-controller)')
    parser.add_argument('--reason', help='lower_snake reason token (RampReason / LegacyDarkReason member)')
    parser.add_argument(
        '--precondition-met',
        action='append',
        default=[],
        metavar='ID',
        help='Confirm a draining precondition (repeat for each): ' + ', '.join(sorted(DRAINING_PRECONDITIONS)),
    )
    parser.add_argument(
        '--allow-quality-decrease',
        action='store_true',
        help='Permit writing a quality-floor percent (' + ', '.join(sorted(QUALITY_FLOOR)) + ') below its floor',
    )
    parser.add_argument('--apply', action='store_true', help='Perform the write (default is a dry run)')
    return parser


def plan_change(args: argparse.Namespace, entry: dict[str, Any] | None) -> tuple[dict[str, Any], str] | str:
    """Return (change, reason) or a refusal code. Pure."""
    if args.percent:
        if entry is not None and entry['locked_by'] is None and entry['percents']:
            return 'percent_write_requires_operator_lock'
        percents = dict(args.percent)
        # A seed equal to the batch percent would cut prod's live first-summary guarantee (100) to the cohort.
        lowered = sorted(n for n, floor in QUALITY_FLOOR.items() if n in percents and percents[n] < floor)
        if lowered and not args.allow_quality_decrease:
            return 'quality_floor:' + ','.join(lowered)
        return {'percents': percents}, args.reason or 'unknown'
    if args.legacy_sync:
        leaving_on = args.legacy_sync != 'on' and (entry is None or entry['legacy_sync'] == 'on')
        missing = sorted(set(DRAINING_PRECONDITIONS) - set(args.precondition_met or ()))
        if leaving_on and missing:
            return 'draining_precondition_unmet:' + ','.join(missing)
        return {'legacy_sync': args.legacy_sync}, args.reason or 'unknown'
    if args.lock:
        return {'locked_by': args.lock}, args.reason or 'locked_by_operator'
    if args.clear_lock:
        return {'locked_by': None}, 'lock_cleared'
    return 'no_operation'


def main(argv: Sequence[str] | None = None, *, client_factory: Callable[..., Any] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project, database = DEFAULT_TARGET[args.env]
    project, database = args.project or project, args.database or database
    client = (client_factory or firestore.Client)(project=project, database=database)
    try:
        document = store.read_ramp(firestore_client=client, timeout=store.OPERATOR_READ_TIMEOUT_SECONDS)
    except Exception:
        print('ramp read failed; no SDK error is printed', file=sys.stderr)
        return 1
    revision = document['revision'] if document is not None else 0
    entry = document['envs'].get(args.env) if document is not None else None
    if args.show:
        print(json.dumps({'env': args.env, 'revision': revision, 'entry': entry}, sort_keys=True))
        return 0
    if args.actor is None or args.actor == CONTROLLER_ACTOR or args.expected_revision is None:
        print('writes need --actor (not ramp-controller) and --expected-revision', file=sys.stderr)
        return 2
    planned = plan_change(args, entry)
    if isinstance(planned, str):
        print('ramp_set refused: ' + planned, file=sys.stderr)
        return 2
    change, reason = planned
    if not args.apply:
        print('dry run: ' + json.dumps({'env': args.env, 'change': change, 'reason': reason, 'revision': revision}))
        return 0
    if os.getenv('GCP_AGENT_TIER') != EXPECTED_TIER[args.env]:
        print('select the matching GCP operator tier before applying', file=sys.stderr)
        return 2
    try:
        new_revision = write_ramp(
            args.env,
            change,
            expected_revision=args.expected_revision,
            actor=args.actor,
            reason=reason,
            firestore_client=client,
        )
    except store.RampRevisionConflict as conflict:
        print(
            f'revision moved: expected={conflict.expected} actual={conflict.actual}; re-read with --show',
            file=sys.stderr,
        )
        return 3
    except store.RampDocumentError as error:
        print('ramp_set refused: ' + str(error), file=sys.stderr)
        return 2
    except Exception:
        print('ramp write failed; no SDK error is printed. Re-read with --show before retrying.', file=sys.stderr)
        return 1
    print(f'written revision={new_revision}; serving processes pick it up within 30s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
