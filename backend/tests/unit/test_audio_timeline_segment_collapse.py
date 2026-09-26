"""Regressions for the dev 2026-09-26 v2 segment collapse (audio-timeline follow-up).

Evidence: dev listen eb78646 + pusher 572672c, managed chain with the Parakeet
window leg. Every segment after the first provider batch was persisted as a
zero-length point sitting exactly on the end of an accepted audio span
(``/v4/listen`` conversations ``(18.9, 18.9)``, ``(28.82, 28.82)`` x3,
``(39.2, 39.2)`` in ``.local/agent-tasks/dev-probe-conversations.json``).

Root cause locked here end to end through the real seams — receiver, managed
chain, VAD gate, window adapter, epoch translator, fake TDT server:

- ``WindowedParakeetSocket._materialize`` clamps every TDT timestamp into
  ``[start, now]``, so a response whose timestamps fall at/beyond the posted
  window duration (TDT drift on re-posted windows) collapses both endpoints
  onto ``now`` — the end of the posted window, which is the end of the last
  accepted provider send span. That is exactly the observed zero point.
- ``SendMap.map_interval``'s edge tolerance clamps provider endpoints that
  overshoot a span end onto that end, so two *different* provider times can
  collapse onto one capture sample instead of being rejected.

The translator-level paths (legacy gated Deepgram/Soniox shape, Modulate
passthrough shape, gate-off direct sends) are audited here with a later-batch
segment: start < end preserved and the exact capture samples.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest

import utils.stt.parakeet_window as window
import utils.stt.provider_resilience as provider_resilience
import utils.stt.streaming as st
import utils.stt.vad_gate as vad_gate
from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator, SendMap
from utils.stt.socket import STTSocket
from utils.stt.vad_gate import GatedSTTSocket

RATE = 16000
T0 = 1_700_000_000.0
REAL_SLEEP = asyncio.sleep


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    """Managed chain + window leg + deterministic VAD; no network, no model."""
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '1')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://tdt.invalid')
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '6')
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://embedding.invalid')
    monkeypatch.setattr(window, 'admission', window.WindowAdmission())
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    for provider in ('parakeet', 'modulate', 'deepgram', 'soniox'):
        monkeypatch.setattr(
            st,
            f'_{provider}_circuit',
            provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30),
        )
    monkeypatch.setattr(st, '_deepgram_is_available', lambda: True)
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)

    def _vad_nonzero(_self, data: bytes) -> bool:
        if len(data) < 2:
            return False
        aligned = data[: len(data) - (len(data) % 2)]
        return bool(np.any(np.frombuffer(aligned, dtype=np.int16)))

    monkeypatch.setattr(vad_gate.VADStreamingGate, '_run_vad', _vad_nonzero)

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(window, 'get_stt_semaphore', semaphore)
    # Window scheduling uses loop-time pacing; the repro feeds audio as fast
    # as the pump can post, so pacing sleeps collapse to a yield. The idle
    # flush is real-time based and would fire mid-feed depending on host
    # speed; pin it out so the post sequence is exactly: pace post, drain post.
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: REAL_SLEEP(0))
    monkeypatch.setattr(window, 'IDLE_FLUSH_SECONDS', 3600.0)


class SeqClient:
    """Fake Parakeet /v1/transcribe returning canned window-relative segments."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append(kwargs)
        data = self.payloads[min(len(self.requests) - 1, len(self.payloads) - 1)]
        return httpx.Response(200, json=data, request=httpx.Request('POST', url))


