"""Bounded Soniox rotation replay and dark-path regressions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen.receiver import ListenReceiver
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.stt.resilient_stream import ResilientAudio
from utils.stt.soniox import soniox_death_reason
from utils.stt.streaming import STTService


class Socket:
    def __init__(self, *, dead=False, reason=None, callback=None):
        self.is_connection_dead = dead
        self.typed_death_reason = reason
        self.death_reason = 'soniox error: 413 max_duration_reached' if dead else None
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


def test_reconnect_count_and_replay_limits():
    ring = ResilientAudio(2)
    ring.append(b'X\x00' * 28, 0)
    assert ring.admit('soniox', 'soniox_rotation')
    ring.record_replay('soniox', 58)
    assert not ring.admit('soniox', 'soniox_rotation')  # extra replay would exceed 30 s
    second = ResilientAudio(2)
    assert second.admit('soniox', 'soniox_rotation')
    assert second.admit('soniox', 'soniox_rotation')
    assert not second.admit('soniox', 'soniox_rotation')  # rolling-minute cap


@pytest.mark.asyncio
async def test_flag_off_uses_existing_failover_without_replay(monkeypatch):
    listener = receiver(monkeypatch, enabled=False)
    assert listener._resilient_audio is None
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


def test_5xx_is_reconnectable_only_with_flag(monkeypatch):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'true')
    assert soniox_death_reason(503, 'server_error') == 'provider_5xx'
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'false')
    assert soniox_death_reason(503, 'server_error') == 'connection_lost'
