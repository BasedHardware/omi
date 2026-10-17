"""Atomic batch protocol ownership, durable projection binding and queue admission."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from config.batch_pipeline import enabled_for
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
) -> dict:
    if not items or tuple(item.segment_id for item in items) != binding.segment_ids:
        raise ValueError('complete ordered sibling set must match immutable projection binding')
    if any(
        item.owner_id != binding.owner_id or item.privacy_generation != binding.privacy_generation for item in items
    ):
        raise ValueError('work identity must match projection binding')
    content_key = f'{binding.owner_id}/{binding.content_id}'

    def commit(tx):
        existing = tx.get('content', content_key)
        if existing.get('dispatch_protocol') == PROTOCOL:
            return {'outcome': 'batch', 'job_id': existing['job_id']}
        if existing.get('status') == 'completed' and is_valid_completed_sync_content_result(existing.get('result')):
            return {'outcome': 'completed', 'result': existing['result']}
        if existing:
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
        if not reserved_recording and not enabled_for(binding.owner_id):
            raise AdmissionDisabled('cohort no longer enabled')
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
            created = Scheduler.enqueue_in_transaction(tx, item, now)
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
            '_admitted_seconds': sum(i.duration_seconds for i in items),
        }

    outcome = store.run(commit)
    seconds = outcome.pop('_admitted_seconds', None)
    if seconds is not None:
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
