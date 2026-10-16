"""Teardown's forced STT tail flush must stay bounded when a failover is refused.

Failure-Class: FC-live-stt-audio-lost-on-provider-death — instance in
``backend/routers/listen/receiver.py`` ``_flush_stt_buffer`` (prod backend-listen
2026-10-14..15, ``RecursionError`` x105/30m): the recovery flush loop treats
``window_replay_action(...) == 'failover'`` as "the re-entry already adopted the
recovery tail, so recurse into the remaining work". That assumption only holds
while a replacement is being adopted (``_replay_ingesting``). When the re-entry
cannot adopt anything — the serving leg is finishing under owner teardown, the
latch ``_teardown_body`` marks (``mark_owner_teardown``) before its forced tail
flush — the same arguments reproduce the same verdict at every depth and the
call chain runs to the recursion limit, dying inside ``would_overflow``'s
comparison (``maximum recursion depth exceeded in comparison``). One event then
produces three ERROR lines: the spawned ``stt_shutdown`` task, the same
exception re-raised into ``receive`` through ``_bounded_teardown``'s
``teardown.exception()``, and ``runtime``'s
``Listen WebSocket operation failed type=RecursionError``.

Guards proven below:
- a finishing leg holds the packet on the receiver's bounded live tail (a later
  adopted leg inherits it; teardown meters whatever never reaches a provider)
  and returns — no recursion, no failover attempt teardown would refuse, no
  false-positive terminal failure;
- a serving leg whose failover attempt is refused falls through to the
  idempotent terminal send path in bounded attempts;
- the historical routes are preserved: a dead, not-finishing leg still delivers
  through the recovery-tail branch; the legacy pinned path still delegates to
  ``legacy_recovery.flush_stt_buffer`` untouched;
- the hold helper always consumes the caller's buffer, birth-notes held audio,
  and meters the tail.
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import routers.listen.receiver as receiver_module
from config.live_stt_replay import ReplayLimits
from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from utils.stt import streaming as st
from utils.stt.replay_delivery import ReplayPacer, ReplayTailSocket
from utils.stt.resilient_stream import ResilientAudio

RATE = 16000


def _receiver(monkeypatch) -> ListenReceiver:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    state = ListenSessionState()
    state.active = True
    state.current_conversation_id = 'conv-recursion'
    collected = []
    host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid-recursion',
            websocket=SimpleNamespace(send_json=AsyncMock(), close=AsyncMock()),
            codec='pcm16',
            sample_rate=RATE,
            channels=1,
            source='desktop',
        ),
        state=state,
        session_id='session-recursion',
        is_multi_channel=False,
        use_custom_stt=False,
        stt_service=st.STTService.soniox,
        stt_model='soniox',
        stt_language='en',
        vocabulary=[],
        language_profile=None,
        client_device_context=SimpleNamespace(platform='test'),
        transcripts=SimpleNamespace(enqueue=collected.extend),
        audio_bytes_send=None,
        spawn=lambda coro, *, name: coro.close(),
    )
    receiver = ListenReceiver(host, [], {})
    receiver._run_on_listen_loop = lambda action, segments: action(segments)
    receiver._capture = lambda *a, **k: None
    return receiver


class _Raw:
    """Serving raw transport: alive, accepts nothing new (queue full)."""

    def __init__(self):
        self.dead = False
        self.reason = None
        self.finished = False

    def send(self, data: bytes) -> bool:
        return False

    def finalize(self) -> None:
        pass

    def finish(self) -> None:
        self.finished = True

    @property
    def is_connection_dead(self) -> bool:
        return self.dead

    @property
    def death_reason(self):
        return self.reason


def _finishing_socket(raw: _Raw) -> object:
    """A serving wrapper whose leg the owner has marked as teardown."""
    return SimpleNamespace(
        send=lambda data, start_sample=None: False,
        finish=lambda: raw.__setattr__('finished', True),
        finalize=lambda: None,
        is_connection_dead=False,
        death_reason=None,
        typed_death_reason=None,
        _finishing=True,
    )


@pytest.mark.asyncio
async def test_teardown_flush_with_finishing_leg_holds_packet_bounded(monkeypatch):
    """Prod shape: the leg is finishing (owner teardown). The flush must hold
    the packet on the bounded live tail and return — never recurse on
    identical arguments, never attempt a failover that teardown would refuse,
    and never false-positive a terminal transcription failure."""
    receiver = _receiver(monkeypatch)
    # A held capture chunk far older than the 3s horizon: the new packet's
    # projected span crosses it, so the window verdict is 'failover' — and the
    # bare finishing wrapper offers no trim anchor to soften it.
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())

    failover_calls = 0

    async def refused_failover() -> bool:
        nonlocal failover_calls
        failover_calls += 1
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert failover_calls == 0
    assert len(receiver._replay_live_tail) == 1
    assert receiver._replay_live_tail[0].data == packet
    assert receiver._replay_tail_bytes == len(packet)
    assert not buffer
    assert receiver._stt_buffer_start_sample is None
    assert not receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_refused_failover_on_serving_leg_falls_through_to_terminal_path(monkeypatch):
    """Chain-exhausted shape: the leg is serving but the failover attempt is
    refused. The flush attempts once, falls through to the idempotent terminal
    send path, and stays bounded — no recursion."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    # A live serving wrapper: no finishing latch.
    receiver.stt_socket = SimpleNamespace(
        send=lambda data, start_sample=None: False,
        finish=lambda: None,
        finalize=lambda: None,
        is_connection_dead=False,
        death_reason=None,
        typed_death_reason=None,
    )

    failover_calls = 0

    async def refused_failover() -> bool:
        nonlocal failover_calls
        failover_calls += 1
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert 1 <= failover_calls <= 3
    assert receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_dead_not_finishing_leg_still_delivers_packet_via_recovery_tail(monkeypatch):
    """Pin the pre-existing topology the guard deliberately preserves: a dead,
    not-finishing leg enters the method's recovery-tail branch, which delivers
    the packet into the live tail directly (the test_live_stt_resilient_stream
    replay-before-current-chunk contract depends on this route). The failover
    arm is never reached, so no recursion — and no bounded-tail double-entry."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    dead = _Raw()
    dead.dead = True
    dead.reason = 'connection_lost'
    receiver.stt_socket = _finishing_socket(dead)
    # Not finishing: drop the teardown latch, keep the dead one.
    receiver.stt_socket._finishing = False
    receiver._replay_ingesting = True

    failover_calls = 0

    async def refused_failover() -> bool:
        nonlocal failover_calls
        failover_calls += 1
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert failover_calls == 0
    assert not buffer
    assert receiver._stt_buffer_start_sample is None
    assert len(receiver._replay_live_tail) == 1
    assert receiver._replay_live_tail[0].data == packet
    assert not receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_hold_helper_clears_buffer_and_releases_start_sample(monkeypatch):
    """The hold helper always consumes the caller's buffer: audio it holds is
    birth-noted and tail-metered; an empty or unpositioned buffer is simply
    released so the next flush starts at a fresh cursor."""
    receiver = _receiver(monkeypatch)
    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    assert receiver._hold_refused_failover_packet(buffer, RATE * 8)
    assert not buffer
    assert receiver._stt_buffer_start_sample is None
    assert len(receiver._replay_live_tail) == 1
    assert receiver._replay_live_tail[0].start == RATE * 8
    assert receiver._replay_tail_bytes == len(packet)

    empty = bytearray()
    assert receiver._hold_refused_failover_packet(empty, None)
    assert not empty
    assert receiver._stt_buffer_start_sample is None
    assert len(receiver._replay_live_tail) == 1


@pytest.mark.asyncio
async def test_finishing_wrapper_with_unmanaged_latch_is_held_under_recovery(monkeypatch):
    """``socket_is_finishing``'s default read ignores a legacy wrapper's
    ``_finishing`` while recovery is on; the flush's teardown read must use the
    unmanaged latch — it is exactly the latch owner teardown marks."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())

    from utils.stt.resilient_stream import socket_is_finishing

    # Document the asymmetry the guard relies on.
    assert not socket_is_finishing(receiver.stt_socket)
    assert socket_is_finishing(receiver.stt_socket, include_unmanaged_finishing=True)

    async def refused_failover() -> bool:
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert len(receiver._replay_live_tail) == 1


