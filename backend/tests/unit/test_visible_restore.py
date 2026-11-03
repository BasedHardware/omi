"""Visible-only paid preview never borrows the managed provider fallback chain."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen import receiver as receiver_module, visible_restore as restore_module
from routers.listen.contracts import ListenRequest
from routers.listen.receiver import ListenReceiver
from routers.listen.local_preview import renew_local_preview
from config.server_batch import owned
from utils.observability import demand_cohort
from utils.stt.streaming import STTService


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', '100')
    now = [100.0]
    monkeypatch.setattr(restore_module.time, 'monotonic', lambda: now[0])
    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner', local_preview=False, sample_rate=16000),
        client_device_context=SimpleNamespace(platform='ios'),
        server_batch_only=True,
        batch_record_capture={'record_lane_owner': 'batch_live_v1', 'server_batch_only': True},
        use_custom_stt=False,
        is_multi_channel=False,
        state=SimpleNamespace(active=True),
        stt_service=STTService.soniox,
        stt_language='en',
        spawn=lambda coro, **kwargs: asyncio.create_task(coro),
    )
    callback = Mock()
    raw = SimpleNamespace(send=Mock(return_value=True), finish=Mock(), is_connection_dead=False)
    dial = AsyncMock(return_value=raw)
    monkeypatch.setattr(receiver_module, 'process_audio_modulate', dial)
    monkeypatch.setattr(receiver_module, 'live_stt_socket_is_dead', lambda sock: sock.is_connection_dead)
    monkeypatch.setattr(
        receiver_module, 'connect_stt_socket_with_fallback', AsyncMock(side_effect=AssertionError('fallback'))
    )
    receiver = SimpleNamespace(
        host=host,
        stt_socket=None,
        _stt_buffer_start_sample=None,
        _build_stt_callbacks=lambda: (None, callback, None),
        _wrap_legacy_stt_socket=lambda raw, epoch: raw,
        _record_selected_epoch=Mock(),
    )
    restore = receiver.visible_restore = restore_module.VisibleRestore(receiver)
    restore.presence.policy.clock = lambda: now[0]
    restore.presence.policy.changed_at = now[0]
    receiver._open_deferred_stream = lambda: ListenReceiver._open_deferred_stream(receiver)
    # Publishing is tested separately by live-demand-presence. No background
    # task is needed to exercise this socket's local visibility policy.
    monkeypatch.setattr(restore.presence, 'observe', restore.presence.policy.observe)
    return SimpleNamespace(
        receiver=receiver, restore=restore, host=host, raw=raw, dial=dial, callback=callback, now=now
    )


def observe(h, visible, foreground=True):
    h.restore.observe({'foreground': foreground, 'transcript_visible': visible})


async def flush(h, data=b'\x01\x00' * 160, *, settle=True):
    # Most unit cases inspect a ready provider. The nonblocking-dial regression
    # below and the real WebSocket harness exercise production scheduling.
    if settle and h.restore.visible() and not h.restore.failed:
        await h.receiver._open_deferred_stream()
    buffer = bytearray(data)
    await ListenReceiver._flush_stt_buffer(h.receiver, buffer)
    assert buffer == b''


@pytest.mark.asyncio
async def test_receive_flush_returns_while_dial_is_blocked_and_hide_wins(harness):
    h = harness
    started, release = asyncio.Event(), asyncio.Event()

    async def dial(*args):
        started.set()
        await release.wait()
        return h.raw

    h.dial.side_effect = dial
    observe(h, True)
    h.now[0] += 15
    try:
        await asyncio.wait_for(flush(h, settle=False), timeout=1)
        await asyncio.wait_for(started.wait(), timeout=1)
        assert h.restore.opening is not None and not h.restore.opening.done()
        # These are sequential receive-loop steps, after flush has returned.
        observe(h, False)
        await asyncio.wait_for(flush(h, settle=False), timeout=1)
        release.set()
        await asyncio.wait_for(h.restore.opening, timeout=1)
        h.raw.send.assert_not_called()
        assert h.receiver.stt_socket is None
        assert h.host.state.active
    finally:
        release.set()
        await h.restore.shutdown()


@pytest.mark.asyncio
async def test_exact_visible_dwell_fresh_audio_and_immediate_hide(harness):
    h = harness
    await flush(h)  # Unreported.
    observe(h, False)  # Foreground alone.
    h.now[0] += 20
    await flush(h)
    observe(h, True)
    h.now[0] += 14.99
    await flush(h)
    h.dial.assert_not_awaited()
    h.now[0] += 0.01
    await flush(h)
    h.dial.assert_awaited_once()
    assert h.host.stt_service == STTService.modulate
    h.raw.send.assert_called_once_with(b'\x01\x00' * 160)
    provider_callback = h.dial.call_args.args[0]
    provider_callback([{'text': 'synthetic preview'}])
    h.callback.assert_called_once()
    observe(h, False)
    h.raw.finish.assert_called_once()
    provider_callback([{'text': 'late synthetic preview'}])
    assert h.callback.call_count == 1
    await flush(h)
    assert h.dial.await_count == 1
    assert h.host.server_batch_only is True
    assert h.host.batch_record_capture['record_lane_owner'] == 'batch_live_v1'


@pytest.mark.asyncio
@pytest.mark.parametrize('dead', [False, True])
async def test_fail_closed_until_new_visible_dwell(harness, dead):
    h = harness
    observe(h, True)
    h.now[0] += 15
    if not dead:
        h.dial.side_effect = RuntimeError('synthetic failure')
    await flush(h)
    if dead:
        h.raw.is_connection_dead = True
        await flush(h)
    h.now[0] += 60
    await flush(h)
    assert h.dial.await_count == 1
    assert not getattr(h.host.state, 'stt_terminal_failure', False)
    observe(h, False)
    observe(h, True)
    h.now[0] += 15
    h.dial.side_effect = None
    h.raw.is_connection_dead = False
    await flush(h)
    assert h.dial.await_count == 2


@pytest.mark.asyncio
async def test_visibility_change_during_dial_discards_candidate(harness):
    h = harness
    observe(h, True)
    h.now[0] += 15

    async def dial(*args):
        observe(h, False)
        return h.raw

    h.dial.side_effect = dial
    await flush(h)
    h.raw.finish.assert_called_once()
    h.raw.send.assert_not_called()


@pytest.mark.asyncio
async def test_kill_switch_and_malformed_reports_fail_closed(harness, monkeypatch):
    h = harness
    observe(h, True)
    h.now[0] += 15
    await flush(h)
    monkeypatch.setenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', '0')
    await flush(h)
    assert h.receiver.stt_socket is None
    monkeypatch.setenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', '100')
    h.restore.observe({'foreground': False, 'transcript_visible': True})
    h.now[0] += 30
    await flush(h)
    assert h.dial.await_count == 1


@pytest.mark.asyncio
async def test_hidden_preview_closes_real_modulate_transport_and_tasks(harness):
    from utils.stt.streaming import SafeModulateSocket

    class Transport:
        close = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Future()

    h = harness
    raw = SafeModulateSocket(Transport(), h.callback, asyncio.get_running_loop())
    h.dial.return_value = raw
    try:
        observe(h, True)
        h.now[0] += 15
        await flush(h)
        raw._handle_utterance({'speaker': 2, 'text': 'Synthetic preview.', 'start_ms': 0, 'duration_ms': 10})
        assert h.callback.call_args.args[0][0]['speaker'] == 'SPEAKER_01'
        observe(h, False)
        assert raw.stream_end.closing
        await h.restore.drain()
        assert raw._send_task.done() and raw._recv_task.done()
        raw._ws.close.assert_awaited_once()
    finally:
        h.restore.close()
        await h.restore.drain()


@pytest.mark.asyncio
async def test_no_audio_monitor_retires_dead_preview_without_ending_batch(harness):
    h = harness
    observe(h, True)
    h.now[0] += 15
    await flush(h)
    h.raw.is_connection_dead = True
    h.host.wait = AsyncMock(return_value=True)
    await h.restore.run()
    assert h.receiver.stt_socket is None
    assert h.restore.failed
    assert h.host.state.active


@pytest.mark.asyncio
async def test_refused_send_counts_failure_once_and_stays_closed(harness, monkeypatch):
    metric = Mock()
    monkeypatch.setattr(restore_module, 'OMI_LISTEN_VISIBLE_RESTORE_STREAMS_TOTAL', metric)
    h = harness
    observe(h, True)
    h.now[0] += 15
    h.raw.send.return_value = False
    await flush(h)
    await flush(h)
    assert h.restore.failed
    assert h.dial.await_count == 1
    assert metric.labels.call_args_list.count(((), {'outcome': 'failed'})) == 1


@pytest.mark.parametrize('percent', ['0', 'bad', '-1', 'nan'])
def test_closed_flag_defaults_and_invalid_values(harness, monkeypatch, percent):
    monkeypatch.setenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', percent)
    assert not restore_module.admitted(harness.host)


@pytest.mark.parametrize('field,value', [('local_preview', True), ('platform', 'macos')])
def test_only_mobile_without_local_preview(harness, field, value):
    if field == 'platform':
        harness.host.client_device_context.platform = value
    else:
        harness.host.request.local_preview = value
    assert not restore_module.admitted(harness.host)


def test_actual_wire_meter_counts_restore_and_existing_provider_seconds(monkeypatch):
    wire, restore_wire = Mock(), Mock()
    monkeypatch.setattr(demand_cohort, 'WIRE_AUDIO', wire)
    monkeypatch.setattr(demand_cohort, 'VISIBLE_RESTORE_WIRE_AUDIO', restore_wire)
    token = demand_cohort.current_visible_restore.set(True)
    try:
        meter = demand_cohort.WireAudioMeter('modulate', 16000)
    finally:
        demand_cohort.current_visible_restore.reset(token)
    meter.written(b'\x00\x00' * 16000)
    restore_wire.inc.assert_called_once_with(1)
    wire.labels.assert_called_once()
    wire.labels.return_value.inc.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_late_visible_stream_keeps_words_on_original_capture_clock(harness):
    from routers.listen.stt_callbacks import build_stt_callbacks
    from routers.listen.receiver import _RecordingSTTSocket
    from utils.audio_timeline import CaptureTimeline

    h = harness
    h.host.request.sample_rate = 2
    timeline = CaptureTimeline(sample_rate=2)
    timeline.accept(b'\x00\x00' * 2, arrival_wall=10, arrival_monotonic=1)  # Hidden audio.
    timeline.accept(b'\x00\x00' * 2, arrival_wall=11, arrival_monotonic=2)
    h.receiver.capture_timeline = timeline
    h.receiver.capture_timeline_v2 = False
    h.receiver.vad_gate = None
    h.receiver._proven_send_owner = lambda *args: None
    h.receiver._record_elapsed_validation = Mock()
    h.receiver._loop_hop = lambda callback: callback
    h.receiver._enqueue_clock_positioned_segments = lambda segments, **kwargs: h.callback(segments)
    h.receiver._build_stt_callbacks = lambda: build_stt_callbacks(h.receiver)
    h.receiver._wrap_legacy_stt_socket = lambda raw, epoch: _RecordingSTTSocket(raw, epoch)
    h.receiver._stt_buffer_start_sample = 2
    observe(h, True)
    h.now[0] += 15
    await flush(h, b'\x01\x00' * 2)
    h.dial.call_args.args[0]([{'text': 'Synthetic visible words.', 'start': 0.0, 'end': 1.0}])
    words = h.callback.call_args.args[0]
    assert [(word['start'], word['end']) for word in words] == [(1.0, 2.0)]
    h.restore.close()
    await h.restore.drain()


@pytest.mark.asyncio
async def test_without_capture_clock_hidden_audio_still_offsets_new_provider_words(harness):
    h = harness
    await flush(h, b'\x00\x00' * 16000)
    observe(h, True)
    h.now[0] += 15
    await flush(h)
    h.dial.call_args.args[0]([{'text': 'Synthetic visible words.', 'start': 0.0, 'end': 0.01}])
    words = h.callback.call_args.args[0]
    assert [(word['start'], word['end']) for word in words] == [(1.0, 1.01)]


@pytest.mark.asyncio
@pytest.mark.parametrize('server_batch_only', [True, False])
async def test_engine_rescind_routes_only_visible_restore_with_durable_custody(harness, monkeypatch, server_batch_only):
    h = harness
    monkeypatch.delenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', raising=False)
    h.host.server_batch_only = server_batch_only
    h.host.request = ListenRequest(websocket=None, uid=h.host.request.uid, sample_rate=16000, local_preview=True)
    h.host.local_preview_batch = True
    h.host._local_preview_pinned = True
    h.receiver.visible_restore = None
    h.receiver.cloud_live_suppressed = True
    h.host.task_supervisor = SimpleNamespace(create_lifetime_task=lambda coro, **kw: coro.close())
    h.receiver.ensure_live_demand_routing = Mock()
    legacy = AsyncMock(side_effect=AssertionError('full cloud stream'))
    monkeypatch.setattr(receiver_module.legacy_recovery, 'flush_stt_buffer', legacy)
    h.receiver.initialize_stt = AsyncMock(side_effect=AssertionError('full cloud initialization'))
    await ListenReceiver._handle_text(
        h.receiver,
        json.dumps(
            {
                'type': 'local_preview_engine_unavailable',
                'reason': 'os_engine_unavailable',
            }
        ),
    )
    assert not h.host.request.local_preview
    assert not renew_local_preview(h.host)
    assert owned(h.host.batch_record_capture)
    h.restore = h.receiver.visible_restore
    assert h.restore is not None
    h.restore.presence.policy.clock = lambda: h.now[0]
    h.restore.presence.policy.changed_at = h.now[0]
    monkeypatch.setattr(h.restore.presence, 'observe', h.restore.presence.policy.observe)
    try:
        await flush(h, settle=False)
        h.dial.assert_not_awaited()
        observe(h, True)
        h.now[0] += 14.99
        await flush(h, settle=False)
        h.dial.assert_not_awaited()
        h.now[0] += 0.01
        await flush(h, settle=False)
        await h.restore.opening
        await flush(h, settle=False)
        h.dial.assert_awaited_once()
        h.raw.send.assert_called_once()
        h.dial.call_args.args[0]([{'text': 'Synthetic restored preview'}])
        h.callback.assert_called_once()
        # Duplicate control and renewal cannot attach a second transcript source.
        await ListenReceiver._handle_text(h.receiver, json.dumps({'type': 'local_preview_engine_unavailable'}))
        assert h.receiver.visible_restore is h.restore
        assert not renew_local_preview(h.host)
        legacy.assert_not_awaited()
        h.receiver.initialize_stt.assert_not_awaited()
        observe(h, False)
        h.dial.call_args.args[0]([{'text': 'late text'}])
        h.callback.assert_called_once()
    finally:
        await h.restore.shutdown()


@pytest.mark.asyncio
async def test_rescind_without_durable_owner_never_opens_full_cloud(harness, monkeypatch):
    h = harness
    h.host.server_batch_only = False
    h.host.batch_record_capture = {}  # A declaration/grant is not durable server custody.
    h.host._local_preview_engine_rescinded = True
    h.receiver.visible_restore = None
    h.receiver.cloud_live_suppressed = True
    h.receiver.initialize_stt = AsyncMock(side_effect=AssertionError('full stream'))
    assert not owned(h.host.batch_record_capture)
    restore_module.attach_visible_restore(h.receiver)
    assert h.receiver.visible_restore is None
    assert await h.receiver._open_deferred_stream()
    buffer = bytearray(b'\x00\x01')
    await ListenReceiver._flush_stt_buffer(h.receiver, buffer)
    assert not buffer
    h.receiver.initialize_stt.assert_not_awaited()
    h.dial.assert_not_awaited()
