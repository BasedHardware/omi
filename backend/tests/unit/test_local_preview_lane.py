"""Mobile local-preview lane: admission, deferred cloud stream, client events."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.cloud_live_stt import local_preview_batch_enabled
from models.message_event import MessageServiceStatusEvent
from routers.listen import local_preview as local_preview_module
from routers.listen import receiver as receiver_module
from routers.listen import runtime as runtime_module
from routers.listen.local_preview import (
    OMI_LISTEN_DEFERRED_STREAM_OPEN_SECONDS,
    OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL,
    REASONS,
    admit_local_preview,
    local_preview_reason,
    note_deferred_stream_closed,
    renew_local_preview,
)
from routers.listen.contracts import ListenRequest
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from utils.metrics import (
    OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL,
    OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL,
)

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
    request = ListenRequest(
        websocket=None,
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


@pytest.mark.parametrize('language', ['multi', 'en'])
@pytest.mark.parametrize(
    ('declared', 'enabled', 'reason'),
    [(True, True, 'admitted'), (True, False, 'kill_switch'), (False, True, 'not_requested')],
)
@pytest.mark.asyncio
async def test_server_batch_only_publishes_local_preview_admission(monkeypatch, language, declared, enabled, reason):
    monkeypatch.setenv(KILL, str(enabled).lower())
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'false')
    monkeypatch.setattr(receiver_module, 'server_batch_suppresses_live', lambda host: True)
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', Mock(side_effect=AssertionError('provider selected')))
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(side_effect=AssertionError('demand attached')))
    monkeypatch.setattr(receiver_module, 'resolve_ondemand_config', lambda: SimpleNamespace(gate_enabled=False))
    host = make_host(local_preview=declared)
    host.request = replace(host.request, language=language)
    host.persistence = SimpleNamespace(call=AsyncMock(side_effect=AssertionError('inventory read')))
    host.asend_event = AsyncMock()
    host.refresh_mobile_batch_admission = lambda: ListenSessionRuntime.refresh_mobile_batch_admission(host)
    fake = make_receiver(host)
    host.receiver = fake
    host.state.realtime_demand.observe = lambda payload: True
    before = counter(OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL, outcome=reason, client_platform='ios')

    assert await ListenReceiver._initialize_stt(fake)
    assert host.server_batch_only is True
    assert fake.cloud_live_suppressed is True
    assert host.local_preview_batch is (reason == 'admitted')
    assert counter(OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL, outcome=reason, client_platform='ios') == before + 1
    await host.refresh_mobile_batch_admission()
    ready = ListenSessionRuntime._ready_event(host).to_json()
    assert ready.get('local_preview') is (True if reason == 'admitted' else None)
    assert 'provider' not in ready

    # Exercise the actual lease-renewal event, including mid-session revocation.
    renewal = '{"type":"client_state","mobile_batch_capability_v1":true}'
    await ListenReceiver._handle_text(fake, renewal)
    payload = host.asend_event.call_args.args[0].to_json()
    assert payload['status'] == 'mobile_batch_admission'
    assert payload.get('local_preview') is ready.get('local_preview')
    if reason == 'admitted':
        assert payload['mobile_standard_batch'] is True
        monkeypatch.setenv(KILL, 'false')
        await ListenReceiver._handle_text(fake, renewal)
        revoked = host.asend_event.call_args.args[0].to_json()
        assert 'local_preview' not in revoked
        assert host.local_preview_batch is False
    assert host.server_batch_only is True
    assert fake.cloud_live_suppressed is True
    host.persistence.call.assert_not_awaited()


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


def open_seconds(**labels):
    """(count, sum) of the deferred-stream open-duration histogram for these labels."""
    samples = [
        sample
        for family in OMI_LISTEN_DEFERRED_STREAM_OPEN_SECONDS.collect()
        for sample in family.samples
        if all(sample.labels.get(k) == v for k, v in labels.items())
    ]
    count = sum(s.value for s in samples if s.name.endswith('_count'))
    total = sum(s.value for s in samples if s.name.endswith('_sum'))
    return count, total


def test_deferred_stream_open_duration_observed_once_at_teardown(monkeypatch):
    clock = [100.0, 103.5]
    monkeypatch.setattr(receiver_module.time, 'monotonic', lambda: clock.pop(0) if len(clock) > 1 else clock[0])
    fake = make_receiver(make_host(stt_service=SimpleNamespace(value='soniox')))
    fake._cloud_live_opening = True
    fake._cloud_live_deferred_by = 'local_preview'
    fake._serving_provider = lambda: ListenReceiver._serving_provider(fake)
    labels = {'deferred_by': 'local_preview', 'provider': 'soniox'}
    count, total = open_seconds(**labels)

    ListenReceiver.note_deferred_stream_opened(fake)
    note_deferred_stream_closed(fake)
    # A second teardown call (or a session that never opened) observes nothing.
    note_deferred_stream_closed(fake)
    assert open_seconds(**labels) == (count + 1, pytest.approx(total + 3.5))

    never_opened = make_receiver(make_host())
    note_deferred_stream_closed(never_opened)
    assert open_seconds(**labels) == (count + 1, pytest.approx(total + 3.5))


def deferred_soniox_receiver():
    fake = make_receiver(make_host(stt_service=SimpleNamespace(value='soniox'), server_batch_only=False))
    fake._cloud_live_deferred_by = 'local_preview'
    fake._serving_provider = lambda: ListenReceiver._serving_provider(fake)
    fake.note_deferred_stream_opened = lambda: ListenReceiver.note_deferred_stream_opened(fake)
    return fake


@pytest.mark.asyncio
async def test_cap_resume_on_flush_stamps_the_deferred_open():
    # The first open hit the funded cap; credit recovered and the flush path opened the stream.
    fake = deferred_soniox_receiver()
    fake.host.state.last_audio_received_time = 1.0
    fake._cloud_live_opening = True
    fake.cap_paused = True

    async def initialize_stt():
        fake.cap_paused = False
        return True

    fake.initialize_stt = initialize_stt
    fake.cap_admission = SimpleNamespace(
        allowed=lambda service: True, packet_allowed=lambda *a: False, note_held=Mock(), record_suppressed=Mock()
    )
    fake.live_hold = None
    fake._stt_buffer_start_sample = None
    fake._emit_stt_cap_live_held = AsyncMock()
    before = counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview')

    await ListenReceiver._flush_stt_buffer(fake, bytearray(320))
    assert fake._deferred_open_at is not None
    assert counter(OMI_LISTEN_DEFERRED_STREAM_OPENED_TOTAL, deferred_by='local_preview') == before + 1


@pytest.mark.asyncio
async def test_teardown_observes_a_stream_its_final_flush_opened(monkeypatch):
    # The stop-time flush is the suspected leak: it opens the stream inside teardown.
    clock = [50.0, 51.25]
    monkeypatch.setattr(receiver_module.time, 'monotonic', lambda: clock.pop(0) if len(clock) > 1 else clock[0])
    fake = deferred_soniox_receiver()
    fake.host.use_custom_stt = False
    fake.host.state.active = True
    fake.recovery = None
    fake.stt_socket = None
    fake.stt_sockets_multi = []
    fake._replay_recovery_task = None
    fake._replay_delivery = None
    fake.vad_gate = None
    fake._replay_tail_bytes = 0

    async def final_flush(buffer, force=False):
        fake._cloud_live_opening = True
        ListenReceiver.note_deferred_stream_opened(fake)

    fake._flush_stt_buffer = final_flush
    fake._drain_stt_sockets = AsyncMock()
    labels = {'deferred_by': 'local_preview', 'provider': 'soniox'}
    count, total = open_seconds(**labels)

    await ListenReceiver._teardown_body(fake, bytearray(320), 0)
    assert open_seconds(**labels) == (count + 1, pytest.approx(total + 1.25))
    fake._drain_stt_sockets.assert_awaited_once()


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
    runtime.request = ListenRequest(websocket=None, uid='batch-owner', local_preview=True)
    runtime.receiver = make_receiver(runtime)
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


@pytest.mark.asyncio
@pytest.mark.parametrize('switch', [None, 'true', 'false', ' OFF ', '0', 'no'])
async def test_engine_unavailable_counts_once_and_rescind_is_sticky(monkeypatch, switch):
    monkeypatch.delenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', raising=False)
    if switch is not None:
        monkeypatch.setenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', switch)
    enabled = switch in {None, 'true'}
    host = make_host(batch_record_capture={'record_lane_owner': 'batch_live_v1', 'server_batch_only': True})
    assert admit_local_preview(host)
    fake = make_receiver(host)
    attach = Mock()
    labels = dict(client_platform='ios', reason='locale_asset_missing')
    before = counter(OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL, **labels)
    original_request = host.request
    event = json.dumps({'type': 'local_preview_engine_unavailable', 'reason': 'locale_asset_missing'})
    await ListenReceiver._handle_text(fake, event)
    await ListenReceiver._handle_text(fake, event)
    assert counter(OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL, **labels) == before + 1
    assert host.local_preview_batch is (not enabled)
    assert host.request.local_preview is (not enabled)
    assert original_request.local_preview is True  # The actual request contract is frozen.
    monkeypatch.setenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', 'true')
    # Neither policy admission nor repeated lease renewal can undo a rescind.
    for _ in range(2):
        assert renew_local_preview(host) is (not enabled)
        assert admit_local_preview(host) is (not enabled)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'raw, expected',
    [
        ('os_too_old', 'os_too_old'),
        ('os_engine_unavailable', 'os_engine_unavailable'),
        ('locale_unsupported', 'locale_unsupported'),
        ('locale_asset_missing', 'locale_asset_missing'),
        ('speech_permission_denied', 'speech_permission_denied'),
        ('bundled_not_installed', 'bundled_not_installed'),
        ('bundled_not_built', 'bundled_not_built'),
        ('engine_error', 'engine_error'),
        ('unbounded-client-input', 'other'),
        ('unknown', 'other'),
        (None, 'other'),
        ([], 'other'),
        ({}, 'other'),
    ],
)
async def test_engine_unavailable_counter_preserves_known_reasons_and_counts_unknown_as_other(
    monkeypatch, raw, expected
):
    monkeypatch.delenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', raising=False)
    host = make_host(client_device_context=SimpleNamespace(platform='unbounded-platform'))
    assert admit_local_preview(host)
    fake = make_receiver(host)
    labels = dict(client_platform='unknown', reason=expected)
    before = counter(OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL, **labels)
    await ListenReceiver._handle_text(fake, json.dumps({'type': 'local_preview_engine_unavailable', 'reason': raw}))
    assert counter(OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL, **labels) == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['a_future_control_kind', 'local_preview_engine_unavailable'])
async def test_unknown_control_and_ungranted_engine_event_are_noops(monkeypatch, kind):
    fake = make_receiver(make_host(local_preview=False, local_preview_batch=False))
    attach = Mock(side_effect=AssertionError('restore attached'))
    await ListenReceiver._handle_text(fake, json.dumps({'type': kind, 'reason': 'engine_error'}))
    assert fake.host.local_preview_batch is False
    assert fake.host.request.local_preview is False
    assert not getattr(fake.host, '_local_preview_engine_reported', False)


def test_ready_event_identifies_server_batch_without_confusing_deferred_stream():
    runtime = object.__new__(ListenSessionRuntime)
    runtime.use_custom_stt = False
    runtime.receiver = SimpleNamespace(cloud_live_suppressed=True)
    assert 'server_batch_only' not in runtime._ready_event().to_json()
    runtime.server_batch_only = True
    payload = runtime._ready_event().to_json()
    assert payload['server_batch_only'] is True
    assert payload['status'] == 'ready'
    assert 'provider' not in payload
    runtime.use_custom_stt = True
    assert 'server_batch_only' not in runtime._ready_event().to_json()
    assert 'server_batch_only' not in MessageServiceStatusEvent(status='initiating').to_json()
