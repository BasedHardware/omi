#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Dry-run-default missing-artifact disposition. No media, keys, deletion or ACK.

Deploy readers to every serving status role before applying. An older reader
can still ACK a held-partial ledger, so do not roll readers back after apply.
Only the rollout lead may apply; this tool does not grant operator authority.
Output is aggregates and digests only. It never writes a plan containing IDs.
"""

import argparse
from dataclasses import fields
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_pipeline_held_disposition as held
from google.cloud import firestore, storage
from google.api_core.exceptions import GoogleAPICallError
from google.cloud.firestore_v1.base_query import FieldFilter
from database.batch_pipeline_artifact_missing import ArtifactMissingStore, fingerprint
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from database.batch_pipeline_projection import held_without_recovery
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.artifacts import ArtifactStore, ProtectionContext
from utils.batch_pipeline.contracts import WorkItem

OPERATION = 'artifact-missing-v1'
require = held.require


def checked(store, sid):
    def read(tx):
        job, _ = RecoveryStore(store).checked(tx, sid)
        require(
            held_without_recovery(job)
            and job.get('recovery_state') == 'failed_held'
            and job.get('quarantine_reason') == 'worker_failed'
            and not job.get('token')
            and job.get('lease_until', 0) <= time.time()
            and job.get('merge_pending') is False
            and not tx.get('results', sid),
            'idle_failed_held_required',
        )
        return job

    return held.readonly_run(store, read)


def inspect(store, artifacts, sid):
    job = checked(store, sid)
    snapshot = {key: value for key, value in job.items() if key != 'artifact_disposition'}
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    proof = artifacts.missing_audio_evidence(item, now=time.time())
    return snapshot, proof


def inspect_candidate(store, artifacts, sid):
    """A permission/transport error is unknown, never evidence for disposition."""
    try:
        snapshot, proof = inspect(store, artifacts, sid)
    except GoogleAPICallError:
        return None, None, 'unknown'
    return snapshot, proof, 'missing' if proof is not None else 'not_missing'


def plan_digest(units, cutoff, bucket):
    return hashlib.sha256(
        json.dumps(
            {
                'operation': OPERATION,
                'namespace': 'batch_pipeline_prod',
                'bucket': bucket,
                'cutoff': cutoff,
                'units': sorted(
                    (sid, fingerprint(job), proof['uri_sha256'], proof['generation']) for sid, job, proof in units
                ),
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
    ).hexdigest()


def apply_one(store, artifacts, sid, snapshot, digest):
    current, proof = inspect(store, artifacts, sid)
    require(current == snapshot and proof is not None, 'cohort_or_artifact_changed')
    return ArtifactMissingStore(store).apply(sid, snapshot, proof, digest, time.time())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prod'], required=True)
    parser.add_argument('--quarantined-before', required=True)
    parser.add_argument('--expect-count', required=True, type=int)
    parser.add_argument('--read-budget', type=int, default=1000)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--apply-limit', type=int, default=1)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    require(not os.getenv('FIRESTORE_EMULATOR_HOST'), 'cloud_only')
    require(
        os.getenv('GCP_AGENT_TIER') in (('prod-operator',) if args.apply else ('ro-prod', 'prod-operator')),
        'wrong_identity',
    )
    require(
        1 <= args.expect_count <= args.read_budget <= 5000 and 1 <= args.apply_limit <= args.expect_count,
        'invalid_budget',
    )
    cutoff = datetime.fromisoformat(args.quarantined_before.replace('Z', '+00:00'))
    require(cutoff.utcoffset() is not None and cutoff.utcoffset().total_seconds() == 0, 'utc_cutoff_required')
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '')
    require(bool(bucket), 'batch_bucket_required')
    client = firestore.Client(project='based-hardware')
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)

    def authorize(item):
        def check(tx):
            generation = tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            user = client.collection('users').document(item.owner_id).get(transaction=tx.transaction).to_dict() or {}
            return ProtectionContext(user.get('data_protection_level', 'enhanced'), generation)

        return held.readonly_run(store, check)

    def forbidden(*args):
        raise RuntimeError('metadata_only_operation')

    artifacts = ArtifactStore(
        storage.Client(project='based-hardware'),
        bucket=bucket,
        namespace=store.namespace,
        authorize=authorize,
        key_for_owner=forbidden,
        register_artifact=forbidden,
    )
    docs = list(
        client.collection('batch_pipeline_prod_jobs')
        .where(filter=FieldFilter('state', '==', 'quarantined'))
        .limit(args.read_budget + 1)
        .stream()
    )
    require(len(docs) <= args.read_budget, 'read_budget_exceeded')
    units = []
    unknown = 0
    for doc in docs:
        job = doc.to_dict() or {}
        if (
            job.get('recovery_state') != 'failed_held'
            or not 0 < job.get('quarantined_at', 0) <= cutoff.timestamp()
            or not held_without_recovery(job)
        ):
            continue
        snapshot, proof, outcome = inspect_candidate(store, artifacts, doc.id)
        unknown += outcome == 'unknown'
        if proof is not None:
            units.append((doc.id, snapshot, proof))
    require(len(units) == args.expect_count, 'missing_cohort_count_changed')
    units.sort(key=lambda unit: unit[0])
    digest = plan_digest(units, cutoff.isoformat(), bucket)
    output = {
        'operation': OPERATION,
        'mode': 'apply' if args.apply else 'dry_run',
        'missing_units': len(units),
        'metadata_unknown_units': unknown,
        'plan_sha256': digest,
        'audio_media_reads': 0,
        'job_completions': 0,
        'object_deletions': 0,
        'ledger_reclaims': 0,
        'provider_calls': 0,
    }
    if args.apply:
        require(args.approve_plan_sha256 == digest, 'approval_digest_changed')
        output['applied'] = sum(
            apply_one(store, artifacts, sid, snapshot, digest) for sid, snapshot, _ in units[: args.apply_limit]
        )
    else:
        output['firestore_writes'] = 0
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except held.Refused as error:
        print(json.dumps({'outcome': 'refused', 'reason': str(error)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({'outcome': 'error', 'reason': 'operation_failed_closed'}))
        sys.exit(1)
