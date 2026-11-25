"""Atomic batch protocol ownership, durable projection binding and queue admission."""

from database import batch_pipeline_upload_metrics as upload_metrics

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable
import time

from config.policy import BatchUnitPolicy, resolve_batch_policy
from config.batch_pipeline import require_record_protocol_ready
from config.record_audio import record_identity, require_record_audio_barrier, restore_pending
from config.record_seal_rules import token_lease_mode
from config.record_latency import recent_record_end, record_fresh_merge_enabled, record_notes_eager_enabled
from database.batch_pipeline_store import Store
from database import batch_pipeline_allowance_hold as allowance_hold
from database.batch_pipeline_staging import artifact_id
from database import batch_pipeline_coalescing_completion as coalescing_completion
from database.sync_ledger import LEDGER_RETENTION_DAYS, is_valid_completed_sync_content_result
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.result_protocol import stamp
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

PROTOCOL = 'batch_v1'
logger = logging.getLogger(__name__)


class AdmissionDisabled(RuntimeError):
    """Cohort was rolled back while staging; no durable work was admitted."""


def admit(
    store: Store,
    items: list[WorkItem],
    binding: ProjectionBinding,
    now: float,
    *,
    namespace: str,
    intake: dict | None = None,
    require_artifacts: bool = False,
    policy: BatchUnitPolicy | None = None,
    enqueue: Callable[..., bool] | None = None,
    adopt: Callable[[dict], bool] | None = None,
    record_barrier: dict | None = None,
    coalescing_group: dict | None = None,
    source_aliases: dict | None = None,
    packing_observations: dict | None = None,
    intake_refusal: allowance_hold.IntakeRefusal | None = None,
) -> dict:
    """Admit one content upload atomically.

    ``enqueue(tx, item, now, *, policy)`` replaces the GPU-ring enqueue for every
    item (the C8 provider-STT stage writes its units outside the ring) and must
    record the admission ``policy`` on the job as the ring does. ``adopt`` lets a caller take over a
    non-batch ledger row it has re-validated inside this transaction (a legacy
    row legacy can no longer finish); the batch ledger write below replaces it.
    A verified intake refusal can park new GPU units before they reach the ring.
    """
    enqueue_item = enqueue or Scheduler.enqueue_in_transaction
    if not items or tuple(item.segment_id for item in items) != binding.segment_ids:
        raise ValueError('complete ordered sibling set must match immutable projection binding')
    if any(
        item.owner_id != binding.owner_id or item.privacy_generation != binding.privacy_generation for item in items
    ):
        raise ValueError('work identity must match projection binding')
    policy = policy or resolve_batch_policy(binding.owner_id)
    content_key = f'{binding.owner_id}/{binding.content_id}'
    serialized_binding = asdict(binding)
    # Ordinary work must remain readable by pre-partial projection hosts
    # throughout the roll. Only partial work requires the new field/readers.
    if not binding.partial_record:
        serialized_binding.pop('partial_record')

    def commit(tx):
        created_units = 0
        if coalescing_group is not None:
            from database.batch_pipeline_coalescing import guard

            guard(tx, coalescing_group, now)
        sources = {getattr(item, 'capture_source_conversation_id', None) for item in items} - {None}
        if sources:
            tx.check_privacy(binding.owner_id, sources, binding.privacy_generation)
        row = {}
        partial_parent = (intake or {}).get('record_partial_parent')
        if binding.record_origin:
            target = binding.target_conversation_id
            if not target:
                raise ValueError('registered record target unavailable')
            key = f'{binding.owner_id}/{target}'
            row = tx.get('conversations', key)
            if not row or row.get('deleted') or row.get('uses_custom_stt') or (partial_parent and row.get('discarded')):
                raise ValueError('registered record target unavailable')
            if row.get('discarded'):
                # Full archives, partial children and ledger replays can name
                # another unit. Read the row's canonical obligation as well.
                obligation_ids = {
                    binding.segment_ids[0],
                    record_identity(binding.owner_id, target)[1],
                }
                if partial_parent:
                    obligation_ids.add(partial_parent)
                if restore_pending(row, *(tx.get('jobs', key) for key in obligation_ids)):
                    raise ValueError('registered record target unavailable')
        existing = tx.get('content', content_key)
        if (
            coalescing_group is not None
            and coalescing_group['mode'] == 'individual'
            and existing.get('job_id') == binding.job_id
        ):
            held = tx.get('intakes', binding.job_id)
            if held.get('coalesce_group') == coalescing_group['id'] and not held.get('coalesce_target'):
                existing = {}  # Fenced conversion of this exact original receipt.
        if existing.get('dispatch_protocol') == PROTOCOL:
            return {'outcome': 'batch', 'job_id': existing['job_id']}
        if existing.get('status') == 'completed' and is_valid_completed_sync_content_result(existing.get('result')):
            return {'outcome': 'completed', 'result': existing['result']}
        if existing and not (adopt is not None and adopt(existing)):
            # Never take a legacy content owner, including ambiguous/expired
            # Redis ownership. Its existing recovery path remains authoritative.
            return {'outcome': 'busy', 'job_id': existing.get('job_id')}
        pending = tx.get('jobs', binding.segment_ids[0])
        partial_metadata = intake or {}
        partial_parent = partial_metadata.get('record_partial_parent')
        if partial_parent:
            pending = tx.get('jobs', partial_parent)
            run = pending.get('partial_run') or {}
            if (
                not pending.get('partial_coordinator')
                or run.get('complete')
                or run.get('generation') != partial_metadata.get('record_partial_generation')
                or run.get('page') != partial_metadata.get('record_partial_page')
                or binding.content_id != partial_metadata.get('record_partial_content')
            ):
                raise ValueError('partial continuation ownership changed')
        reserved_recording = (
            pending.get('state') == 'record_pending'
            and pending.get('owner_id') == binding.owner_id
            and pending.get('conversation_id') == binding.target_conversation_id
            and (partial_parent or pending.get('record_content_id') == binding.content_id)
        )
        admission = policy
        if reserved_recording:
            raw = pending.get('policy')
            # Main already accepts a reserved native capture after rollback.
            # A pre-E1 reservation is the durable receipt of that admission.
            admission = (
                BatchUnitPolicy.from_dict(raw)
                if raw is not None
                else replace(policy, batch_enabled=True, live_admission_enabled=True, live_record_enabled=True)
            )
        if partial_parent and admission.provider_reason == 'byok':
            raise ValueError('partial BYOK excluded')
        if binding.native_record and policy.stt_route == 'provider':
            # Capture reserved custody before units existed. Complete only the
            # unit route now; retain every recorded cohort/funding decision.
            admission = replace(
                admission,
                stt_route=policy.stt_route,
                provider_reason='byok' if admission.provider_reason == 'byok' else policy.provider_reason,
                provider_service=policy.provider_service,
            )
        if not admission.batch_enabled:
            raise AdmissionDisabled('recorded admission policy does not enable batch')
        if binding.record_origin:
            key = f'{binding.owner_id}/{binding.target_conversation_id}'
            if binding.native_record:
                require_record_protocol_ready()
                require_record_audio_barrier(row, expected=record_barrier)
            expected = (
                row.get('record_lane_owner')
                if partial_parent and reserved_recording
                else 'batch_live_v1' if reserved_recording else 'batch_sync_v1'
            )
            if row.get('record_lane_owner') not in {None, expected}:
                raise ValueError('record owner is immutable')
            if row.get('record_lane_owner') != expected:
                tx.patch('conversations', key, {'record_lane_owner': expected})
        park_allowance = (
            intake_refusal is not None
            and enqueue is None
            and not reserved_recording
            and not binding.native_record
            and partial_metadata.get('lane') in {'fresh', 'backfill'}
            and admission.stt_route == 'parakeet'
            and admission.provider_reason != 'byok'
            and allowance_hold.intake_enabled()
            and intake_refusal.current(tx.get(allowance_hold.OWNERS, owner_key(binding.owner_id)), time.time())
        )
        parked = 0
        for item in items:
            if require_artifacts:
                key = artifact_id(item.segment_id, item.audio_uri)
                artifact = tx.get('artifacts', key)
                if (
                    not artifact
                    or artifact.get('owner_id') != item.owner_id
                    or artifact.get('privacy_generation') != item.privacy_generation
                    or artifact.get('cleanup_after')
                    or artifact.get('erasure_requested')
                ):
                    raise ValueError('audio staging reservation missing or reclaimed')
                artifact.pop('write_pending_until', None)
                tx.put('artifacts', key, artifact)
            proposal = (source_aliases or {}).get(item.segment_id)
            if proposal is not None:
                from database.batch_pipeline_source_reuse import enqueue_alias, attach_alias_artifacts

                created = enqueue_alias(tx, item, now, policy=admission, proposal=proposal)
                attach_alias_artifacts(tx, item, proposal)
            else:
                created = (
                    Scheduler.enqueue_in_transaction(tx, item, now, policy=admission, park_allowance=True)
                    if park_allowance
                    else enqueue_item(tx, item, now, policy=admission)
                )
                if getattr(item, 'source_reuse_key', None):
                    marked = tx.get('jobs', item.segment_id)
                    stamp(marked, 'source_reuse_version')
                    tx.put('jobs', item.segment_id, marked)
            created_units += int(bool(created) and not item.shadow)
            job = tx.get('jobs', item.segment_id)
            if park_allowance and created and job.get('state') == allowance_hold.STATE:
                parked += 1
            previous_binding = dict(job.get('projection_binding') or {})
            if previous_binding.get('partial_record') is False:
                previous_binding.pop('partial_record')
            if not created and previous_binding != serialized_binding:
                raise ValueError('existing segment cannot change its immutable intake binding')
            job['projection_binding'] = serialized_binding
            if created and packing_observations and item.segment_id in packing_observations:
                job['packing_observation'] = packing_observations[item.segment_id]
            if created and binding.native_record:
                # Admission commits after staging. Reuse the pending-job and
                # conversation snapshots already read in this transaction.
                job['record_intake_claimed_at'] = pending.get('record_intake_claimed_at')
                job['record_sealed_at'] = row.get('record_sealed_at')
                job['record_ready_at'] = time.time()
                finished = row.get('finished_at')
                if isinstance(finished, datetime):
                    finished = finished.timestamp()
                if recent_record_end(finished, now):
                    job['record_finished_at'] = finished
                    # All siblings retain this dispatch owner even if the
                    # recording ages out or the urgency switch changes later.
                    if not binding.partial_record and record_notes_eager_enabled():
                        job['record_notes_after_complete'] = True
                    if record_fresh_merge_enabled():
                        # Seal/staging latency must not demote a new recording
                        # behind this owner's unresolved historical captures.
                        # All siblings use the recording end, not unit ends.
                        job['fresh_capture'] = True
            if binding.native_record and record_barrier is not None and token_lease_mode() != 'off':
                job['record_input_upload_revision'] = record_barrier.get('record_upload_revision')
            if partial_metadata.get('release'):
                # Readers (hard-3, the 2h alarm) split released backfill from fresh audio per row.
                job['release'] = partial_metadata['release']
            tx.put('jobs', item.segment_id, job)
        if intake is not None:
            tx.put('intakes', binding.job_id, {**intake, 'accepted_at': now})
        timestamp = datetime.fromtimestamp(now, timezone.utc)
        tx.put(
            'content',
            content_key,
            {
                **coalescing_completion.manifest(coalescing_group),
                **{k: v for k, v in (intake or {}).items() if k in {'upload_arrived_at', 'upload_entitlement'}},
                'status': 'processing',
                'job_id': binding.job_id,
                'lane': 'batch',
                'dispatch_protocol': PROTOCOL,
                'updated_at': timestamp,
                'created_at': timestamp,
                # A legacy row taken over through ``adopt`` (stranded claim, contract (h));
                # the zero-lost census reads it (scripts/legacy_dark/lost_recordings.py).
                **({'adopted_legacy_job_id': existing.get('job_id')} if existing else {}),
                'batch_pipeline': {
                    'protocol_version': 1,
                    'namespace': namespace,
                    'segment_ids': list(binding.segment_ids),
                },
            },
        )
        return {
            'outcome': 'batch',
            'job_id': binding.job_id,
            '_policy_id': admission.policy_id,
            '_admitted_seconds': sum(i.duration_seconds for i in items),
            '_reused_seconds': sum(i.duration_seconds for i in items if i.segment_id in (source_aliases or {})),
            '_created_units': created_units,
            '_allowance_parked': parked,
        }

    outcome = store.run(commit)
    created_units = int(outcome.pop('_created_units', 0) or 0)
    if created_units:
        upload_metrics.CREATED.labels(upload_metrics.bounded_class((intake or {}).get('upload_entitlement'))).inc(
            created_units
        )
    parked = outcome.pop('_allowance_parked', 0)
    if parked:
        record_decision(DispatchPath.BATCH_INTAKE, False, DispatchReason.ALLOWANCE_EXHAUSTED)
        logger.info('event=batch_allowance_intake outcome=parked units=%s', parked)
    policy_id = str(outcome.pop('_policy_id', policy.policy_id))
    reused_seconds = outcome.pop('_reused_seconds', 0.0)
    if reused_seconds:
        from utils.batch_pipeline.source_reuse import observe

        observe('avoided_asr_input', float(reused_seconds))
    seconds = outcome.pop('_admitted_seconds', None)
    if seconds is not None:
        from config.policy.telemetry import record_policy_source

        record_policy_source('admission', policy_id)
        record_correctness('admitted', seconds=float(seconds))
    return outcome


def cache_completed(store: Store, uid: str, content_id: str, job_id: str, intake: dict, now: float) -> bool:
    """Expose a completed legacy receipt without recompute or Redis dependence."""

    def commit(tx):
        ledger = tx.get('content', f'{uid}/{content_id}')
        result = ledger.get('result')
        if ledger.get('status') != 'completed' or not is_valid_completed_sync_content_result(result):
            return False
        conversation_ids = [*(result.get('new_memories') or []), *(result.get('updated_memories') or [])]
        tx.check_privacy(uid, conversation_ids)
        tx.put(
            'intakes',
            job_id,
            {
                **intake,
                'owner_id': uid,
                'content_id': content_id,
                'segment_ids': [],
                'conversation_ids': conversation_ids,
                'accepted_at': now,
                'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS),
            },
        )
        return True

    return store.run(commit)