@pytest.mark.asyncio
async def test_finishing_leg_off_path_keeps_legacy_failover_route(monkeypatch):
    """Recovery off (legacy pinned path): the flush delegates to
    legacy_recovery.flush_stt_buffer, which already attempted the failover
    before recursing — the legacy loop must be untouched by this guard."""
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'false')
    receiver = _receiver(monkeypatch)
    receiver.recovery = None
    receiver.recovery_enabled = False
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=False)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())

    legacy_called = []

    async def legacy_flush(recv, buf, *, force=False):
        legacy_called.append((bytes(buf), force))
        buf.clear()
        recv._stt_buffer_start_sample = None

    monkeypatch.setattr(receiver_module.legacy_recovery, 'flush_stt_buffer', legacy_flush)

    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert legacy_called == [(packet, True)]


@pytest.mark.asyncio
async def test_held_tail_packet_is_birth_noted_for_recovery_pacing(monkeypatch):
    """A held packet's birth wall time rides in the tail entry, so a later
    adopted leg's pump paces and residence-bounds it exactly like live audio
    (ReplayTailSocket._pump_tail reads packet_deadline from the birth ledger)."""
    receiver = _receiver(monkeypatch)
    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    receiver._hold_refused_failover_packet(buffer, RATE * 8)
    entry = receiver._replay_live_tail[0]
    assert entry.start == RATE * 8
    assert entry.data == packet
    assert entry.received > 0
    # The birth ledger knows the interval, so lookup resolves it.
    assert receiver._live_birth.lookup(entry.start) is not None


