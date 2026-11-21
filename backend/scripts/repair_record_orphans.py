#!/usr/bin/env python3
"""One bounded orphan page. Default dry-run; aggregate output only.

Approval binds a freshly reconstructed plan; no plan or identifiers are printed.
Private cursor files must not be committed or copied into coordination systems.
"""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.refactor_modes import batch_live_orphan_repair_enabled
from database._client import get_firestore_client
from database.batch_pipeline_store import FirestoreStore
from scripts.backfill_record_seal_nojob import read_server_flags, write_cursor
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.record_orphan_repair import OPERATION, discover, plan_repair, apply_repair, summary, EXITS
from utils.other.local_storage import create_storage_client


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'operation': OPERATION, 'outcome': 'invalid_arguments'}))
        raise SystemExit(2)


def run(args):
    after = json.loads(Path(args.after_file).read_text())['after'] if args.after_file else None
    flags = read_server_flags(args.server_flags_file)
    client = get_firestore_client()
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
    storage = create_storage_client()
    artifacts = artifacts_for(store)
    paths, next_after = discover(client, limit=args.limit, after=after)
    planned = plan_repair(store, paths, storage, artifacts, server_flags=flags)
    report = {**summary(planned), 'apply': args.apply}
    if args.next_file:
        write_cursor(args.next_file, next_after)
    if args.apply:
        outcomes = apply_repair(store, planned, args.approve_plan_sha256, storage, artifacts)
        report.update(outcomes=outcomes, outcome_exits={key: EXITS[key] for key in outcomes})
    return report


def main(argv=None):
    parser = CountsOnlyParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=128)
    parser.add_argument('--after-file')
    parser.add_argument('--next-file')
    parser.add_argument('--server-flags-file', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    allowed = {'prod-operator'} if args.apply else {'ro-prod', 'prod-operator'}
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('GCP_AGENT_TIER') not in allowed:
        parser.error('wrong identity')
    if not 1 <= args.limit <= 128:
        parser.error('bounded page required')
    if args.apply and (not args.approve_plan_sha256 or not batch_live_orphan_repair_enabled()):
        parser.error('dark switch and explicit digest approval required')
    if args.after_file and args.next_file and Path(args.after_file).resolve() == Path(args.next_file).resolve():
        parser.error('distinct private cursor files required')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    # SDK/provider diagnostics can contain private object paths. Suppress them
    # even on exceptions; only our closed aggregate vocabulary reaches output.
    with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
        report = run(args)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': OPERATION, 'outcome': 'error'}))
        sys.exit(1)
