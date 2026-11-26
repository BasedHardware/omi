"""Diagnostic-only ordinary-sync replay through the real workerd handler."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from hashlib import sha256
import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

import fakeredis
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import tiktoken

from testing import store_fixtures
from testing.finalization_replay.candidate import replay_database
from testing.finalization_replay.corpus import DEFAULT_TEST_KEY, pack, read_corpus, seed_document
from testing.finalization_replay.driver import _ReplayKey, _clear, _seed
from testing.finalization_replay.metrics import install_firestore_meter
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


def _run_side(cases, side, binary, database, key, worker_backend):
    _enable_worker_backend(worker_backend)

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
            tiktoken.encoding_for_model('text-embedding-3-large')
            # replay_environment loads and patches the selected Redis module.
            redis_db = sys.modules['database.redis_db']
            with fakeredis.FakeRedis() as redis, patch.object(redis_db, 'r', redis), patch.object(
                redis_db, 'create_bounded_redis_client', lambda *_a, **_kw: redis
            ):
                runtime = importlib.import_module('testing.finalization_replay.ordinary_sync_runtime')
                return runtime.run_cases(states, side, binary, database, key, worker_backend, server, client, url)


def _paired(payload, worker_binary, worker_backend):
    side_timeout = int(os.environ.get('ORACLE_DIAG_SIDE_TIMEOUT_SECONDS', '240'))
    if side_timeout <= 0:
        raise ValueError('ORACLE_DIAG_SIDE_TIMEOUT_SECONDS must be positive')
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
            timeout=side_timeout,
        )
        if result.returncode:
            detail = result.stderr.decode(errors='replace')[-2000:]
            raise RuntimeError(f'{side} replay child failed (exit {result.returncode}): {detail}')
        sides.append(json.loads(result.stdout))
    paired = []
    for python, go in zip(*sides, strict=True):
        if python['name'] != go['name']:
            raise ValueError('ordinary-sync replay sides returned different case names')
        paired.append({**python, **go, 'errors': {**python['errors'], **go['errors']}})
    return paired


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

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-binary', required=True)
    parser.add_argument('--worker-backend', required=True)
    parser.add_argument('--side', choices=('python', 'go'))
    args = parser.parse_args()
    payload = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    corpus_sha256 = sha256(payload).hexdigest()
    cases = _stored_sync_cases(read_corpus(payload))
    payload = json.dumps({'version': 1, 'cases': cases}, ensure_ascii=True).encode()
    if args.side is None:
        observations = _paired(payload, args.worker_binary, args.worker_backend)
        json.dump({'corpus_sha256': corpus_sha256, 'cases': observations}, sys.stdout)
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
