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
import math
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
from database.batch_pipeline_speech_redrive import SpeechRedriveStore, independent_redrive, replaceable_modulate_intent
from config.batch_language_recovery import (
    MAX_AUDIO_SECONDS,
    ESTIMATED_USD_PER_AUDIO_HOUR,
    REPAIR_EPOCH,
    duration_limited,
    independent_attempted,
    language_guarded,
    words_repair_eligible,
)
from database.batch_pipeline_store import FirestoreStore
from database.sync_ledger import batch_ledger_owes_held_units
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.recovery_disposition import inspect_audio, STAGES, REASONS
from utils.batch_pipeline.speech_redrive import prepared_independent_one, redrive_one
from utils.batch_pipeline import redrive_scope as scope
from utils.executors import storage_executor

OPERATION = 'speech-empty-multilingual-paid-epoch-2-v1'
# Lead ruling 7fa3d2: one explicit Modulate call per language-guard words unit.
REPAIR_OPERATION = 'language-guard-words-repair-v1'
PREPARED_OPERATION = 'prepared-independent-recovery-v1'
require = held.require


def paid_digest(
    census_digest,
    speech_count,
    paid_epoch,
    *,
    silent=False,
    independent=False,
    repair=False,
    prepared=False,
    max_seconds=None,
    usd_cap=None,
):
    # The prepared take-over binds its scoped bound and spend cap into the plan
    # the approver signs; existing epochs keep their byte-stable digests.
    body = {
        'operation': (
            PREPARED_OPERATION
            if prepared
            else REPAIR_OPERATION if repair else 'independent-language-recovery-v1' if independent else OPERATION
        ),
        'provider': 'soniox' if (prepared or independent) else 'modulate',
        'census_sha256': census_digest,
        'speech_count': speech_count,
        'paid_epoch': paid_epoch,
        'silent': silent,
    }
    if prepared:
        body['max_seconds'] = max_seconds
        body['usd_cap'] = usd_cap
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def epoch1_failure(job):
    """Closed stage/reason of the spent recovery. Selection pays any failed_held
    speech unit, not only empty ASR, so the approver must see the mix."""
    failure = (job.get('recovery') or {}).get('failure') or {}
    stage, reason = failure.get('stage'), failure.get('reason')
    return f'{stage}/{reason}' if stage in STAGES and reason in REASONS else 'unrecorded'


def eligible(job, after, cutoff, independent=False, repair=False):
    if repair:
        return (
            after <= job.get('quarantined_at', 0) <= cutoff
            and job.get('state') == 'quarantined'
            and job.get('recovery_state') == 'failed_held'
            and not job.get('speech_redrive')
            and not job.get('silence_disposition')
            and words_repair_eligible(job)
        )
    if not independent:
        return scope.eligible(job, after, cutoff)
    marker = job.get('speech_redrive') or {}
    return (
        after <= job.get('quarantined_at', 0) <= cutoff
        and job.get('state') == 'quarantined'
        and job.get('recovery_state') == 'failed_held'
        and independent_redrive(job)
        and not independent_attempted(job)
        and not job.get('silence_disposition')
        and (not marker or replaceable_modulate_intent(job, marker))
    )


def prepared_eligible(job, after, cutoff, max_seconds):
    """Sealed selection: guarded epoch-1 intents above the runtime bound only.

    The global 60s independent bound stays untouched; this predicate exists so
    an operator plan may admit exactly the sealed ids a lead granted, and only
    while their intent is still unspent (no receipt, no result, no marker). It
    admits both the still-`prepared` units and the exact `failed_held` shape
    #23795's duration-limit refusal settles without ever starting the intent.
    """
    recovery = job.get('recovery') or {}
    return (
        after <= job.get('quarantined_at', 0) <= cutoff
        and job.get('state') == 'quarantined'
        and job.get('quarantine_reason') == 'worker_failed'
        and language_guarded(job)
        and (job.get('recovery_state') == 'prepared' and not recovery.get('settled_at') or duration_limited(job))
        and recovery.get('epoch') == 1
        and bool(recovery.get('token'))
        and not recovery.get('started_at')
        and not recovery.get('recognizers')
        and not independent_attempted(job)
        and not job.get('result')
        and not job.get('speech_redrive')
        and not job.get('silence_disposition')
        and not job.get('terminal_disposition')
        and MAX_AUDIO_SECONDS < job.get('duration_seconds', 0) <= max_seconds
    )


