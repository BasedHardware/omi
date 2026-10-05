"""Bounded Soniox rotation replay and dark-path regressions."""

import asyncio
from types import SimpleNamespace

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

from config.stt_provider_policy import provider_for_service
from routers.listen import receiver as listen_receiver
from routers.listen.receiver import ListenReceiver
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.stt.live_metrics import WINDOW_REPLAY_SAFE_TRIMS
from utils.stt.live_failure import live_stt_terminal_reason
from utils.stt.recovery_state import LiveRecoveryController, RecoveryState
from utils.stt.resilient_stream import ResilientAudio, socket_is_finishing, window_replay_action
from utils.stt.soniox import soniox_death_reason
from utils.stt.streaming import STTService
from utils.stt import streaming as st


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


class Socket:
    def __init__(self, *, dead=False, reason=None, callback=None, finishing=False, raw=None):
        self.is_connection_dead = dead
        self.typed_death_reason = reason
        self.death_reason = 'soniox error: 413 max_duration_reached' if dead else None
        self._finishing = finishing
        self.raw = raw
        self.callback = callback
        self.sent = []
        self.finished = False

    def send(self, data, start_sample=None):
        self.sent.append((start_sample, data))
        if self.callback is not None:
            self.callback(
                [
                    {
                        'text': data[::2].decode(),
                        '_capture_start_sample': start_sample,
                        '_capture_end_sample': start_sample + len(data) // 2,
                    }
                ]
            )
        return True

    def finish(self):
        self.finished = True


def receiver(monkeypatch, *, enabled=True):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'true' if enabled else 'false')
    host = MagicMock()
    host.is_multi_channel = False
    host.use_custom_stt = False
    host.request.sample_rate = 2
    host.state.active = True
    host.state.stt_terminal_failure = False
    host.stt_service = STTService.soniox
    result = ListenReceiver(host, [], {})
    return result


@pytest.mark.asyncio
async def test_rotation_replays_only_unfinalized_audio_without_gap_or_duplicate(monkeypatch):
    listener = receiver(monkeypatch)
    ring = listener._resilient_audio
    assert ring is not None
    emitted = []

    def on_segments(segments):
        emitted.extend(s['text'] for s in listener._filter_replayed_segments(segments, 'soniox'))

    ring.append(b'A\x00A\x00', 0)
    on_segments([{'text': 'A', '_capture_start_sample': 0, '_capture_end_sample': 2}])
    ring.append(b'B\x00B\x00', 2)
    new = Socket(callback=on_segments)
    old = Socket(dead=True, reason='soniox_rotation')
    listener.stt_socket = old
    listener._stt_rebuild = (lambda: (on_segments, on_segments, None), 2)
    listener._create_stt_socket = AsyncMock(return_value=new)
    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._failover_stt_socket()
    assert old.finished
    assert new.sent == [(2, b'B\x00B\x00')]
    assert emitted == ['A', 'BB']
    assert listener._stt_failed_providers == set()


def test_ring_is_bounded_and_freed():
    ring = ResilientAudio(2)
    ring.append(b'X\x00' * 40, 0)
    assert ring.buffered_bytes == 15 * 2 * 2
    assert ring.snapshot()[0][0] == 10
    ring.close()
    assert ring.snapshot() == ()
    assert ring.buffered_bytes == 0


def test_window_replay_reserves_capacity_before_accepting_more_audio():
    ring = ResilientAudio(2, ring_seconds=3)
    ring.append(b'A\x00' * 4, 0)
    assert not ring.would_overflow(b'B\x00' * 2, 4)
    assert ring.would_overflow(b'C\x00' * 3, 4)
    ring.finalize_through(4)
    assert not ring.would_overflow(b'C\x00' * 3, 4)


