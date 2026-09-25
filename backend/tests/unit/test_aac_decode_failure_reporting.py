"""Regression: undecodable AAC frames must fail loudly, not silently.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance fix; the AAC
decoder collapsed every FFmpeg rejection into ``b''`` so the receiver's
decode-failure contract (per-frame warning, streak, ``silent_mic`` fallback)
never fired for AAC, leaving only FFmpeg's context-free
``ERROR:libav.aac:Channel element 1.7 is not allocated`` / ``Reserved bit
set.`` native lines (~130 events / 30 min across the ``libav.aac`` family,
Loop S sensor, 2026-08-30/31) as the trace of sessions that recorded with no
transcript, no ring buffer, and no fallback metric. Same collapse at the
audio-decode boundary as #11732 fixed at the opus boundary.

These tests drive the real ``AACDecoder`` (real PyAV codec context, real
ADTS bytes encoded in-process) and the real ``ListenReceiver.receive_data``
loop — only the websocket transport is scripted, the pattern
``test_listen_receiver_decode_failure_report.py`` established for opus.
Corruption shapes are the deterministic per-signature mutations validated
against the pinned PyAV 12.0.0 (see the operational note
``docs/operational/aac-decode-failure-reporting.md``).
"""

import array
import logging
import math
import os
import tempfile
import threading
from types import SimpleNamespace

import av
import numpy as np
import pytest

from routers.listen import receiver as receiver_module
from routers.listen.receiver import DECODE_FAILURE_STREAK_ALERT, ListenReceiver
from utils.aac import AACDecodeError, AACDecoder, NativeDuplicateSuppressionFilter

# ---------------------------------------------------------------------------
# Real ADTS frames, encoded in-process (no fixtures, no network).
# ---------------------------------------------------------------------------


def _encode_adts_frames(count: int = 10, rate: int = 16000, layout: str = 'mono', channels: int = 1) -> list:
    """Real AAC/ADTS frames via a real PyAV encoder (mono/stereo, any rate)."""
    with tempfile.NamedTemporaryFile(suffix='.aac', delete=False) as tmp:
        path = tmp.name
    try:
        container = av.open(path, 'w', format='adts')
        stream = container.add_stream('aac', rate=rate)
        stream.layout = layout
        for i in range(count):
            n = 1024
            if channels == 1:
                pcm = array.array('h', (int(10000 * math.sin(i * 300 * t / rate)) for t in range(n)))
                arr = np.frombuffer(pcm, dtype='int16').reshape(1, -1)
            else:
                left = array.array('h', (int(9000 * math.sin(i * 200 * t / rate)) for t in range(n)))
                right = array.array('h', (int(7000 * math.cos(i * 130 * t / rate)) for t in range(n)))
                interleaved = array.array('h')
                for l, r in zip(left, right):
                    interleaved.append(l)
                    interleaved.append(r)
                arr = np.frombuffer(interleaved, dtype='int16').reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(arr, format='s16', layout=layout)
            frame.sample_rate = rate
            pkts = stream.encode(frame)
            if pkts:
                container.mux(pkts)
        pkts = stream.close()
        if pkts:
            container.mux(pkts)
        container.close()
        with open(path, 'rb') as fh:
            data = fh.read()
    finally:
        os.unlink(path)

    frames = []
    i = 0
    while i + 7 <= len(data):
        if data[i] == 0xFF and (data[i + 1] & 0xF0) == 0xF0:
            length = ((data[i + 3] & 0x03) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5)
            frames.append(data[i : i + length])
            i += length
        else:
            i += 1
    return frames


def _capture_native_logs():
    """Handler capturing libav.aac records; returns (records, remover)."""
    records: list = []

    def _capture(record: logging.LogRecord) -> None:
        records.append(record)

    handler = logging.Handler()
    handler.emit = _capture  # type: ignore[assignment, method-assign]  # test-local capture
    logger = logging.getLogger('libav.aac')
    logger.addHandler(handler)
    return records, lambda: logger.removeHandler(handler)


@pytest.fixture(scope='module')
def adts_frames():
    return _encode_adts_frames()


