"""Real record registration/admission/drain; only infrastructure leaves are local."""

import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import os
from unittest.mock import patch

from testing.replay_harness.report import StageResult, record_exception
from testing.replay_harness.stages.evidence import Recording, EvidenceMismatch, verify_recordings
from testing.replay_harness.stages.observe import AdmissionObserver


def seed_recordings(seed, environment, live, storage):
    from config.record_audio import record_identity
    from utils.batch_pipeline.scheduler import owner_key

    rows, drainers = seed['rows'], seed.get('drainers', 1)
    if type(rows) is not int or not 1 <= rows <= 500 or type(drainers) is not int or not 1 <= drainers <= 64:
        raise ValueError('invalid bounded admission seed')
    chunk_seconds = seed.get('chunk_seconds', 1)
    capture_seconds = seed.get('capture_seconds', 1)
    if any(type(value) is not int or not 1 <= value <= 60 for value in (chunk_seconds, capture_seconds)):
        raise ValueError('invalid bounded synthetic duration')
    recordings = []
    users = []
    replay_users = getattr(environment.harness, 'replay_users', [])
    environment.harness.replay_users = replay_users
    for index in range(rows):
        if not users or seed.get('distinct_owners'):
            users.append(environment.harness.seed_user(f'synthetic-replay-owner-{index}'))
            replay_users.append(users[-1])
        uid = users[-1]
        cid = f'synthetic-replay-conversation-{index}'
        capture = environment.clock.time() - 120
        conversation = {
            'id': cid,
            'source': 'omi',
            'language': 'en',
            'status': 'completed',
            'record_lane_owner': live.OWNER,
            'private_cloud_sync_enabled': True,
            'data_protection_level': 'standard',
            'record_audio_closed': True,
            'started_at': datetime.fromtimestamp(capture, timezone.utc),
            'finished_at': datetime.fromtimestamp(capture + capture_seconds, timezone.utc),
        }
        environment.store.client.collection('users').document(uid).collection('conversations').document(cid).set(
            conversation
        )
        if seed['durable']:
            bucket = (
                os.environ['BUCKET_AUDIO_DERIVED']
                if seed.get('chunk_bucket') == 'regional'
                else storage.private_cloud_sync_bucket
            )
            blob = environment.storage.bucket(bucket).blob(f'chunks/{uid}/{cid}/{capture:.3f}.bin')
            blob.upload_from_string(b'\x01\x00' * (16000 * chunk_seconds))
        live.register_recording(
            uid, conversation, store=environment.store, now=environment.clock.time(), server_flags={}
        )
        content, segment = record_identity(uid, cid)
        recordings.append(Recording(uid, owner_key(uid), cid, content, segment, capture, chunk_seconds))
    if seed.get('privacy_blocked'):
        for uid in users:
            environment.store.client.collection('users').document(uid).update({'data_protection_level': 'e2ee'})
    environment.storage.archive_listing_failure = seed.get('archive_listing_failure', False)
    return recordings, drainers


class AdmissionDriver:
    async def run(self, case, environment):
        from utils.batch_pipeline import live
        from utils.other import storage

        concurrency = case.corpus['admission'].get('drain_concurrency', 16)
        if type(concurrency) is not int or not 1 <= concurrency <= 64:
            raise ValueError('invalid drain concurrency')
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'RECORD_DRAIN_CONCURRENCY': str(concurrency)}))
            stack.enter_context(patch.object(live, 'time', environment.clock.module()))
            stack.enter_context(patch.object(live, 'create_storage_client', lambda: environment.storage))
            stack.enter_context(patch.object(live, 'private_cloud_sync_bucket', storage.private_cloud_sync_bucket))
            recordings, drainers = seed_recordings(case.corpus['admission'], environment, live, storage)
            with AdmissionObserver(live, environment.store) as observer:
                # Real tasks, real db_executor offload and native retry policy.
                outcomes = await asyncio.gather(
                    *(live.drain_recordings(environment.store) for _ in range(drainers)), return_exceptions=True
                )
                for outcome in outcomes:
                    if isinstance(outcome, Exception) and id(outcome) not in observer.seen:
                        observer.record(outcome, 'driver')
            jobs = [
                environment.store.client.collection(f'{environment.store.namespace}_jobs')
                .document(record.segment_id)
                .get()
                .to_dict()
                or {}
                for record in recordings
            ]
            admitted = sum(row.get('state') == 'ready' for row in jobs)
            details = {
                'rows': len(recordings),
                'drainers': drainers,
                'drain_concurrency': concurrency,
                'admitted': admitted,
                'pending': sum(row.get('state') == 'record_pending' for row in jobs),
            }
            errors = observer.errors
            if errors:
                # Prefer the actual intake transaction, while preserving every
                # other observation and its distinct boundary identity.
                first = next(
                    (
                        e
                        for e in errors
                        if e.get('operation') == 'admit'
                        and e.get('transaction') == 'database.batch_pipeline_intake.admit.commit'
                        and e['exception_type'] == 'FirestoreContentionExhausted'
                    ),
                    errors[0],
                )
                return StageResult('admission', 'stopped', **first, observations=errors, details=details)
            try:
                verify_recordings(environment.store, environment.storage, recordings)
            except EvidenceMismatch as error:
                return StageResult(
                    'admission',
                    'stopped',
                    reason=f'admission:verify:{error.code}',
                    operation='verify',
                    guard=error.code,
                    missing_input=error.code,
                    details=details,
                )
            except Exception as error:
                return StageResult(
                    'admission', 'stopped', **record_exception(error, 'admission', operation='verify'), details=details
                )
            details['verified_recordings'] = len(recordings)
            return StageResult('admission', 'pass', details=details)
