"""HTTP collision names retain their pre-Q12 ledger owner across rolls and repair."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import UploadFile
import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_store import FirestoreStore
from routers import sync as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_capture_time_skew import client  # noqa: F401
from utils.batch_pipeline import artifact_reupload, intake
from utils.sync.content_id import compute_sync_content_id
from utils.sync.empty_upload import prepare_sync_uploads
from utils.sync.pipeline import _retrieve_file_paths_v2
from utils.sync.stage import collection_name
from utils.transcription_allowance import TranscriptionAllowance

UID = 'synthetic-uid'
SECRET = 'synthetic-collision-rollout'
AUDIO = b'\x01\0\0\0\x42'


def _names():
    stamp = int(datetime.now(timezone.utc).timestamp()) - 10
    stem = 'audio_omi_opus_16000_1_fs160'
    return f'{stem}_{stamp}_u0.bin', f'{stem}_u0_{stamp}.bin'


def _old_identity(legacy_name):
    # Frozen wire identity: the old code hashed the renamed basename and bytes.
    payload = f'{UID}\n{legacy_name}:{hashlib.sha256(AUDIO).hexdigest()}'
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def existing_upload(client, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', SECRET)
    raw, legacy = _names()
    content_id = _old_identity(legacy)
    key = ('users', UID, collection_name('sync_content_ledger'), content_id)
    firestore = StrictFirestore(
        {key: {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_original', 'status': 'processing'}}
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=firestore)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_a, **_k: store)
    monkeypatch.setattr(intake, 'shadow_from_env', lambda value: value)
    monkeypatch.setattr(router, 'compute_sync_content_id', compute_sync_content_id)
    monkeypatch.setattr(router, 'accept_batch_upload', intake.accept_upload)
    policy = BatchUnitPolicy(batch_enabled=True)
    monkeypatch.setattr(router, 'resolve_batch_policy', lambda *_a: policy)
    monkeypatch.setattr(router, 'ramp_admission_policy', lambda *_a, **_k: policy)
    monkeypatch.setattr(
        router,
        'resolve_transcription_allowance',
        lambda *_a: TranscriptionAllowance('managed', None, 'usage_budget_available'),
    )

    async def batch_route(**_kwargs):
        return router.RecordUploadRoute.BATCH

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    status = {
        'job_id': 'bp_original',
        'status': 'processing',
        'total_files': 1,
        'total_segments': 1,
        'poll_after_ms': 5000,
        'lane': 'fresh',
    }
    monkeypatch.setattr(intake, 'durable_status', lambda *_a: dict(status))
    monkeypatch.setattr(router, 'admit_sync_job_poll', lambda *_a: True)
    decode = Mock(side_effect=AssertionError('existing content must not create a new decode/job'))
    artifacts = Mock(side_effect=AssertionError('ordinary retry must not stage new GPU input'))
    monkeypatch.setattr(intake, 'decode_units', decode)
    monkeypatch.setattr(intake, 'artifacts_for', artifacts)
    return SimpleNamespace(
        client=client,
        raw=raw,
        legacy=legacy,
        content_id=content_id,
        key=key,
        firestore=firestore,
        store=store,
        decode=decode,
        artifacts=artifacts,
    )


def _post(existing, repair=False):
    query = '?repair_job_id=bp_original' if repair else ''
    return existing.client.post('/v2/sync-local-files' + query, files=[('files', (existing.raw, AUDIO))])


@pytest.mark.parametrize('switch', ['true', 'false'])
def test_old_identity_retry_and_repoll_keep_the_existing_job(existing_upload, monkeypatch, switch):
    monkeypatch.setenv('SYNC_COLLISION_SUFFIX_ENABLED', switch)
    existing = existing_upload
    before = deepcopy(existing.firestore.rows)
    for _ in range(2):
        response = _post(existing)
        assert response.status_code == 202, response.text
        assert response.json()['job_id'] == 'bp_original'
        poll = existing.client.get('/v2/sync-local-files/bp_original')
        assert poll.status_code == 200 and poll.json()['job_id'] == 'bp_original'
    assert existing.firestore.rows == before
    existing.decode.assert_not_called()
    existing.artifacts.assert_not_called()
    router.create_sync_job.assert_not_called()


@pytest.mark.parametrize('switch', ['true', 'false'])
def test_old_identity_artifact_repair_keeps_owner_and_stages_once(existing_upload, monkeypatch, switch):
    monkeypatch.setenv('SYNC_COLLISION_SUFFIX_ENABLED', switch)
    existing = existing_upload
    existing.firestore.rows[existing.key]['artifact_missing_units'] = ['missing']
    stage = Mock()
    monkeypatch.setattr(intake, 'artifacts_for', lambda *_a: SimpleNamespace(stage_audio=stage))

    async def restore(store, uid, content_id, paths, *, artifacts, **_binding):
        assert store is existing.store and uid == UID and content_id == existing.content_id
        assert [Path(path).name for path in paths] == [existing.legacy]
        assert [Path(path).read_bytes() for path in paths] == [AUDIO]
        artifacts.stage_audio('original-missing-unit')

        def settled(tx):
            ledger = tx.get('content', f'{uid}/{content_id}')
            ledger.pop('artifact_missing_units')
            tx.put('content', f'{uid}/{content_id}', ledger)

        store.run(settled)

    # Real artifact restoration and its CAS/no-restaging behavior are exercised
    # by test_batch_artifact_missing_reupload; this isolates the HTTP identity seam.
    monkeypatch.setattr(artifact_reupload, 'restore_upload', restore)
    for _ in range(2):
        response = _post(existing, repair=True)
        assert response.status_code == 202, response.text
        assert response.json()['job_id'] == 'bp_original'
    stage.assert_called_once_with('original-missing-unit')
    assert existing.firestore.rows == {
        existing.key: {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_original', 'status': 'processing'}
    }
    existing.decode.assert_not_called()
    router.create_sync_job.assert_not_called()


def test_new_acceptance_and_old_revision_use_identical_ledger_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', SECRET)
    raw, legacy = _names()
    ids = []
    for switch, job in [('true', 'new'), ('false', 'rollback')]:
        monkeypatch.setenv('SYNC_COLLISION_SUFFIX_ENABLED', switch)
        uploads = prepare_sync_uploads([UploadFile(filename=raw, file=BytesIO(AUDIO))], UID)
        paths = _retrieve_file_paths_v2(uploads, UID, job)
        assert [Path(path).name for path in paths] == [legacy]
        ids.append(compute_sync_content_id(UID, paths))
    # This is the basename an actual pre-Q12 revision stages. The hash function
    # is unchanged, so no alternate lookup or new ledger alias is required.
    old_path = tmp_path / 'old-revision' / legacy
    old_path.parent.mkdir()
    old_path.write_bytes(AUDIO)
    assert ids == [compute_sync_content_id(UID, [str(old_path)])] * 2 == [_old_identity(legacy)] * 2


@pytest.mark.parametrize('switch', ['true', 'false'])
def test_colliding_pair_remains_two_distinct_uploads(tmp_path, monkeypatch, switch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', SECRET)
    monkeypatch.setenv('SYNC_COLLISION_SUFFIX_ENABLED', switch)
    raw, legacy = _names()
    plain = raw.replace('_u0.bin', '.bin')
    uploads = prepare_sync_uploads([UploadFile(filename=name, file=BytesIO(AUDIO)) for name in (plain, raw)], UID)
    paths = _retrieve_file_paths_v2(uploads, UID, 'pair')
    assert [Path(path).name for path in paths] == [plain, legacy]
    assert [Path(path).read_bytes() for path in paths] == [AUDIO, AUDIO]
    assert len({compute_sync_content_id(UID, [path]) for path in paths}) == 2


@pytest.mark.parametrize('switch', ['true', 'false'])
def test_unrenamable_alias_pair_keeps_legacy_refusal(client, monkeypatch, switch):
    monkeypatch.setenv('SYNC_COLLISION_SUFFIX_ENABLED', switch)
    raw, legacy = _names()
    response = client.post('/v2/sync-local-files', files=[('files', (name, AUDIO)) for name in (raw, legacy)])
    assert response.status_code == 400
    assert response.json()['code'] == 'invalid_capture_time'
