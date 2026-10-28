#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Owner-scoped strict-VAD census and silent-only failed-held disposition.

Dry-run uses read-only Firestore transactions and GCS downloads. Canonical audio
exists only in memory. Never calls STT, resets a paid intent, or prints identifiers,
URIs, keys, exception bodies, words, or audio. Run with the existing secure runtime
ENCRYPTION_SECRET and BUCKET_BATCH_PIPELINE; do not fetch secrets in this script.
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

OPERATION = 'strict-vad-held-disposition-v1'


class Refused(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


SERVER_FLAG_ROLES = ('K_SERVICE', 'OMI_SYNC_STACK_ROLE')


def load_server_flags(path):
    """The serving role's live settings for units with no stored recovery policy.

    Without a file, such a unit is refused ('policy_unpinned'). This operator
    process's own environment is never used to pin a policy. The file is a JSON
    object exported from the serving role's env (e.g. the Cloud Run service);
    only its role name and BATCH_PIPELINE_* keys are kept, and it is never printed.
    """
    if not path:
        return None
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise Refused('server_flags_unreadable')
    require(
        isinstance(raw, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items()),
        'server_flags_invalid',
    )
    require(bool(raw.get('K_SERVICE', '').strip()), 'server_flags_role_required')
    return {k: v for k, v in raw.items() if k in SERVER_FLAG_ROLES or k.startswith('BATCH_PIPELINE_')}


def fingerprint(job):
    values = {
        key: job.get(key)
        for key in (
            'segment_id',
            'owner_id',
            'projection_binding',
            'audio_uri',
            'capture_at',
            'duration_seconds',
            'privacy_generation',
            'quarantined_at',
            'recovery',
        )
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan_digest(owner, namespace, cutoff, units):
    body = {
        'operation': OPERATION,
        'owner': owner,
        'namespace': namespace,
        'cutoff': cutoff,
        'units': sorted((sid, key, decision) for sid, key, decision in units),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def readonly_run(store, operation):
    from google.cloud import firestore
    from database.batch_pipeline_store import FirestoreTransaction

    @firestore.transactional
    def read(transaction):
        view = FirestoreTransaction(store.client, store.namespace, transaction)
        result = operation(view)
        require(not view.writes, 'unexpected_readonly_mutation')
        return result

    return read(store.client.transaction(read_only=True))


def checked_job(store, sid, uid, key):
    from database.batch_pipeline_quarantine_recovery import RecoveryStore
    from database.sync_ledger import batch_ledger_owes_held_units

    def check(tx):
        job, binding = RecoveryStore(store).checked(tx, sid, allow_completed_silence=True)
        result = tx.get('results', sid)
        require(binding.owner_id == uid and fingerprint(job) == key, 'cohort_changed')
        marker = job.get('silence_disposition') or {}
        if marker.get('state') == 'completed':
            require(job.get('result', {}).get('outcome') == 'silence', 'invalid_completed_disposition')
            return job
        require(
            job.get('state') == 'quarantined'
            and job.get('quarantine_reason') == 'worker_failed'
            and job.get('recovery_state') == 'failed_held',
            'not_failed_held',
        )
        require(
            not job.get('token')
            and job.get('lease_until', 0) <= time.time()
            and job.get('merge_pending') is False
            and not job.get('result')
            and not result,
            'active_or_receipted',
        )
        require(bool(job.get('recovery', {}).get('settled_at')), 'missing_terminal_intent')
        ledger = tx.get('content', f'{uid}/{binding.content_id}')
        require(batch_ledger_owes_held_units(ledger), 'completed_ledger')
        return job

    return readonly_run(store, check)


def inspect_unit(store, artifacts, sid, uid, key):
    from utils.batch_pipeline.contracts import held_silence_allowed
    from utils.batch_pipeline.contracts import WorkItem
    from utils.batch_pipeline.recovery_disposition import inspect_audio

    job = checked_job(store, sid, uid, key)
    if (job.get('silence_disposition') or {}).get('state') == 'completed':
        return 'silent'
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    audio = artifacts.fetch_audio(item)
    _, _, spans = inspect_audio(item, audio)
    # Drop all raw buffers before the next unit. No temporary files/caches.
    del audio
    if not spans:
        require(held_silence_allowed(job, 0), 'held_speech_blocks_silence')
    return 'speech' if spans else 'silent'


def apply_silent(store, artifacts, sid, uid, key, approved_digest, *, server_flags):
    from database.batch_pipeline_policy import UnpinnedPolicyRefused
    from database.batch_pipeline_quarantine_recovery import SilenceDispositionStore
    from utils.batch_pipeline.contracts import WorkItem
    from utils.batch_pipeline.recovery_disposition import (
        inspect_audio,
        silence_payload,
        result_outcome,
        result_vad_evidence,
    )

    job = checked_job(store, sid, uid, key)
    if (job.get('silence_disposition') or {}).get('state') == 'completed':
        return 'already_applied'
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    _, duration, spans = inspect_audio(item, artifacts.fetch_audio(item))
    require(not spans, 'silence_decision_changed')
    protocol = SilenceDispositionStore(store, server_flags=server_flags)
    try:
        job = protocol.prepare_silence(sid, uid, approved_digest, time.time())
    except UnpinnedPolicyRefused:
        return 'policy_unpinned'
    token = job['silence_disposition']['token']
    uri = artifacts.find_recovery_result(item, token)
    if uri:
        payload = artifacts.load_result(item, uri)
        require(result_outcome(payload) == 'silence', 'different_artifact_outcome')
    else:
        payload = silence_payload(duration)
        uri = artifacts.persist_recovery_result(item, payload, token)
    require(
        protocol.complete_silence(
            sid, token, approved_digest, uri, time.time(), measured_held_vad_speech_seconds=result_vad_evidence(payload)
        ),
        'completion_fenced',
    )
    return 'applied_silence'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prod'], required=True)
    parser.add_argument('--owner-env', default='DAVID_UID')
    parser.add_argument('--quarantined-before', required=True, help='UTC ISO-8601 cutoff')
    parser.add_argument('--expect-count', type=int, required=True)
    parser.add_argument('--max-units', type=int, default=200)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--apply-limit', type=int, default=1, help='Fixed silent prefix; repeat is idempotent')
    parser.add_argument(
        '--server-flags-file', help='Serving role env JSON for units with no stored policy; absent refuses them'
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    require(not os.getenv('FIRESTORE_EMULATOR_HOST'), 'explicit_cloud_only')
    require(
        args.stage == 'prod' and os.getenv('GCP_AGENT_TIER') == ('prod-operator' if args.apply else 'ro-prod'),
        'wrong_identity',
    )
    require(
        1 <= args.max_units <= 200
        and 1 <= args.expect_count <= args.max_units
        and 1 <= args.apply_limit <= args.max_units,
        'invalid_budget',
    )
    uid = os.getenv(args.owner_env, '')
    require(bool(uid) and '/' not in uid, 'owner_pin_required')
    cutoff_time = datetime.fromisoformat(args.quarantined_before.replace('Z', '+00:00'))
    require(cutoff_time.utcoffset() is not None and cutoff_time.utcoffset().total_seconds() == 0, 'utc_cutoff_required')
    cutoff = cutoff_time.timestamp()
    server_flags = load_server_flags(args.server_flags_file)
    # Check availability before making any cloud read. Never fetch or print secrets.
    secret = os.getenv('ENCRYPTION_SECRET', '').encode()
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '')
    require(len(secret) >= 32 and bool(bucket), 'secure_runtime_material_required')
    os.environ['OMI_ENV_STAGE'] = args.stage
    configure_rollout_runtime()
    from google.cloud import firestore, storage
    from google.cloud.firestore_v1.base_query import FieldFilter
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.artifact_policy import create_artifact_store
    from config.batch_pipeline import empty_asr_disposition_enabled

    client = firestore.Client(project='based-hardware')
    store = FirestoreStore(f'batch_pipeline_{args.stage}', firestore_client=client)

    # Artifact authorization is read-only too; registration is never invoked in dry-run.
    class ReadOnlyStore:
        namespace = store.namespace
        client = store.client

        def run(self, operation):
            return readonly_run(store, operation)

    read_store = ReadOnlyStore()
    artifacts = create_artifact_store(
        store if args.apply else read_store, storage.Client(project='based-hardware'), bucket, secret
    )

    # The normal artifact authorizer uses its own transaction. Override it with
    # the exact same privacy checks in an explicitly read-only transaction.
    def authorize(item):
        from utils.batch_pipeline.artifacts import ProtectionContext

        def check(tx):
            generation = tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            user = client.collection('users').document(item.owner_id).get(transaction=tx.transaction).to_dict() or {}
            return ProtectionContext(user.get('data_protection_level', 'enhanced'), generation)

        return readonly_run(store, check)

    artifacts.authorize = authorize
    docs = list(
        client.collection(f'{store.namespace}_jobs')
        .where(filter=FieldFilter('owner_id', '==', uid))
        .limit(1001)
        .stream()
    )
    require(len(docs) <= 1000, 'owner_read_budget')
    selected = []
    for doc in docs:
        job = doc.to_dict() or {}
        if 0 < job.get('quarantined_at', 0) <= cutoff and (
            job.get('state') == 'quarantined'
            and job.get('recovery_state') == 'failed_held'
            or job.get('silence_disposition')
        ):
            selected.append((doc.id, fingerprint(job)))
    require(len(selected) == args.expect_count, 'cohort_count_changed')
    selected.sort()
    units = []
    for sid, key in selected:
        units.append((sid, key, inspect_unit(read_store, artifacts, sid, uid, key)))
    digest = plan_digest(uid, store.namespace, cutoff, units)
    counts = Counter(decision for _, _, decision in units)
    output = {
        'mode': 'apply' if args.apply else 'dry_run',
        'operation': OPERATION,
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'owner_count': 1,
        'units': len(units),
        'strict_vad': dict(counts),
        'silent_fraction': counts['silent'] / len(units),
        'plan_sha256': digest,
        'unpinned_policy': 'server_flags' if server_flags else 'refuse',
        'paid_stt_calls': 0,
        'firestore_writes': 0,
    }
    if args.apply:
        # Per-unit mutation consumes its persisted recovery owner part.
        require(args.approve_plan_sha256 == digest, 'approval_digest_changed')
        silent = [(sid, key) for sid, key, decision in units if decision == 'silent'][: args.apply_limit]
        output['outcomes'] = dict(
            Counter(
                apply_silent(store, artifacts, sid, uid, key, digest, server_flags=server_flags) for sid, key in silent
            )
        )
        del output['firestore_writes']
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        print(json.dumps({'outcome': 'refused', 'reason': str(error)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({'outcome': 'error', 'reason': 'operation_failed_closed'}))
        sys.exit(1)