@pytest.mark.asyncio
async def test_take_tail_transfers_held_packets_to_replacement_leg(monkeypatch):
    """The hold arm's packets must survive leg replacement: ReplayTailSocket
    is constructed over the receiver's live tail, so its take_tail hands the
    held packets to the successor instead of losing them."""
    receiver = _receiver(monkeypatch)
    receiver._stt_buffer_start_sample = RATE * 8
    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    receiver._hold_refused_failover_packet(buffer, RATE * 8)

    tail = ReplayTailSocket(
        _finishing_socket(_Raw()),
        ReplayPacer(RATE, 'soniox', None, limits=ReplayLimits()),
        receiver._replay_live_tail,
        receiver.host,
        source='soniox',
    )
    transferred = tail.take_tail()
    assert [entry.data for entry in transferred] == [packet]
    # take_tail swaps in a fresh deque: the receiver's reference (the old one,
    # now emptied into the transfer) no longer gates tail bookkeeping.
    assert tail.tail is not receiver._replay_live_tail
    assert not tail.tail
    assert tail._tail_bytes == 0


@pytest.mark.asyncio
async def test_finishing_socket_with_raw_latch_is_finishing_under_default_read(monkeypatch):
    """The recovery-aware wrapper shapes both land in the hold arm: a managed
    ``leg_outcome.owner_closing`` latch reads as finishing under every read,
    and a legacy wrapper with no recovery pin reads its own ``_finishing``
    through the default read (only recovery-pinned wrappers hide it)."""
    from utils.stt.resilient_stream import socket_is_finishing

    outcome = SimpleNamespace(owner_closing=True)
    managed = SimpleNamespace(leg_outcome=outcome, _finishing=False, raw=None)
    assert socket_is_finishing(managed)
    assert socket_is_finishing(managed, include_unmanaged_finishing=True)

    # A wrapper whose raw carries the latch, with recovery pinned off: both
    # reads agree it is finishing.
    wrapped = SimpleNamespace(_finishing=False, raw=SimpleNamespace(_finishing=True), recovery_enabled=False)
    assert socket_is_finishing(wrapped)
    assert socket_is_finishing(wrapped, include_unmanaged_finishing=True)

    # Only a recovery-pinned wrapper hides the unmanaged latch from the
    # default read — the asymmetry the guard's unmanaged read covers.
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    pinned = SimpleNamespace(_finishing=False, raw=SimpleNamespace(_finishing=True), recovery_enabled=True)
    assert not socket_is_finishing(pinned)
    assert socket_is_finishing(pinned, include_unmanaged_finishing=True)