def _receiver(monkeypatch, *, v2: bool, conversation='conv-collapse'):
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
    state = ListenSessionState()
    state.current_conversation_id = conversation
    collected = []
    host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid-collapse',
            websocket=SimpleNamespace(send_json=AsyncMock(), close=AsyncMock()),
            codec='pcm16',
            sample_rate=RATE,
            channels=1,
            source='desktop',
        ),
        state=state,
        is_multi_channel=False,
        use_custom_stt=False,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=collected.extend),
        client_device_context=SimpleNamespace(platform='test'),
        language='en',
        stt_language='multi',
        multi_lang_enabled=True,
        stt_model='parakeet-window',
        stt_service=st.STTService.parakeet,
        vocabulary=[],
        spawn=lambda coro, **kw: coro.close(),
    )
    receiver = ListenReceiver(host, [], {})
    receiver.collected = collected
    return receiver


async def _feed(receiver, socket, pattern, *, chunk=0.5):
    """Feed decoded frames through the capture clock and the live socket.

    Mirrors the receive loop: every chunk is accepted by the timeline, gets an
    ownership range, and is sent to the provider with its capture start sample
    exactly the way ``flush_live_stt_buffer`` does.
    """
    timeline = receiver.capture_timeline
    wall = T0
    mono = 0.0
    for seconds, speech in pattern:
        pcm = (b'\x01\x00' if speech else b'\x00\x00') * int(chunk * RATE)
        for _ in range(int(seconds / chunk)):
            wall += chunk
            mono += chunk
            start, end, _ = timeline.accept(pcm, wall, mono)
            receiver._note_accepted_frame(start, end)
            assert socket.send(pcm, start_sample=start)
            await REAL_SLEEP(0)


async def _wait_posts(client, count: int) -> None:
    deadline = asyncio.get_running_loop().time() + 5
    while len(client.requests) < count:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f'expected {count} POSTs, got {len(client.requests)}')
        await REAL_SLEEP(0)


# ---------------------------------------------------------------------------
# The dev collapse, reproduced hermetically through the real managed chain
# ---------------------------------------------------------------------------


async def _drive_window_session(monkeypatch, *, v2: bool):
    """Real receiver -> managed chain -> window leg -> fake TDT server.

    Post sequence is deterministic: pace pinned far above the audio length, so
    the only posts are the gate's hangover-finalize pause post (triggered on
    the second silence chunk, running just after speech resumes) and the drain
    post. Audio: 6 s speech, 1 s delivered silence, 3 s speech -> gated spans
    [0, 6.5] and [6.5, 9.5] over capture [0, 6.5] and [7.0, 9.5], anchor 4.5
    after the pause post emits the first sentence.
    """
    receiver = _receiver(monkeypatch, v2=v2)
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '600')
    client = SeqClient(
        [
            {'segments': [{'text': 'One.', 'start': 0.3, 'end': 4.5}]},
            {
                'segments': [
                    # Window-relative to the drain window [4.5, 9.5].
                    {'text': 'Two.', 'start': 0.2, 'end': 0.9},
                    # Past the posted window duration (5.0 s), like the dev
                    # TDT drift: unmappable, must not become a segment.
                    {'text': 'One.', 'start': 5.8, 'end': 7.5},
                ]
            },
        ]
    )
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    assert await receiver.initialize_stt()
    socket = receiver.stt_socket
    assert isinstance(socket.raw, window.WindowedParakeetSocket)
    await _feed(receiver, socket, [(6, True), (1, False), (3, True)])
    await _wait_posts(client, 1)
    await socket.drain_and_close()
    assert len(client.requests) == 2
    return receiver


