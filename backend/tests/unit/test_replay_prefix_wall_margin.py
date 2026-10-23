"""Prefix-wall slack for the paced replay prefix (P47 local-delivery deaths).

A full replay prefix is REPLAY_PREFIX_SECONDS of audio delivered at exactly the
endpoint rate into a wall of the same length: the budget is spent by
construction, and the only slack is the last packet's write-confirm poll
(~30 ms). The pump sleeps the whole time — the listen pod is idle — so a write
that confirms a few tens of milliseconds late on the last packet rejects the
successor as ``replay_send_stalled``. Holding a margin back from the prefix
(``LISTEN_REPLAY_PREFIX_MARGIN_SECONDS``) lands the audio inside the wall.
"""

import asyncio

import pytest

from config.live_stt_replay import (
    DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS,
    REPLAY_PREFIX_MARGIN_ENV,
    ReplayLimits,
    replay_prefix_margin_seconds,
)
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import Transport, full_ring, stop
from utils.stt.live_metrics import REPLAY_SKIPPED
from utils.stt.replay_delivery import REPLAY_PREFIX_SECONDS, ReplayPacer, bounded_snapshot, replay_packets
from utils.stt.resilient_stream import replay_chunks
from utils.stt.streaming import SafeModulateSocket

SAMPLE_RATE = 16000
PACKET_SECONDS = 16384 / (2 * SAMPLE_RATE)  # 0.512s per 16 KiB packet


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


def audio_seconds(chunks) -> float:
    return sum(len(data) for _, data in chunks) / (2 * SAMPLE_RATE)


class SlowAckTransport(Transport):
    """Every audio write confirms ``write_seconds`` after it starts, on the
    virtual clock; the final one may take ``last_write_seconds`` instead. The
    socket is open and accepting, just not instantly."""

    def __init__(self, timer, write_seconds, last_write_seconds=None, packets=None):
        super().__init__()
        self.timer = timer
        self.write_seconds = write_seconds
        self.last_write_seconds = last_write_seconds
        self.packets = packets
        self.writes = []

    async def send(self, data):
        if isinstance(data, bytes):
            started = self.timer.now
            delay = self.write_seconds
            if (
                self.last_write_seconds is not None
                and self.packets is not None
                and len(self.writes) == self.packets - 1
            ):
                delay = self.last_write_seconds
            await self.timer.sleep(delay)
            self.writes.append((started, self.timer.now))
        self.sent.append(data)
        self.sent_at.append(self.timer.now)
        if isinstance(data, bytes):
            self.byte_count += len(data)


async def run_prefix(virtual_clock, write_seconds, last_write_seconds=None):
    """Dial a Modulate successor and pump a full-ring prefix through the real
    adapter with recovery writer pacing, the way _pump_replacement does."""
    ring = full_ring()
    prefix = bounded_snapshot(ring, 'parakeet', 'modulate', rate=1.0, wall_seconds=REPLAY_PREFIX_SECONDS)
    packets = len(list(replay_packets(prefix)))
    transport = SlowAckTransport(virtual_clock, write_seconds, last_write_seconds, packets)
    raw = SafeModulateSocket(transport, lambda _: None, asyncio.get_running_loop())
    raw.enable_writer_pacing(SAMPLE_RATE, 1.0)
    raw.replay_send = lambda data, start: raw.send(data)
    try:
        pacer = ReplayPacer(SAMPLE_RATE, 'modulate', raw, limits=ReplayLimits())
        began = virtual_clock.now
        rejected = await replay_chunks(
            raw,
            prefix,
            source=ring,
            provider='parakeet',
            soniox=None,
            pacer=pacer,
            deadline=began + REPLAY_PREFIX_SECONDS,
            await_writes=True,
        )
        return raw, transport, prefix, rejected, virtual_clock.now - began
    finally:
        await stop([raw])


@pytest.mark.asyncio
async def test_exact_wall_prefix_is_rejected_by_a_50ms_final_write_confirm_while_idle(monkeypatch, virtual_clock):
    monkeypatch.setenv(REPLAY_PREFIX_MARGIN_ENV, '0')
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, write_seconds=0.050)

    assert audio_seconds(prefix) == REPLAY_PREFIX_SECONDS  # the full wall's worth of audio
    packets = len(list(replay_packets(prefix)))
    assert packets == 40
    # Every packet was admitted on its 1x slot and the queue never held more
    # than two, so this is neither a full queue nor a stalled transport: the
    # last packet's slot is 32 ms before the wall and its write confirmed 50 ms
    # after it started.
    assert raw._send_queue.enqueued_audio == packets
    assert raw._send_queue.written_audio == packets - 1
    assert raw._send_queue.high_water <= 2
    assert len(transport.writes) == packets - 1
    assert transport.writes[-1][0] == pytest.approx((packets - 2) * PACKET_SECONDS, abs=0.02)
    assert rejected is not None
    assert raw.is_connection_dead
    assert raw.typed_death_reason == 'replay_send_stalled'
    assert raw.death_reason == 'replay wall budget exhausted'
    assert wall >= REPLAY_PREFIX_SECONDS


