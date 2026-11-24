"""Replay ordinary sync at the stored-conversation boundary on both engines."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID, uuid4

from testing.finalization_replay.candidate import replay_database
from testing.finalization_replay.corpus import DEFAULT_TEST_KEY, read_corpus
from testing.finalization_replay.driver import _ReplayKey, _clear, _observe, _seed
from testing.finalization_replay.providers import allow_provider_port, provider_server
from testing.finalization_replay.reference import run_reference
from testing.replay_harness.env import emulator_endpoint, replay_environment
from testing.replay_harness.guard import private_text


def _python_sync(state):
    from utils.enrichment.callback import enrich_conversation

    result = enrich_conversation(state.uid, state.cid, state.case['document'].get('language') or 'en')
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


def _go_sync(state, binary, database, key, url):
    job = _seed_worker_intent(state)
    check_status = state.case['name'] == 'ordinary-sync-kept'
    process = subprocess.run(
        [str(binary), '-test.run=^TestOrdinarySyncReplay$', '-test.timeout=75s'],
        env={
            'PATH': os.environ['PATH'],
            'FIRESTORE_EMULATOR_HOST': emulator_endpoint(),
            'TEST_DATABASE_URL': database,
            'TEST_DATABASE_REQUIRED': '1',
            'OMI_ORDINARY_SYNC_REPLAY': '1',
        },
        input=json.dumps(
            {
                'Project': state.client.project,
                'Origin': url,
                'Key': key,
                'Owner': state.uid,
                'Conversation': state.cid,
                'CheckStatus': check_status,
            }
        ),
        text=True,
        capture_output=True,
        timeout=80,
    )
    result = re.search(r'^ORDINARY_SYNC_RESULT=(\w+)$', process.stdout, re.MULTILINE)
    if process.returncode or result is None:
        raise RuntimeError('workerd worker replay failed')
    if check_status:
        from testing.finalization_replay.status_route import check_status_route

        check_status_route(state, job.id, process.stdout)
    row = job.get().to_dict()
    fanout = row.get('fanout_key', '')
    state.admitted = {'job_id': job.id, 'fanout_key': fanout, 'own_key': False}
    state.queue_fanout_key = fanout
    if result[1] != 'success':
        return result[1]
    final = state.conversation.get().to_dict()
    return 'discarded' if final.get('discarded') else final['status']


def _receiver(client):
    from fastapi.responses import JSONResponse
    from routers.sync_finalization_reference import ReferenceRequest, _adapt

    def dispatch(body, headers):
        if headers.get('Authorization') != 'Bearer replay-only':
            return 403, {}
        result = _adapt(client, ReferenceRequest.model_validate(body))
        if isinstance(result, JSONResponse):
            return result.status_code, json.loads(result.body)
        return 200, result

    return dispatch


def _observe_sync(state, run, leaves, url):
    from utils import executors
    from utils.episodes import finalize
    from utils.enrichment import callback

    futures = []
    submit = executors.submit_with_context

    def track(executor, fn, *args, **kwargs):
        future = submit(executor, fn, *args, **kwargs)
        futures.append(future)
        return future

    leaves.enter_context(patch.object(callback, 'submit_with_context', track))
    leaves.enter_context(patch.object(finalize, 'submit_with_context', track))
    try:
        return run_reference(state, leaves, url, run=run)
    finally:
        for future in futures:
            future.result(timeout=12)


def _home_observation(state):
    from utils.home_feed.projection import reveal_display

    row = state.conversation.get().to_dict()
    membership = state.user.collection('episode_links').document(state.cid).get().to_dict()
    return {
        'display': reveal_display(state.uid, row.get('home_display')),
        'has_tasks': row.get('home_has_tasks'),
        'hidden': row.get('home_hidden'),
        'has_episode_membership': membership is not None,
    }


def _run_side(cases, side, binary, database, key):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from testing import store_fixtures

    client = firestore.Client(project=f'demo-sync-replay-{uuid4().hex[:12]}', credentials=AnonymousCredentials())
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    with ExitStack() as cleanup, provider_server() as server:
        cleanup.callback(client.close)
        cleanup.callback(_clear, client)
        url = f'http://127.0.0.1:{server.server_port}'
        states = _seed(client, cases, url)
        with patch.object(store_fixtures, '_emulator_client', lambda: client), replay_environment(
            _ReplayKey(key, client.project, url)
        ), allow_provider_port(server.server_port, connect, connect_ex):
            import fakeredis
            import tiktoken

            tiktoken.encoding_for_model('text-embedding-3-large')
            from database import redis_db

            with fakeredis.FakeRedis() as redis, patch.object(redis_db, 'r', redis), patch.object(
                redis_db, 'create_bounded_redis_client', lambda *_a, **_kw: redis
            ):
                if side == 'go':
                    server.reference = _receiver(client)

                def invoke(state):
                    if side == 'python':
                        return _python_sync(state)
                    return _go_sync(state, binary, database, key, url)

                from utils.episodes import client_gate, finalize

                outputs = []
                for state in states:
                    out = {'name': state.case['name'], 'errors': {}}
                    outputs.append(out)
                    server.state = state
                    server.errors.clear()
                    client_gate.note_client_seen(state.uid)
                    finalize.attach_synced_at_intake(state.uid, state.cid, state.conversation.get().to_dict())
                    state.replay_token_calls.clear()  # Intake is outside the finalization replay boundary.
                    with ExitStack() as leaves:
                        _observe(state, lambda target: _observe_sync(target, invoke, leaves, url), out, side)
                    if side in out:
                        out[side]['provider_token_calls'] = state.replay_token_calls
                        out[side]['home'] = _home_observation(state)
                        out[side]['notes_prompt_sha256'] = state.notes_prompt_hashes
                    if server.errors:
                        out['errors'][side] = server.errors[0]
    return outputs


def _paired(payload, binary, key_file):
    sides = []
    for side in ('python', 'go'):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'testing.finalization_replay.serving', binary, key_file, side],
            input=payload,
            capture_output=True,
            timeout=240,
        )
        if result.returncode:
            raise RuntimeError(f'{side} replay child failed')
        sides.append(json.loads(result.stdout))
    return [{**python, **go, 'errors': {**python['errors'], **go['errors']}} for python, go in zip(*sides, strict=True)]


def main():
    emulator_endpoint()
    binary, key_file, *side = sys.argv[1:]
    payload = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    cases = read_corpus(payload)
    for case in cases:
        row = case.get('document')
        if (
            not isinstance(row, dict)
            or row.get('status') != 'completed'
            or row.get('sync_content_revision') != 1
            or any(case.get(k) for k in ('trigger', 'own_key', 'final_attempt', 'repeat'))
        ):
            raise ValueError('ordinary-sync fixtures must start at a stored sync row')
    if not side:
        json.dump(_paired(payload, binary, key_file), sys.stdout)
        return
    key = private_text(Path(key_file)).rstrip('\r\n') if key_file else DEFAULT_TEST_KEY
    if len(key.encode()) < 32 or '\x00' in key or side[0] not in {'python', 'go'}:
        raise ValueError('invalid ordinary-sync replay parameters')
    logging.disable(logging.CRITICAL)
    dsn = os.environ['TEST_DATABASE_URL']
    # Validate the loopback DSN and keep both engines on disposable state.
    with replay_database(dsn) as database, open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(
        sink
    ), redirect_stderr(sink):
        result = _run_side(cases, side[0], Path(binary).resolve(strict=True), database, key)
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit(f'ordinary-sync replay driver failed: {type(error).__name__}')
