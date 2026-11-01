"""Live-tail catch-up pacing (P47b: follow-up B of the local-delivery deaths).

Audio that arrives while a successor dials and replays its prefix is held in
the 26 s live tail. Before this change the tail pump drained it at exactly the
endpoint rate: ``_next_audio_slot`` discards every missed slot and the pump
never runs ahead of 1x, so a near-full prefix left the leg a permanent 15-25 s
backlog, every later pump slip added to it for good, and the next client burst
tripped the tail bound (``send_queue_full``) while the vendor socket was
healthy. The pump now drains at the catch-up rate
(``LISTEN_LIVE_TAIL_CATCHUP_RATE``, default 1.5x; ``1`` restores the exact-rate
tail) while the tail holds more than TAIL_CATCHUP_FLOOR_SECONDS of audio, then
returns to the sustained rate.

Every scenario drives the real adapter over the shared virtual clock, so the
clock only advances inside sleeps and the process is idle throughout, exactly
as the listen pod is in production. The client captures on a fixed cadence
independent of the pump, so a stalled pump finds every packet it missed.
"""

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest

from config.live_stt_replay import (
    DEFAULT_LIVE_TAIL_CATCHUP_RATE,
    LIVE_TAIL_CATCHUP_RATE_ENV,
    MAX_LIVE_TAIL_CATCHUP_RATE,
    ReplayLimits,
    live_tail_catchup_rate,
)
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import Transport, stop
from utils.stt import soniox as soniox_module
from utils.stt import streaming as st
from utils.stt.live_metrics import TAIL_CATCHUP
from utils.stt.replay_delivery import (
    LIVE_TAIL_SECONDS,
    TAIL_CATCHUP_CEILINGS,
    TAIL_CATCHUP_FLOOR_SECONDS,
    BirthLedger,
    ReplayPacer,
    ReplayTailSocket,
    abort_replay_socket,
    enable_recovery_writer_pace,
    tail_catchup_rate,
)
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket

SAMPLE_RATE = 16000
BYTES_PER_SECOND = 2 * SAMPLE_RATE
# Dial (5 s) plus the margined prefix (19 s) at 1x: the tail a successor
# inherits after a near-full prefix.
HOLD_SECONDS = 24.0
FLOOR = TAIL_CATCHUP_FLOOR_SECONDS


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def _adapter_clocks(monkeypatch, virtual_clock):
    monkeypatch.setattr(st, 'clock', lambda: virtual_clock.now)
    monkeypatch.setattr(soniox_module, 'clock', lambda: virtual_clock.now)


def tail_host():
    return SimpleNamespace(
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        spawn=lambda coro, name=None: asyncio.create_task(coro),
    )


def catchup_seconds(successor='modulate'):
    return TAIL_CATCHUP.labels(successor=successor)._value.get()


class SlippingPacer(ReplayPacer):
    """The pump coroutine is descheduled for ``slip`` seconds right before an
    armed send: an event-loop stall (P32 measured up to 745 ms) as the pacer
    experiences it. The client keeps capturing meanwhile."""

    timer = None
    slip = 0.75

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slips_at = deque()

    async def send(self, *args, **kwargs):
        if self.slips_at and self.timer.now >= self.slips_at[0]:
            self.slips_at.popleft()
            await self.timer.sleep(self.slip)
        return await super().send(*args, **kwargs)


