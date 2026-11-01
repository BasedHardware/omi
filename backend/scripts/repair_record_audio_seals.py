#!/usr/bin/env python3
"""Repair exact record_pending jobs after retained-tail proof; dry-run by default.

Input: private JSON array of exact pending job IDs (1..128, no discovery scan).
Dry-run with ro-prod or prod-operator; a separately authorized operator must use
prod-operator with --apply --approve-plan-sha256 DIGEST from the dry-run.
Firestore emulator use is refused. This script prints
only aggregate counts, closed dispositions and the opaque plan digest.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database._client import get_firestore_client
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.record_seal_repair import apply_seals, plan_seals, plan_summary
from utils.other.local_storage import create_storage_client
from utils.batch_pipeline.record_producer_proof import load_pusher_pod_proof


def read_job_ids(path):
    values = json.loads(Path(path).read_text())
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 128
        or any(not isinstance(v, str) or not v or '/' in v or len(v) > 1500 for v in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError('expected 1..128 unique exact job IDs')
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids-file', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument(
        '--pusher-pods-file', help='private kubectl pusher pod List JSON; no environment payload needed'
    )
    parser.add_argument(
        '--pusher-pods-captured-at', help='RFC3339 capture time; inventory must be at most 5 minutes old'
    )
    parser.add_argument(
        '--producers-stopped',
        action='store_true',
        help='explicit operator attestation for legacy identity-less tokens only',
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    allowed_tiers = ('prod-operator',) if args.apply else ('ro-prod', 'prod-operator')
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('GCP_AGENT_TIER') not in allowed_tiers:
        parser.error('wrong identity for requested operation')
    if args.apply and not args.approve_plan_sha256:
        parser.error('apply requires a dry-run plan digest')
    if bool(args.pusher_pods_file) != bool(args.pusher_pods_captured_at):
        parser.error('pod inventory file and capture time are required together')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    job_ids = read_job_ids(args.ids_file)
    store = FirestoreStore('batch_pipeline_prod', firestore_client=get_firestore_client())
    proof = (
        load_pusher_pod_proof(args.pusher_pods_file, args.pusher_pods_captured_at) if args.pusher_pods_file else None
    )
    plan = plan_seals(
        store,
        job_ids,
        create_storage_client(),
        artifacts_for(store),
        producer_proof=proof,
        producers_stopped=args.producers_stopped,
    )
    report = plan_summary(plan)
    report['apply'] = args.apply
    if args.apply:
        report['outcomes'] = apply_seals(store, plan, args.approve_plan_sha256)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Exception messages can carry identifiers or storage paths.
        print(json.dumps({'operation': 'record-seal-repair-v1', 'outcome': 'error'}))
        sys.exit(1)
