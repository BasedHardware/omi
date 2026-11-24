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

    items = asyncio.run(run_cases(sorted(p for p in FIXTURES.iterdir() if p.name.startswith('admission-'))))
    write_report(items, tmp_path)
    print('\n' + table(items))
    by_id = {item['item']: item for item in items}
    # The contention case is a load-sensitive stress shape: whether retries
    # exhaust depends on scheduling, so CI accepts exactly two outcomes for it.
    stress = 'admission-drain-contention'
    assert all(item['expectation_met'] for item in items if item['item'] != stress), table(items)
    item = by_id['admission-not-durable']
    assert item['verdict'] == 'FAIL' and item['furthest_stage'] == 'admission'
    assert 'ValueError' in item['stop_reason']
    assert 'retained_capture_not_durable' in by_id['admission-not-durable']['stop_reason']
    control = by_id['admission-control']
    assert control['verdict'] == 'PASS'
    assert control['stages'][0]['details']['verified_recordings'] == 1
    assert by_id['admission-regional-only']['verdict'] == 'PASS'
    assert 'validate_record_tail' in by_id['admission-partial-inventory']['stop_reason']
    assert 'TimeoutError' in by_id['admission-archive-listing-failure']['stop_reason']
    contention = by_id[stress]
    stage = contention['stages'][0]
    if contention['verdict'] == 'FAIL':
        assert 'FirestoreContentionExhausted' in contention['stop_reason'], table(items)
        assert stage['operation'] == 'admit'
        assert stage['transaction'] == 'database.batch_pipeline_intake.admit.commit'
    else:
        assert contention['verdict'] == 'PASS', table(items)
        assert stage['details']['pending'] == 0 and stage['details']['admitted'] == stage['details']['rows']


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


@pytest.mark.parametrize('missing', ['artifact', 'blob'])
def test_missing_staging_for_one_of_two_recordings_fails(monkeypatch, missing):
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    from dataclasses import replace
    from urllib.parse import urlsplit
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.stages import admission
    from testing.replay_harness.report import item_report
    from database.batch_pipeline_staging import artifact_id

    original = admission.verify_recordings

    def remove_one_staged_recording(store, storage, recordings):
        assert len(recordings) == 2
        second = recordings[1]
        job = store.client.collection(f'{store.namespace}_jobs').document(second.segment_id).get().to_dict()
        uri = job['audio_uri']
        if missing == 'artifact':
            store.client.collection(f'{store.namespace}_artifacts').document(
                artifact_id(second.segment_id, uri)
            ).delete()
        else:
            parsed = urlsplit(uri)
            storage.bucket(parsed.netloc).blob(parsed.path.lstrip('/'), generation=int(parsed.fragment)).delete()
        # The first recording is still completely staged; it cannot mask the second.
        original(store, storage, recordings[:1])
        return original(store, storage, recordings)

    monkeypatch.setattr(admission, 'verify_recordings', remove_one_staged_recording)
    case = replace(
        load_case(FIXTURES / 'admission-control'),
        corpus={'admission': {'rows': 2, 'drainers': 1, 'durable': True, 'distinct_owners': True}},
    )

    async def run():
        with replay_environment() as environment:
            result = await admission.AdmissionDriver().run(case, environment)
            return item_report(case.manifest, [result])

    report = asyncio.run(run())
    assert report['verdict'] == 'FAIL' and not report['expectation_met']
    assert report['stages'][0]['operation'] == 'verify'
    assert report['stages'][0]['details']['admitted'] == 2
    assert ('missing_artifact' if missing == 'artifact' else 'NotFound') in report['stop_reason']


def test_privacy_block_is_captured_at_real_admission_boundary():
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    from dataclasses import replace
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.stages.admission import AdmissionDriver

    case = replace(
        load_case(FIXTURES / 'admission-control'),
        corpus={'admission': {'rows': 1, 'durable': True, 'privacy_blocked': True}},
    )

    async def run():
        with replay_environment() as environment:
            return await AdmissionDriver().run(case, environment)

    result = asyncio.run(run())
    assert result.exception_type == 'BatchPrivacyBlocked'
    # Since #24587 the drain's lease claim meets the privacy fence before
    # admission does; either real boundary must surface the block.
    assert result.operation in ('admit', 'read_pending') and 'BatchPrivacyBlocked' in result.reason
    assert result.details['pending'] == 1
