#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Owner-scoped terminal-empty repair, dry-run default; no content in output.

Injected runtime encryption material only. Audio is read/decrypted in RAM. The
historical attestation asserts GPU padded empty and (for exhausted legacy rows)
multilingual empty, since old intents did not persist provider provenance. It
never asserts multilingual exhaustion for the old GPU canary. Its positive-VAD
route needs explicit epoch-2 authorization and a new, at-most-once paid token.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.rollout_cohorts import configure_rollout_runtime
import batch_pipeline_held_disposition as held
from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter
from database.batch_pipeline_policy import UnpinnedPolicyRefused
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_terminal_empty import TerminalEmptyStore, intent_snapshot, spent_canary, exhausted, idle
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.quarantine_recovery import log_terminal_empty
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    silence_payload,
    terminal_empty_payload,
    result_outcome,
)
from utils.batch_pipeline.speech_redrive import redrive_one

OPERATION = 'terminal-empty-disposition-v1'
require = held.require


def fingerprint(job):
    return hashlib.sha256(
        json.dumps([held.fingerprint(job), intent_snapshot(job)], sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def plan_digest(uid, cutoff, units, attestation, paid_epoch):
    return hashlib.sha256(
        json.dumps(
            {
                'operation': OPERATION,
                'owner': uid,
                'namespace': 'batch_pipeline_prod',
                'cutoff': cutoff,
                'units': sorted(units),
                'historical_attestation': attestation,
                'canary_paid_epoch': paid_epoch,
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
    ).hexdigest()


def checked_job(store, sid, uid, key):
    def check(tx):
        job, binding = TerminalEmptyStore(store, server_flags=None).checked(tx, sid)  # Read-only; never resolves.
        result = tx.get('results', sid)
        require(binding.owner_id == uid and fingerprint(job) == key, 'cohort_changed')
        marker = job.get('terminal_disposition') or {}
        if marker:
            require(
                marker.get('state') in {'prepared', 'completed'}
                and marker.get('prior_intents') == intent_snapshot(job),
                'invalid_terminal_intent',
            )
        else:
            require(idle(job, result, time.time()), 'unit_not_idle')
        return job

    return held.readonly_run(store, check)


def inspect_unit(store, artifacts, sid, uid, key, attestation):
    job = checked_job(store, sid, uid, key)
    marker = job.get('terminal_disposition') or {}
    if marker:
        return marker['outcome']
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    _, _, spans = inspect_audio(item, artifacts.fetch_audio(item))
    require(spent_canary(job) or exhausted(job, attestation), 'missing_exhaustion_evidence')
    if not spans:
        return 'silence'
    has_padded_empty = (
        job.get('worker_empty_evidence') == {'padded_retry': 'empty', 'version': 1}
        or attestation
        and not job.get('worker_empty_evidence')
    )
    if spent_canary(job):
        require(has_padded_empty, 'missing_padded_retry_evidence')
        return 'canary_recovery'
    require(has_padded_empty, 'missing_padded_retry_evidence')
    return 'no_recoverable_speech'


def apply_one(store, artifacts, sid, uid, key, decision, digest, attestation, paid_epoch, *, server_flags):
    if decision == 'canary_recovery':
        require(paid_epoch == 2, 'canary_epoch_2_authorization_required')
    job = checked_job(store, sid, uid, key)
    protocol = TerminalEmptyStore(store, server_flags=server_flags)
    try:
        job = protocol.prepare(sid, uid, digest, intent_snapshot(job), decision, attestation, time.time())
    except UnpinnedPolicyRefused:
        return 'policy_unpinned'
    marker = job['terminal_disposition']
    if marker['state'] == 'completed':
        return 'already_applied'
    if decision == 'canary_recovery':
        require(paid_epoch == 2, 'canary_epoch_2_authorization_required')
        # Epoch 1 stays untouched; the existing paid-epoch CAS handles provider,
        # cap, privacy, lost replies, and no retry after an uncertain call.
        return redrive_one(
            store,
            artifacts,
            sid,
            uid,
            digest,
            job['recovery'],
            server_flags=server_flags,
            gpu_padded_retry_empty=attestation,
        )
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    uri = artifacts.find_recovery_result(item, marker['token'])
    if uri:
        require(result_outcome(artifacts.load_result(item, uri)) == decision, 'artifact_outcome_changed')
    else:
        _, duration, spans = inspect_audio(item, artifacts.fetch_audio(item))
        require(bool(spans) == (decision == 'no_recoverable_speech'), 'vad_changed')
        payload = terminal_empty_payload(duration, spans) if spans else silence_payload(duration)
        uri = artifacts.persist_recovery_result(item, payload, marker['token'])
    changed = protocol.complete(sid, marker['token'], digest, uri, time.time())
    if changed and decision == 'no_recoverable_speech':
        log_terminal_empty()
    return 'completed' if changed else 'fenced'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prod'], required=True)
    parser.add_argument('--owner-env', default='DAVID_UID')
    parser.add_argument('--quarantined-before', required=True)
    parser.add_argument('--expect-count', required=True, type=int)
    parser.add_argument('--attest-pre-provenance-exhaustion', action='store_true')
    parser.add_argument(
        '--canary-paid-epoch',
        choices=[2],
        type=int,
        help='Explicit separate authorization only for a positive-VAD GPU canary',
    )
    parser.add_argument('--metadata-only', action='store_true', help='Read-only eligibility, no VAD or executable plan')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--apply-limit', type=int, default=1)
    parser.add_argument(
        '--server-flags-file', help='Serving role env JSON for units with no stored policy; absent refuses them'
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    require(not os.getenv('FIRESTORE_EMULATOR_HOST'), 'cloud_only')
    require(
        os.getenv('GCP_AGENT_TIER')
        in (('human', 'prod-operator') if args.apply else ('human', 'prod-operator', 'ro-prod')),
        'wrong_identity',
    )
    require(1 <= args.expect_count <= 20 and 1 <= args.apply_limit <= args.expect_count, 'invalid_budget')
    uid = os.getenv(args.owner_env, '')
    require(bool(uid) and '/' not in uid, 'owner_pin_required')
    cutoff_time = datetime.fromisoformat(args.quarantined_before.replace('Z', '+00:00'))
    offset = cutoff_time.utcoffset()
    require(offset is not None and offset.total_seconds() == 0, 'utc_cutoff_required')
    cutoff = cutoff_time.timestamp()
    server_flags = held.load_server_flags(args.server_flags_file)
    os.environ['OMI_ENV_STAGE'] = args.stage
    configure_rollout_runtime()
    if args.metadata_only:
        require(not args.apply, 'metadata_cannot_apply')
        client = firestore.Client(project='based-hardware')
        store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
        docs = list(
            client.collection('batch_pipeline_prod_jobs')
            .where(filter=FieldFilter('owner_id', '==', uid))
            .limit(1001)
            .stream()
        )
        require(len(docs) <= 1000, 'owner_read_budget')
        jobs = [(doc.id, doc.to_dict() or {}) for doc in docs]
        selected = [
            (sid, job)
            for sid, job in jobs
            if 0 < job.get('quarantined_at', 0) <= cutoff and job.get('state') == 'quarantined'
        ]
        require(len(selected) == args.expect_count, 'cohort_count_changed')
        counts = Counter()
        for sid, job in selected:
            job = checked_job(store, sid, uid, fingerprint(job))
            decision = (
                'spent_gpu_canary_needs_vad'
                if spent_canary(job)
                else (
                    'definite_multilingual_empty_needs_vad'
                    if exhausted(job, args.attest_pre_provenance_exhaustion)
                    else 'missing_exhaustion_evidence'
                )
            )
            counts[decision] += 1
        print(
            json.dumps(
                {
                    'operation': OPERATION,
                    'mode': 'metadata_only',
                    'owner_count': 1,
                    'units': len(selected),
                    'eligibility': dict(counts),
                    'firestore_writes': 0,
                    'paid_stt_calls': 0,
                    'executable_plan': False,
                },
                sort_keys=True,
            )
        )
        return
    secret, bucket = os.getenv('ENCRYPTION_SECRET', '').encode(), os.getenv('BUCKET_BATCH_PIPELINE', '')
    require(len(secret) >= 32 and bool(bucket), 'secure_runtime_material_required')
    os.environ['OMI_ENV_STAGE'] = args.stage
    client = firestore.Client(project='based-hardware')
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)

    class ReadOnlyStore:
        namespace, client = store.namespace, store.client

        def run(self, operation):
            return held.readonly_run(store, operation)

    read_store = ReadOnlyStore()
    artifacts = create_artifact_store(
        store if args.apply else read_store, storage.Client(project='based-hardware'), bucket, secret
    )

    def authorize(item):
        def check(tx):
            generation = tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            user = client.collection('users').document(item.owner_id).get(transaction=tx.transaction).to_dict() or {}
            return ProtectionContext(user.get('data_protection_level', 'enhanced'), generation)

        return held.readonly_run(store, check)

    artifacts.authorize = authorize
    docs = list(
        client.collection('batch_pipeline_prod_jobs')
        .where(filter=FieldFilter('owner_id', '==', uid))
        .limit(1001)
        .stream()
    )
    require(len(docs) <= 1000, 'owner_read_budget')
    selected = []
    for doc in docs:
        job = doc.to_dict() or {}
        if 0 < job.get('quarantined_at', 0) <= cutoff and (
            job.get('state') == 'quarantined' or job.get('terminal_disposition')
        ):
            selected.append((doc.id, fingerprint(job)))
    require(len(selected) == args.expect_count, 'cohort_count_changed')
    units = [
        (sid, key, inspect_unit(read_store, artifacts, sid, uid, key, args.attest_pre_provenance_exhaustion))
        for sid, key in sorted(selected)
    ]
    counts = Counter(decision for _, _, decision in units)
    require(counts['canary_recovery'] <= 1, 'canary_paid_budget')
    digest = plan_digest(uid, cutoff, units, args.attest_pre_provenance_exhaustion, args.canary_paid_epoch)
    output = {
        'operation': OPERATION,
        'mode': 'apply' if args.apply else 'dry_run',
        'owner_count': 1,
        'units': len(units),
        'dispositions': dict(counts),
        'plan_sha256': digest,
        'maximum_additional_paid_calls': counts['canary_recovery'],
        'unpinned_policy': 'server_flags' if server_flags else 'refuse',
        'firestore_writes': 0,
        'paid_stt_calls': 0,
    }
    if args.apply:
        # Per-unit mutation consumes its persisted recovery owner part.
        require(args.approve_plan_sha256 == digest, 'approval_digest_changed')
        require(not counts['canary_recovery'] or args.canary_paid_epoch == 2, 'canary_epoch_2_authorization_required')
        outcomes = Counter(
            apply_one(
                store,
                artifacts,
                sid,
                uid,
                key,
                decision,
                digest,
                args.attest_pre_provenance_exhaustion,
                args.canary_paid_epoch,
                server_flags=server_flags,
            )
            for sid, key, decision in units[: args.apply_limit]
        )
        output['outcomes'] = dict(outcomes)
        del output['firestore_writes'], output['paid_stt_calls']
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except held.Refused as error:
        print(json.dumps({'outcome': 'refused', 'reason': str(error)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({'outcome': 'error', 'reason': 'operation_failed_closed'}))
        sys.exit(1)
