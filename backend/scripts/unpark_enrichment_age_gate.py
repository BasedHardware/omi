#!/usr/bin/env python3
"""Digest-approved age-gate unpark; default dry-run, counts and digest only.

Dry-run requires ro-prod or prod-operator. Apply requires prod-operator and the
fresh dry-run plan digest. The checkpoint is private, newest-first keyset state:
keep the input unchanged between dry-run and apply, advance only after settling
the page, and start refused rows from the beginning after remediation. An empty
page resets the cursor but does not prove that no later rows will be parked.
ENRICHMENT_AGE_GATE_UNPARK_ENABLED=false disables apply before any client access.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import enrichment as enrichment_config
from database._client import get_firestore_client
from utils.enrichment import age_gate
from utils.enrichment.unpark import apply_unpark, discover, plan_unpark, summary


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'operation': 'enrichment-age-gate-unpark-v1', 'outcome': 'invalid_arguments'}))
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
    if args.apply and not args.approve_plan_sha256:
        parser.error('apply requires a dry-run plan digest')
    if args.after_file and Path(args.after_file).resolve() == Path(args.next_file).resolve():
        parser.error('input and output cursor files must differ')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    after = json.loads(Path(args.after_file).read_text())['after'] if args.after_file else None
    client = get_firestore_client()
    document_ids, next_after = discover(client, limit=args.limit, after=after)
    plan = plan_unpark(client, document_ids, now=time.time(), max_age_seconds=age_gate.max_age_seconds())
    report = {**summary(plan), 'apply': args.apply}
    # Validate and persist the next private checkpoint before any data mutation.
    # It does not advance the input; the operator chooses when to use it.
    write_cursor(args.next_file, next_after)
    if args.apply:
        report['outcomes'] = apply_unpark(client, plan, args.approve_plan_sha256, pace_seconds=args.pace_seconds)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': 'enrichment-age-gate-unpark-v1', 'outcome': 'error'}))
        sys.exit(1)
