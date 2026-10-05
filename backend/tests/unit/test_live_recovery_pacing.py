"""Deterministic jitter contract for the two recovery pacing seams.

A timer that lands a few milliseconds late on every positive pacing sleep must
be absorbed against the accumulated audio slot: write starts stay anchored to
``previous_slot + audio_duration`` at 1x, small oversleeps are compensated on
the next slot instead of accumulating drift, a stall of one frame or longer
rebases on the wall clock, and no seam ever banks unbounded catch-up credit.
"""

import asyncio

import pytest

from config.live_stt_replay import ReplayLimits
from utils.stt import replay_delivery
from utils.stt.replay_delivery import RecoveryWriterPace, ReplayPacer

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.030
FRAME = b'\x01\x00' * int(SAMPLE_RATE * FRAME_SECONDS)
OVERSHOOT = 0.005
FRAMES = 20


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


class OvershootingClock:
    """Positive pacing sleeps land OVERSHOOT late; non-positive sleeps yield."""

    def __init__(self):
        self.now = 0.0

    async def sleep(self, seconds):
        if seconds > 0:
            self.now += seconds + OVERSHOOT
        await asyncio.sleep(0)


@pytest.fixture
def clock(monkeypatch):
    timer = OvershootingClock()
    monkeypatch.setattr(replay_delivery, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'sleep', timer.sleep)
    return timer


class StubSocket:
    is_connection_dead = False

    def __init__(self, timer):
        self.timer = timer
        self.starts = []

    def send(self, data, start_sample=None):
        self.starts.append(self.timer.now)
        return True


def assert_slot_anchored(starts, next_slot):
    assert len(starts) == FRAMES
    assert next_slot == pytest.approx(FRAMES * FRAME_SECONDS, abs=1e-9)
    assert starts[-1] == pytest.approx((FRAMES - 1) * FRAME_SECONDS + OVERSHOOT, abs=1e-9)
    assert starts[-1] - starts[0] >= (FRAMES - 1) * FRAME_SECONDS
    assert all(b - a >= FRAME_SECONDS - OVERSHOOT - 1e-9 for a, b in zip(starts, starts[1:]))


@pytest.mark.asyncio
async def test_replay_pacer_sub_frame_oversleep_stays_on_audio_slots(clock):
    socket = StubSocket(clock)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', limits=ReplayLimits())
    for n in range(FRAMES):
        assert await pacer.send(socket, FRAME, n * 480, lambda: True, replay=True)
    assert_slot_anchored(socket.starts, pacer.next_send)


@pytest.mark.asyncio
async def test_recovery_writer_pace_sub_frame_oversleep_stays_on_audio_slots(clock):
    pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    starts = []
    for _ in range(FRAMES):
        await pace.throttle(len(FRAME))
        starts.append(pace.note_write(len(FRAME)))
        pace.complete_write()
    assert_slot_anchored(starts, pace.next_write)


@pytest.mark.asyncio
async def test_replay_pacer_long_stall_rebases_without_catch_up_credit(clock):
    socket = StubSocket(clock)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', limits=ReplayLimits())
    for n in range(FRAMES):
        assert await pacer.send(socket, FRAME, n * 480, lambda: True, replay=True)
    clock.now += 10.0
    before = clock.now
    assert await pacer.send(socket, FRAME, FRAMES * 480, lambda: True, replay=True)
    assert socket.starts[-1] == before
    assert pacer.next_send == pytest.approx(before + FRAME_SECONDS, abs=1e-9)
    assert await pacer.send(socket, FRAME, (FRAMES + 1) * 480, lambda: True, replay=True)
    assert socket.starts[-1] - before >= FRAME_SECONDS - OVERSHOOT - 1e-9


@pytest.mark.asyncio
async def test_recovery_writer_long_stall_rebases_without_catch_up_credit(clock):
    pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    starts = []
    for _ in range(FRAMES):
        await pace.throttle(len(FRAME))
        starts.append(pace.note_write(len(FRAME)))
        pace.complete_write()
    clock.now += 10.0
    before = clock.now
    await pace.throttle(len(FRAME))
    starts.append(pace.note_write(len(FRAME)))
    assert starts[-1] == before
    assert pace.next_write == pytest.approx(before + FRAME_SECONDS, abs=1e-9)
    await pace.throttle(len(FRAME))
    starts.append(pace.note_write(len(FRAME)))
    assert starts[-1] - before >= FRAME_SECONDS - OVERSHOOT - 1e-9


@pytest.mark.asyncio
async def test_blocked_write_clamps_to_completion_and_banks_no_credit(clock):
    pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    await pace.throttle(len(FRAME))
    first = pace.note_write(len(FRAME))
    clock.now += 0.6
    pace.complete_write()
    assert pace.next_write == pytest.approx(first + 0.6, abs=1e-9)
    await pace.throttle(len(FRAME))
    second = pace.note_write(len(FRAME))
    assert second == pytest.approx(first + 0.6, abs=1e-9)
    assert pace.next_write == pytest.approx(second + FRAME_SECONDS, abs=1e-9)
