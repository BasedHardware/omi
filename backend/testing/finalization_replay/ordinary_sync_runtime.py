"""Ordinary-sync serving bindings, loaded after pinning and emulator isolation."""

from collections.abc import Mapping
from contextlib import ExitStack
from datetime import datetime
from hashlib import sha256
import json
import os
import re
import subprocess
from unittest.mock import patch
from uuid import UUID

from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database import episode_attach_memo, episode_timeline
from database.apps import PUBLIC_APPROVED_APPS_CACHE_KEY
from database.cache import get_memory_cache
from database.redis_db import delete_generic_cache
from models.conversation import Structured
from routers.sync_finalization_reference import ReferenceRequest, _adapt
from testing.finalization_replay import reference as reference_module
from testing.finalization_replay.corpus import FIXED_DATE, unpack
from testing.finalization_replay.driver import _observe
from testing.finalization_replay.firestore_proxy import FirestoreProxy
from testing.finalization_replay.metrics import suspend_meter
from testing.finalization_replay.ordinary_sync_retry import UNREADABLE, check_ciphertext, retry_to_park
from testing.finalization_replay.speaker_trace import record_speaker_trace
from testing.replay_harness.env import emulator_endpoint
from utils import ai_profile_refresh, analytics, executors
from utils.conversations.episode_attach_key import content_key
from utils.conversations.llm_input_dedupe import output_fingerprint
from utils.enrichment import callback
from utils.episodes import client_gate, finalize

HOURLY_USAGE_REPLAY_TIME = FIXED_DATE.replace(minute=30)


class HourlyUsageReplayClock(datetime):
    @classmethod
    def now(cls, tz=None):
        midhour = HOURLY_USAGE_REPLAY_TIME
        return midhour.astimezone(tz) if tz is not None else midhour.replace(tzinfo=None)


def remember_python_memo(state, key):
    if key:
        with suspend_meter():
            link = state.client.document(state.home_dirty_receipt_path).get().to_dict() or {}
        if link.get('attach_revision') == key:
            state.episode_attach_memo_writer_keys.append(key)


def _reset_fixture_caches():

    # The two replay sides each share a process and a fake Redis across fixtures.
    # Reset the marketplace's two cache layers before any measured work.
    get_memory_cache().clear()
    delete_generic_cache(PUBLIC_APPROVED_APPS_CACHE_KEY)


def _python_sync(state):
    try:

        result = callback.enrich_conversation(state.uid, state.cid, state.case['document'].get('language') or 'en')
    except ModuleNotFoundError as error:
        state.diag_missing_module = error.name
        raise
    if result is None:
        return 'deferred'
    return 'discarded' if result.discarded else result.status.value


def _seed_worker_intent(state):
    job_id = str(UUID(bytes=sha256(f'listen-finalization:{state.uid}:{state.cid}:1'.encode()).digest()[:16], version=4))
    owner = {'finalization_engine': 'go', 'finalization_owner_epoch': 1, 'finalization_revision': 1}
    state.conversation.update(owner | {'finalization_job_id': job_id, 'status': 'processing'})
    job = state.client.collection('conversation_finalization_jobs').document(job_id)
    job.create(
        owner
        | {
            'status': 'queued',
            'schema_version': 1,
            'uid': state.uid,
            'conversation_id': state.cid,
            'processing_trigger': 'sync_update',
        }
    )
    return job


class UnexpectedGoOutcome(RuntimeError):
    """An ordinary-sync fixture stopped before its expected terminal path."""


