"""Admission incident reproductions on real loopback transactions, never fast units."""

import asyncio
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


def test_admission_seed_cases(tmp_path):
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import write_report, table

    items = asyncio.run(
        run_cases(
            [
                FIXTURES / name
                for name in (
                    'admission-not-durable',
                    'admission-drain-contention',
                    'admission-control',
                )
            ]
        )
    )
    write_report(items, tmp_path)
    print('\n' + table(items))
    by_id = {item['item']: item for item in items}
    assert all(item['expectation_met'] for item in items), table(items)
    for name, reason in [
        ('admission-not-durable', 'ValueError'),
        ('admission-drain-contention', 'FirestoreContentionExhausted'),
    ]:
        item = by_id[name]
        assert item['verdict'] == 'FAIL' and item['furthest_stage'] == 'admission'
        assert reason in item['stop_reason']
    assert 'retained_capture_not_durable' in by_id['admission-not-durable']['stop_reason']
    control = by_id['admission-control']
    assert control['verdict'] == 'PASS'
    assert control['stages'][0]['details']['admitted'] == 1


def test_environment_refuses_cloud_and_uses_local_leaves():
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    from io import BytesIO
    import socket
    import google.auth
    from google.cloud import firestore, storage
    from google.api_core.exceptions import PreconditionFailed
    import grpc
    from testing.replay_harness.env import replay_environment

    previous = dict(os.environ)
    with replay_environment() as environment:
        for factory in (firestore.Client, storage.Client, google.auth.default):
            with pytest.raises(RuntimeError, match='refuses cloud'):
                factory()
        with pytest.raises(RuntimeError, match='non-emulator'):
            grpc.insecure_channel('production.invalid:443')
        with pytest.raises(RuntimeError, match='refuses cloud'):
            grpc.secure_channel('production.invalid:443', grpc.ssl_channel_credentials())
        with socket.socket() as connection:
            with pytest.raises(RuntimeError, match='non-emulator'):
                connection.connect(('127.0.0.1', 9))
        environment.redis.set('synthetic-replay', 'local')
        assert environment.redis.get('synthetic-replay') == 'local'
        blob = environment.storage.bucket('replay-staged').blob('synthetic/test.bin')
        blob.upload_from_file(BytesIO(b'synthetic'), if_generation_match=0)
        blob.reload()
        assert blob.generation > 0 and blob.download_as_bytes() == b'synthetic'
        with pytest.raises(PreconditionFailed):
            blob.upload_from_file(BytesIO(b'replacement'), if_generation_match=0)
        root = environment.storage.root
    assert not root.exists()
    assert dict(os.environ) == previous