@pytest.fixture(scope='module')
def adts_frames_stereo():
    return _encode_adts_frames(count=6, layout='stereo', channels=2)


@pytest.fixture(scope='module')
def adts_frames_44k():
    return _encode_adts_frames(count=6, rate=44100)


# ---------------------------------------------------------------------------
# Deterministic per-signature corruption shapes (probe-validated)
# ---------------------------------------------------------------------------


def _corrupt_payload(frame: bytes) -> bytes:
    """Valid ADTS header, scrambled payload — the shape behind the prod
    ``channel element … is not allocated`` / ``Reserved bit set.`` lines."""
    return frame[:7] + bytes((b * 13 + 7) & 0xFF for b in frame[7:])


def _bitflip_first_quarter(frame: bytes) -> bytes:
    """One flipped byte in the first quarter — ``Number of bands (…) exceeds
    limit (…)`` / ``channel element`` shapes; deterministic per frame."""
    pos = len(frame) // 4
    return frame[:pos] + bytes([frame[pos] ^ 0xFF]) + frame[pos + 1 :]


def _overwrite_with_ff_run(frame: bytes) -> bytes:
    """16-byte 0xFF run after the header — ``Error decoding AAC frame
    header.`` (a false sync-word pattern inside the payload)."""
    return frame[:7] + b'\xff' * 16 + frame[23:]


def _truncate(frame: bytes, keep: float = 0.7) -> bytes:
    return frame[: int(len(frame) * keep)]


# ---------------------------------------------------------------------------
# Real decoder: typed failure instead of silence
# ---------------------------------------------------------------------------