@pytest.mark.asyncio
async def test_exact_wall_prefix_survives_only_a_sub_30ms_write_confirm(monkeypatch, virtual_clock):
    monkeypatch.setenv(REPLAY_PREFIX_MARGIN_ENV, '0')
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, write_seconds=0.010)

    assert audio_seconds(prefix) == REPLAY_PREFIX_SECONDS
    assert rejected is None
    assert not raw.is_connection_dead
    assert REPLAY_PREFIX_SECONDS - 0.05 <= wall <= REPLAY_PREFIX_SECONDS


@pytest.mark.asyncio
@pytest.mark.parametrize('write_seconds', [0.050, 0.250, 0.450])
async def test_default_margin_lands_the_prefix_inside_the_wall(monkeypatch, virtual_clock, write_seconds):
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, write_seconds)

    assert audio_seconds(prefix) == REPLAY_PREFIX_SECONDS - DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    assert len(list(replay_packets(prefix))) == 38
    assert len(transport.writes) == 38
    assert raw._send_queue.high_water <= 2
    assert rejected is None
    assert not raw.is_connection_dead
    assert wall < REPLAY_PREFIX_SECONDS
    # Still 1x: no packet was written before its audio slot.
    for n, (started, _) in enumerate(transport.writes):
        assert started >= n * PACKET_SECONDS - 0.001


@pytest.mark.asyncio
async def test_default_margin_absorbs_a_final_write_confirm_up_to_the_margin(monkeypatch, virtual_clock):
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, 0.050, last_write_seconds=0.900)

    assert len(transport.writes) == 38
    assert transport.writes[-1][1] - transport.writes[-1][0] == pytest.approx(0.900)
    assert rejected is None
    assert not raw.is_connection_dead
    assert wall < REPLAY_PREFIX_SECONDS


@pytest.mark.asyncio
async def test_default_margin_still_rejects_a_final_write_confirm_later_than_the_margin(monkeypatch, virtual_clock):
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, 0.050, last_write_seconds=1.500)

    assert rejected is not None
    assert raw.typed_death_reason == 'replay_send_stalled'
    assert raw.death_reason == 'replay wall budget exhausted'


@pytest.mark.asyncio
async def test_sustained_sub_realtime_transport_is_rejected_regardless_of_margin(monkeypatch, virtual_clock):
    # 0.9s per 0.512s packet: the endpoint drains slower than the 1x pace, so
    # the pump runs out of wall inside its own slot/capacity wait. (That return
    # carries no typed reason today; the receiver claims it as connection_lost.)
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    raw, transport, prefix, rejected, wall = await run_prefix(virtual_clock, write_seconds=0.900)

    assert rejected is not None
    assert len(transport.writes) < 38
    assert wall >= REPLAY_PREFIX_SECONDS - 0.001


def test_bounded_snapshot_holds_the_margin_back_and_meters_it(monkeypatch):
    ring = full_ring()
    labels = dict(source='parakeet', successor='modulate')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)

    prefix = bounded_snapshot(ring, 'parakeet', 'modulate', rate=1.0, wall_seconds=REPLAY_PREFIX_SECONDS)

    assert audio_seconds(prefix) == REPLAY_PREFIX_SECONDS - DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(
        135 - (REPLAY_PREFIX_SECONDS - DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS)
    )
    # The newest audio is what ships; the margin comes off the oldest end.
    assert prefix[-1][0] + len(prefix[-1][1]) // 2 == 135 * SAMPLE_RATE


@pytest.mark.parametrize(
    'wall, rate, margin, expected',
    [
        (REPLAY_PREFIX_SECONDS, 1.0, '0', REPLAY_PREFIX_SECONDS),
        (REPLAY_PREFIX_SECONDS, 1.0, '', REPLAY_PREFIX_SECONDS - DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        (REPLAY_PREFIX_SECONDS, 1.0, '2.5', REPLAY_PREFIX_SECONDS - 2.5),
        (10.0, 1.0, '', 9.0),  # episode remaining shorter than the prefix wall
        (REPLAY_PREFIX_SECONDS, 0.5, '', (REPLAY_PREFIX_SECONDS - 1.0) * 0.5),  # slower endpoint
        (0.5, 1.0, '', 0.0),  # margin larger than the wall keeps nothing rather than overshooting
    ],
)
def test_bounded_snapshot_margin_shapes(monkeypatch, wall, rate, margin, expected):
    if margin:
        monkeypatch.setenv(REPLAY_PREFIX_MARGIN_ENV, margin)
    else:
        monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    prefix = bounded_snapshot(full_ring(), 'parakeet', 'modulate', rate=rate, wall_seconds=wall)
    assert audio_seconds(prefix) == pytest.approx(expected)


@pytest.mark.parametrize(
    'raw, expected',
    [
        (None, DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('0', 0.0),
        ('0.0', 0.0),
        ('1.5', 1.5),
        (' 3 ', 3.0),
        ('10', 10.0),
        ('10.5', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('-1', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('inf', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('nan', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
        ('off', DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS),
    ],
)
def test_replay_prefix_margin_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    else:
        monkeypatch.setenv(REPLAY_PREFIX_MARGIN_ENV, raw)
    assert replay_prefix_margin_seconds() == expected