class Leg:
    """A paid leg behind the live tail: the real Modulate adapter over the
    virtual-clock Transport (20 ms per write), the tail wrapper the receiver
    builds, and a real-time client feeding it. Each captured packet carries a
    distinct sample marker so the wire can be checked for order, loss and
    duplication byte for byte."""

    def __init__(self, timer, *, recovery, packet_seconds, write_wait_seconds=None, pacer_cls=ReplayPacer):
        self.timer = timer
        self.transport = Transport()
        self.transport.timer = timer
        self.raw = SafeModulateSocket(self.transport, lambda _: None, asyncio.get_running_loop())
        send = self.raw.send
        self.raw.send = lambda data, start_sample=None: send(data)
        limits = ReplayLimits()
        if recovery:
            enable_recovery_writer_pace(self.raw, SAMPLE_RATE, limits, lambda: None)
        self.birth = BirthLedger()
        self.pacer = pacer_cls(SAMPLE_RATE, 'modulate', self.raw, limits=limits)
        self.delivery = ReplayTailSocket(
            self.raw,
            self.pacer,
            deque(),
            tail_host(),
            source='parakeet',
            birth=self.birth,
            write_wait_seconds=write_wait_seconds,
        )
        self.packet_seconds = packet_seconds
        self.packet_bytes = int(packet_seconds * BYTES_PER_SECOND)
        self.produced = []
        self.rejected_at = None
        self._count = 0
        self._sample = 0
        self._due = packet_seconds

    def emit(self, data=None):
        if data is None:
            self._count += 1
            data = (self._count % 65535 + 1).to_bytes(2, 'little') * (self.packet_bytes // 2)
        start = self._sample
        self.birth.note(start, start + len(data) // 2)
        accepted = self.delivery.send(data, start)
        self.produced.append(data)
        self._sample += len(data) // 2
        if not accepted and self.rejected_at is None:
            self.rejected_at = self.timer.now
        return accepted

    def burst(self, seconds):
        """One oversized client frame, as the receiver flushes it: a single
        tail entry the pump splits into 16 KiB packets."""
        self._count += 1
        marker = (self._count % 65535 + 1).to_bytes(2, 'little')
        return self.emit(marker * int(seconds * SAMPLE_RATE))

    async def capture(self, until):
        while self._due < until:
            if self.timer.now < self._due:
                await self.timer.sleep(self._due - self.timer.now)
            self.emit()
            self._due += self.packet_seconds

    async def observe(self, until, samples, every=1.0):
        while self.timer.now < until:
            samples.append((self.timer.now, self.backlog_seconds, self.oldest_age))
            await self.timer.sleep(every)

    @property
    def backlog_seconds(self):
        return self.delivery._tail_bytes / BYTES_PER_SECOND

    @property
    def oldest_age(self):
        return self.timer.now - self.delivery.tail[0].received if self.delivery.tail else 0.0

    def assert_alive(self):
        assert self.rejected_at is None
        assert not self.delivery.is_connection_dead
        assert not self.raw.is_connection_dead
        assert self.delivery.typed_death_reason is None

    def assert_wire_is_the_capture(self):
        """Ordered, no duplicate, no gap: the wire is a prefix of the capture,
        and what is still held is at most the floor plus one packet."""
        wire = self.transport.pcm
        expected = b''.join(self.produced)
        assert wire == expected[: len(wire)]
        assert len(expected) - len(wire) <= (FLOOR + self.packet_seconds) * BYTES_PER_SECOND

    def assert_wire_rate_within(self, multiple, window=4.0):
        """No ``window`` of wire writes carries more than ``multiple`` real
        time of audio plus the two-packet queue allowance."""
        stamps = self.transport.sent_at
        sizes = [len(frame) for frame in self.transport.sent if isinstance(frame, bytes)]
        assert len(stamps) == len(sizes)
        allowance = 2 * max(sizes)
        start = 0
        for end in range(len(stamps)):
            while stamps[end] - stamps[start] > window:
                start += 1
            assert sum(sizes[start : end + 1]) <= multiple * window * BYTES_PER_SECOND + allowance

    async def close(self):
        await abort_replay_socket(self.delivery)


@pytest.mark.asyncio
async def test_near_full_prefix_backlog_drains_at_catch_up_and_returns_to_realtime(monkeypatch, virtual_clock):
    monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    leg = Leg(virtual_clock, recovery=True, packet_seconds=0.5)
    counted_before = catchup_seconds()
    try:
        # Capture during the dial and the paced prefix is held, never pumped.
        await leg.capture(until=HOLD_SECONDS)
        assert leg.backlog_seconds == pytest.approx(HOLD_SECONDS, abs=0.5)
        leg.delivery.start_tail()

        # The excess over the floor drains at (1.5 - 1.0) s per s of wall time
        # against real-time input; allow a little for packet granularity.
        drain = (HOLD_SECONDS - FLOOR) / (DEFAULT_LIVE_TAIL_CATCHUP_RATE - 1.0)
        settled_by = HOLD_SECONDS + drain + 3.0
        samples = []
        await asyncio.gather(leg.capture(until=settled_by), leg.observe(settled_by, samples))

        leg.assert_alive()
        # Bounded latency: the oldest held packet never ages past the tail
        # bound, the backlog only falls (one packet of jitter), and the leg
        # ends within a packet of the floor instead of carrying 24 s for life.
        assert max(age for _, _, age in samples) <= LIVE_TAIL_SECONDS
        assert all(later <= earlier + 0.5 for (_, earlier, _), (_, later, _) in zip(samples, samples[1:]))
        assert leg.backlog_seconds <= FLOOR + 0.5
        first_settled = next(t for t, backlog, _ in samples if backlog <= FLOOR + 0.5)
        assert first_settled <= HOLD_SECONDS + drain + 1.0
        # The wire is the capture, in order, with nothing lost or repeated.
        leg.assert_wire_is_the_capture()
        # Never above the catch-up ceiling, and never deeper than the two
        # packets the replay queue allows.
        leg.assert_wire_rate_within(DEFAULT_LIVE_TAIL_CATCHUP_RATE)
        assert leg.raw._send_queue.high_water <= 2
        counted = catchup_seconds() - counted_before
        assert counted > HOLD_SECONDS
        assert counted <= len(leg.transport.pcm) / BYTES_PER_SECOND

        # A later 3 s client burst, which killed the 1x leg (see the kill
        # switch case), is now absorbed and drained.
        assert leg.burst(3.0)
        await leg.capture(until=settled_by + 3.0 / (DEFAULT_LIVE_TAIL_CATCHUP_RATE - 1.0) + 3.0)
        leg.assert_alive()
        assert leg.backlog_seconds <= FLOOR + 0.5
        leg.assert_wire_is_the_capture()
    finally:
        await leg.close()


@pytest.mark.asyncio
async def test_kill_switch_keeps_the_exact_rate_tail_and_the_permanent_backlog(monkeypatch, virtual_clock):
    """``LISTEN_LIVE_TAIL_CATCHUP_RATE=1`` is the pre-change tail: the backlog
    a near-full prefix leaves is carried for the rest of the leg, and a 3 s
    client burst trips the 26 s bound as ``send_queue_full`` while the vendor
    socket is healthy and draining at 1x."""
    monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, '1')
    leg = Leg(virtual_clock, recovery=True, packet_seconds=0.5)
    counted_before = catchup_seconds()
    try:
        await leg.capture(until=HOLD_SECONDS)
        leg.delivery.start_tail()
        await leg.capture(until=HOLD_SECONDS + 60.0)

        leg.assert_alive()
        assert leg.backlog_seconds >= HOLD_SECONDS - 1.0
        assert leg.oldest_age >= HOLD_SECONDS - 1.0
        assert catchup_seconds() == counted_before
        assert leg.raw._writer_pace.rate == 1.0

        assert not leg.burst(3.0)
        assert leg.delivery.is_connection_dead
        assert leg.delivery.typed_death_reason == 'send_queue_full'
        assert not leg.raw.is_connection_dead
    finally:
        await leg.close()


@pytest.mark.asyncio
async def test_client_burst_on_an_initial_leg_is_absorbed_without_tripping_the_tail_bound(monkeypatch, virtual_clock):
    """An initial paid leg (no writer pace, 2 s write confirm) receiving the
    receiver's real 30 ms flushes takes a 5 s client frame: the pump drains
    the excess at 1.5x and settles back under the floor with the confirm
    bound untouched."""
    monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    leg = Leg(virtual_clock, recovery=False, packet_seconds=0.03, write_wait_seconds=2.0)
    try:
        leg.delivery.start_tail()
        await leg.capture(until=2.0)
        assert leg.backlog_seconds <= FLOOR
        assert leg.burst(5.0)
        assert leg.backlog_seconds >= 5.0

        drain = (5.0 - FLOOR) / (DEFAULT_LIVE_TAIL_CATCHUP_RATE - 1.0)
        samples = []
        settled_by = 2.0 + drain + 2.0
        await asyncio.gather(leg.capture(until=settled_by), leg.observe(settled_by, samples, every=0.5))

        leg.assert_alive()
        assert leg.backlog_seconds <= FLOOR + 0.03
        assert max(age for _, _, age in samples) <= 5.0 + 0.1
        leg.assert_wire_is_the_capture()
        leg.assert_wire_rate_within(DEFAULT_LIVE_TAIL_CATCHUP_RATE, window=2.0)
        assert leg.raw._writer_pace is None
    finally:
        await leg.close()


@pytest.mark.asyncio
async def test_client_burst_at_the_exact_rate_is_carried_for_the_rest_of_the_leg(monkeypatch, virtual_clock):
    monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, '1')
    leg = Leg(virtual_clock, recovery=False, packet_seconds=0.03, write_wait_seconds=2.0)
    try:
        leg.delivery.start_tail()
        await leg.capture(until=2.0)
        assert leg.burst(5.0)
        await leg.capture(until=14.0)
        leg.assert_alive()
        assert leg.backlog_seconds >= 5.0 - 0.1
    finally:
        await leg.close()