@pytest.mark.asyncio
async def test_hold_arm_never_marks_terminal_failure_and_flush_stays_reusable(monkeypatch):
    """After a hold, the receiver must stay usable: a second flush against a
    newly adopted serving leg works normally (state untouched by the hold)."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)
    assert not receiver.host.state.stt_terminal_failure
    assert not receiver.host.state.active is False

    # A second packet holds too: the tail accumulates, nothing crashes.
    receiver._stt_buffer_start_sample = RATE * 8
    second = bytearray(b'\x03\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(second, force=True), timeout=2)
    assert len(receiver._replay_live_tail) == 2
    assert receiver._replay_tail_bytes == 2 * len(b'\x03\x00' * 480)
    assert not receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_bounded_teardown_awaits_and_surfaces_teardown_task_outcome(monkeypatch):
    """The sensor's paired line exists because receive's teardown re-entry
    awaits the spawned stt_shutdown task and re-raises its exception. Pin that
    delivery: a teardown task that fails is surfaced (so failures stay
    visible), and one that succeeds lets receive's finally complete cleanly —
    with the recursion fixed, a clean teardown is the prod path."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    receiver.shutdown_deadline = time.monotonic() + 5.0
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())

    completed = []

    # _bounded_teardown spawns the teardown body via host.spawn; give the
    # double a real spawning spawn.
    receiver.host.spawn = lambda coro, *, name: asyncio.create_task(coro, name=name)

    async def clean_teardown(buf, decoded):
        completed.append(True)

    # Clean path: _teardown_body runs the hold arm and returns normally.
    monkeypatch.setattr(receiver, '_teardown_body', clean_teardown)
    await asyncio.wait_for(receiver._bounded_teardown(bytearray(b'\x02\x00' * 480), 960), timeout=2)
    assert completed == [True]

    failed = []

    async def failing_teardown(buf, decoded):
        failed.append(True)
        raise RuntimeError('provider drain failed')

    monkeypatch.setattr(receiver, '_teardown_body', failing_teardown)
    with pytest.raises(RuntimeError, match='provider drain failed'):
        await asyncio.wait_for(receiver._bounded_teardown(bytearray(b'\x02\x00' * 480), 960), timeout=2)
    assert failed == [True]


def test_window_verdict_matrix_for_flush_arm_decisions():
    """The flush arm reads only the verdict: pin window_replay_action on the
    wrapper shapes the arms distinguish — bare wrapper without a raw cannot
    fail anything (verdict only), raw-backed wrapper gets its fail() called
    before the verdict, and a fitting packet is appended."""
    from utils.stt.resilient_stream import window_replay_action

    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    ring.append(b'\x01\x00' * 480, 0)
    big = bytes(bytearray(b'\x02\x00' * 480))

    # Bare finishing wrapper: verdict is failover, nothing to fail.
    bare = _finishing_socket(_Raw())
    assert window_replay_action(ring, bare, big, RATE * 8) == 'failover'

    # Raw-backed wrapper with a fail latch: the raw learns why before failover.
    raw = _Raw()
    raw.failures = []
    raw.request_replay_cut = lambda: None
    raw.window_replay_diagnostics = None
    backed = SimpleNamespace(
        send=lambda data, start_sample=None: False,
        finish=lambda: None,
        finalize=lambda: None,
        is_connection_dead=False,
        death_reason=None,
        typed_death_reason=None,
        _finishing=False,
        raw=raw,
        fail=lambda reason, **kw: raw.failures.append(reason),
    )
    assert window_replay_action(ring, backed, big, RATE * 8) == 'failover'
    assert raw.failures == ['capacity_full']

    # A packet that fits the horizon is appended, whatever the wrapper.
    small_ring = ResilientAudio(RATE, ring_seconds=30, strict_replay=True, recovery_enabled=True)
    small_ring.append(b'\x01\x00' * 480, 0)
    assert window_replay_action(small_ring, bare, b'\x02\x00' * 480, 480) == 'append'