class WindowRaw:
    def __init__(self, *, pending_speech):
        self.pending_speech = pending_speech
        self.socket = None
        self.failure = None
        self.cut_requests = 0

    def has_untranscribed_speech(self):
        return self.pending_speech

    def request_replay_cut(self):
        self.cut_requests += 1

    def fail(self, reason, *, capacity_subtype=None):
        self.failure = reason
        self.socket.is_connection_dead = True
        self.socket.typed_death_reason = reason
        self.socket.death_reason = reason
        self.socket.capacity_subtype = capacity_subtype


def test_window_replay_pressure_only_cuts_pending_speech():
    ring = ResilientAudio(2, ring_seconds=9, strict_replay=True)
    ring.append(b'A\x00' * 10, 0)  # Five seconds of capture; next second reaches 2/3 of the ring.
    pending = WindowRaw(pending_speech=True)
    assert window_replay_action(ring, Socket(raw=pending), b'B\x00' * 2, 10) == 'append'
    assert pending.cut_requests == 1
    assert pending.failure is None

    no_speech = WindowRaw(pending_speech=False)
    assert window_replay_action(ring, Socket(raw=no_speech), b'B\x00' * 2, 10) == 'append'
    assert no_speech.cut_requests == 0


def window_receiver_at_ring_limit(monkeypatch, *, pending_speech):
    listener = receiver(monkeypatch, enabled=False)
    listener.host.stt_service = STTService.parakeet
    listener.host.stt_model = 'parakeet-window'
    listener.host.language = 'en'
    listener.host.stt_language = 'en'
    listener.host.language_profile = None
    listener.host.multi_lang_enabled = False
    listener.host.request.uid = 'user'
    listener.host.client_device_context.platform = 'ios'
    listener.host.state.fair_use_dg_budget_exhausted = False
    listener.host.state.fair_use_track_dg_usage = False
    listener.host.state.dg_usage_ms_pending = 0
    listener._capture = lambda *_args: None
    ring = listener._window_replay_audio
    assert ring is not None
    ring.ring_seconds = 3
    ring.append(b'A\x00' * 6, 0)
    raw = WindowRaw(pending_speech=pending_speech)
    old = Socket(raw=raw)
    raw.socket = old
    listener.stt_socket = old
    listener._stt_buffer_start_sample = 6
    return listener, ring, raw, old


@pytest.mark.asyncio
async def test_window_ring_trims_only_after_all_speech_is_transcribed(monkeypatch):
    listener, ring, raw, old = window_receiver_at_ring_limit(monkeypatch, pending_speech=False)
    sent = []

    async def flush(_websocket, _state, *, stt_socket, buffer, start_sample, **_kwargs):
        sent.append((stt_socket, start_sample, bytes(buffer)))
        buffer.clear()
        return True

    monkeypatch.setattr(listen_receiver, 'flush_live_stt_buffer', flush)
    listener._failover_stt_socket = AsyncMock(return_value=True)
    before = WINDOW_REPLAY_SAFE_TRIMS._value.get()
    listener.host.spawn = lambda coro, **kw: asyncio.create_task(coro)
    await listener._flush_stt_buffer(bytearray(b'B\x00' * 2), force=True)
    if listener._replay_recovery_task is not None:
        await listener._replay_recovery_task
    assert raw.failure is None
    listener._failover_stt_socket.assert_not_awaited()
    assert sent == [(old, 6, b'B\x00' * 2)]
    assert ring.snapshot() == ((2, b'A\x00' * 4), (6, b'B\x00' * 2))
    assert WINDOW_REPLAY_SAFE_TRIMS._value.get() == before + 1


