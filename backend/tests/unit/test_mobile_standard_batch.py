import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from starlette.datastructures import UploadFile
from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from config.policy import BatchUnitPolicy
from config.policy.ramp import owner_load
from database import batch_ramp
from utils.batch_pipeline import intake as batch_intake

import pytest

from utils.audio_timeline import CaptureTimeline
from utils.sync.mobile_standard_batch import mobile_standard_batch_enabled
from utils.other import storage
from routers.listen import runtime as runtime_module
from routers.listen.runtime import ListenSessionRuntime
from utils import rollout_cohorts


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
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
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
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    with pytest.raises(OSError):
        storage.archive_mobile_batch_raw_files('owner', [str(audio)])


@pytest.fixture
def mobile_sync_router():
    # Router/module loading and dependency stubs are fixture setup, not upload
    # behavior. Keep their cleanup paired here, including on assertion failure.
    module, saved, jobs, bytes_io, _, _ = _load_sync_router_for_fast_path()
    try:
        yield module, jobs, bytes_io
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
@pytest.mark.parametrize('start,end', [(None, None), (20, 10), (0, float('nan'))])
async def test_partial_ramp_unknown_incoming_audio_keeps_real_upload_on_legacy(
    mobile_sync_router, monkeypatch, start, end
):
    module, jobs, bytes_io = mobile_sync_router
    monkeypatch.setenv('BATCH_PIPELINE_RAMP_EXCLUDE_HEAVY_OWNERS', 'on')
    candidate = BatchUnitPolicy(batch_enabled=True, batch_percent=5)
    module.resolve_batch_policy = MagicMock(return_value=candidate)
    module.registered_record_response = AsyncMock(return_value=None)
    incoming = []

    def classify(uid, policy, *, incoming_audio_seconds, **kwargs):
        incoming.append(incoming_audio_seconds)
        return batch_ramp.ramp_admission_policy(uid, policy, incoming_audio_seconds=incoming_audio_seconds)

    module.ramp_admission_policy = classify
    monkeypatch.setattr(
        batch_ramp,
        'read_owner_load',
        lambda uid, **kwargs: owner_load([], [], 100000, incoming_audio_seconds=kwargs['incoming_audio_seconds']),
    )
    store = MemoryStore()
    monkeypatch.setattr(batch_intake, 'FirestoreStore', lambda *args: store)
    monkeypatch.setattr(batch_intake, 'current_stage', lambda: 'dev')
    module.accept_batch_upload = AsyncMock(wraps=batch_intake.accept_upload)
    response = await module.sync_local_files_v2(
        files=[UploadFile(filename='synthetic.opus', file=bytes_io(b'synthetic'))],
        uid='test-uid',
        audio_start_seconds=start,
        audio_end_seconds=end,
    )
    assert response.status_code == 202
    assert incoming == [None]
    assert not module.create_sync_job.call_args.kwargs['policy'].batch_enabled
    assert not module.accept_batch_upload.call_args.kwargs['policy'].batch_enabled
    assert not store.rows


@pytest.mark.asyncio
@pytest.mark.parametrize('archive_fails', [False, True])
async def test_upload_acceptance_requires_archive_before_receipt_or_dispatch(mobile_sync_router, archive_fails):
    module, jobs, bytes_io = mobile_sync_router
    calls = []

    def archive(uid, paths, metadata=None):
        calls.append(('archive', uid, list(paths)))
        if archive_fails:
            raise OSError('archive unavailable')

    module.archive_mobile_batch_raw_files = archive
    module.start_background_task = MagicMock()
    uploads = [UploadFile(filename='audio_omimobilebatch001_opus_16000_1_fs160_1000.bin', file=bytes_io(b'original'))]
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