@pytest.mark.asyncio
async def test_pump_slips_are_recovered_instead_of_accumulating(monkeypatch, virtual_clock):
    """Four 750 ms stalls of the pump coroutine (the P32 loop-lag maximum)
    while the client keeps capturing the receiver's real 30 ms flushes. A
    stall that long is 25 frames past the armed slot, so ``_next_audio_slot``
    rebases and the slot credit is gone for good: each one used to be a
    permanent 750 ms of lag. Now a single stall sits under the floor, and the
    moment a second one pushes the tail over it the pump drains back."""
    monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    leg = Leg(virtual_clock, recovery=True, packet_seconds=0.03, pacer_cls=SlippingPacer)
    leg.pacer.timer = virtual_clock
    leg.pacer.slips_at = deque([4.0, 8.0, 12.0, 16.0])
    try:
        leg.delivery.start_tail()
        samples = []
        await asyncio.gather(leg.capture(until=20.0), leg.observe(20.0, samples, every=0.25))

        leg.assert_alive()
        assert not leg.pacer.slips_at
        assert max(backlog for _, backlog, _ in samples) <= FLOOR + leg.pacer.slip + 0.03
        assert leg.backlog_seconds <= FLOOR + 0.03
        assert leg.oldest_age <= FLOOR + 0.03
        leg.assert_wire_is_the_capture()
        leg.assert_wire_rate_within(DEFAULT_LIVE_TAIL_CATCHUP_RATE, window=2.0)
    finally:
        await leg.close()