@pytest.mark.asyncio
async def test_window_ring_limit_with_pending_speech_replays_before_current_chunk(monkeypatch):
    listener, ring, raw, old = window_receiver_at_ring_limit(monkeypatch, pending_speech=True)
    replayed = []

    class Replacement(Socket):
        def replay_send(self, data, start):
            replayed.append((start, data))
            return self.send(data, start_sample=start)

    new = Replacement()
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    listener._create_stt_socket = AsyncMock(return_value=new)
    listener._wrap_legacy_stt_socket = lambda socket, _epoch: socket
    listener._record_selected_epoch = lambda _epoch, _socket: None
    monkeypatch.setattr(
        listen_receiver,
        'get_stt_service_for_language',
        lambda *args, **kwargs: (STTService.soniox, 'en', 'soniox'),
    )
    monkeypatch.setattr(listen_receiver, 'fallback_socket_is_serving', AsyncMock(return_value=True))

    async def flush(_websocket, _state, *, stt_socket, buffer, start_sample, **_kwargs):
        assert getattr(stt_socket, 'connection', stt_socket) is new
        stt_socket.send(bytes(buffer), start_sample=start_sample)
        buffer.clear()
        return True

    monkeypatch.setattr(listen_receiver, 'flush_live_stt_buffer', flush)
    listener.host.spawn = lambda coro, **kw: asyncio.create_task(coro)
    await listener._flush_stt_buffer(bytearray(b'B\x00' * 2), force=True)
    if listener._replay_recovery_task is not None:
        await listener._replay_recovery_task
    assert raw.failure == 'capacity_full'
    assert old.finished
    assert live_stt_terminal_reason(old, 'connection_lost') == 'capacity_full'
    assert listener._pending_live_failover.reason == 'capacity_full'
    assert replayed == [(0, b'A\x00' * 6 + b'B\x00' * 2)]
    assert new.sent == replayed
    assert ring.snapshot() == ((0, b'A\x00' * 6), (6, b'B\x00' * 2))


