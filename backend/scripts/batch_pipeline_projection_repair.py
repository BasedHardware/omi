#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Re-project one owner's committed backlog. Dry-run by default; aggregate output only."""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database._client import get_firestore_client
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.projection import Projector
from utils.batch_pipeline.projection_repair import plan_owner, apply_owner
from utils.rollout_cohorts import configure_rollout_runtime

LOCAL_NAMESPACE_ID = re.compile(r'[a-z0-9_]{1,40}')


def local_firestore_client():
    # Loopback emulator only: explicit anonymous credentials so a local run
    # never uses interactive ADC or a service-account payload.
    project = (
        os.getenv('GCLOUD_PROJECT')
        or os.getenv('FIREBASE_PROJECT_ID')
        or os.getenv('GOOGLE_CLOUD_PROJECT')
        or 'demo-omi-local'
    )
    return firestore.Client(project=project, credentials=AnonymousCredentials())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prod', 'local'], required=True)
    parser.add_argument('--owner-env', default='DAVID_UID')
    parser.add_argument(
        '--local-namespace',
        help='id after batch_pipeline_test_ for --stage local; emulator-only, never a prod namespace',
    )
    parser.add_argument('--max-units', type=int, default=1000)
    parser.add_argument('--lookback-units', type=int, default=100)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    args = parser.parse_args()
    # Suppress library logs containing identifiers or content; own output is counts only.
    logging.disable(logging.CRITICAL)
    if args.stage == 'prod':
        if args.local_namespace:
            parser.error('--local-namespace applies to --stage local only; prod is fixed batch_pipeline_prod')
        if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('GCP_AGENT_TIER') != (
            'prod-operator' if args.apply else 'ro-prod'
        ):
            parser.error('wrong identity for requested operation')
        namespace, client = 'batch_pipeline_prod', get_firestore_client()
    else:
        host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
        if not host.startswith(('127.0.0.1:', 'localhost:')):
            parser.error('local requires loopback emulator; no cloud fallback')
        namespace_id = args.local_namespace or 'repair'
        if not LOCAL_NAMESPACE_ID.fullmatch(namespace_id):
            parser.error('--local-namespace must match [a-z0-9_]{1,40} (the batch_pipeline_test_<id> id)')
        namespace, client = f'batch_pipeline_test_{namespace_id}', local_firestore_client()
    owner = os.getenv(args.owner_env, '')
    os.environ['OMI_ENV_STAGE'] = args.stage
    store = FirestoreStore(namespace, firestore_client=client)
    plan = plan_owner(store, owner, max_units=args.max_units, lookback_units=args.lookback_units)
    report = {key: value for key, value in plan.items() if key != 'units'}
    report.update(apply=args.apply, planned_units=len(plan['units']))
    if args.apply:
        if args.approve_plan_sha256 != plan['plan_sha256']:
            parser.error('fresh dry-run plan approval required')
        if plan['unpinned_units']:
            parser.error('stored projection policy required; operator environment cannot pin it')
        configure_rollout_runtime()
        artifacts = artifacts_for(store)
        projector = Projector(
            store, artifacts.load_result, fetch_audio=artifacts.fetch_audio, require_lineage_fence=True
        )
        report['outcomes'] = apply_owner(projector, plan)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Library exceptions may contain storage paths/account identifiers.
        # Durable receipts make a fresh dry-run safe after any uncertain reply.
        print(json.dumps({'operation': 'batch-projection-repair-v1', 'outcome': 'error'}))
        sys.exit(1)