class TestAACDecoderRaisesTypedError:

    def test_corrupt_frame_raises_aac_decode_error(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_corrupt_payload(adts_frames[1]))

    def test_truncated_frame_raises_aac_decode_error(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_truncate(adts_frames[1]))

    def test_garbage_without_adts_sync_raises_aac_decode_error(self):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(bytes(60))

    def test_band_limit_corruption_raises_aac_decode_error(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_bitflip_first_quarter(adts_frames[2]))

    def test_false_sync_run_raises_aac_decode_error(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_overwrite_with_ff_run(adts_frames[3]))

    def test_header_only_payload_raises_aac_decode_error(self, adts_frames):
        """A truncated header-only fragment (< 7 bytes) is rejected, not
        silently skipped: the receiver's streak must see it, because a client
        sending header fragments mid-stream is the desync shape behind the
        prod ``Error decoding AAC frame header.`` lines."""
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(adts_frames[1][:6])

    def test_stereo_corrupt_frame_raises_aac_decode_error(self, adts_frames_stereo):
        """Corruption detection must not depend on channel count: a scrambled
        stereo payload raises the same typed failure through the stereo
        resampler path."""
        decoder = AACDecoder(uid='u', session_id='s', channels=2)
        with pytest.raises(AACDecodeError):
            decoder.decode(_corrupt_payload(adts_frames_stereo[1]))

    def test_error_message_carries_ffmpeg_detail_and_cause(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError) as excinfo:
            decoder.decode(_corrupt_payload(adts_frames[1]))
        assert str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, av.AVError)

    def test_clean_frames_decode_to_pcm(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        pcm = decoder.decode(adts_frames[1])
        assert pcm
        # mono s16 PCM: even byte count, at least one 1024-sample frame
        assert len(pcm) % 2 == 0
        assert len(pcm) >= 2048

    def test_persistent_context_decodes_a_whole_stream(self, adts_frames):
        """The codec context is persistent by design — every frame of a real
        stream must decode through the one context (regression guard for the
        decode() rewrite touching context lifecycle)."""
        decoder = AACDecoder(uid='u', session_id='s')
        total = 0
        for frame in adts_frames[1:]:
            pcm = decoder.decode(frame)
            assert len(pcm) % 2 == 0
            total += len(pcm)
        assert total >= 2048 * (len(adts_frames) - 1)

    def test_decoder_recovers_after_a_corrupt_frame(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        first = decoder.decode(adts_frames[1])
        with pytest.raises(AACDecodeError):
            decoder.decode(_corrupt_payload(adts_frames[2]))
        after = decoder.decode(adts_frames[3])
        assert first and after

    def test_empty_payload_still_returns_empty_bytes(self):
        decoder = AACDecoder(uid='u', session_id='s')
        assert decoder.decode(b'') == b''


# ---------------------------------------------------------------------------
# Constructor contract: resampler configuration actually used
# ---------------------------------------------------------------------------


class TestDecoderResamplerContract:

    def test_stereo_frames_decode_to_two_channel_pcm(self, adts_frames_stereo):
        """channels=2 must configure a stereo resampler: decoded PCM stays
        two-channel (double the mono byte count for the same samples)."""
        decoder = AACDecoder(uid='u', session_id='s', channels=2)
        mono = AACDecoder(uid='u', session_id='s', channels=1)
        pcm_stereo = decoder.decode(adts_frames_stereo[1])
        pcm_mono_of_stereo = mono.decode(adts_frames_stereo[1])
        assert pcm_stereo and pcm_mono_of_stereo
        assert len(pcm_stereo) == 2 * len(pcm_mono_of_stereo)

    def test_44100hz_input_resamples_to_16k(self, adts_frames_44k):
        """sample_rate=16000 must drive real resampling: 44.1 kHz input comes
        back as 16 kHz PCM. Expected samples derive from the frames the ADTS
        parser actually found minus the encoder-priming frame (index 0);
        measured output lands within 5% of that."""
        decoder = AACDecoder(uid='u', session_id='s', sample_rate=16000)
        decoded_frames = adts_frames_44k[1:]
        total_bytes = 0
        for frame in decoded_frames:
            total_bytes += len(decoder.decode(frame))
        total_samples = total_bytes // 2
        expected = len(decoded_frames) * 1024 * 16000 / 44100
        assert abs(total_samples - expected) < expected * 0.05


# ---------------------------------------------------------------------------
# Native duplicate suppression: no context-free ERROR:libav.aac lines
# ---------------------------------------------------------------------------


class TestNativeDuplicateSuppressed:

    def test_corrupt_decode_emits_no_libav_aac_error_log(self, adts_frames):
        decoder = AACDecoder(uid='u', session_id='s')
        records, remove = _capture_native_logs()
        try:
            with pytest.raises(AACDecodeError):
                decoder.decode(_corrupt_payload(adts_frames[1]))
        finally:
            remove()
        assert not [r for r in records if r.levelno >= logging.ERROR]

    def test_unsuppressed_the_same_corruption_does_emit_native_log(self, adts_frames):
        """Negative control: with the suppression filter removed, the same
        corrupt frame DOES produce the native libav.aac ERROR — proving the
        suppression test is not vacuous."""
        corrupt = _corrupt_payload(adts_frames[1])
        libav_logger = logging.getLogger('libav.aac')
        filters_before = list(libav_logger.filters)
        libav_logger.filters = [
            f for f in libav_logger.filters if not isinstance(f, NativeDuplicateSuppressionFilter)
        ]  # negative control
        records, remove = _capture_native_logs()
        try:
            decoder = AACDecoder(uid='u', session_id='s')
            with pytest.raises(AACDecodeError):
                decoder.decode(corrupt)
        finally:
            remove()
            libav_logger.filters = filters_before
        assert records, 'expected the native libav.aac ERROR without suppression'

    def test_suppression_scoped_to_decode_window_only(self, adts_frames):
        """Outside our own decode call the libav.aac logger must stay live —
        other av users (transcode endpoints, speech profiles) still get their
        native error logs. The error raised inside decode must not suppress a
        later, unrelated native error."""
        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_corrupt_payload(adts_frames[1]))

        records, remove = _capture_native_logs()
        try:
            logging.getLogger('libav.aac').error('channel element 9.9 is not allocated')
        finally:
            remove()
        assert len(records) == 1

    def test_suppression_window_is_thread_local(self):
        """One session mid-decode must not mute a concurrent thread's native
        error: the flag is thread-local by contract."""
        import utils.aac as aac_module

        other_thread_records: list = []
        ready = threading.Event()
        release = threading.Event()

        def other_thread_decode():
            records, remove = _capture_native_logs()
            try:
                # this thread's flag is unset, so its native log must flow
                # even while the main thread holds its own window open.
                ready.set()
                release.wait(timeout=5)
                logging.getLogger('libav.aac').error('channel element 7.7 is not allocated')
            finally:
                remove()
                other_thread_records.extend(records)

        main_flag_active = False

        def hold_window():
            nonlocal main_flag_active
            aac_module.aac_decode_in_progress.active = True
            main_flag_active = getattr(aac_module.aac_decode_in_progress, 'active', False)
            ready.wait(timeout=5)
            release.set()
            aac_module.aac_decode_in_progress.active = False

        t_hold = threading.Thread(target=hold_window)
        t_other = threading.Thread(target=other_thread_decode)
        t_other.start()
        t_hold.start()
        t_hold.join(timeout=5)
        t_other.join(timeout=5)

        assert main_flag_active, 'main thread window opened'
        assert other_thread_records, 'concurrent thread native log must not be muted'
        assert not getattr(aac_module.aac_decode_in_progress, 'active', False)

    def test_flag_cleared_when_decode_raises(self, adts_frames):
        """The finally-clause contract: even the raising path must leave the
        window closed (a stuck-open flag would mute all future native logs
        in this thread)."""
        import utils.aac as aac_module

        decoder = AACDecoder(uid='u', session_id='s')
        with pytest.raises(AACDecodeError):
            decoder.decode(_corrupt_payload(adts_frames[1]))
        assert not getattr(aac_module.aac_decode_in_progress, 'active', False)

    def test_suppression_filter_directly_reflects_flag(self):
        """Unit contract of the filter: flag unset → record passes; flag set
        in this thread → record dropped."""
        import utils.aac as aac_module

        record = logging.LogRecord('libav.aac', logging.ERROR, __file__, 1, 'msg', None, None)
        filt = NativeDuplicateSuppressionFilter()
        aac_module.aac_decode_in_progress.active = True
        try:
            assert filt.filter(record) is False
        finally:
            aac_module.aac_decode_in_progress.active = False
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# Real receiver loop: streak, warning shape, one-shot silent-mic fallback
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


def _host(websocket, channels=1):
    return SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, uid='uid-1', codec='aac', sample_rate=16000, channels=channels),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=lambda _segments: None),
        start_live_transcription=lambda: None,
    )


