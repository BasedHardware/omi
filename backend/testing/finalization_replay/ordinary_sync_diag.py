"""Diagnostic-only ordinary-sync replay through the real workerd handler."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from collections.abc import Mapping
from hashlib import sha256
import importlib
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
from testing.finalization_replay.firestore_proxy import FirestoreProxy
from testing.finalization_replay import reference as reference_module
from testing.finalization_replay.metrics import suspend_meter
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
    for name in ('config', 'routers', 'utils', 'database', 'models'):
        package = sys.modules.get(name)
        if package is None:
            package = importlib.import_module(name)
        target = str(Path(backend) / name)
        if (
            package is not None
            and hasattr(package, '__path__')
            and Path(target).is_dir()
            and target not in package.__path__
        ):
            package.__path__.insert(0, target)


def _python_sync(state):
    try:
        from utils.enrichment.callback import enrich_conversation

        result = enrich_conversation(state.uid, state.cid, state.case['document'].get('language') or 'en')
    except ModuleNotFoundError as error:
        state.diag_missing_module = error.name
        raise
    if result is None:
        return 'deferred'
    return 'discarded' if result.discarded else result.status.value


def _python_sync_with_memo_evidence(state):
    """Capture the row keys Python actually offers to its attach memo writers."""
    from database import episode_attach_memo, episode_timeline
    from utils.conversations.episode_attach_key import content_key

    original_attach_recorded = episode_timeline.attach_recorded
    original_complete = episode_attach_memo.complete

    def attach_recorded(*args, **kwargs):
        row = kwargs.get('attach_row')
        key = content_key(row) if isinstance(row, Mapping) else None
        result = original_attach_recorded(*args, **kwargs)
        if key:
            state.episode_attach_memo_writer_keys.append(key)
        return result

    def complete(uid, cid, row, owner, *args, **kwargs):
        key = content_key(row) if isinstance(row, Mapping) else None
        result = original_complete(uid, cid, row, owner, *args, **kwargs)
        if uid == state.uid and cid == state.cid and key:
            state.episode_attach_memo_writer_keys.append(key)
        return result

    with patch.object(episode_timeline, 'attach_recorded', attach_recorded), patch.object(
        episode_attach_memo, 'complete', complete
    ):
        return _python_sync(state)


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


def _go_sync(state, binary, database, key, url, firestore_proxy):
    with suspend_meter():
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
        'job': {
            'state': row.get('status', ''),
            'outcome': result[1],
            'cause': cause[1] if cause else '',
        }
    }
    if result[1] != 'success':
        return result[1]
    with suspend_meter():
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
            state.compare_full_derived_documents = True
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
                    state.replay_side = side
                    if side == 'python':
                        return _python_sync_with_memo_evidence(state)
                    privacy_document_path = f"batch_pipeline_privacy/{sha256(state.uid.encode('utf-8')).hexdigest()}"
                    with FirestoreProxy(
                        emulator_endpoint(), privacy_document_path, state.home_dirty_receipt_path
                    ) as proxy:
                        return _go_sync(state, binary, database, key, url, proxy)

                from utils.episodes import client_gate, finalize

                outputs = []
                for state in states:
                    out = {'name': state.case['name'], 'errors': {}}
                    outputs.append(out)
                    server.state = state
                    server.errors.clear()
                    client_gate.note_client_seen(state.uid)
                    with ExitStack() as leaves:
                        _observe(
                            state,
                            lambda target: _observe_sync(target, invoke, leaves, url),
                            out,
                            side,
                            setup=lambda target: finalize.attach_synced_at_intake(
                                target.uid, target.cid, target.conversation.get().to_dict()
                            ),
                        )
                    if getattr(state, 'diag_missing_module', None):
                        out['errors'][side] = f'ModuleNotFoundError: {state.diag_missing_module}'
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
            detail = result.stderr.decode(errors='replace')[-2000:]
            raise RuntimeError(f'{side} replay child failed (exit {result.returncode}): {detail}')
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
        sys.exit(f'ordinary-sync replay driver failed: {type(error).__name__}: {error}')
