import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from starlette.datastructures import UploadFile
from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path

import pytest

from utils.sync.mobile_standard_batch import mobile_standard_batch_enabled
from utils.other import storage
from routers.listen import runtime as runtime_module
from routers.listen.runtime import ListenSessionRuntime


@pytest.mark.parametrize(
    'enabled,percent,uids,expected',
    [
        ('', '100', 'owner', False),
        ('false', '100', 'owner', False),
        ('true', '0', '', False),
        ('true', '0', 'owner', True),
        ('true', 'bad', '', False),
        ('true', '101', '', False),
        ('true', '100', '', True),
    ],
)
def test_rollout_defaults_and_allowlist(monkeypatch, enabled, percent, uids, expected):
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', enabled)
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_PERCENT', percent)
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', uids)
    assert mobile_standard_batch_enabled('owner') is expected
    assert not mobile_standard_batch_enabled('')


def test_cohort_is_stable_and_bounded(monkeypatch):
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_PERCENT', '5')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', '')
    first = [mobile_standard_batch_enabled(f'u{i}') for i in range(10000)]
    assert first == [mobile_standard_batch_enabled(f'u{i}') for i in range(10000)]
    assert 400 < sum(first) < 600


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'apps,webhook,custom,private,allowed',
    [
        ([], 0, False, True, True),
        (['transcript-app'], 0, False, True, False),
        ([], 5, False, True, False),
        ([], 0, True, True, False),
        ([], 0, False, False, False),
    ],
)
async def test_consumer_admission(monkeypatch, apps, webhook, custom, private, allowed):
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', 'owner')
    monkeypatch.setattr(runtime_module.user_db, 'get_user_private_cloud_sync_enabled', lambda uid: private)
    monkeypatch.setattr(runtime_module, 'get_enabled_apps', lambda uid: apps)
    monkeypatch.setattr(runtime_module, 'get_audio_bytes_webhook_seconds', lambda uid: webhook)
    monkeypatch.setattr(runtime_module, 'user_webhook_status_db', lambda uid, kind: False)
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='owner')
    runtime.private_cloud_sync_enabled = private
    runtime.use_custom_stt = custom

    async def call(fn, *args):
        return fn(*args)

    runtime.persistence = SimpleNamespace(call=call)
    await runtime.refresh_mobile_batch_admission()
    assert runtime.mobile_standard_batch is allowed


@pytest.mark.asyncio
async def test_developer_transcript_webhook_keeps_live_stream(monkeypatch):
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', 'owner')
    monkeypatch.setattr(runtime_module.user_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(runtime_module, 'get_enabled_apps', lambda uid: [])
    monkeypatch.setattr(runtime_module, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(runtime_module, 'user_webhook_status_db', lambda uid, kind: True)
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='owner')
    runtime.private_cloud_sync_enabled = True
    runtime.use_custom_stt = False

    async def call(fn, *args):
        return fn(*args)

    runtime.persistence = SimpleNamespace(call=call)
    await runtime.refresh_mobile_batch_admission()
    assert not runtime.mobile_standard_batch


@pytest.mark.asyncio
async def test_inventory_failure_is_live_only_and_kill_switch_is_immediate(monkeypatch):
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', 'owner')
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='owner')
    runtime.private_cloud_sync_enabled = True
    runtime.use_custom_stt = False
    runtime.persistence = SimpleNamespace(call=AsyncMock(side_effect=RuntimeError('offline')))
    await runtime.refresh_mobile_batch_admission()
    assert not runtime.mobile_standard_batch
    runtime.mobile_standard_batch = True
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'false')
    await runtime.refresh_mobile_batch_admission()
    assert not runtime.mobile_standard_batch


class Blob:
    def __init__(self, name):
        self.name = name
        self.data = None
        self.metadata = None

    def upload_from_string(self, data, **kwargs):
        self.data = data


class Bucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return self.blobs.setdefault(name, Blob(name))


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_archive_original_opus_and_silence_before_decode(monkeypatch, tmp_path, protection):
    # WAL framing containing an unchanged speech frame and an unchanged silent frame.
    raw = b'\x03\x00\x00\x00abc\x03\x00\x00\x00\xf8\xff\xfe'
    audio = tmp_path / 'audio_omimobilebatch001_opus_16000_1_fs160_1000.bin'
    audio.write_bytes(raw)
    bucket = Bucket()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: protection)
    monkeypatch.setattr(storage.encryption, 'encrypt_audio_chunk', lambda data, uid: b'encrypted:' + data)
    storage.archive_mobile_batch_raw_files('owner', [str(audio)])
    storage.archive_mobile_batch_raw_files('owner', [str(audio)])
    assert len(bucket.blobs) == 1
    blob = next(iter(bucket.blobs.values()))
    assert blob.data == (b'encrypted:' + raw if protection == 'enhanced' else raw)
    assert blob.metadata['sha256'] == hashlib.sha256(raw).hexdigest()
    assert blob.name.startswith('raw-mobile-batch/owner/')


def test_legacy_upload_does_not_gain_archive_io(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, '_get_storage_client', lambda: pytest.fail('legacy upload must remain unchanged'))
    storage.archive_mobile_batch_raw_files('owner', [str(tmp_path / 'audio_omi_opus_16000_1_fs160_1000.bin')])


def test_archive_failure_propagates_for_retry(monkeypatch, tmp_path):
    audio = tmp_path / 'audio_omimobilebatch001_opus_16000_1_fs160_1000.bin'
    audio.write_bytes(b'original')

    class Broken(Blob):
        def upload_from_string(self, *args, **kwargs):
            raise OSError('storage unavailable')

    monkeypatch.setattr(
        storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: SimpleNamespace(blob=Broken))
    )
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    with pytest.raises(OSError):
        storage.archive_mobile_batch_raw_files('owner', [str(audio)])


@pytest.mark.asyncio
@pytest.mark.parametrize('archive_fails', [False, True])
async def test_upload_acceptance_requires_archive_before_receipt_or_dispatch(archive_fails):
    module, saved, jobs, bytes_io, _, _ = _load_sync_router_for_fast_path()
    try:
        calls = []

        def archive(uid, paths):
            calls.append(('archive', uid, list(paths)))
            if archive_fails:
                raise OSError('archive unavailable')

        module.archive_mobile_batch_raw_files = archive
        module.start_background_task = MagicMock()
        uploads = [
            UploadFile(filename='audio_omimobilebatch001_opus_16000_1_fs160_1000.bin', file=bytes_io(b'original'))
        ]
        if archive_fails:
            with pytest.raises(module.HTTPException) as rejected:
                await module.sync_local_files_v2(files=uploads, uid='test-uid')
            assert rejected.value.status_code == 500
            response = None
        else:
            response = await module.sync_local_files_v2(files=uploads, uid='test-uid')
        assert calls and calls[0][0] == 'archive'
        if archive_fails:
            module.enqueue_sync_job.assert_not_called()
            module.start_background_task.assert_not_called()
            jobs.mark_job_completed.assert_not_called()
        else:
            assert response.status_code == 202
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
