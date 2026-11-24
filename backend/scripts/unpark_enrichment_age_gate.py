#!/usr/bin/env python3
"""Digest-approved age-gate unpark; default dry-run, counts and digest only.

Dry-run requires ro-prod or prod-operator. Apply requires prod-operator and the
fresh dry-run plan digest. The checkpoint is private, newest-first keyset state:
keep the input unchanged between dry-run and apply, advance only after settling
the page, and start refused rows from the beginning after remediation. Both modes
require the confirmed serving age window. A changed page requires a new dry-run.
ENRICHMENT_AGE_GATE_UNPARK_ENABLED=false disables apply before any client access.
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import enrichment as enrichment_config
from utils.enrichment import age_gate
from utils.enrichment.unpark import OPERATION, apply_unpark, discover, plan_unpark, summary

PROJECT = 'based-hardware'
TASKS_LOCATION = 'us-central1'


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'operation': OPERATION, 'outcome': 'invalid_arguments'}))
        raise SystemExit(2)


def write_cursor(path, after):
    """Atomically checkpoint an opaque page key under private scratch only."""
    path = Path(path)
    parent = path.parent.resolve()
    scratch = Path('/Volumes/Ephemeral/scratch').resolve()
    if not parent.is_relative_to(scratch) or parent.stat().st_mode & 0o077:
        raise ValueError('cursor directory must be private scratch (0700)')
    with tempfile.NamedTemporaryFile(mode='w', dir=parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump({'after': after}, handle)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = CountsOnlyParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=128)
    parser.add_argument('--after-file')
    parser.add_argument('--next-file', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--pace-seconds', type=float, default=1.0)
    parser.add_argument(
        '--serving-max-age-hours', type=float, required=True, help='Confirmed effective age window of the serving fleet'
    )
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    allowed = {'prod-operator'} if args.apply else {'ro-prod', 'prod-operator'}
    if (
        os.getenv('FIRESTORE_EMULATOR_HOST')
        or os.getenv('SERVICE_ACCOUNT_JSON')
        or os.getenv('GCP_AGENT_TIER') not in allowed
    ):
        parser.error('wrong identity for requested operation')
    if args.apply and not enrichment_config.age_gate_unpark_enabled():
        parser.error('age-gate unpark is disabled')
    if not 1 <= args.limit <= 128 or not 0 <= args.pace_seconds <= 60:
        parser.error('limit must be 1..128 and pace must be 0..60')
    if args.apply and not re.fullmatch(r'[0-9a-f]{64}', args.approve_plan_sha256 or ''):
        parser.error('apply requires a valid dry-run plan digest')
    if args.serving_max_age_hours < 0 or not math.isfinite(args.serving_max_age_hours * 3600):
        parser.error('serving age window must be finite and nonnegative')
    if args.after_file and Path(args.after_file).resolve() == Path(args.next_file).resolve():
        parser.error('input and output cursor files must differ')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    os.environ['ENRICHMENT_MAX_AGE_HOURS'] = str(args.serving_max_age_hours)
    after = json.loads(Path(args.after_file).read_text())['after'] if args.after_file else None
    client = firestore.Client(project=PROJECT)
    document_ids, next_after = discover(client, limit=args.limit, after=after)
    plan = plan_unpark(client, document_ids, now=time.time(), max_age_seconds=age_gate.max_age_seconds())
    report = {
        **summary(plan),
        'apply': args.apply,
        'project': PROJECT,
        'serving_max_age_hours': args.serving_max_age_hours,
    }
    if args.apply and args.approve_plan_sha256 != plan['plan_sha256']:
        report.pop('plan_sha256')
        print(json.dumps({**report, 'outcome': 'plan_changed'}, sort_keys=True))
        return
    # Validate and persist the next private checkpoint before any data mutation.
    # It does not advance the input; the operator chooses when to use it.
    write_cursor(args.next_file, next_after)
    if args.apply:
        os.environ['SYNC_TASKS_PROJECT'] = PROJECT
        os.environ['SYNC_TASKS_LOCATION'] = TASKS_LOCATION
        os.environ['DEMAND_PROCESSING_ENABLED'] = 'false'
        report['outcomes'] = apply_unpark(client, plan, args.approve_plan_sha256, pace_seconds=args.pace_seconds)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': OPERATION, 'outcome': 'error'}))
        sys.exit(1)