@pytest.mark.parametrize('reason', ['timeout', 'provider_5xx', 'capacity_full'])
@pytest.mark.asyncio
async def test_failed_window_replays_only_untranscribed_audio_once(monkeypatch, reason):
    listener = receiver(monkeypatch, enabled=False)
    listener.host.stt_service = STTService.parakeet
    listener.host.stt_model = 'parakeet-window'
    listener.host.language = 'en'
    listener.host.stt_language = 'en'
    listener.host.language_profile = None
    listener.host.multi_lang_enabled = False
    listener.host.request.uid = 'user'
    listener.host.client_device_context.platform = 'ios'
    listener.capture_timeline.accept(b'A\x00' * 2, arrival_wall=10.0, arrival_monotonic=1.0)
    listener.capture_timeline.accept(b'B\x00' * 2, arrival_wall=11.0, arrival_monotonic=2.0)
    ring = listener._window_replay_audio
    assert ring is not None
    ring.append(b'A\x00' * 2, 0)
    assert listener._filter_replayed_segments(
        [{'text': 'already', '_capture_start_sample': 0, '_capture_end_sample': 2}], 'parakeet'
    )
    ring.finalize_through(2)  # model the emitted anchor; this fake socket has no window pump
    ring.append(b'B\x00' * 2, 2)
    old = Socket(dead=True, reason=reason)
    listener.stt_socket = old
    epoch = ProviderEpochTranslator(listener.capture_timeline, 2, project_times=False)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, epoch), 2)

    class EpochSocket(Socket):
        def replay_send(self, data, start):
            epoch.note_accepted(start, len(data) // 2)
            return self.send(data, start_sample=start)

    new = EpochSocket()
    listener._create_stt_socket = AsyncMock(return_value=new)
    listener._wrap_legacy_stt_socket = lambda raw, epoch: raw
    listener._record_selected_epoch = lambda epoch, socket: None
    monkeypatch.setattr(
        'routers.listen.receiver.get_stt_service_for_language',
        lambda *args, **kwargs: (STTService.soniox, 'en', 'soniox'),
    )
    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._failover_stt_socket()
    assert new.sent == [(2, b'B\x00' * 2)]
    translated = epoch.translate([{'text': 'new', 'start': 0.0, 'end': 1.0}])
    epoch.stitch_replayed_timestamps(translated)
    assert [(s['_capture_start_sample'], s['_capture_end_sample']) for s in translated] == [(2, 4)]
    assert [(s['start'], s['end']) for s in translated] == [(1.0, 2.0)]
    assert ring.snapshot() == ((2, b'B\x00' * 2),)
    assert listener._filter_replayed_segments(translated, 'soniox') == translated
    assert ring.snapshot() == ()
    assert old.finished
    assert listener.host.stt_service == st.STTService.soniox


@pytest.mark.asyncio
async def test_two_partial_replay_failures_preserve_tail_and_new_audio(monkeypatch):
    monkeypatch.setattr("utils.stt.replay_delivery.REPLAY_PACKET_BYTES", 4)
    listener = receiver(monkeypatch, enabled=False)
    listener.host.stt_service = STTService.parakeet
    listener.host.stt_model = 'parakeet-window'
    listener.host.language = listener.host.stt_language = 'en'
    listener.host.language_profile = None
    listener.host.multi_lang_enabled = False
    listener.host.request.uid = 'user'
    listener.host.client_device_context.platform = 'ios'
    ring = listener._window_replay_audio
    assert ring is not None
    for index, letter in enumerate('ABCD'):
        data = (letter.encode() + b'\x00') * 2
        listener.capture_timeline.accept(data, arrival_wall=10 + index, arrival_monotonic=1 + index)
        ring.append(data, index * 2)
    ring.finalize_through(2)  # A has already produced text.
    old = Socket(dead=True, reason='provider_5xx')
    listener.stt_socket = old
    epochs = []

    def rebuild():
        epoch = ProviderEpochTranslator(listener.capture_timeline, 2, project_times=False)
        epochs.append(epoch)
        return lambda _: None, lambda _: None, epoch

    listener._stt_rebuild = (rebuild, 2)
    listener._wrap_legacy_stt_socket = lambda raw, epoch: raw
    listener._record_selected_epoch = lambda epoch, socket: None
    monkeypatch.setattr('routers.listen.receiver.managed_chain_enabled', lambda host: True)
    providers = (STTService.modulate, STTService.soniox, STTService.deepgram)
    monkeypatch.setattr(
        'routers.listen.receiver.get_stt_service_for_language',
        lambda *args, **kwargs: next(
            (service, 'en', service.value)
            for service in providers
            if provider_for_service(service) not in kwargs['exclude']
        ),
    )
    sockets = []

    async def create(*args, epoch, **kwargs):
        rejected = (4, 6, None)[len(sockets)]

        class ReplaySocket(Socket):
            def replay_send(self, data, start):
                if start == rejected:
                    if len(sockets) == 1:
                        new_audio = b'E\x00' * 2
                        listener.capture_timeline.accept(new_audio, arrival_wall=14, arrival_monotonic=5)
                        ring.append(new_audio, 8)  # Arrives after the first replay snapshot.
                    return False
                epoch.note_accepted(start, len(data) // 2)
                return self.send(data, start_sample=start)

        raw = ReplaySocket()
        sockets.append(raw)
        return raw

    listener._create_stt_socket = create
    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._failover_stt_socket()
    assert [socket.sent for socket in sockets] == [
        [(2, b'B\x00' * 2)],
        [(2, b'B\x00' * 2), (4, b'C\x00' * 2)],
        [(2, b'B\x00' * 2), (4, b'C\x00' * 2), (6, b'D\x00' * 2), (8, b'E\x00' * 2)],
    ]
    assert sockets[0].finished and sockets[1].finished and old.finished
    translated = epochs[-1].translate([{'text': 'D', 'start': 2.0, 'end': 3.0}])
    epochs[-1].stitch_replayed_timestamps(translated)
    assert [(s['_capture_start_sample'], s['_capture_end_sample']) for s in translated] == [(6, 8)]
    assert [(s['start'], s['end']) for s in translated] == [(3.0, 4.0)]
    assert ring.snapshot() == ((2, b'B\x00' * 2), (4, b'C\x00' * 2), (6, b'D\x00' * 2), (8, b'E\x00' * 2))


def test_replay_epoch_maps_new_socket_time_to_original_capture_position():
    timeline = CaptureTimeline(sample_rate=2)
    timeline.accept(b'A\x00' * 2, arrival_wall=10.0, arrival_monotonic=1.0)
    timeline.accept(b'B\x00' * 2, arrival_wall=11.0, arrival_monotonic=2.0)
    replay_epoch = ProviderEpochTranslator(timeline, 2, project_times=True)
    replay_epoch.provider_label = 'soniox'
    replay_epoch.note_accepted(2, 2)
    segments = replay_epoch.translate([{'text': 'BB', 'start': 0.0, 'end': 1.0}])
    assert [(s['_capture_start_sample'], s['_capture_end_sample']) for s in segments] == [(2, 4)]
    assert [(s['start'], s['end']) for s in segments] == [(10.0, 11.0)]


def test_clock_only_replay_timestamps_continue_on_capture_sample_axis():
    timeline = CaptureTimeline(sample_rate=2)
    timeline.accept(b'A\x00' * 2, arrival_wall=10.0, arrival_monotonic=1.0)
    timeline.accept(b'B\x00' * 2, arrival_wall=11.0, arrival_monotonic=2.0)
    replay_epoch = ProviderEpochTranslator(timeline, 2, project_times=False)
    replay_epoch.provider_label = 'soniox'
    replay_epoch.replay_origin_sample = 2
    replay_epoch.note_accepted(2, 2)
    segments = replay_epoch.translate([{'text': 'BB', 'start': 0.0, 'end': 1.0}])
    replay_epoch.stitch_replayed_timestamps(segments)
    assert [(s['_capture_start_sample'], s['_capture_end_sample']) for s in segments] == [(2, 4)]
    assert [(s['start'], s['end']) for s in segments] == [(1.0, 2.0)]


def test_reconnect_reentry_is_one_controller_repeat_per_session():
    controller = LiveRecoveryController(SimpleNamespace())
    controller.begin()
    controller.mark_attempted('soniox')
    assert controller.state is RecoveryState.provider_died
    assert controller.grant_soniox_reentry('soniox')
    assert controller.grant_soniox_reentry('soniox')
    assert not controller.grant_soniox_reentry('other')
    assert controller.reserve('soniox', 'soniox')
    assert controller.dial_attempts == 2
    assert controller.state is RecoveryState.recovering
    assert not controller.grant_soniox_reentry('soniox')
    assert not controller.reserve('soniox', 'soniox')
    assert controller.dial_attempts == 2


def test_reconnect_reentry_never_extends_past_the_episode():
    now = [0.0]
    controller = LiveRecoveryController(SimpleNamespace(), clock=lambda: now[0])
    controller.begin()
    controller.mark_attempted('soniox')
    assert controller.grant_soniox_reentry('soniox')
    now[0] = 61.0
    assert controller.episode_expired()
    assert not controller.admission_open()
    assert not controller.can_attempt('soniox')
    assert not controller.reserve('soniox', 'soniox')
    assert not controller.reserve('modulate-velma-2', 'modulate')

    fresh = LiveRecoveryController(SimpleNamespace(), clock=lambda: now[0])
    fresh.begin()
    assert fresh.reserve('modulate-velma-2', 'modulate')


def test_recovery_states_walk_dial_replay_adopt_to_recovered():
    controller = LiveRecoveryController(SimpleNamespace())
    controller.begin()
    assert controller.state is RecoveryState.provider_died
    assert controller.reserve('modulate-velma-2', 'modulate')
    assert controller.state is RecoveryState.recovering
    token = object()
    controller.set_candidate(token)
    controller.replaying()
    assert controller.state is RecoveryState.replaying
    controller.adopted(token)
    assert controller.state is not RecoveryState.recovered
    assert controller.deadline is not None
    controller.note_transcript(True, candidate=token)
    assert controller.state is RecoveryState.recovered
    assert controller.deadline is None


def test_text_bound_to_candidate_before_adoption_releases_on_adopt():
    controller = LiveRecoveryController(SimpleNamespace())
    controller.begin()
    controller.reserve('soniox', 'soniox')
    token = object()
    controller.set_candidate(token)
    controller.replaying()
    controller.note_transcript(True, candidate=token)
    assert controller.state is not RecoveryState.recovered
    controller.adopted(token)
    assert controller.state is RecoveryState.recovered


def test_whitespace_text_and_stale_candidate_tokens_never_release_the_episode():
    controller = LiveRecoveryController(SimpleNamespace())
    controller.begin()
    controller.reserve('soniox', 'soniox')
    token = object()
    controller.set_candidate(token)
    controller.replaying()
    controller.adopted(token)
    controller.note_transcript(False, candidate=token)
    controller.note_transcript(True, candidate=object())
    controller.note_transcript(True)
    assert controller.state is not RecoveryState.recovered
    assert controller.deadline is not None
    controller.note_transcript(True, candidate=token)
    assert controller.state is RecoveryState.recovered


@pytest.mark.asyncio
async def test_transient_soniox_reentry_replays_newest_twenty_second_prefix(monkeypatch):
    listener = receiver(monkeypatch)
    ring = listener._resilient_audio
    assert ring is not None
    ring.ring_seconds = 150
    for index in range(135):
        ring.append(b'R\x00' * 2, index * 2)
    listener.recovery.mark_attempted('soniox')
    listener.stt_socket = Socket(dead=True, reason='soniox_rotation')
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    dialed = []

    async def dial(callback, *args, **kwargs):
        raw = Socket()
        dialed.append(raw)
        return raw

    monkeypatch.setattr(listen_receiver, 'process_audio_soniox', dial)
    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._failover_stt_socket()
    assert len(dialed) == 1
    assert listener.recovery.dial_attempts == 2
    assert dialed[0].sent == [(230, b'R\x00' * 40)]
    assert ring.buffered_bytes == 80
    assert ring.capture_bounds == (230, 270)


@pytest.mark.asyncio
async def test_consumed_reentry_blocks_a_second_repeat_and_next_provider_serves(monkeypatch):
    listener = receiver(monkeypatch)
    listener.recovery.mark_attempted('soniox')
    listener.stt_socket = Socket(dead=True, reason='soniox_rotation')
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    dialed = []

    async def dial(callback, *args, **kwargs):
        raw = Socket()
        dialed.append(raw)
        return raw

    monkeypatch.setattr(listen_receiver, 'process_audio_soniox', dial)
    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._reconnect_stt_socket_locked()
    assert len(dialed) == 1
    assert listener.recovery.dial_attempts == 2
    assert not listener.recovery.grant_soniox_reentry('soniox')
    dialed[0].is_connection_dead = True
    dialed[0].typed_death_reason = 'connection_lost'
    dialed[0].death_reason = 'ws closed'
    assert not await listener._reconnect_stt_socket_locked()
    assert len(dialed) == 1
    assert listener.recovery.dial_attempts == 2
    assert listener.recovery.state is not RecoveryState.exhausted


@pytest.mark.asyncio
async def test_flag_off_uses_existing_failover_without_replay(monkeypatch):
    listener = receiver(monkeypatch, enabled=False)
    assert listener._resilient_audio is None
    original = [{'text': 'unchanged', 'start': 1.25, 'end': 2.5, 'speaker': '0'}]
    assert listener._filter_replayed_segments(original, 'soniox') is original
    assert original == [{'text': 'unchanged', 'start': 1.25, 'end': 2.5, 'speaker': '0'}]
    listener.stt_socket = Socket(dead=True, reason='soniox_rotation')
    listener._rebuild_stt_socket_locked = AsyncMock(return_value=True)
    assert await listener._failover_stt_socket()
    listener._rebuild_stt_socket_locked.assert_awaited_once()
    assert soniox_death_reason(503, 'unavailable') == 'connection_lost'


@pytest.mark.asyncio
async def test_teardown_does_not_reconnect(monkeypatch):
    listener = receiver(monkeypatch)
    listener.stt_socket = Socket(dead=True, reason='soniox_rotation')
    listener._stt_rebuild = (lambda: (None, None, None), 2)
    listener._create_stt_socket = AsyncMock()
    listener.finish()
    assert listener._resilient_audio.buffered_bytes == 0
    assert not await listener._reconnect_stt_socket_locked()
    listener._create_stt_socket.assert_not_awaited()


@pytest.mark.asyncio
async def test_soniox_finishing_socket_does_not_start_reconnect_or_fallback(monkeypatch):
    listener = receiver(monkeypatch)
    socket = Socket(dead=True, reason='soniox_rotation', raw=Socket(finishing=True))
    assert not socket_is_finishing(socket)
    socket.leg_outcome = SimpleNamespace(owner_closing=True)
    listener.stt_socket = socket
    listener._stt_rebuild = (lambda: (None, None, None), 2)
    listener._create_stt_socket = AsyncMock()
    listener._rebuild_stt_socket_locked = AsyncMock(return_value=True)

    assert socket_is_finishing(socket)
    assert not await listener._failover_stt_socket()

    listener._create_stt_socket.assert_not_awaited()
    listener._rebuild_stt_socket_locked.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_rate_limit_uses_backoff_instead_of_same_provider_reconnect(monkeypatch):
    listener = receiver(monkeypatch)
    listener.stt_socket = Socket(dead=True, reason='provider_rate_limited')
    listener._stt_rebuild = (lambda: (None, None, None), 2)
    listener._create_stt_socket = AsyncMock()

    assert not await listener._reconnect_stt_socket_locked()

    listener._create_stt_socket.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_provider_reconnect_releases_old_open_stream_gauge_lease(monkeypatch):
    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS

    listener = receiver(monkeypatch)
    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before = gauge._value.get()
    old = listener._wrap_legacy_stt_socket(Socket(dead=True, reason='soniox_rotation'), None)
    listener.stt_socket = old
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    listener._create_stt_socket = AsyncMock(return_value=Socket())

    with patch('routers.listen.receiver.fallback_socket_is_serving', new=AsyncMock(return_value=True)):
        assert await listener._failover_stt_socket()

    assert gauge._value.get() == before + 1
    listener.finish()
    assert gauge._value.get() == before


def test_5xx_is_reconnectable_only_with_flag(monkeypatch):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'true')
    assert soniox_death_reason(503, 'server_error') == 'provider_5xx'
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'false')
    assert soniox_death_reason(503, 'server_error') == 'connection_lost'


@pytest.mark.parametrize('sample_rate', [8000, 16000, 48000])
def test_replacement_headroom_shrinks_only_after_progress_frees_base_horizon(sample_rate):
    ring = ResilientAudio(sample_rate, ring_seconds=90, strict_replay=True)
    ring.reserve_replacement_headroom()
    capture = b'\x01\x00' * (105 * sample_rate)
    ring.append(capture, 0)
    assert ring.ring_seconds == 105
    assert ring.finalize_through(29 * sample_rate) == 29 * sample_rate * 2
    assert ring.ring_seconds == 105
    assert ring.capture_bounds == (29 * sample_rate, 105 * sample_rate)
    assert ring.finalize_through(30 * sample_rate) == sample_rate * 2
    assert ring.ring_seconds == 90
    assert ring.snapshot() == ((30 * sample_rate, capture[30 * sample_rate * 2 :]),)
    # All fifteen seconds of headroom still fit after reclaiming the cap.
    assert not ring.would_overflow(b'\x02\x00' * (15 * sample_rate), 105 * sample_rate)
    assert ring.would_overflow(b'\x02\x00' * (15 * sample_rate + 1), 105 * sample_rate)
