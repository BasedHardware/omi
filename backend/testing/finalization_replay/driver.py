"""Subprocess protocol for backend-go/tools/replay."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout, redirect_stderr
import json
import logging
import os
from pathlib import Path
import signal
import sys
from unittest.mock import patch
from uuid import uuid4

from testing.finalization_replay.candidate import migrate, replay_database, run_candidate
from testing.finalization_replay.corpus import DEFAULT_TEST_KEY, read_corpus
from testing.finalization_replay.reference import run_reference
from testing.finalization_replay.state import CaseState
from testing.replay_harness.env import emulator_endpoint, replay_environment
from testing.replay_harness.guard import private_text


def _observe(state, run, output, side):
    try:
        before = state.documents()
        output[side] = state.observe(run(state), before)
    except Exception as error:
        output['errors'][side] = type(error).__name__


def _clear(client):
    for collection in client.collections():
        client.recursive_delete(collection)


class _ReplayKey:
    def __init__(self, key, project):
        self.key = key
        self.project = project

    def apply(self, settings):
        settings.update(
            {
                'ENCRYPTION_SECRET': self.key,
                'FIREBASE_PROJECT_ID': self.project,
                'GOOGLE_CLOUD_PROJECT': self.project,
            }
        )


def _seed(client, cases):
    states = [CaseState(client, case) for case in cases]
    if len({state.uid for state in states}) != len(states):
        raise ValueError('each case needs its own replay uid')
    for state in states:
        state.seed()
    return states


def replay(cases, jobd, dsn, key):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from testing import store_fixtures

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
        # Seed both sides before product imports install SDK-wide write hooks.
        reference_cases, candidate_cases = _seed(reference, cases), _seed(candidate, cases)
        for state, output in zip(candidate_cases, outputs, strict=True):
            _observe(state, lambda target: run_candidate(target, jobd, database, key), output, 'go')
        # After this point product hooks can run only against the Python project.
        with patch.object(store_fixtures, '_emulator_client', lambda: reference), replay_environment(
            _ReplayKey(key, reference.project)
        ):
            for state, output in zip(reference_cases, outputs, strict=True):
                with ExitStack() as leaves:
                    _observe(state, lambda target: run_reference(target, leaves), output, 'python')
    return outputs


def _terminate(_signum, _frame):
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, _terminate)
    emulator_endpoint()
    corpus, jobd, key_file = sys.argv[1:]
    key = private_text(Path(key_file)).rstrip('\r\n') if key_file else DEFAULT_TEST_KEY
    if len(key.encode()) < 32 or '\x00' in key:
        raise ValueError('replay key must be at least 32 bytes')
    cases = read_corpus(Path(corpus))
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink), redirect_stderr(sink):
        result = replay(cases, Path(jobd).resolve(strict=True), os.environ['TEST_DATABASE_URL'], key)
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        sys.exit(f'finalization replay driver failed: {type(exc).__name__}')
