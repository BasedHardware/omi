"""Late cap decisions join by capture coordinates, before any immutable source exists."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tests.unit.test_cap_hold_durability import fragment_sink  # noqa: F401
from utils.observability import held_content
from utils.sync import live_cap_hold as live
from utils.sync.live_cap_capture import OrderedCapture


async def test_one_second_spaced_early_slivers_join_the_receiver_denied_suffix(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    rate, first, end = 16000, 240480, 960000  # 15.03s funded; 44.97s held.
    clock = [100.0]
    monkeypatch.setattr(live.time, 'monotonic', lambda: clock[0])
    sink.host.state.conversation_sample_ranges = []
    receiver = SimpleNamespace(
        host=sink.host,
        _cap_decided_spans=[],
        capture_timeline=SimpleNamespace(wall=lambda sample: 1000 + sample / rate),
        _owner_for_sample=lambda sample: 'conversation',
    )
    period = b''.join(frame.to_bytes(2, 'little') for frame in range(30000))
    pcm = (period * ((end + 29999) // 30000))[: end * 2]
    encoded = []
    original = live.live_cap_codec.encode

    def encode(path, data, rate, **kwargs):
        encoded.append(data)
        return original(path, data, rate, **kwargs)

    monkeypatch.setattr(live.live_cap_codec, 'encode', encode)
    coalesced = held_content.TRANSITION_TAIL.labels(outcome='coalesced')._value.get()
    sealed_tails = held_content.TRANSITION_TAIL.labels(outcome='sealed')._value.get()
    sink.observe(receiver, pcm[: first * 2], rate, 0, True)
    # Provider-side decisions arrive before the receiver drains its older PCM.
    # Capture order deliberately differs from the one-second callback order.
    for start, frames in ((275200, 480), (259200, 480), (284800, 160)):
        sink.observe(receiver, pcm[start * 2 : (start + frames) * 2], rate, start, False)
        await sink.flush()  # The real updater does not force a resume seal.
        clock[0] += 1
    await sink.observe_async(receiver, pcm[first * 2 :], rate, first, False)
    await sink.close()
    shape = [(sum(seconds for _, seconds in parts), len(parts)) for _, parts in sealed]
    assert len(sealed) == 1, shape
    assert len(staged) == 1
    assert sink.seconds == pytest.approx(44.97)
    assert [meta['source_frames'] for _, parts in sealed for meta, _ in parts] == [240000, 240000, 239520]
    assert b''.join(encoded) == pcm[first * 2 :]
    assert held_content.TRANSITION_TAIL.labels(outcome='coalesced')._value.get() == coalesced + 3
    assert held_content.TRANSITION_TAIL.labels(outcome='sealed')._value.get() == sealed_tails


@pytest.mark.parametrize('boundary', ['owner', 'rate', 'sample_gap', 'wall_gap', 'month'])
def test_ordered_capture_preserves_real_boundaries(boundary):
    capture = OrderedCapture()
    wall = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp() - 0.01 if boundary == 'month' else 1000
    capture.add(
        160 if boundary == 'sample_gap' else 80,
        b'\2\0' * 80,
        8000 if boundary == 'rate' else 16000,
        wall + (0.5 if boundary == 'wall_gap' else 0.01 if boundary == 'month' else 0.005),
        'b' if boundary == 'owner' else 'a',
    )
    capture.add(0, b'\1\0' * 80, 16000, wall, 'a')
    spans = capture.take(15, force=True)
    assert len(spans) == 2
    assert [bytes(span.data) for span in spans] == [b'\1\0' * 80, b'\2\0' * 80]
    assert capture.seconds == 0


async def test_idle_capture_is_durable_at_the_existing_age_bound(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    clock = [100.0]
    monkeypatch.setattr(live.time, 'monotonic', lambda: clock[0])
    sink.host.state.conversation_sample_ranges = []
    receiver = SimpleNamespace(
        host=sink.host,
        _cap_decided_spans=[],
        capture_timeline=SimpleNamespace(wall=lambda sample: 1000 + sample / 16000),
        _owner_for_sample=lambda sample: 'conversation',
    )
    sink.observe(receiver, b'\1\0' * 160, 16000, 0, False)
    await sink.flush()
    assert not staged
    clock[0] += sink.bound
    await sink.flush()
    assert len(staged) == 1
    assert sink.buffered_seconds() == 0
    await sink.close()
    assert len(sealed) == 1 and sink.seconds == 0.01