def fingerprint(job, independent=False, repair=False, prepared=False):
    if prepared:
        # The take-over freezes the exact prepared intent. start()/settle() only
        # append fields, so a spent unit replays without a cohort_changed refusal.
        recovery = job.get('recovery') or {}
        return scope.digest(
            {
                'unit': held.fingerprint({**job, 'recovery': None}),
                'intent': {key: recovery.get(key) for key in ('token', 'epoch', 'privacy_generation', 'prepared_at')},
                'provider': 'soniox',
            }
        )
    if repair:
        return scope.digest({'unit': held.fingerprint(job), 'operation': REPAIR_OPERATION, 'provider': 'modulate'})
    if not independent:
        return held.fingerprint(job)
    marker = job.get('speech_redrive') or {}
    previous = marker.get('prior_speech_redrive') or {} if marker.get('provider') == 'soniox' else marker
    return scope.digest({'unit': held.fingerprint(job), 'prior_paid_intent': previous, 'provider': 'soniox'})


def prepared_budget(durations, usd_cap):
    """Refuse a sealed plan whose closed cost estimate exceeds the granted cap."""
    total = sum(durations)
    estimated = total / 3600 * ESTIMATED_USD_PER_AUDIO_HOUR
    require(math.isfinite(usd_cap) and estimated <= usd_cap, 'spend_cap_exceeded')
    return total, estimated


def checked_prepared(store, sid, uid, key, after, cutoff, max_seconds):
    """Read-only revalidation: sealed identity, unspent epoch-1 intent, scoped bound."""

    def check(tx):
        job, binding = RecoveryStore(store).checked(tx, sid, allow_completed_recovery=True)
        require(binding.owner_id == uid and fingerprint(job, prepared=True) == key, 'cohort_changed')
        if job.get('recovery_state') == 'prepared' or duration_limited(job):
            require(prepared_eligible(job, after, cutoff, max_seconds), 'unit_not_eligible')
            ledger = tx.get('content', f'{uid}/{binding.content_id}')
            require(batch_ledger_owes_held_units(ledger), 'completed_ledger')
        else:
            # This plan (or the runtime, after the freeze) already spent it; the
            # frozen intent token in the fingerprint is the identity proof.
            require(job.get('recovery_state') in {'running', 'recovered', 'failed_held'}, 'cohort_changed')
        return job

    return held.readonly_run(store, check)


def checked_job(store, sid, uid, key, independent=False, repair=False):

    def check(tx):
        job, binding = RecoveryStore(store).checked(
            tx, sid, allow_completed_silence=True, allow_completed_speech_redrive=True
        )
        result = tx.get('results', sid)
        require(binding.owner_id == uid and fingerprint(job, independent, repair) == key, 'cohort_changed')
        if repair:
            # Never consults or resets the spent Soniox attempt; one repair intent per unit.
            require(words_repair_eligible(job), 'repair_not_eligible')
            speech = job.get('speech_redrive') or {}
            if speech:
                require(
                    speech.get('paid_epoch') == REPAIR_EPOCH
                    and speech.get('provider') == 'modulate'
                    and speech.get('prior_recovery') == job.get('recovery')
                    and speech.get('state') in {'prepared', 'running', 'completed', 'failed_held'},
                    'invalid_paid_intent',
                )
                return job
            require(not job.get('silence_disposition'), 'conflicting_dispositions')
            require(SpeechRedriveStore.terminal(job, result, time.time()), 'not_failed_held')
            ledger = tx.get('content', f'{uid}/{binding.content_id}')
            require(batch_ledger_owes_held_units(ledger), 'completed_ledger')
            return job
        require(not independent or not independent_attempted(job), 'independent_already_attempted')
        silence, speech = job.get('silence_disposition') or {}, job.get('speech_redrive') or {}
        require(not (silence and speech), 'conflicting_dispositions')
        if silence:
            require(silence.get('state') in {'prepared', 'completed'}, 'invalid_silence_intent')
            return job
        if speech:
            if independent and replaceable_modulate_intent(job, speech):
                require(SpeechRedriveStore.terminal(job, result, time.time()), 'not_failed_held')
                return job
            require(
                speech.get('paid_epoch') == (3 if independent else 2)
                and speech.get('provider') == ('soniox' if independent else 'modulate')
                and speech.get('prior_recovery') == job.get('recovery')
                and speech.get('state') in {'prepared', 'running', 'completed', 'failed_held'},
                'invalid_paid_intent',
            )
            return job
        require(SpeechRedriveStore.terminal(job, result, time.time()), 'not_failed_held')
        require(not independent or independent_redrive(job), 'language_guard_required')
        ledger = tx.get('content', f'{uid}/{binding.content_id}')
        require(batch_ledger_owes_held_units(ledger), 'completed_ledger')
        return job

    return held.readonly_run(store, check)