def _go_sync(state, binary, database, key, url, firestore_proxy):
    with suspend_meter():
        original = state.conversation.get().to_dict() if state.case['name'] == UNREADABLE else None
        job = _seed_worker_intent(state)
    firestore_proxy.reset()
    process = subprocess.run(
        [str(binary), '-test.run=^TestOrdinarySyncReplay$', '-test.timeout=75s'],
        env={
            'PATH': os.environ['PATH'],
            'FIRESTORE_EMULATOR_HOST': firestore_proxy.address,
            'TEST_DATABASE_URL': database,
            'TEST_DATABASE_REQUIRED': '1',
            'OMI_ORDINARY_SYNC_REPLAY': '1',
        },
        input=json.dumps(
            {'Project': state.client.project, 'Origin': url, 'Key': key, 'Owner': state.uid, 'Conversation': state.cid}
        ),
        text=True,
        capture_output=True,
        timeout=80,
    )
    state.add_firestore_operations(**firestore_proxy.counts())
    state.firestore_operation_sources = firestore_proxy.operation_sources()
    for bucket, count in firestore_proxy.home_receipt_trace().items():
        value = {'set_true': True, 'set_false': False, 'deleted': 'deleted'}.get(bucket)
        for _ in range(count):
            state.record_home_dirty_receipt_write(value)
    result = re.search(r'^ORDINARY_SYNC_RESULT=(\w+)$', process.stdout, re.MULTILINE)
    cause = re.search(r'^ORDINARY_SYNC_CAUSE=(\w+)$', process.stdout, re.MULTILINE)
    if process.returncode or result is None:
        details = '\n'.join((process.stdout + process.stderr).splitlines()[-12:])[-2000:]
        raise RuntimeError(f'workerd worker replay failed (exit {process.returncode}): {details}')
    with suspend_meter():
        row = job.get().to_dict() or {}
    fanout = row.get('fanout_key', '')
    state.admitted = {
        'job_id': job.id,
        'fanout_key': fanout,
        'own_key': False,
        'engine': row.get('finalization_engine', ''),
        'owner_epoch': row.get('finalization_owner_epoch', 0),
        'revision': row.get('finalization_revision', 0),
    }
    state.queue_fanout_key = fanout
    state.go_evidence = {
        'firestore_rpc_failures': firestore_proxy.rpc_failures(),
        'job': {
            'state': row.get('status', ''),
            'outcome': result[1],
            'cause': cause[1] if cause else '',
        },
    }
    if result[1] != 'success':
        if (
            state.case['name'] == UNREADABLE
            and result[1] == 'failure'
            and cause is not None
            and cause[1] == 'conversation_unreadable'
            and row.get('status') == 'dead_letter'
        ):
            with suspend_meter():
                check_ciphertext(original, state.conversation.get().to_dict())
            state.go_evidence['ciphertext_kept'] = True
            return result[1]
        raise UnexpectedGoOutcome
    with suspend_meter():
        final = state.conversation.get().to_dict()
    return 'discarded' if final.get('discarded') else final['status']


def _receiver(client):
    def dispatch(body, headers):
        if headers.get('Authorization') != 'Bearer replay-only':
            return 403, {}
        result = _adapt(client, ReferenceRequest.model_validate(body))
        if isinstance(result, JSONResponse):
            return result.status_code, json.loads(result.body)
        return 200, result

    return dispatch


def _observed_notes_output(observation):
    document = observation.get('conversation') or {}
    if not isinstance(document.get('structured'), dict):
        return None
    try:
        return output_fingerprint(Structured.model_validate(unpack(document['structured'])))
    except (ValidationError, TypeError, ValueError):
        return None


