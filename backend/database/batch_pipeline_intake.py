"""Atomic batch protocol ownership, durable projection binding and queue admission."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from config.policy import BatchUnitPolicy, resolve_batch_policy
from database.batch_pipeline_store import Store
from database.batch_pipeline_staging import artifact_id
from database.sync_ledger import LEDGER_RETENTION_DAYS, is_valid_completed_sync_content_result
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import Scheduler

PROTOCOL = 'batch_v1'


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
) -> dict:
    """Admit one content upload atomically.

    ``enqueue(tx, item, now, *, policy)`` replaces the GPU-ring enqueue for every
    item (the C8 provider-STT stage writes its units outside the ring) and must
    record the admission ``policy`` on the job as the ring does. ``adopt`` lets a caller take over a
    non-batch ledger row it has re-validated inside this transaction (a legacy
    row legacy can no longer finish); the batch ledger write below replaces it.
    With both unset, behaviour is unchanged.
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

    def commit(tx):
        existing = tx.get('content', content_key)
        if existing.get('dispatch_protocol') == PROTOCOL:
            return {'outcome': 'batch', 'job_id': existing['job_id']}
        if existing.get('status') == 'completed' and is_valid_completed_sync_content_result(existing.get('result')):
            return {'outcome': 'completed', 'result': existing['result']}
        if existing and not (adopt is not None and adopt(existing)):
            # Never take a legacy content owner, including ambiguous/expired
            # Redis ownership. Its existing recovery path remains authoritative.
            return {'outcome': 'busy', 'job_id': existing.get('job_id')}
        pending = tx.get('jobs', binding.segment_ids[0])
        reserved_recording = (
            pending.get('state') == 'record_pending'
            and pending.get('owner_id') == binding.owner_id
            and pending.get('conversation_id') == binding.target_conversation_id
            and pending.get('record_content_id') == binding.content_id
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
        if not admission.batch_enabled:
            raise AdmissionDisabled('recorded admission policy does not enable batch')
        if binding.record_origin:
            key = f'{binding.owner_id}/{binding.target_conversation_id}'
            row = tx.get('conversations', key)
            if not row or row.get('deleted') or row.get('uses_custom_stt'):
                raise ValueError('registered record target unavailable')
            expected = 'batch_live_v1' if reserved_recording else 'batch_sync_v1'
            if row.get('record_lane_owner') not in {None, expected}:
                raise ValueError('record owner is immutable')
            if row.get('record_lane_owner') != expected:
                tx.patch('conversations', key, {'record_lane_owner': expected})
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
            created = enqueue_item(tx, item, now, policy=admission)
            job = tx.get('jobs', item.segment_id)
            if not created and job.get('projection_binding') != asdict(binding):
                raise ValueError('existing segment cannot change its immutable intake binding')
            job['projection_binding'] = asdict(binding)
            tx.put('jobs', item.segment_id, job)
        if intake is not None:
            tx.put('intakes', binding.job_id, {**intake, 'accepted_at': now})
        timestamp = datetime.fromtimestamp(now, timezone.utc)
        tx.put(
            'content',
            content_key,
            {
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
        }

    outcome = store.run(commit)
    policy_id = str(outcome.pop('_policy_id', policy.policy_id))
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