@pytest.mark.asyncio
async def test_window_drifted_timestamps_do_not_collapse_onto_span_edge(monkeypatch):
    """The dev failure: TDT returns drifted timestamps on a later window post.

    Before the fix the drifted segment was emitted with start == end at the
    drain window's end — the end of the last accepted send span — and persisted
    as a v2 zero-length segment exactly like the dev probe conversations
    (``(18.9, 18.9)``, ``(28.82, 28.82)`` x3, ``(39.2, 39.2)``).
    """
    receiver = await _drive_window_session(monkeypatch, v2=True)

    assert [segment['text'] for segment in receiver.collected] == ['One.', 'Two.']
    for segment in receiver.collected:
        assert segment['end'] > segment['start'], f'zero-length segment collapsed onto a span edge: {segment}'
        assert segment.get('_conversation_id') == 'conv-collapse'
    timeline = receiver.capture_timeline
    # Pause post: window [0, 6.5], first sentence maps 1:1 onto the span.
    first = receiver.collected[0]
    assert first['start'] == pytest.approx(timeline.wall(int(0.3 * RATE)))
    assert first['end'] == pytest.approx(timeline.wall(int(4.5 * RATE)))
    # Drain post: window-relative [0.2, 0.9] over anchor 4.5 — a later-batch
    # segment mapped through the accepted send span, start < end preserved.
    good = receiver.collected[1]
    assert good['start'] == pytest.approx(timeline.wall(int(4.7 * RATE)))
    assert good['end'] == pytest.approx(timeline.wall(int(5.4 * RATE)))


@pytest.mark.asyncio
async def test_window_drifted_timestamps_do_not_collapse_clock_only(monkeypatch):
    """Flag-off sessions keep legacy times and must not collapse either.

    The same collapse would persist a zero-length segment through the legacy
    path (the managed chain's offset rebase keeps start == end), which is the
    prod-relevant shape: prod runs the legacy chain but the same window
    adapter and translator feed its speaker-ID windows.
    """
    receiver = await _drive_window_session(monkeypatch, v2=False)

    assert [segment['text'] for segment in receiver.collected] == ['One.', 'Two.']
    for segment in receiver.collected:
        assert segment['end'] > segment['start'], f'zero-length segment collapsed: {segment}'
        assert segment['end'] - segment['start'] >= 0.5


# ---------------------------------------------------------------------------
# Translator hardening: never clamp two provider times onto one point
# ---------------------------------------------------------------------------


class TestSendMapCollapseRejection:
    def test_two_times_beyond_span_end_within_tolerance_reject(self):
        """Both endpoints past a span end (<= tolerance) used to clamp onto it."""
        sm = SendMap(RATE)
        sm.add_accepted_spans([(0, RATE)])
        # Distinct provider times, both within the 0.25 s edge tolerance past
        # the span end: clamping both onto the span end would fabricate a
        # zero-length interval, so the mapping must fail closed instead.
        assert sm.map_interval(int(1.05 * RATE), int(1.15 * RATE)) is None
        assert sm.map_interval(int(1.001 * RATE), int(1.249 * RATE)) is None

    def test_start_in_span_with_end_overshoot_keeps_positive_interval(self):
        sm = SendMap(RATE)
        sm.add_accepted_spans([(0, RATE)])
        mapped = sm.map_interval(int(0.9 * RATE), int(1.1 * RATE))
        assert mapped == (int(0.9 * RATE), RATE)

    def test_later_batch_segment_maps_independently_across_spans(self):
        """A segment after the first provider batch keeps start < end.

        Two accepted sends with a skipped capture silence between them (the
        later batch sits at provider time [0.9 s, 1.1 s]); the segment starts
        in the first span and ends in the second: each endpoint maps through
        its own span, never through the skip.
        """
        sm = SendMap(RATE)
        sm.add_accepted_spans([(0, RATE), (5 * RATE, RATE)])
        mapped = sm.map_interval(RATE - 1600, RATE + 1600)
        assert mapped == (RATE - 1600, 5 * RATE + 1600)
        assert mapped[0] < mapped[1]