def _observe_sync(state, run, leaves, url):

    record_speaker_trace(state, leaves)
    futures = []
    submit = executors.submit_with_context

    def track(executor, fn, *args, **kwargs):
        future = submit(executor, fn, *args, **kwargs)
        futures.append(future)
        return future

    leaves.enter_context(patch.object(callback, 'submit_with_context', track))
    leaves.enter_context(patch.object(finalize, 'submit_with_context', track))
    leaves.enter_context(patch.object(ai_profile_refresh, 'submit_with_context', track))
    leaves.enter_context(patch.object(reference_module, '_run', run))
    if state.replay_side == 'python':
        original_attach_recorded = episode_timeline.attach_recorded
        original_complete = episode_attach_memo.complete

        def attach_recorded(*args, **kwargs):
            row = kwargs.get('attach_row')
            key = content_key(row) if isinstance(row, Mapping) else None
            result = original_attach_recorded(*args, **kwargs)
            remember_python_memo(state, key)
            return result

        def complete(uid, cid, row, owner, *args, **kwargs):
            key = content_key(row) if isinstance(row, Mapping) else None
            result = original_complete(uid, cid, row, owner, *args, **kwargs)
            if uid == state.uid and cid == state.cid:
                remember_python_memo(state, key)
            return result

        leaves.enter_context(patch.object(episode_timeline, 'attach_recorded', attach_recorded))
        leaves.enter_context(patch.object(episode_attach_memo, 'complete', complete))
    try:
        if state.replay_side == 'python' and state.case['name'] == UNREADABLE:
            # The route drives its own durable outbox. The direct callback
            # harness's BYOK and provider setup does not belong to its meter.
            return run(state)
        return reference_module.run_reference(state, leaves, url)
    finally:
        for future in futures:
            future.result(timeout=12)


def run_cases(states, side, binary, database, key, worker_backend, server, client, url):
    with patch.object(analytics, 'datetime', HourlyUsageReplayClock):
        if side == 'go':
            server.reference = _receiver(client)

        def invoke(state):
            state.replay_side = side
            if side == 'python':
                if state.case['name'] == UNREADABLE:
                    state.python_retry = retry_to_park(state, worker_backend)
                    return state.python_retry['outcome']
                return _python_sync(state)
            privacy_document_path = f"batch_pipeline_privacy/{sha256(state.uid.encode('utf-8')).hexdigest()}"
            with FirestoreProxy(emulator_endpoint(), privacy_document_path, state.home_dirty_receipt_path) as proxy:
                return _go_sync(state, binary, database, key, url, proxy)

        def attach_at_intake(target):
            row = target.conversation.get().to_dict() or {}
            key = episode_attach_memo.current_key(target.uid, row) if side == 'python' else None
            result = finalize.attach_synced_at_intake(target.uid, target.cid, row)
            remember_python_memo(target, key)
            return result

        outputs = []
        for state in states:
            _reset_fixture_caches()
            out = {'name': state.case['name'], 'errors': {}}
            outputs.append(out)
            server.state = state
            server.errors.clear()
            state.replay_side = side
            client_gate.note_client_seen(state.uid)
            with ExitStack() as leaves:
                _observe(
                    state,
                    lambda target: _observe_sync(target, invoke, leaves, url),
                    out,
                    side,
                    setup=attach_at_intake,
                )
            if getattr(state, 'diag_missing_module', None):
                out['errors'][side] = f'ModuleNotFoundError: {state.diag_missing_module}'
            if side in out:
                out[side]['ordinary_sync_diagnostic'] = True
                if state.case['name'] == 'kept-with-effects':
                    out[side]['observed_notes_output'] = _observed_notes_output(out[side])
                out[side]['hourly_usage_replay_bucket'] = HOURLY_USAGE_REPLAY_TIME.strftime('%Y-%m-%d-%H')
                if getattr(state, 'python_retry', None):
                    out[side]['python_retry'] = state.python_retry
                calls = getattr(state, 'replay_token_calls', [])
                out[side]['provider_token_calls'] = calls
                prompt = sum(call['input'] for call in calls if not call['embedding'])
                completion = sum(call['output'] for call in calls if not call['embedding'])
                out[side]['cost']['llm_tokens'] = {
                    'prompt': prompt,
                    'completion': completion,
                    'total': prompt + completion,
                }
                out[side]['cost']['embedding_tokens'] = sum(call['input'] for call in calls if call['embedding'])
            if server.errors:
                out['errors'][side] = server.errors[0]
    return outputs