def test_visibility_resume_keeps_the_existing_live_capture_wall_clock_gap():
    timeline = CaptureTimeline(sample_rate=16000)
    first, _, _ = timeline.accept(bytes(320), arrival_wall=1000.01, arrival_monotonic=1.01)
    resumed, _, anchored = timeline.accept(bytes(320), arrival_wall=1060.01, arrival_monotonic=61.01)
    assert anchored
    assert timeline.wall(first) == pytest.approx(1000.0)
    assert timeline.wall(resumed) == pytest.approx(1060.0)


@pytest.mark.asyncio
async def test_mobile_lease_preserves_shared_live_demand_and_visibility_tracking(monkeypatch):
    from routers.listen import receiver as receiver_module
    from routers.listen.contracts import ListenSessionState
    from routers.listen.demand_routing import LiveDemandRouting
    from routers.listen.receiver import ListenReceiver

    monkeypatch.setattr(
        receiver_module,
        'resolve_ondemand_config',
        lambda: SimpleNamespace(gate_enabled=False),
    )
    receiver = object.__new__(ListenReceiver)

    def close_unstarted_publish(coro, **kwargs):
        # The real demand observer runs; external presence publishing is outside
        # this control-message contract and must stay hermetic.
        coro.close()
        return SimpleNamespace(done=lambda: True)

    receiver.host = SimpleNamespace(
        onboarding_handler=None,
        use_custom_stt=False,
        state=ListenSessionState(),
        refresh_mobile_batch_admission=AsyncMock(),
        asend_event=AsyncMock(),
        mobile_standard_batch=True,
        spawn=close_unstarted_publish,
    )
    receiver.live_demand = LiveDemandRouting(receiver, eligible=True)
    for visible in (False, True):
        await receiver._handle_text(
            json.dumps(
                {
                    'type': 'client_state',
                    'foreground': True,
                    'transcript_visible': visible,
                    'mobile_batch_capability_v1': True,
                }
            )
        )
        assert receiver.live_demand.policy.state == ('visible' if visible else 'hidden')
        event = receiver.host.asend_event.call_args.args[0]
        assert event.status == 'mobile_batch_admission'
        assert event.mobile_standard_batch is True
    assert receiver.host.state.realtime_demand.reports == 2
    assert receiver.host.refresh_mobile_batch_admission.await_count == 2


@pytest.mark.asyncio
async def test_mobile_renewal_awaits_expired_membership_and_warm_packets_cost_zero_reads(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', 'owner')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_PERCENT', '0')
    monkeypatch.setattr(runtime_module.user_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(runtime_module, 'get_enabled_apps', lambda uid: [])
    monkeypatch.setattr(runtime_module, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(runtime_module, 'user_webhook_status_db', lambda uid, kind: False)
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='owner')
    runtime.private_cloud_sync_enabled = True
    runtime.use_custom_stt = False

    async def call(fn, *args):
        return fn(*args)

    runtime.persistence = SimpleNamespace(call=call)
    release = threading.Event()
    reads = []
    member = [True]

    def read(uid):
        reads.append(uid)
        assert release.wait(1)
        return {'prod': {'mobile-standard-batch': member[0]}}

    rollout_cohorts.configure_rollout_runtime()
    cache = rollout_cohorts._TTLReads(read)
    monkeypatch.setattr(rollout_cohorts, '_cache', cache)
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(rollout_cohorts, '_background_submitter', pool.submit)
        for allowed in [True, False]:
            member[0] = allowed
            release.clear()

            async def unblock():
                await asyncio.sleep(0)
                release.set()

            pulse = asyncio.create_task(unblock())
            try:
                await runtime.refresh_mobile_batch_admission()
            finally:
                release.set()
                await pulse
            assert runtime.mobile_standard_batch is allowed
            for _ in range(100):
                await runtime.refresh_mobile_batch_admission()
                assert runtime.mobile_standard_batch is allowed
            assert len(reads) == (1 if allowed else 2)
            cache.entries['owner'].expires = 0
        monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'false')
        await runtime.refresh_mobile_batch_admission()
        assert not runtime.mobile_standard_batch and len(reads) == 2
