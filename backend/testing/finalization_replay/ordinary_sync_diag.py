"""Diagnostic-only ordinary-sync replay through the real workerd handler."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from hashlib import sha256
import importlib.util
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
from testing.finalization_replay.corpus import DEFAULT_TEST_KEY, pack, read_corpus, seed_document
from testing.finalization_replay.driver import _ReplayKey, _clear, _observe, _seed
from testing.finalization_replay import reference as reference_module
from testing.replay_harness.env import emulator_endpoint, replay_environment


def _worker_providers(worker_backend):
    path = Path(worker_backend) / 'testing' / 'finalization_replay' / 'providers.py'
    spec = importlib.util.spec_from_file_location('workerd_replay_providers', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('workerd replay provider module is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.provider_server, module.allow_provider_port


def _enable_worker_backend(worker_backend):
    backend = str(Path(worker_backend).resolve(strict=True))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    for name in ('routers', 'utils', 'database', 'models'):
        package = sys.modules.get(name)
        target = str(Path(backend) / name)
        if (
            package is not None
            and hasattr(package, '__path__')
            and Path(target).is_dir()
            and target not in package.__path__
        ):
            package.__path__.insert(0, target)


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
            {'Project': state.client.project, 'Origin': url, 'Key': key, 'Owner': state.uid, 'Conversation': state.cid}
        ),
        text=True,
        capture_output=True,
        timeout=80,
    )
    result = re.search(r'^ORDINARY_SYNC_RESULT=(\w+)$', process.stdout, re.MULTILINE)
    cause = re.search(r'^ORDINARY_SYNC_CAUSE=(\w+)$', process.stdout, re.MULTILINE)
    if process.returncode or result is None:
        raise RuntimeError('workerd worker replay failed')
    row = job.get().to_dict() or {}
    fanout = row.get('fanout_key', '')
    state.admitted = {'job_id': job.id, 'fanout_key': fanout, 'own_key': False}
    state.queue_fanout_key = fanout
    state.go_evidence = {
        'job': {
            'state': row.get('status', ''),
            'outcome': result[1],
            'cause': cause[1] if cause else '',
        }
    }
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
    leaves.enter_context(patch.object(reference_module, '_run', run))
    try:
        return reference_module.run_reference(state, leaves, url)
    finally:
        for future in futures:
            future.result(timeout=12)


def _run_side(cases, side, binary, database, key, worker_backend):
    _enable_worker_backend(worker_backend)
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from testing import store_fixtures
    from testing.finalization_replay.metrics import install_firestore_meter

    install_firestore_meter()
    provider_server, allow_provider_port = _worker_providers(worker_backend)

    client = firestore.Client(project=f'demo-sync-replay-{uuid4().hex[:12]}', credentials=AnonymousCredentials())
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    with ExitStack() as cleanup, provider_server() as server:
        cleanup.callback(client.close)
        cleanup.callback(_clear, client)
        url = f'http://127.0.0.1:{server.server_port}'
        states = _seed(client, cases, url)
        for state in states:
            state.notes_prompt_hashes = []
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
                    with ExitStack() as leaves:
                        _observe(state, lambda target: _observe_sync(target, invoke, leaves, url), out, side)
                    if server.errors:
                        out['errors'][side] = server.errors[0]
    return outputs


def _paired(payload, worker_binary, worker_backend):
    sides = []
    for side in ('python', 'go'):
        result = subprocess.run(
            [
                sys.executable,
                '-B',
                '-m',
                'testing.finalization_replay.ordinary_sync_diag',
                '--worker-binary',
                worker_binary,
                '--worker-backend',
                worker_backend,
                '--side',
                side,
            ],
            input=payload,
            capture_output=True,
            timeout=240,
        )
        if result.returncode:
            raise RuntimeError(f'{side} replay child failed')
        sides.append(json.loads(result.stdout))
    return [{**python, **go, 'errors': {**python['errors'], **go['errors']}} for python, go in zip(*sides, strict=True)]


def _stored_sync_cases(cases):
    """Project each fixture to the one stored-row sync admission the seam supports."""
    normalized = []
    for original in cases:
        case = dict(original)
        supplied = case.get('document')
        if supplied is None:
            case['document'] = {}
        row = seed_document(case, case.get('conversation_id', case['name']))
        if row is None:
            raise ValueError('ordinary-sync diagnostics require a seeded conversation row')
        row['status'] = 'completed'
        row.setdefault('sync_content_revision', 1)
        case['document'] = pack(row)
        normalized.append(case)
    return normalized


def main():
    emulator_endpoint()
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-binary', required=True)
    parser.add_argument('--worker-backend', required=True)
    parser.add_argument('--side', choices=('python', 'go'))
    args = parser.parse_args()
    payload = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    cases = _stored_sync_cases(read_corpus(payload))
    payload = json.dumps({'version': 1, 'cases': cases}, ensure_ascii=True).encode()
    if args.side is None:
        json.dump(_paired(payload, args.worker_binary, args.worker_backend), sys.stdout)
        return
    key = DEFAULT_TEST_KEY
    if len(key.encode()) < 32 or '\x00' in key:
        raise ValueError('invalid ordinary-sync replay parameters')
    logging.disable(logging.CRITICAL)
    dsn = os.environ['TEST_DATABASE_URL']
    # Validate the loopback DSN and keep both engines on disposable state.
    with replay_database(dsn) as database, open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(
        sink
    ), redirect_stderr(sink):
        result = _run_side(
            cases, args.side, Path(args.worker_binary).resolve(strict=True), database, key, args.worker_backend
        )
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit(f'ordinary-sync replay driver failed: {type(error).__name__}')