class TestTranslatorDegenerateIntervals:
    def _timeline(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(b'\x01\x00' * RATE, arrival_wall=T0, arrival_monotonic=0.0)
        return timeline

    def test_v2_rejects_zero_length_provider_interval(self):
        translator = ProviderEpochTranslator(self._timeline(), RATE, project_times=True)
        translator.note_accepted(0, 2 * RATE)
        translated = translator.translate([{'start': 1.0, 'end': 1.0, 'text': 'partial'}])
        assert translated == []
        assert translator.rejected_segments == 1

    def test_clock_only_keeps_zero_length_provider_segment_without_window(self):
        """Flag-off must stay byte-identical: Modulate partials (start == end)
        still flow through with their provider times, only without a capture
        window."""
        translator = ProviderEpochTranslator(self._timeline(), RATE, project_times=False)
        translator.note_accepted(0, 2 * RATE)
        translated = translator.translate([{'start': 1.0, 'end': 1.0, 'text': 'partial'}])
        assert [segment['text'] for segment in translated] == ['partial']
        assert translated[0]['start'] == 1.0 and translated[0]['end'] == 1.0
        assert '_capture_start_sample' not in translated[0]
        assert translator.rejected_segments == 1

    def test_v2_rejects_collapsed_interval_with_reason(self):
        reasons = []
        translator = ProviderEpochTranslator(self._timeline(), RATE, project_times=True, on_reject=reasons.append)
        translator.note_accepted(0, RATE)
        translated = translator.translate([{'start': 1.05, 'end': 1.2, 'text': 'collapsed'}])
        assert translated == []
        assert reasons == ['collapsed_interval']
        assert translator.rejected_segments == 1


# ---------------------------------------------------------------------------
# LIVE_SPEAKER_CAPTURE_CLOCK: runtime kill switch for the always-on §9 path
# ---------------------------------------------------------------------------


class TestSpeakerCaptureClockKillSwitch:
    def test_default_on_and_falsy_values_off(self, monkeypatch):
        from config.audio_timeline import live_speaker_capture_clock_enabled

        monkeypatch.delenv('LIVE_SPEAKER_CAPTURE_CLOCK', raising=False)
        assert live_speaker_capture_clock_enabled() is True
        for value in ('0', 'false', 'no', 'off', ' FALSE '):
            monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', value)
            assert live_speaker_capture_clock_enabled() is False
        for value in ('', '1', 'true', 'on', 'anything-else'):
            monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', value)
            assert live_speaker_capture_clock_enabled() is True

    @pytest.mark.asyncio
    async def test_clock_only_windows_attached_by_default_reverted_when_off(self, monkeypatch):
        receiver = _receiver(monkeypatch, v2=False)
        timeline = receiver.capture_timeline
        timeline.accept(b'\x01\x00' * (2 * RATE), arrival_wall=T0, arrival_monotonic=0.0)
        segment = {
            'id': 'seg-1',
            'start': 0.25,
            'end': 1.25,
            'text': 'hello',
            '_capture_start_sample': int(0.25 * RATE),
            '_capture_end_sample': int(1.25 * RATE),
        }
        receiver._enqueue_clock_positioned_segments([dict(segment)])
        attached = receiver.collected[0]
        assert attached['_capture_abs_start'] == pytest.approx(T0 + 0.25)
        assert attached['_capture_abs_end'] == pytest.approx(T0 + 1.25)
        assert attached['start'] == 0.25 and attached['end'] == 1.25

        monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', 'false')
        receiver.collected.clear()
        receiver._enqueue_clock_positioned_segments([dict(segment)])
        reverted = receiver.collected[0]
        # Transcript identical, speaker-ID window gone: the matcher falls back
        # to the legacy first-audio + provider-time formula.
        assert reverted['start'] == 0.25 and reverted['end'] == 1.25
        assert '_capture_abs_start' not in reverted
        assert '_capture_start_sample' not in reverted


# ---------------------------------------------------------------------------
# Provider-path audit: every path the translator serves maps a later batch
# ---------------------------------------------------------------------------


class _RecordingSocket(STTSocket):
    """Fake raw provider socket that accepts everything it is sent."""

    manages_vad = False

    def __init__(self):
        self.sent_samples = 0

    def send(self, data: bytes) -> bool:
        self.sent_samples += len(data) // 2
        return True

    def finalize(self) -> None:
        pass

    def finish(self) -> None:
        pass

    @property
    def is_connection_dead(self) -> bool:
        return False

    @property
    def death_reason(self):
        return None


def _audit_receiver(monkeypatch, *, gate):
    """Receiver + fresh epoch in the legacy (non-managed) wiring shape."""
    receiver = _receiver(monkeypatch, v2=True, conversation='conv-audit')
    receiver.vad_gate = gate
    _parakeet_callback, _modulate_callback, epoch = receiver._build_stt_callbacks()
    return receiver, epoch


@pytest.mark.asyncio
async def test_gated_socket_later_batch_maps_across_skipped_silence(monkeypatch):
    """Legacy Deepgram/Soniox shape: receiver gate active, non-passthrough.

    Provider time is the gated stream (cumulative audio actually forwarded);
    the epoch's send spans are the gate's ``send_spans``. A segment from the
    second speech burst must map across the skipped silence with start < end.
    """
    receiver, epoch = _audit_receiver(
        monkeypatch, gate=vad_gate.VADStreamingGate(sample_rate=RATE, mode='active', hangover_ms=300)
    )
    gated = GatedSTTSocket(_RecordingSocket(), gate=receiver.vad_gate, passthrough_audio=False, send_tracker=epoch)
    await _feed(receiver, gated, [(4, True), (2, False), (3, True)])
    # Gated spans at 0.5 s chunks: [0, 4.5] (speech + one hangover chunk)
    # then [6.0, 9.0] (the burst resumes; a 0.5 s chunk exceeds the 300 ms
    # pre-roll budget, so the span starts at the onset chunk). Provider time
    # 4.8 s is 0.3 s into the second span -> capture 6.3 s.
    translated = epoch.translate([{'start': 4.8, 'end': 6.4, 'text': 'later', 'speaker': 'SPEAKER_0'}])
    assert translated and translated[0]['end'] > translated[0]['start']
    assert translated[0]['_capture_start_sample'] == int(6.3 * RATE)
    assert translated[0]['_capture_end_sample'] == int(7.9 * RATE)


@pytest.mark.asyncio
async def test_passthrough_socket_later_batch_maps(monkeypatch):
    """Modulate shape: gate in passthrough, the provider sees every frame."""
    receiver, epoch = _audit_receiver(monkeypatch, gate=None)
    passthrough = GatedSTTSocket(_RecordingSocket(), gate=None, passthrough_audio=True, send_tracker=epoch)
    await _feed(receiver, passthrough, [(4, True), (2, False), (3, True)])
    translated = epoch.translate([{'start': 6.5, 'end': 8.2, 'text': 'later', 'speaker': 'SPEAKER_00'}])
    assert translated and translated[0]['end'] > translated[0]['start']
    assert translated[0]['_capture_start_sample'] == int(6.5 * RATE)
    assert translated[0]['_capture_end_sample'] == int(8.2 * RATE)


@pytest.mark.asyncio
async def test_gate_off_direct_sends_later_batch_maps(monkeypatch):
    """Gate off / gate lost mid-session: every send is one contiguous span.

    This is also the relay shape of the Parakeet RNNT WebSocket leg
    (``ParakeetWebSocketSocket``): the provider timestamps the audio stream it
    received, so the mapping is the recorded direct sends.
    """
    receiver, epoch = _audit_receiver(monkeypatch, gate=None)
    direct = GatedSTTSocket(_RecordingSocket(), gate=None, send_tracker=epoch)
    await _feed(receiver, direct, [(4, True), (2, False), (3, True)])
    translated = epoch.translate([{'start': 6.5, 'end': 8.2, 'text': 'later', 'speaker': 'SPEAKER_00'}])
    assert translated and translated[0]['end'] > translated[0]['start']
    assert translated[0]['_capture_start_sample'] == int(6.5 * RATE)
    assert translated[0]['_capture_end_sample'] == int(8.2 * RATE)