@pytest.mark.asyncio
async def test_flush_serving_leg_adopted_failover_reroutes_packet(monkeypatch):
    """On a serving leg the legacy-parity attempt succeeds (replacement
    adopted): the flush retries the packet against the new socket inside the
    same bounded loop instead of recursing or holding."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    # Serving wrapper whose send keeps failing (never accepts).
    receiver.stt_socket = SimpleNamespace(
        send=lambda data, start_sample=None: False,
        finish=lambda: None,
        finalize=lambda: None,
        is_connection_dead=False,
        death_reason=None,
        typed_death_reason=None,
    )

    attempts = 0

    async def adopted_once_then_exhausted() -> bool:
        """Prod-shaped adoption: the first attempt replaces the socket, the
        recovery latch refuses any further rebuild (exhausted)."""
        nonlocal attempts
        attempts += 1
        receiver.stt_socket = SimpleNamespace(
            send=lambda data, start_sample=None: True,
            finish=lambda: None,
            finalize=lambda: None,
            is_connection_dead=False,
            death_reason=None,
            typed_death_reason=None,
        )
        return attempts == 1

    monkeypatch.setattr(receiver, '_failover_stt_socket', adopted_once_then_exhausted)

    sent_via = []

    async def flush(websocket, state, *, stt_socket, buffer, start_sample, **_kwargs):
        sent_via.append((stt_socket is not None, bytes(buffer)))
        buffer.clear()
        return True

    # The receiver imports flush_live_stt_buffer into its own namespace.
    monkeypatch.setattr(receiver_module, 'flush_live_stt_buffer', flush)

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert attempts >= 1
    assert sent_via, 'packet must reach the terminal send path after adoption'


@pytest.mark.asyncio
async def test_dead_leg_with_recovery_pinned_finishing_wrapper_keeps_recovery_route(monkeypatch):
    """Route pin: a dead leg whose wrapper carries the finishing latch with
    recovery pinned ON is invisible to the default finishing read, so the
    guard recurses into the recovery-tail branch exactly as before the fix —
    that branch delivers the packet and terminates (never the hold arm)."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    dead = _Raw()
    dead.dead = True
    dead.reason = 'connection_lost'
    wrapper = _finishing_socket(dead)
    wrapper._finishing = True  # recovery-pinned: hidden from the default read
    wrapper.recovery_enabled = True
    receiver.stt_socket = wrapper

    failover_calls = 0

    async def refused_failover() -> bool:
        nonlocal failover_calls
        failover_calls += 1
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    packet = b'\x02\x00' * 480
    buffer = bytearray(packet)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert failover_calls == 0
    # Delivered through the recovery-tail branch, not the hold arm.
    assert not receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_hold_helper_releases_cursor_when_capture_position_unknown(monkeypatch):
    """A teardown flush may race the cursor: with no start sample the helper
    cannot invent a capture position, so it releases the buffer without a
    phantom tail entry."""
    receiver = _receiver(monkeypatch)
    buffer = bytearray(b'\x02\x00' * 480)
    assert receiver._hold_refused_failover_packet(buffer, None)
    assert not buffer
    assert not receiver._replay_live_tail
    assert receiver._replay_tail_bytes == 0
    assert receiver._stt_buffer_start_sample is None


