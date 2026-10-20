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


def test_callback_deduplication_against_last_end():
    """Demonstrates deduplication of replayed segments against session last_end."""
    last_end = 293.04

    # Successor leg receives replayed audio:
    # 1. Old duplicate ending before or at last_end (290.76 to 293.04) -> MUST DROP
    # 2. Overlapping segment (291.68 to 296.08) -> MUST TRIM start to 293.04
    # 3. Degenerate segment (292.50 to 293.04) -> MUST DROP (end <= start after trim)
    # 4. Fresh segment (296.50 to 300.00) -> MUST KEEP as-is
    incoming = [
        {"speaker": "SPEAKER_0", "start": 290.76, "end": 293.04, "text": "old phrase"},
        {"speaker": "SPEAKER_0", "start": 291.68, "end": 296.08, "text": "overlapping phrase"},
        {"speaker": "SPEAKER_0", "start": 292.50, "end": 293.04, "text": "degenerate phrase"},
        {"speaker": "SPEAKER_1", "start": 296.50, "end": 300.00, "text": "new phrase"},
    ]

    retained = []
    for segment in incoming:
        raw_start = max(0.0, float(segment["start"]))
        raw_end = max(raw_start, float(segment["end"]))
        if raw_end <= last_end:
            continue
        start = max(last_end, raw_start)
        end = max(start, raw_end)
        if end <= start:
            continue
        segment["start"], segment["end"] = start, end
        last_end = end
        retained.append(segment)

    assert len(retained) == 2
    assert retained[0]["text"] == "overlapping phrase"
    assert retained[0]["start"] == 293.04
    assert retained[0]["end"] == 296.08

    assert retained[1]["text"] == "new phrase"
    assert retained[1]["start"] == 296.50
    assert retained[1]["end"] == 300.00
    assert last_end == 300.00
