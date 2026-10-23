#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Digest-bound, one-owner epoch-2 speech recovery. Dry-run never writes or calls STT.

Use securely injected runtime secrets. Audio is decrypted only in memory. Output
contains counts/digests only; no identifiers, URIs, tokens, words or error bodies.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
from dataclasses import fields

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.rollout_cohorts import configure_rollout_runtime
import batch_pipeline_held_disposition as held
from google.cloud import firestore, storage
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from database.batch_pipeline_store import FirestoreStore
from database.sync_ledger import batch_ledger_owes_held_units
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.recovery_disposition import inspect_audio, STAGES, REASONS
from utils.batch_pipeline.speech_redrive import redrive_one
from utils.batch_pipeline import redrive_scope as scope
from utils.executors import storage_executor

OPERATION = 'speech-empty-multilingual-paid-epoch-2-v1'
require = held.require


def paid_digest(census_digest, speech_count, paid_epoch, *, silent=False):
    return hashlib.sha256(
        json.dumps(
            {
                'operation': OPERATION,
                'provider': 'modulate',
                'census_sha256': census_digest,
                'speech_count': speech_count,
                'paid_epoch': paid_epoch,
                'silent': silent,
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
    ).hexdigest()


def epoch1_failure(job):
    """Closed stage/reason of the spent recovery. Selection pays any failed_held
    speech unit, not only empty ASR, so the approver must see the mix."""
    failure = (job.get('recovery') or {}).get('failure') or {}
    stage, reason = failure.get('stage'), failure.get('reason')
    return f'{stage}/{reason}' if stage in STAGES and reason in REASONS else 'unrecorded'


def checked_job(store, sid, uid, key):

    def check(tx):
        job, binding = RecoveryStore(store).checked(
            tx, sid, allow_completed_silence=True, allow_completed_speech_redrive=True
        )
        result = tx.get('results', sid)
        require(binding.owner_id == uid and held.fingerprint(job) == key, 'cohort_changed')
        silence, speech = job.get('silence_disposition') or {}, job.get('speech_redrive') or {}
        require(not (silence and speech), 'conflicting_dispositions')
        if silence:
            require(silence.get('state') in {'prepared', 'completed'}, 'invalid_silence_intent')
            return job
        if speech:
            require(
                speech.get('paid_epoch') == 2
                and speech.get('provider') == 'modulate'
                and speech.get('prior_recovery') == job.get('recovery')
                and speech.get('state') in {'prepared', 'running', 'completed', 'failed_held'},
                'invalid_paid_intent',
            )
            return job
        require(SpeechRedriveStore.terminal(job, result, time.time()), 'not_failed_held')
        ledger = tx.get('content', f'{uid}/{binding.content_id}')
        require(batch_ledger_owes_held_units(ledger), 'completed_ledger')
        return job

    return held.readonly_run(store, check)


def inspect_unit(store, artifacts, sid, uid, key):

    job = checked_job(store, sid, uid, key)
    # Immutable intent attestations retain the original census on replay, even
    # after results have projected and audio has entered completion retention.
    if job.get('speech_redrive'):
        return 'speech'
    if (job.get('silence_disposition') or {}).get('state') == 'completed':
        return 'silent'
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    _, _, spans = inspect_audio(item, artifacts.fetch_audio(item))
    return 'speech' if spans else 'silent'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prod'], required=True)
    parser.add_argument('--owner-env', default='DAVID_UID')
    parser.add_argument('--quarantined-before', required=True)
    parser.add_argument('--quarantined-after', required=True)
    parser.add_argument('--unit-ids-file', help='Private JSON list; intersect with owner/time/held selection')
    parser.add_argument('--cohort-file', required=True, help='Create-only private dry-run manifest; required on replay')
    parser.add_argument('--silent', action='store_true', help='Persist suppression of downstream derived effects')
    parser.add_argument('--expect-count', type=int, required=True)
    parser.add_argument('--expect-speech-count', type=int, required=True)
    parser.add_argument('--source-census-sha256', help='Required with --apply; optional dry-run assertion')
    parser.add_argument('--paid-epoch', type=int, choices=[2], required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--apply-limit', type=int, default=1, help='Fixed speech prefix, replay is idempotent')
    parser.add_argument(
        '--server-flags-file', help='Serving role env JSON for units with no stored policy; absent refuses them'
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    require(not os.getenv('FIRESTORE_EMULATOR_HOST'), 'explicit_cloud_only')
    require(
        os.getenv('GCP_AGENT_TIER')
        in (('prod-operator', 'human') if args.apply else ('ro-prod', 'prod-operator', 'human')),
        'wrong_identity',
    )
    require(
        1 <= args.expect_count <= 200
        and 1 <= args.expect_speech_count <= 67
        and 1 <= args.apply_limit <= args.expect_speech_count,
        'invalid_budget',
    )
    uid = os.getenv(args.owner_env, '')
    require(bool(uid) and '/' not in uid, 'owner_pin_required')

    def utc_stamp(value):
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0, 'utc_cutoff_required')
        return stamp.timestamp()

    cutoff = utc_stamp(args.quarantined_before)
    after = utc_stamp(args.quarantined_after)
    require(0 < after <= cutoff, 'invalid_time_window')
    ids = scope.unit_ids(args.unit_ids_file)
    scope_spec = scope.scope_body(uid, 'batch_pipeline_prod', after, cutoff, args.silent, ids)
    require(not args.apply or bool(args.source_census_sha256), 'source_census_required')
    require(not args.apply or Path(args.cohort_file).is_file(), 'cohort_file_required')
    server_flags = held.load_server_flags(args.server_flags_file)
    secret = os.getenv('ENCRYPTION_SECRET', '').encode()
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '')
    require(len(secret) >= 32 and bool(bucket), 'secure_runtime_material_required')
    os.environ['OMI_ENV_STAGE'] = args.stage
    configure_rollout_runtime()

    client = firestore.Client(project='based-hardware')
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)

    class ReadOnlyStore:
        namespace = store.namespace
        client = store.client

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
    cohort_path = Path(args.cohort_file)
    if cohort_path.exists():
        # Freeze the exact IDs and decisions across canary projection and replay.
        manifest = scope.load(cohort_path, scope_spec, args.expect_count)
        units = [tuple(unit) for unit in manifest['units']]
    else:
        selected = []
        collection = client.collection('batch_pipeline_prod_jobs')
        candidates = (
            (collection.document(sid).get() for sid in ids) if ids is not None else scope.owner_jobs(collection, uid)
        )
        for doc in candidates:
            job = doc.to_dict() or {}
            selected_here = job.get('owner_id') == uid and scope.eligible(job, after, cutoff)
            require(ids is None or selected_here, 'unit_not_eligible')
            if selected_here:
                selected.append((doc.id, held.fingerprint(job)))
                require(len(selected) <= args.expect_count, 'cohort_count_changed')
        require(len(selected) == args.expect_count, 'cohort_count_changed')
        units = []
        # Leaf fanout belongs to the CLI coordinator, never a storage worker.
        ordered = sorted(selected)
        for start in range(0, len(ordered), 4):
            group = ordered[start : start + 4]
            futures = [
                storage_executor.submit(inspect_unit, read_store, artifacts, sid, uid, key) for sid, key in group
            ]
            units.extend((sid, key, future.result()) for (sid, key), future in zip(group, futures))
        manifest = {'scope': scope_spec, 'units': [list(unit) for unit in units]}
    census = scope.digest(manifest)
    require(not args.source_census_sha256 or census == args.source_census_sha256, 'source_census_changed')
    # Validate every immutable binding/intent before any mutation or paid dispatch.
    failures = {}
    digest = paid_digest(census, sum(d == 'speech' for _, _, d in units), args.paid_epoch, silent=args.silent)
    for sid, key, decision in units:
        job = checked_job(read_store, sid, uid, key)
        marker = job.get('speech_redrive')
        if marker:
            require(
                marker.get('plan_digest') == digest and marker.get('silent', False) is args.silent,
                'paid_intent_changed',
            )
        else:
            require(scope.eligible(job, after, cutoff), 'unit_not_eligible')
        require(inspect_unit(read_store, artifacts, sid, uid, key) == decision, 'speech_decision_changed')
        failures[sid] = epoch1_failure(job)
    counts = Counter(decision for _, _, decision in units)
    require(counts['speech'] == args.expect_speech_count, 'speech_count_changed')
    if not cohort_path.exists():
        scope.write(cohort_path, manifest)
    output = {
        'mode': 'apply' if args.apply else 'dry_run',
        'operation': OPERATION,
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'owner_count': 1,
        'units': len(units),
        'strict_vad': dict(counts),
        # Not in the digest: the approved census is unchanged by this report.
        'speech_epoch1_failures': dict(Counter(failures[sid] for sid, _, decision in units if decision == 'speech')),
        'paid_epoch': args.paid_epoch,
        'silent': args.silent,
        'unpinned_policy': 'server_flags' if server_flags else 'refuse',
        'source_census_sha256': census,
        'plan_sha256': digest,
        'maximum_additional_paid_calls': counts['speech'],
        'paid_stt_calls': 0,
        'firestore_writes': 0,
    }
    if args.apply:

        # Per-unit mutation consumes its persisted recovery owner part.
        require(args.approve_plan_sha256 == digest, 'approval_digest_changed')
        outcomes = Counter()
        stopped = False
        # Always the same sorted prefix. Increasing the limit includes receipts
        # from the canary; it never silently selects one extra unattempted unit.
        for sid, key, _decision in [u for u in units if u[2] == 'speech'][: args.apply_limit]:
            job = checked_job(read_store, sid, uid, key)
            outcome = redrive_one(
                store, artifacts, sid, uid, digest, job['recovery'], server_flags=server_flags, silent=args.silent
            )
            outcomes[outcome] += 1
            if not scope.successful(outcome):
                stopped = True
                break
        output['outcomes'] = dict(outcomes)
        output['stopped'] = stopped
        del output['paid_stt_calls'], output['firestore_writes']
    print(json.dumps(output, indent=2, sort_keys=True))
    if args.apply and stopped:
        sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except (held.Refused, scope.ScopeRefused) as error:
        print(json.dumps({'outcome': 'refused', 'reason': str(error)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({'outcome': 'error', 'reason': 'operation_failed_closed'}))
        sys.exit(1)
