"""Mobile local-preview lane: admission, deferred cloud stream, client events."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.cloud_live_stt import local_preview_batch_enabled
from models.message_event import MessageServiceStatusEvent
from routers.listen import local_preview as local_preview_module
from routers.listen import receiver as receiver_module
from routers.listen import runtime as runtime_module
from routers.listen.local_preview import REASONS, admit_local_preview, local_preview_reason, renew_local_preview
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from utils.metrics import OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL

KILL = 'LOCAL_PREVIEW_BATCH_ENABLED'


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(KILL, raising=False)
    monkeypatch.delenv('CLOUD_LIVE_STT_MODE', raising=False)
    monkeypatch.setattr(local_preview_module, 'local_preview_batch_owned', lambda uid: uid == 'batch-owner')


def counter(metric, **labels):
    return sum(
        sample.value
        for family in metric.collect()
        for sample in family.samples
        if sample.name.endswith('_total') and all(sample.labels.get(k) == v for k, v in labels.items())
    )


def make_host(**overrides):
    request = SimpleNamespace(
        uid=overrides.pop('uid', 'batch-owner'),
        local_preview=overrides.pop('local_preview', True),
        onboarding_mode=overrides.pop('onboarding_mode', False),
        source=overrides.pop('source', 'omi'),
        sample_rate=16000,
    )
    values = dict(
        request=request,
        use_custom_stt=False,
        is_multi_channel=False,
        private_cloud_sync_enabled=True,
        client_device_context=SimpleNamespace(platform='ios'),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ('raw', 'enabled'),
    [(None, True), ('', True), ('true', True), ('anything', True), ('false', False), (' OFF ', False), ('0', False)],
)
def test_kill_switch_is_on_unless_set_off(raw, enabled):
    env = {} if raw is None else {KILL: raw}
    assert local_preview_batch_enabled(env=env) is enabled


@pytest.mark.parametrize(
    ('overrides', 'reason'),
    [
        ({}, 'admitted'),
        ({'local_preview': False}, 'not_requested'),
        ({'use_custom_stt': True}, 'custom_stt'),
        ({'is_multi_channel': True}, 'multi_channel'),
        ({'onboarding_mode': True}, 'onboarding'),
        ({'source': 'phone_call'}, 'phone_call'),
        ({'private_cloud_sync_enabled': False}, 'private_sync_off'),
        ({'uid': 'stream-owner'}, 'not_batch_lane'),
    ],
)
def test_admission_reasons(overrides, reason):
    assert local_preview_reason(make_host(**overrides)) == reason
    assert reason in REASONS


def test_kill_switch_refuses_before_policy(monkeypatch):
    monkeypatch.setenv(KILL, 'false')
    monkeypatch.setattr(
        local_preview_module, 'local_preview_batch_owned', Mock(side_effect=AssertionError('policy read'))
    )
    assert local_preview_reason(make_host()) == 'kill_switch'


def test_policy_error_keeps_streaming(monkeypatch):
    monkeypatch.setattr(local_preview_module, 'local_preview_batch_owned', Mock(side_effect=RuntimeError('cache')))
    host = make_host()
    assert admit_local_preview(host) is False
    assert host.local_preview_batch is False


def test_admission_pins_once_and_counts(monkeypatch):
    host = make_host()
    before = counter(OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL, outcome='admitted', client_platform='ios')
    assert admit_local_preview(host) is True
    # A later policy change cannot flip a pinned session; only the kill switch revokes.
    monkeypatch.setattr(local_preview_module, 'local_preview_batch_owned', lambda uid: False)
    assert admit_local_preview(host) is True
    assert counter(OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL, outcome='admitted', client_platform='ios') == before + 1
    assert renew_local_preview(host) is True
    monkeypatch.setenv(KILL, 'false')
    assert renew_local_preview(host) is False
    assert host.local_preview_batch is False


def make_receiver(host):
    host.state = SimpleNamespace(realtime_demand=SimpleNamespace(totals=dict))
    host.task_supervisor = SimpleNamespace(create_lifetime_task=Mock())
    fake = SimpleNamespace(host=host, cloud_live_suppressed=False, _telemetry_platform=lambda: 'ios')
    return fake


@pytest.mark.asyncio
async def test_local_preview_session_defers_then_opens_on_socket_audio(monkeypatch):
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', Mock())
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(side_effect=AssertionError('demand attached')))
    fake = make_receiver(make_host())

    assert await ListenReceiver._initialize_stt(fake)
    assert fake.cloud_live_suppressed is True
    assert fake.host.local_preview_batch is True
    assert fake._cloud_live_deferred_by == 'local_preview'
    # A deferred session never hands over between lanes.
    monkeypatch.setattr(receiver_module, 'switch_live_demand', AsyncMock(side_effect=AssertionError('switched')))
    assert await ListenReceiver._switch_live_demand(fake, 'vendor') is False

    # Audio reaching the socket (the journal refused it) opens today's stream.
    opened = []

    async def initialize_stt():
        assert fake._cloud_live_opening is True
        opened.append(True)
        fake.live_demand = SimpleNamespace(run=Mock(return_value='run'))
        fake.stt_socket = object()
        return True

    fake.initialize_stt = initialize_stt
    fake.stt_socket = None
    fake.stt_sockets_multi = []
    fake.ensure_live_demand_routing = lambda: ListenReceiver.ensure_live_demand_routing(fake)
    fake.note_deferred_stream_opened = lambda: ListenReceiver.note_deferred_stream_opened(fake)
    before = counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview')
    assert await ListenReceiver._open_deferred_stream(fake) is True
    assert opened == [True]
    assert fake.cloud_live_suppressed is False
    fake.host.task_supervisor.create_lifetime_task.assert_called_once_with('run', name='live_demand_routing')
    assert counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview') == before + 1
    # Idempotent: a later cap recovery or re-init never starts a second routing task.
    assert fake.ensure_live_demand_routing() is None
    fake.host.task_supervisor.create_lifetime_task.assert_called_once()


@pytest.mark.asyncio
async def test_cap_paused_deferred_open_waits_for_cap_recovery(monkeypatch):
    fake = make_receiver(make_host())
    fake.stt_socket = None
    fake.stt_sockets_multi = []
    fake._cloud_live_deferred_by = 'local_preview'
    fake.live_demand = None
    fake.ensure_live_demand_routing = lambda: ListenReceiver.ensure_live_demand_routing(fake)
    fake.note_deferred_stream_opened = lambda: ListenReceiver.note_deferred_stream_opened(fake)

    async def initialize_stt():
        fake.cap_paused = True  # Cap admission refused: no socket, audio goes to LiveHeldAudio.
        return True

    fake.initialize_stt = initialize_stt
    before = counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview')
    assert await ListenReceiver._open_deferred_stream(fake) is True
    assert counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview') == before
    fake.host.task_supervisor.create_lifetime_task.assert_not_called()
    # Cap recovers: initialization attaches demand; the open counts once and routing starts once.
    fake.live_demand = SimpleNamespace(run=Mock(return_value='run'))
    for _ in range(2):
        ListenReceiver.note_deferred_stream_opened(fake)
        fake.ensure_live_demand_routing()
    assert counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview') == before + 1
    fake.host.task_supervisor.create_lifetime_task.assert_called_once_with('run', name='live_demand_routing')


@pytest.mark.asyncio
async def test_flush_opens_deferred_stream_only_with_audio(monkeypatch):
    legacy = AsyncMock()
    monkeypatch.setattr(receiver_module.legacy_recovery, 'flush_stt_buffer', legacy)
    fake = SimpleNamespace(
        cloud_live_suppressed=True,
        _open_deferred_stream=AsyncMock(side_effect=AssertionError('opened without audio')),
    )
    # Empty buffer: nothing to transcribe, nothing opens.
    await ListenReceiver._flush_stt_buffer(fake, bytearray())
    legacy.assert_awaited_once()

    # A failed open stops this flush; the session's terminal path already ran.
    fake._open_deferred_stream = AsyncMock(return_value=False)
    legacy.reset_mock()
    await ListenReceiver._flush_stt_buffer(fake, bytearray(b'\x00\x01'))
    fake._open_deferred_stream.assert_awaited_once()
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_off_mode_defers_and_multi_channel_never_does(monkeypatch):
    monkeypatch.setenv('CLOUD_LIVE_STT_MODE', 'off')
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', Mock())
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(side_effect=AssertionError('demand attached')))
    fake = make_receiver(make_host(local_preview=False))
    assert await ListenReceiver._initialize_stt(fake)
    assert fake.cloud_live_suppressed is True
    assert fake._cloud_live_deferred_by == 'off'

    multi = make_receiver(make_host(local_preview=False, is_multi_channel=True))
    multi.cap_admission = None
    multi.channel_configs = []
    multi.host.use_custom_stt = True  # Return before provider dialing; only the deferral decision matters.
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(return_value=None))
    assert await ListenReceiver._initialize_stt(multi)
    assert multi.cloud_live_suppressed is False


@pytest.mark.asyncio
async def test_not_batch_lane_keeps_todays_stream(monkeypatch):
    selected = Mock()
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', selected)
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(return_value=None))
    fake = make_receiver(make_host(uid='stream-owner', use_custom_stt=True))
    fake.cap_admission = None
    assert await ListenReceiver._initialize_stt(fake)
    assert fake.cloud_live_suppressed is False
    assert fake.host.local_preview_batch is False
    selected.assert_called_with(fake.host)


@pytest.mark.asyncio
async def test_local_preview_grants_mobile_batch_without_inventory_reads(monkeypatch):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='batch-owner')
    runtime.local_preview_batch = True
    runtime.persistence = SimpleNamespace(call=AsyncMock(side_effect=AssertionError('inventory read')))
    monkeypatch.setattr(runtime_module, 'warm_rollout_cohorts', AsyncMock(side_effect=AssertionError('cohort')))
    await runtime.refresh_mobile_batch_admission()
    assert runtime.mobile_standard_batch is True

    # Kill switch: the next renewal revokes and falls back to the ordinary admission (off here).
    monkeypatch.setenv(KILL, 'false')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'false')
    runtime.private_cloud_sync_enabled = True
    runtime.use_custom_stt = False
    await runtime.refresh_mobile_batch_admission()
    assert runtime.local_preview_batch is False
    assert runtime.mobile_standard_batch is False


def test_ready_event_for_deferred_session_names_no_provider():
    runtime = object.__new__(ListenSessionRuntime)
    runtime.use_custom_stt = False
    runtime.mobile_standard_batch = True
    runtime.local_preview_batch = True
    runtime.receiver = SimpleNamespace(cloud_live_suppressed=True)
    payload = runtime._ready_event().to_json()
    assert payload == {
        'type': 'service_status',
        'status': 'ready',
        'mobile_standard_batch': True,
        'local_preview': True,
    }


def test_local_preview_field_is_absent_for_older_clients():
    payload = MessageServiceStatusEvent(status='mobile_batch_admission', mobile_standard_batch=False).to_json()
    assert 'local_preview' not in payload
