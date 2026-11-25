"""Subprocess protocol for backend-go/tools/replay."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal
import socket
import sys
from unittest.mock import patch
from uuid import uuid4

from testing.finalization_replay.candidate import migrate, replay_database, run_candidate
from testing.finalization_replay.corpus import DEFAULT_TEST_KEY, pack, read_corpus
from testing.finalization_replay.metrics import install_firestore_meter, measure
from testing.finalization_replay.providers import allow_provider_port, provider_server
from testing.finalization_replay.reference import run_reference
from testing.finalization_replay.state import CaseState
from testing.replay_harness.env import emulator_endpoint, replay_environment
from testing.replay_harness.guard import private_text


def _observe(state, run, output, side):
    try:
        before = state.documents()
        state.start()
        with measure(state):
            status = run(state)
        output[side] = state.observe(status, before)
    except Exception as error:
        output['errors'][side] = type(error).__name__
        finished = datetime.now(timezone.utc)
        output[side] = {
            'status': 'execution_error',
            'queue_fanout_key': state.queue_fanout_key,
            'updated_at_changed': False,
            'admitted': state.admitted,
            'started_at': (state.started_at or finished).isoformat(),
            'finished_at': finished.isoformat(),
            'provider_calls': sorted(state.provider_calls),
            'effects': pack(state.effects),
            'conversation': None,
            'derived_documents': {},
            'webhooks': sorted(state.webhooks, key=lambda delivery: delivery['app']),
            'cost': state.cost(),
            'go_evidence': state.go_evidence,
        }


def _clear(client):
    for collection in client.collections():
        client.recursive_delete(collection)


class _ReplayKey:
    def __init__(self, key, project, url):
        self.key = key
        self.project = project
        self.url = url

    def apply(self, settings):
        settings.update(
            {
                'ENCRYPTION_SECRET': self.key,
                'FIREBASE_PROJECT_ID': self.project,
                'GOOGLE_CLOUD_PROJECT': self.project,
                'OMI_LLM_GATEWAY_URL': self.url,
                'OMI_LLM_GATEWAY_FEATURE_MODE': 'gateway',
                'OMI_SHAPED_AGENT_MODE': 'on',
                'OPENAI_BASE_URL': f'{self.url}/v1',
                'PINECONE_INDEX_NAME': 'replay-local',
                **({'TIKTOKEN_CACHE_DIR': os.environ['TIKTOKEN_CACHE_DIR']} if os.getenv('TIKTOKEN_CACHE_DIR') else {}),
            }
        )


def _seed(client, cases, url):
    states = [CaseState(client, case) for case in cases]
    if len({state.uid for state in states}) != len(states):
        raise ValueError('each case needs its own replay uid')
    for state in states:
        state.seed(url)
    return states


def replay(cases, jobd, dsn, key):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from testing import store_fixtures

    install_firestore_meter()

    project = f'demo-replay-{uuid4().hex[:12]}'
    outputs = [{'name': case['name'], 'errors': {}} for case in cases]

    def client(suffix):
        return firestore.Client(project=f'{project}-{suffix}', credentials=AnonymousCredentials())

    with replay_database(dsn) as database, ExitStack() as cleanup:
        migrate(jobd, database)
        reference, candidate = client('python'), client('go')
        for firestore_client in (reference, candidate):
            cleanup.callback(firestore_client.close)
            cleanup.callback(_clear, firestore_client)
        connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
        with provider_server() as server:
            url = f'http://127.0.0.1:{server.server_port}'
            # Seed both sides before product imports install SDK-wide write hooks.
            reference_cases, candidate_cases = _seed(reference, cases, url), _seed(candidate, cases, url)
            for state, output in zip(candidate_cases, outputs, strict=True):
                _observe(state, lambda target: run_candidate(target, jobd, database, key), output, 'go')
            # After this point product hooks can run only against the Python project.
            with patch.object(store_fixtures, '_emulator_client', lambda: reference), replay_environment(
                _ReplayKey(key, reference.project, url)
            ), allow_provider_port(server.server_port, connect, connect_ex):
                import fakeredis
                import tiktoken

                # Load the pinned data file under the network guard. A missing
                # tokenizer must fail the replay instead of suppressing vector work.
                tiktoken.encoding_for_model('text-embedding-3-large')
                from database import redis_db

                # Product Redis helpers expect bytes just as they do from redis-py.
                with fakeredis.FakeRedis() as redis, patch.object(redis_db, 'r', redis), patch.object(
                    redis_db, 'create_bounded_redis_client', lambda *_a, **_kw: redis
                ):
                    for state, output in zip(reference_cases, outputs, strict=True):
                        server.state = state
                        server.errors.clear()
                        with ExitStack() as leaves:
                            _observe(state, lambda target: run_reference(target, leaves, url), output, 'python')
                        if server.errors:
                            output['errors']['python'] = 'ReplayProviderError'
    return outputs


def _terminate(_signum, _frame):
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, _terminate)
    emulator_endpoint()
    jobd, key_file = sys.argv[1:]
    key = private_text(Path(key_file)).rstrip('\r\n') if key_file else DEFAULT_TEST_KEY
    if len(key.encode()) < 32 or '\x00' in key:
        raise ValueError('replay key must be at least 32 bytes')
    cases = read_corpus(sys.stdin.buffer.read(16 * 1024 * 1024 + 1))
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink), redirect_stderr(sink):
        result = replay(cases, Path(jobd).resolve(strict=True), os.environ['TEST_DATABASE_URL'], key)
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        sys.exit(f'finalization replay driver failed: {type(exc).__name__}')