def _receiver(frames, channels=1):
    websocket = _FramesWebSocket(list(frames) + [{'type': 'websocket.disconnect', 'code': 1000}])
    receiver = ListenReceiver(_host(websocket, channels), [], {})
    receiver.aac_decoder = AACDecoder(uid='uid-1', session_id='sid-1', channels=channels)
    return receiver


@pytest.fixture
def recorded_fallbacks(monkeypatch):
    calls = []
    monkeypatch.setattr(receiver_module, 'record_fallback', lambda **kwargs: calls.append(kwargs))
    return calls


class TestReceiverIntegration:

    @pytest.mark.anyio
    async def test_corrupt_aac_frame_logs_codec_message_and_advances_streak(
        self, adts_frames, caplog, recorded_fallbacks
    ):
        corrupt = _corrupt_payload(adts_frames[1])
        receiver = _receiver([{'bytes': corrupt}])
        with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
            await receiver.receive_data()

        (message,) = [r.getMessage() for r in caplog.records if 'decode failed' in r.getMessage()]
        assert 'codec=aac' in message
        assert 'type=AACDecodeError' in message
        assert f'bytes={len(corrupt)}' in message
        assert 'streak=1' in message

    @pytest.mark.anyio
    async def test_aac_stream_undecodable_reports_silent_mic_once(self, recorded_fallbacks):
        frame = bytes(60)
        frames = [{'bytes': frame}] * (DECODE_FAILURE_STREAK_ALERT + 3)
        receiver = _receiver(frames)

        await receiver.receive_data()

        assert receiver.decode_failure_streak == DECODE_FAILURE_STREAK_ALERT + 3
        assert recorded_fallbacks == [
            {
                'component': 'silent_mic',
                'from_mode': 'aac',
                'to_mode': 'none',
                'reason': 'capability_mismatch',
                'outcome': 'exhausted',
            }
        ]

    @pytest.mark.anyio
    async def test_recovery_after_corrupt_frames_resets_streak_no_fallback(self, adts_frames, recorded_fallbacks):
        corrupt_then_clean = [{'bytes': _corrupt_payload(adts_frames[1])}] * 3 + [{'bytes': adts_frames[2]}]
        receiver = _receiver(corrupt_then_clean)

        await receiver.receive_data()

        assert receiver.decode_failure_streak == 0
        assert recorded_fallbacks == []

    @pytest.mark.anyio
    async def test_clean_aac_stream_produces_no_decode_failure_logs(self, adts_frames, caplog, recorded_fallbacks):
        frames = [{'bytes': f} for f in adts_frames[1:6]]
        receiver = _receiver(frames)

        with caplog.at_level(logging.WARNING, receiver_module.__name__):
            await receiver.receive_data()

        assert not [r for r in caplog.records if 'decode failed' in r.getMessage()]
        assert recorded_fallbacks == []

    @pytest.mark.anyio
    async def test_corrupt_and_clean_interleaved_resets_streak_each_recovery(
        self, adts_frames, caplog, recorded_fallbacks
    ):
        """The prod-relevant shape: a flaky client stream with corrupt frames
        scattered among good ones. Each good frame resets the streak, so the
        session never reaches the silent-mic threshold it must not reach —
        but every corrupt frame is still individually reported."""
        stream = []
        expected_failures = 0
        for i in range(1, 8):
            if i % 2 == 0:
                stream.append({'bytes': _corrupt_payload(adts_frames[i])})
                expected_failures += 1
            else:
                stream.append({'bytes': adts_frames[i]})
        receiver = _receiver(stream)

        with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
            await receiver.receive_data()

        failures = [r for r in caplog.records if 'decode failed' in r.getMessage()]
        assert len(failures) == expected_failures
        assert receiver.decode_failure_streak == 0
        assert recorded_fallbacks == []

    @pytest.mark.anyio
    async def test_decoder_recovers_after_burst_of_corrupt_frames(self, adts_frames, recorded_fallbacks):
        """A burst of corruption must not poison the persistent codec
        context: the first clean frame after a run of failures still decodes,
        and the streak resets — the flaky-network recovery shape."""
        frames = [{'bytes': _corrupt_payload(adts_frames[1])}] * 4 + [{'bytes': adts_frames[3]}]
        receiver = _receiver(frames)

        await receiver.receive_data()

        assert receiver.decode_failure_streak == 0
        assert recorded_fallbacks == []

    @pytest.mark.anyio
    async def test_second_consecutive_corrupt_frame_advances_streak(self, adts_frames, caplog):
        """The streak is per-frame evidence, cumulative across consecutive
        failures: the second corrupt frame logs streak=2 with the same
        codec/type shape (the per-frame report the prod feed lacked)."""
        corrupt = _corrupt_payload(adts_frames[1])
        receiver = _receiver([{'bytes': corrupt}, {'bytes': corrupt}])

        with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
            await receiver.receive_data()

        failures = [r.getMessage() for r in caplog.records if 'decode failed' in r.getMessage()]
        assert len(failures) == 2
        assert 'streak=1' in failures[0]
        assert 'streak=2' in failures[1]

    @pytest.mark.anyio
    async def test_initialize_decoders_builds_real_aac_decoder(self):
        """The production wiring path: initialize_decoders must construct the
        real AACDecoder for codec=aac with the request's uid, sample rate,
        and channel count (not leave the slot None, which would AttributeError
        into the streak path for every frame)."""
        websocket = _FramesWebSocket([{'type': 'websocket.disconnect', 'code': 1000}])
        host = _host(websocket)
        host.session_id = 'sid-real'
        receiver = ListenReceiver(host, [], {})

        receiver.initialize_decoders()

        assert isinstance(receiver.aac_decoder, AACDecoder)
        assert receiver.aac_decoder.uid == 'uid-1'
        assert receiver.aac_decoder.session_id == 'sid-real'
        assert receiver.aac_decoder.resampler.rate == 16000