def inspect_unit(
    store, artifacts, sid, uid, key, independent=False, repair=False, prepared=False, after=0, cutoff=0, max_seconds=0.0
):

    if prepared:
        # A prepared take-over always buys the recognizer, even if local VAD
        # falls below one frame; its validated empty reply settles failed_held.
        checked_prepared(store, sid, uid, key, after, cutoff, max_seconds)
        return 'speech'
    job = checked_job(store, sid, uid, key, independent, repair)
    # Independent-language plans always buy a recognizer, even if local VAD
    # falls below one frame. Only its validated empty reply can close silence.
    # A words repair is speech by its bound worker VAD receipt.
    if independent or repair:
        return 'speech'
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
    parser.add_argument('--paid-epoch', type=int, choices=[1, 2, 3, REPAIR_EPOCH], required=True)
    parser.add_argument(
        '--independent-language', action='store_true', help='Soniox-only explicit epoch 3; exact unit IDs required'
    )
    parser.add_argument(
        '--language-guard-repair',
        action='store_true',
        help='Lead 7fa3d2: one Modulate call per guarded words unit, epoch 4; exact unit IDs required',
    )
    parser.add_argument(
        '--prepared-independent',
        action='store_true',
        help='Operator take-over of sealed prepared epoch-1 intents above the 60s bound; exact unit IDs required',
    )
    parser.add_argument(
        '--max-seconds',
        type=float,
        help='Scoped per-unit bound for --prepared-independent; must exceed the runtime 60s',
    )
    parser.add_argument('--usd-cap', type=float, help='Total estimated spend cap for --prepared-independent')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--apply-limit', type=int, default=1, help='Fixed speech prefix, replay is idempotent')
    parser.add_argument(
        '--server-flags-file', help='Serving role env JSON for units with no stored policy; absent refuses them'
    )
    args = parser.parse_args()
    repair = args.language_guard_repair
    prepared = args.prepared_independent
    require(not (repair and args.independent_language), 'conflicting_plans')
    require(not (prepared and (args.independent_language or repair)), 'conflicting_plans')
    if prepared:
        require(args.paid_epoch == 1, 'provider_epoch_mismatch')
        require(bool(args.unit_ids_file), 'exact_prepared_units_required')
        require(not args.silent, 'silent_mode_unsupported')
        # Infinite bounds are not bounds: only finite values may scope the plan.
        require(
            args.max_seconds is not None and math.isfinite(args.max_seconds) and args.max_seconds > MAX_AUDIO_SECONDS,
            'scoped_bound_required',
        )
        require(args.usd_cap is not None and math.isfinite(args.usd_cap) and args.usd_cap > 0, 'usd_cap_required')
    else:
        require(
            args.paid_epoch == (REPAIR_EPOCH if repair else 3 if args.independent_language else 2),
            'provider_epoch_mismatch',
        )
    require(not args.independent_language or bool(args.unit_ids_file), 'exact_independent_units_required')
    require(not repair or bool(args.unit_ids_file), 'exact_repair_units_required')
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
            if prepared:
                selected_here = job.get('owner_id') == uid and prepared_eligible(job, after, cutoff, args.max_seconds)
            else:
                selected_here = job.get('owner_id') == uid and eligible(
                    job, after, cutoff, args.independent_language, repair
                )
            require(ids is None or selected_here, 'unit_not_eligible')
            if selected_here:
                selected.append((doc.id, fingerprint(job, args.independent_language, repair, prepared)))
                require(len(selected) <= args.expect_count, 'cohort_count_changed')
        require(len(selected) == args.expect_count, 'cohort_count_changed')
        units = []
        # Leaf fanout belongs to the CLI coordinator, never a storage worker.
        ordered = sorted(selected)
        for start in range(0, len(ordered), 4):
            group = ordered[start : start + 4]
            futures = [
                storage_executor.submit(
                    inspect_unit,
                    read_store,
                    artifacts,
                    sid,
                    uid,
                    key,
                    args.independent_language,
                    repair,
                    prepared,
                    after,
                    cutoff,
                    args.max_seconds or 0.0,
                )
                for sid, key in group
            ]
            units.extend((sid, key, future.result()) for (sid, key), future in zip(group, futures))
        manifest = {'scope': scope_spec, 'units': [list(unit) for unit in units]}
    census = scope.digest(manifest)
    require(not args.source_census_sha256 or census == args.source_census_sha256, 'source_census_changed')
    # Validate every immutable binding/intent before any mutation or paid dispatch.
    failures = {}
    durations = {}
    digest = paid_digest(
        census,
        sum(d == 'speech' for _, _, d in units),
        args.paid_epoch,
        silent=args.silent,
        independent=args.independent_language,
        repair=repair,
        prepared=prepared,
        max_seconds=args.max_seconds,
        usd_cap=args.usd_cap,
    )
    for sid, key, decision in units:
        if prepared:
            job = checked_prepared(read_store, sid, uid, key, after, cutoff, args.max_seconds)
        else:
            job = checked_job(read_store, sid, uid, key, args.independent_language, repair)
        durations[sid] = job.get('duration_seconds') or 0
        marker = job.get('speech_redrive')
        if marker and not (args.independent_language and replaceable_modulate_intent(job, marker)):
            require(
                marker.get('plan_digest') == digest and marker.get('silent', False) is args.silent,
                'paid_intent_changed',
            )
        elif not prepared:
            require(eligible(job, after, cutoff, args.independent_language, repair), 'unit_not_eligible')
        require(
            inspect_unit(
                read_store,
                artifacts,
                sid,
                uid,
                key,
                args.independent_language,
                repair,
                prepared,
                after,
                cutoff,
                args.max_seconds or 0.0,
            )
            == decision,
            'speech_decision_changed',
        )
        failures[sid] = epoch1_failure(job)
    counts = Counter(decision for _, _, decision in units)
    require(counts['speech'] == args.expect_speech_count, 'speech_count_changed')
    total_audio_seconds, estimated_usd_total = (
        prepared_budget([durations[sid] for sid, _, decision in units if decision == 'speech'], args.usd_cap)
        if prepared
        else (0, 0)
    )
    if not cohort_path.exists():
        scope.write(cohort_path, manifest)
    output = {
        'mode': 'apply' if args.apply else 'dry_run',
        'operation': (
            PREPARED_OPERATION
            if prepared
            else (
                REPAIR_OPERATION
                if repair
                else 'independent-language-recovery-v1' if args.independent_language else OPERATION
            )
        ),
        'provider': 'soniox' if (prepared or args.independent_language) else 'modulate',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'owner_count': 1,
        'units': len(units),
        'strict_vad': (
            {'worker_vad_speech': counts['speech']}
            if repair
            else {'unmeasured': counts['speech']} if args.independent_language or prepared else dict(counts)
        ),
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
    if args.independent_language or repair:
        output['max_audio_seconds_per_unit'] = MAX_AUDIO_SECONDS
    if args.independent_language:
        # Soniox rate; a repair's Modulate call is metered by its own allowance.
        output['estimated_usd_per_unit_at_cap'] = MAX_AUDIO_SECONDS / 3600 * ESTIMATED_USD_PER_AUDIO_HOUR
    if prepared:
        output['runtime_max_audio_seconds'] = MAX_AUDIO_SECONDS
        output['max_audio_seconds_per_unit'] = args.max_seconds
        output['estimated_usd_per_unit_at_cap'] = args.max_seconds / 3600 * ESTIMATED_USD_PER_AUDIO_HOUR
        output['total_audio_seconds'] = total_audio_seconds
        output['estimated_usd_total'] = estimated_usd_total
        output['usd_cap'] = args.usd_cap
    if args.apply:

        # Per-unit mutation consumes its persisted recovery owner part.
        require(args.approve_plan_sha256 == digest, 'approval_digest_changed')
        outcomes = Counter()
        stopped = False
        # Always the same sorted prefix. Increasing the limit includes receipts
        # from the canary; it never silently selects one extra unattempted unit.
        for sid, key, _decision in [u for u in units if u[2] == 'speech'][: args.apply_limit]:
            if prepared:
                checked_prepared(read_store, sid, uid, key, after, cutoff, args.max_seconds)
                outcome = prepared_independent_one(
                    store,
                    artifacts,
                    sid,
                    uid,
                    args.max_seconds,
                    server_flags=server_flags,
                )
            else:
                job = checked_job(read_store, sid, uid, key, args.independent_language, repair)
                outcome = redrive_one(
                    store,
                    artifacts,
                    sid,
                    uid,
                    digest,
                    job['recovery'],
                    server_flags=server_flags,
                    silent=args.silent,
                    independent_language=args.independent_language,
                    repair=repair,
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
