"""Unit tests for issue #22755:
Live STT speaker renumbering and audio re-transcription / overlap duplication.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from utils.stt.speaker_identity import (
    ConversationSpeakerIdAllocator,
    SpeakerProviderEpoch,
)
from utils.stt.parakeet_window import (
    RawSegment,
    WindowedParakeetSocket,
)
from utils.stt import live_session
from utils.stt import streaming as st


@pytest.mark.anyio
async def test_materialize_drops_already_emitted_and_prevents_zero_length():
    """Segments ending at or before last_emitted_end or collapsing to zero length are dropped."""
    socket = object.__new__(WindowedParakeetSocket)
    socket._last_emitted_end = 293.04
    socket._embedded_this_window = False
    socket._slice_pcm = lambda pcm, s, e: b""
    socket._assign_speaker = AsyncMock(return_value=0)

    # 1. Segment completely within previously emitted range: (290.76, 293.04)
    raw1 = RawSegment(text="hello", start=0.76, end=3.04)
    # 2. Segment straddling boundary with non-trivial tail: (291.68, 296.08)
    raw2 = RawSegment(text="dinner is ready", start=1.68, end=6.08)
    # 3. Degenerate zero-length / boundary-coincident segment: (292.00, 293.04) -> after trim (293.04, 293.04)
    raw3 = RawSegment(text="repeat", start=2.00, end=3.04)

    # Window starts at 290.00, duration 10.0
    emitted, beyond = await socket._materialize(
        [raw1, raw2, raw3],
        pcm=b"\x00" * 32000,
        start=290.0,
        dur=10.0,
    )

    # raw1 is dropped (already emitted <= 293.04)
    # raw3 is dropped (after trimming start to 293.04, end is <= start)
    # raw2 is trimmed to start at 293.04 and end at 296.08
    assert len(emitted) == 1
    assert emitted[0]["text"] == "dinner is ready"
    assert emitted[0]["start"] == 293.04
    assert emitted[0]["end"] == 296.08
    assert emitted[0]["start"] < emitted[0]["end"]


def test_successor_same_provider_preserves_speaker_scope_and_prevents_renumbering():
    """A same-provider successor socket maintains the same speaker_id_scope,

    ensuring ConversationSpeakerIdAllocator does not re-allocate new speaker IDs.
    """
    allocator = ConversationSpeakerIdAllocator()

    # Initial stream epoch for provider
    epoch = SpeakerProviderEpoch("session-connection-123")
    first_block = [
        {"speaker": "SPEAKER_0", "start": 10.0, "end": 15.0, "text": "First voice"},
        {"speaker": "SPEAKER_1", "start": 15.0, "end": 20.0, "text": "Second voice"},
    ]
    epoch.stamp(first_block, "parakeet")
    for s in first_block:
        allocator.assign(s)

    assert first_block[0]["speaker_id"] == 0
    assert first_block[1]["speaker_id"] == 1
    initial_scope = first_block[0]["speaker_id_scope"]

    # Mid-session successor socket connects with same_provider=True (reusing the epoch)
    successor_epoch = epoch  # Preserved across same-provider replacement
    second_block = [
        {"speaker": "SPEAKER_0", "start": 25.0, "end": 30.0, "text": "First voice again"},
        {"speaker": "SPEAKER_1", "start": 30.0, "end": 35.0, "text": "Second voice again"},
    ]
    successor_epoch.stamp(second_block, "parakeet")
    for s in second_block:
        allocator.assign(s)

    # Speaker IDs must be preserved (0 and 1), NOT reallocated to 2 and 3!
    assert second_block[0]["speaker_id_scope"] == initial_scope
    assert second_block[0]["speaker_id"] == 0
    assert second_block[1]["speaker_id"] == 1


@pytest.mark.anyio
async def test_production_callback_deduplication_against_last_end(monkeypatch):
    """Drives the actual production callback in live_session to verify that replayed audio
    segments are trimmed or dropped against session.last_end without generating degenerate segments.
    """
    from types import SimpleNamespace
    from tests.unit.test_live_speaker_carry import _managed_receiver

    callbacks = []
    raw_socket = SimpleNamespace(is_connection_dead=False, finish=lambda: None, send=lambda data: True)

    async def connect_soniox(callback, *args, **kwargs):
        callbacks.append(callback)
        return raw_socket

    async def pick_primary(**kwargs):
        return await kwargs['connect_primary'](), kwargs['primary_service']

    monkeypatch.setattr(st, 'process_audio_soniox', connect_soniox)
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(st, 'deepgram_fallback_model', lambda language: None)
    monkeypatch.setattr(live_session.st, 'connect_stt_socket_with_fallback', pick_primary)
    monkeypatch.setenv('SONIOX_API_KEY', 'test')

    receiver, stamped = _managed_receiver()
    session = live_session.LiveChainSession(receiver)
    await session.connect(16000)
    assert len(callbacks) == 1

    # Simulate existing progress up to 293.04
    session.last_end = 293.04

    # Invoke the actual production callback with replayed/overlapping audio
    incoming = [
        {"speaker": "SPEAKER_0", "start": 290.76, "end": 293.04, "text": "old phrase"},
        {"speaker": "SPEAKER_0", "start": 291.68, "end": 296.08, "text": "overlapping phrase"},
        {"speaker": "SPEAKER_0", "start": 292.50, "end": 293.04, "text": "degenerate phrase"},
        {"speaker": "SPEAKER_1", "start": 296.50, "end": 300.00, "text": "new phrase"},
    ]
    callbacks[0](incoming)

    # Verify that the production receiver received deduplicated segments:
    # 1. "old phrase" dropped (raw_end <= 293.04)
    # 2. "degenerate phrase" dropped (end <= start after trim)
    # 3. "overlapping phrase" trimmed to (293.04, 296.08)
    # 4. "new phrase" kept as-is (296.50, 300.00)
    assert len(stamped) == 1
    emitted = stamped[0]
    assert len(emitted) == 2
    assert emitted[0]["text"] == "overlapping phrase"
    assert emitted[0]["start"] == 293.04
    assert emitted[0]["end"] == 296.08

    assert emitted[1]["text"] == "new phrase"
    assert emitted[1]["start"] == 296.50
    assert emitted[1]["end"] == 300.00
    assert session.last_end == 300.00


@pytest.mark.anyio
async def test_mid_session_parakeet_window_replacement_emits_fresh_audio():
    """Verify that a successor WindowedParakeetSocket created mid-session (session.last_end > 0)
    measures stream time on its own socket axis (starting at 0.0) and emits fresh audio
    instead of dropping it due to cross-axis last_emitted_end seeding.
    """
    # 1. Correct successor socket: _last_emitted_end starts at 0.0 (the socket's own stream axis)
    socket = object.__new__(WindowedParakeetSocket)
    socket._last_emitted_end = 0.0
    socket._embedded_this_window = False
    socket._slice_pcm = lambda pcm, s, e: b""
    socket._assign_speaker = AsyncMock(return_value=0)
    socket._record_materialize_drop = MagicMock()

    raw = RawSegment(text="fresh words after reconnect", start=1.0, end=4.5)

    emitted, beyond = await socket._materialize(
        [raw],
        pcm=b"\x00" * 32000,
        start=0.0,
        dur=10.0,
    )

    # Fresh audio must be emitted, NOT dropped as 'already_emitted'
    assert len(emitted) == 1
    assert emitted[0]["text"] == "fresh words after reconnect"
    assert emitted[0]["start"] == 1.0
    assert emitted[0]["end"] == 4.5
    # The socket's stream boundary advances to 4.5
    socket._last_emitted_end = max(socket._last_emitted_end, max(float(item["end"]) for item in emitted))
    assert socket._last_emitted_end == 4.5
    socket._record_materialize_drop.assert_not_called()

    # 2. Bugged socket: if seeded with session.last_end = 600.0, _materialize drops all fresh audio
    bugged_socket = object.__new__(WindowedParakeetSocket)
    bugged_socket._last_emitted_end = 600.0  # Erroneous cross-axis seeding
    bugged_socket._embedded_this_window = False
    bugged_socket._slice_pcm = lambda pcm, s, e: b""
    bugged_socket._assign_speaker = AsyncMock(return_value=0)
    bugged_socket._record_materialize_drop = MagicMock()

    bugged_emitted, _ = await bugged_socket._materialize(
        [raw],
        pcm=b"\x00" * 32000,
        start=0.0,
        dur=10.0,
    )
    # The bug would silently drop all fresh audio whose stream end (4.5) <= 600.0!
    assert len(bugged_emitted) == 0


@pytest.mark.anyio
async def test_new_window_socket_axis_not_contaminated_by_session_last_end(monkeypatch):
    """Verify that LiveChainSession.new_window does not seed last_emitted_end with session.last_end,
    ensuring that a successor socket preserves its own stream clock boundary at 0.0.
    """
    from types import SimpleNamespace
    from tests.unit.test_live_speaker_carry import _managed_receiver

    created_sockets = []

    class MockWindowSocket:
        def __init__(self):
            self.last_emitted_end = 0.0
            self.allow_no_text_rescue = False
            self.progress_deadline_enabled = False
            self.is_connection_dead = False

        def finish(self):
            pass

    def mock_connect_window(callback, sample_rate):
        sock = MockWindowSocket()
        created_sockets.append(sock)
        return sock

    monkeypatch.setattr("utils.stt.parakeet_window.connect_window", mock_connect_window)

    receiver, _ = _managed_receiver()
    receiver.host.stt_service = live_session.st.STTService.parakeet
    receiver.host.stt_model = "parakeet-window"
    session = live_session.LiveChainSession(receiver)
    # Session has already progressed to 600s before mid-session socket replacement
    session.last_end = 600.0

    monkeypatch.setenv("HOSTED_PARAKEET_API_URL", "http://fake-parakeet")
    monkeypatch.setattr(live_session, "window_allocation", lambda uid: True)
    monkeypatch.setattr(live_session, "window_language_supported", lambda h, l: True)
    monkeypatch.setattr(live_session, "VADStreamingGate", lambda **kwargs: MagicMock())

    async def fake_pick_window(**kwargs):
        return await kwargs["connect_primary"](), kwargs["primary_service"]

    monkeypatch.setattr(live_session.st, "connect_stt_socket_with_fallback", fake_pick_window)
    monkeypatch.setattr(live_session.st, "stt_service_models", ["parakeet-window"])

    await session.connect(16000)

    assert len(created_sockets) == 1
    # The socket's stream axis must remain at 0.0, NOT contaminated by session.last_end (600.0)
    assert created_sockets[0].last_emitted_end == 0.0