@pytest.mark.asyncio
async def test_pump_slips_at_the_exact_rate_are_permanent(monkeypatch, virtual_clock):
    monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, '1')
    leg = Leg(virtual_clock, recovery=True, packet_seconds=0.03, pacer_cls=SlippingPacer)
    leg.pacer.timer = virtual_clock
    leg.pacer.slips_at = deque([4.0, 8.0, 12.0, 16.0])
    try:
        leg.delivery.start_tail()
        await leg.capture(until=20.0)
        leg.assert_alive()
        assert not leg.pacer.slips_at
        # Four unrecovered stalls, each short of its full length only by the
        # one frame the slot anchoring absorbs.
        assert leg.backlog_seconds >= 4 * (leg.pacer.slip - 2 * 0.03)
        assert leg.oldest_age >= 4 * (leg.pacer.slip - 2 * 0.03)
    finally:
        await leg.close()


class ParakeetWindowStub:
    """A window successor: no send queue, no wire, no capacity wait."""

    is_connection_dead = False
    typed_death_reason = None

    def __init__(self, timer):
        self.timer = timer
        self.sent = []
        self.sent_at = []

    def send(self, data, start_sample=None):
        self.sent.append(data)
        self.sent_at.append(self.timer.now)
        return True

    def finish(self):
        pass


@pytest.mark.asyncio
async def test_window_successor_drains_at_its_own_higher_ceiling(monkeypatch, virtual_clock):
    monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, '3')
    socket = ParakeetWindowStub(virtual_clock)
    pacer = ReplayPacer(SAMPLE_RATE, 'parakeet', socket, limits=ReplayLimits())
    assert pacer.catchup_rate == 3.0
    delivery = ReplayTailSocket(socket, pacer, deque(), tail_host(), source='soniox', birth=BirthLedger())
    counted_before = catchup_seconds('parakeet')
    packet = b'\x01\x00' * 8000  # 0.5 s
    for n in range(20):
        assert delivery.send(packet, n * 8000)
    assert delivery._tail_bytes == 20 * len(packet)
    delivery.start_tail()
    await virtual_clock.sleep(0.5 * 20 / 3.0 + 0.6)
    assert socket.sent == [packet] * 20
    assert delivery._tail_bytes == 0
    assert not delivery.is_connection_dead
    # Eighteen packets go at 3x while the tail holds more than the floor; the
    # nineteenth sees exactly the floor (two packets) and the rest go at 1x.
    gaps = [b - a for a, b in zip(socket.sent_at, socket.sent_at[1:])]
    assert all(gap == pytest.approx(0.5 / 3.0, abs=1e-6) for gap in gaps[:-1])
    assert gaps[-1] == pytest.approx(0.5, abs=1e-6)
    assert catchup_seconds('parakeet') - counted_before == pytest.approx(18 * 0.5)


class StubSocket:
    is_connection_dead = False

    def send(self, data, start_sample=None):
        return True


