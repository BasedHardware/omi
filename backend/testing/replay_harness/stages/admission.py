"""Real record registration/admission/drain; only infrastructure leaves are local."""

import asyncio
from datetime import datetime, timezone
import logging
import sys
from contextlib import ExitStack
from unittest.mock import patch

from testing.replay_harness.report import StageResult, record_exception


class AdmissionDriver:
    async def run(self, case, environment):
        from utils.batch_pipeline import live
        from utils.other import storage
        from config.record_audio import record_identity

        errors = []

        class Collector(logging.Handler):
            def emit(self, event):
                error = sys.exc_info()[1]
                if error is not None and 'outcome=retry' in event.msg:
                    errors.append(record_exception(error, 'admission'))

        collector = Collector()
        live.logger.addHandler(collector)
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(live, 'time', environment.clock.module()))
                stack.enter_context(patch.object(live, 'create_storage_client', lambda: environment.storage))
                stack.enter_context(patch.object(live, 'private_cloud_sync_bucket', storage.private_cloud_sync_bucket))
                corpus = case.corpus
                seed = corpus['admission']
                rows = seed['rows']
                drainers = seed.get('drainers', 1)
                if (
                    type(rows) is not int
                    or not 1 <= rows <= 500
                    or type(drainers) is not int
                    or not 1 <= drainers <= 64
                ):
                    raise ValueError('invalid bounded admission seed')
                uid = environment.harness.seed_user('synthetic-replay-owner')
                environment.harness.replay_users = [uid]
                segments = []
                for index in range(rows):
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
                        'finished_at': datetime.fromtimestamp(capture + 1, timezone.utc),
                    }
                    reference = (
                        environment.store.client.collection('users')
                        .document(uid)
                        .collection('conversations')
                        .document(cid)
                    )
                    reference.set(conversation)
                    if seed['durable']:
                        blob = environment.storage.bucket(storage.private_cloud_sync_bucket).blob(
                            f'chunks/{uid}/{cid}/{capture:.3f}.bin'
                        )
                        # Synthetic PCM is generated locally; no capture or paid
                        # response participates in these structural fixtures.
                        blob.upload_from_string(b'\x01\x00' * 16000)
                    live.register_recording(
                        uid, conversation, store=environment.store, now=environment.clock.time(), server_flags={}
                    )
                    segments.append(record_identity(uid, cid)[1])
                # Each coroutine has its own busy_owners set. All select the
                # same due page, and product run_blocking uses real db_executor.
                outcomes = await asyncio.gather(
                    *(live.drain_recordings(environment.store) for _ in range(drainers)), return_exceptions=True
                )
                for outcome in outcomes:
                    if isinstance(outcome, BaseException):
                        errors.append(record_exception(outcome, 'admission'))
                pending = [
                    environment.store.client.collection(f'{environment.store.namespace}_jobs')
                    .document(sid)
                    .get()
                    .to_dict()
                    or {}
                    for sid in segments
                ]
                admitted = sum(row.get('state') != 'record_pending' for row in pending)
                details = {'rows': rows, 'drainers': drainers, 'admitted': admitted, 'pending': rows - admitted}
                if errors:
                    # Prefer the contention contract when multiple real retry
                    # sites were observed; retain every sanitized observation.
                    first = next(
                        (e for e in errors if e['exception_type'] == 'FirestoreContentionExhausted'), errors[0]
                    )
                    return StageResult('admission', 'stopped', **first, observations=errors, details=details)
                if admitted != rows:
                    return StageResult(
                        'admission',
                        'stopped',
                        reason='admission:pending_obligation',
                        guard='pending_obligation',
                        details=details,
                    )
                if any(not row.get('projection_binding') for row in pending):
                    return StageResult(
                        'admission',
                        'stopped',
                        reason='admission:missing_binding',
                        missing_input='projection_binding',
                        details=details,
                    )
                # Binding/intake and staged artifacts are part of admission's
                # success predicate; a changed job state alone is insufficient.
                for table in ('intakes', 'artifacts'):
                    if not list(
                        environment.store.client.collection(f'{environment.store.namespace}_{table}').limit(1).stream()
                    ):
                        return StageResult(
                            'admission',
                            'stopped',
                            reason=f'admission:missing_{table}',
                            missing_input=table,
                            details=details,
                        )
                return StageResult('admission', 'pass', details=details)
        finally:
            live.logger.removeHandler(collector)