@pytest.mark.asyncio
async def test_hold_arm_leaves_replay_delivery_and_recovery_state_untouched(monkeypatch):
    """The hold arm parks the packet for the CURRENT receiver only: it must
    not fabricate an adoption (_replay_delivery stays None), must not open a
    recovery episode, and must not latch the client as gone."""
    receiver = _receiver(monkeypatch)
    receiver._stt_buffer_start_sample = RATE * 8
    buffer = bytearray(b'\x02\x00' * 480)
    receiver._hold_refused_failover_packet(buffer, RATE * 8)

    assert receiver._replay_delivery is None
    assert receiver._replay_ingesting is False
    assert receiver._replay_recovery_task is None
    assert not receiver.client_closing
    assert receiver.recovery.state.value == 'serving'


@pytest.mark.asyncio
async def test_trim_verdict_still_sends_through_the_normal_flush_path(monkeypatch):
    """The arms key on the verdict: 'trim' is not 'failover' — the packet goes
    straight to the send path with the trim applied to the ring."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = SimpleNamespace(
        send=lambda data, start_sample=None: False,
        finish=lambda: None,
        finalize=lambda: None,
        is_connection_dead=False,
        death_reason=None,
        typed_death_reason=None,
        has_untranscribed_speech=lambda: False,
    )

    failover_calls = 0

    async def refused_failover() -> bool:
        nonlocal failover_calls
        failover_calls += 1
        return False

    monkeypatch.setattr(receiver, '_failover_stt_socket', refused_failover)

    sent = []

    async def flush(websocket, state, *, stt_socket, buffer, start_sample, **_kwargs):
        sent.append(bytes(buffer))
        buffer.clear()
        return True

    monkeypatch.setattr(receiver_module, 'flush_live_stt_buffer', flush)

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert failover_calls == 0
    assert len(sent) == 1
    assert not buffer


@pytest.mark.asyncio
async def test_hold_arm_rejects_packets_beyond_the_tail_budget(monkeypatch):
    """The bounded live tail has a hard byte budget (LIVE_TAIL_SECONDS); the
    hold arm must respect it — a packet beyond the bound is released, not
    parked, so the hold arm cannot grow without limit during teardown."""
    receiver = _receiver(monkeypatch)
    receiver._stt_buffer_start_sample = 0
    oversized = b'\x02\x00' * (RATE * 2 * 30)  # 30s of PCM: beyond the 26s tail bound
    buffer = bytearray(oversized)
    assert receiver._hold_refused_failover_packet(buffer, 0)
    assert not buffer
    assert not receiver._replay_live_tail
    assert receiver._replay_tail_bytes == 0

    # A normal packet still parks after the refused oversized one.
    receiver._stt_buffer_start_sample = 480
    normal = bytearray(b'\x03\x00' * 480)
    assert receiver._hold_refused_failover_packet(normal, 480)
    assert len(receiver._replay_live_tail) == 1
    assert receiver._replay_tail_bytes == 960


@pytest.mark.asyncio
async def test_receive_task_state_contract_around_teardown_flush(monkeypatch):
    """receive_data's finally flips client_closing/_receiving before the
    teardown body runs; the flush's hold arm must not depend on either flag
    (teardown is exactly when they are already set)."""
    receiver = _receiver(monkeypatch)
    ring = ResilientAudio(RATE, ring_seconds=3, strict_replay=True, recovery_enabled=True)
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    ring.append(b'\x01\x00' * 480, 0)
    receiver._stt_buffer_start_sample = RATE * 8
    receiver.stt_socket = _finishing_socket(_Raw())
    # Mirror receive_data's finally state at teardown time.
    receiver.client_closing = True
    receiver._receiving = False

    buffer = bytearray(b'\x02\x00' * 480)
    await asyncio.wait_for(receiver._flush_stt_buffer(buffer, force=True), timeout=2)

    assert len(receiver._replay_live_tail) == 1
    assert not buffer
    assert not receiver.host.state.stt_terminal_failure