@pytest.mark.asyncio
async def test_prefix_replay_never_uses_the_catch_up_rate(monkeypatch, virtual_clock):
    monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', limits=ReplayLimits())
    assert pacer.rate == 1.0 and pacer.catchup_rate == DEFAULT_LIVE_TAIL_CATCHUP_RATE
    frame = b'\x01\x00' * 8000  # 0.5 s
    for n in range(10):
        assert await pacer.send(StubSocket(), frame, n * 8000, lambda: True, replay=True)
    assert pacer.next_send == pytest.approx(10 * 0.5)
    for n in range(10, 20):
        assert await pacer.send(StubSocket(), frame, n * 8000, lambda: True, replay=False)
    assert pacer.next_send == pytest.approx(20 * 0.5)
    for n in range(20, 23):
        assert await pacer.send(StubSocket(), frame, n * 8000, lambda: True, replay=False, catchup=True)
    assert pacer.next_send == pytest.approx(20 * 0.5 + 3 * 0.5 / DEFAULT_LIVE_TAIL_CATCHUP_RATE)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeModulateSocket, SafeSonioxSocket])
@pytest.mark.parametrize('env, expected', [(None, DEFAULT_LIVE_TAIL_CATCHUP_RATE), ('1', 1.0), ('3', 2.0)])
async def test_recovery_writer_pace_is_installed_at_the_family_ceiling(monkeypatch, kind, env, expected):
    if env is None:
        monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    else:
        monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, env)
    raw = kind(Transport(), lambda _: None, asyncio.get_running_loop())
    try:
        enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), lambda: None)
        assert raw._writer_pace.rate == expected
    finally:
        await stop([raw])


def test_unidentified_transport_writer_pace_stays_at_the_sustained_rate(monkeypatch):
    monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    installed = []
    socket = SimpleNamespace(enable_writer_pacing=lambda sample_rate, rate, budget: installed.append(rate))
    enable_recovery_writer_pace(socket, SAMPLE_RATE, ReplayLimits(rate=0.5), lambda: None)
    assert installed == [0.5]


@pytest.mark.parametrize(
    'env, family_name, rate, expected',
    [
        (None, 'soniox', 1.0, DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        (None, 'modulate', 1.0, DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        (None, 'deepgram', 1.0, DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        (None, 'parakeet', 1.0, DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        (None, 'unknown', 1.0, 1.0),
        ('1', 'soniox', 1.0, 1.0),
        ('1', 'parakeet', 1.0, 1.0),
        ('3', 'soniox', 1.0, TAIL_CATCHUP_CEILINGS['soniox']),
        ('3', 'modulate', 1.0, TAIL_CATCHUP_CEILINGS['modulate']),
        ('3', 'parakeet', 1.0, 3.0),
        ('4', 'parakeet', 1.0, TAIL_CATCHUP_CEILINGS['parakeet']),
        (None, 'soniox', 0.5, 0.5 * DEFAULT_LIVE_TAIL_CATCHUP_RATE),  # a slower endpoint scales down
        ('2', 'soniox', 0.5, 1.0),
    ],
)
def test_tail_catchup_rate_shapes(monkeypatch, env, family_name, rate, expected):
    if env is None:
        monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    else:
        monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, env)
    assert tail_catchup_rate(ReplayLimits(rate=rate), family_name) == pytest.approx(expected)


def test_family_ceilings_stay_inside_the_env_clamp():
    assert all(1.0 < ceiling <= MAX_LIVE_TAIL_CATCHUP_RATE for ceiling in TAIL_CATCHUP_CEILINGS.values())
    assert TAIL_CATCHUP_CEILINGS['parakeet'] >= max(
        TAIL_CATCHUP_CEILINGS[f] for f in ('soniox', 'modulate', 'deepgram')
    )


@pytest.mark.parametrize(
    'raw, expected',
    [
        (None, DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('1', 1.0),
        ('1.0', 1.0),
        ('1.25', 1.25),
        (' 2 ', 2.0),
        ('4', 4.0),
        ('4.5', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('0.5', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('0', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('-1', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('inf', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('nan', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
        ('off', DEFAULT_LIVE_TAIL_CATCHUP_RATE),
    ],
)
def test_live_tail_catchup_rate_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(LIVE_TAIL_CATCHUP_RATE_ENV, raising=False)
    else:
        monkeypatch.setenv(LIVE_TAIL_CATCHUP_RATE_ENV, raw)
    assert live_tail_catchup_rate() == expected
