"""Soniox local delivery deaths: three typed causes, one bounded diagnostic line.

Until 2026-10-21 (P34) every local delivery bound — the send queue filling,
replay pacing stalling, a frame's delivery deadline expiring — latched as
``capacity_full``, which read as destination capacity while at peak ~200/h
Soniox legs failed over to Parakeet (P32). These tests pin the split, the
bounded death log (queue depth and age, time since the last send; never a UID
or content), and that the new tokens stay censored provider evidence.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from types import SimpleNamespace

from config.live_stt_replay import ReplayLimits
from utils.observability import fallback as fallback_mod
from utils.stt import resilient_stream, soniox
from utils.stt.connect_metrics import ERROR_CLASS_CAPABILITY, connect_error_class
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_reason import (
    LIVE_STT_FAILURE_REASONS,
    LOCAL_DELIVERY_DEATH_REASONS,
    LOCAL_DELIVERY_EXPIRED,
    LOCAL_DELIVERY_REPLAY_SEND_STALLED,
    LOCAL_DELIVERY_SEND_QUEUE_FULL,
    normalize_live_stt_reason,
)
from utils.stt.live_signal import provider_observation
from utils.stt.replay_delivery import AudioDeliveryExpired
from utils.stt.send_queue import AudioSendQueue
from utils.stt.streaming import SafeSonioxSocket

DIAGNOSTIC_LINE = re.compile(
    r'^Soniox local delivery death subtype=(?P<subtype>\w+) queue_packets=(?P<packets>-?\d+) '
    r'queue_age_seconds=(?P<age>-?\d+\.\d+) since_last_send_seconds=(?P<since>-?\d+\.\d+) '
    r'session_age_seconds=(?P<session>\d+\.\d+)$'
)


class BlockingWebSocket:
    """Audio writes stall until ``release`` is set; no inbound frames ever arrive.

    Tests set ``release`` before leaving the loop: a writer parked in
    ``wait_for(queue.get())`` whose future already resolved keeps running after
    ``asyncio.run`` cancels it (3.11 ``wait_for`` swallows that cancellation),
    so a never-released stall would hang loop teardown.
    """

    def __init__(self) -> None:
        self.sent: list[bytes | str] = []
        self.block = True
        self.release = asyncio.Event()

    async def send(self, data):
        self.sent.append(data)
        if self.block and isinstance(data, (bytes, bytearray)) and data:
            await self.release.wait()

    async def close(self) -> None:
        pass

    def __aiter__(self):
        async def gen():
            await self.release.wait()
            return
            yield ''  # pragma: no cover - makes this an async generator

        return gen()


async def _settle(ws: BlockingWebSocket) -> None:
    ws.release.set()
    await asyncio.sleep(0.01)


def _diagnostic(caplog) -> re.Match | None:
    for record in caplog.records:
        if record.getMessage().startswith('Soniox local delivery death'):
            return DIAGNOSTIC_LINE.match(record.getMessage())
    return None


def test_local_delivery_tokens_stay_bounded_and_censored():
    for token in (LOCAL_DELIVERY_SEND_QUEUE_FULL, LOCAL_DELIVERY_REPLAY_SEND_STALLED, LOCAL_DELIVERY_EXPIRED):
        assert token in LIVE_STT_FAILURE_REASONS
        assert normalize_live_stt_reason(token) == token
        # A local bound is never evidence against the provider (P32: these
        # deaths were misread as Parakeet capacity).
        assert provider_observation('failover', token) is None
        assert connect_error_class(token) == ERROR_CLASS_CAPABILITY


def test_send_queue_full_death_is_typed_with_bounded_diagnostics(monkeypatch, caplog):
    monkeypatch.setattr(soniox, 'recovery_enabled', lambda: True)

    async def main() -> SafeSonioxSocket:
        ws = BlockingWebSocket()
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        try:
            # Synchronous sends have no await point, so the writer task cannot
            # drain mid-fill: the 2001st put hits the maxsize deterministically.
            for _ in range(2010):
                if not sock.send(b'\x01\x00' * 160):
                    break
            return sock
        finally:
            await _settle(ws)

    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = asyncio.run(main())
    assert sock.is_connection_dead
    assert sock.typed_death_reason == 'send_queue_full'
    match = _diagnostic(caplog)
    assert match, 'bounded death log missing for a local delivery death'
    assert match.group('subtype') == 'send_queue_full'
    assert int(match.group('packets')) == 2000
    assert float(match.group('age')) >= 0.0
    # The stalled writer never completed a wire write: the -1 sentinel, not 0.
    assert float(match.group('since')) == -1.0


def test_send_queue_full_diagnostics_report_time_since_last_send(monkeypatch, caplog):
    monkeypatch.setattr(soniox, 'recovery_enabled', lambda: True)

    async def main() -> SafeSonioxSocket:
        ws = BlockingWebSocket()
        ws.block = False
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        try:
            sock.send(b'\x01\x00' * 160)
            await asyncio.sleep(0.05)  # The writer completes this one write.
            ws.block = True
            for _ in range(2010):
                if not sock.send(b'\x01\x00' * 160):
                    break
            return sock
        finally:
            await _settle(ws)

    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = asyncio.run(main())
    assert sock.typed_death_reason == 'send_queue_full'
    match = _diagnostic(caplog)
    assert match
    assert float(match.group('since')) >= 0.0


def test_replay_send_stall_death_is_typed(monkeypatch, caplog):
    monkeypatch.setattr(soniox, 'recovery_enabled', lambda: True)

    async def main():
        ws = BlockingWebSocket()
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        try:
            monkeypatch.setattr(sock, 'replay_limits', ReplayLimits(queue_wait_seconds=0.001))
            sock._send_queue = AudioSendQueue(maxsize=1)
            sock._send_task.cancel()
            await asyncio.gather(sock._send_task, return_exceptions=True)
            assert sock.send(b'\x01\x00')
            admitted = await sock.wait_send_capacity()
            return sock, admitted
        finally:
            await _settle(ws)

    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock, admitted = asyncio.run(main())
    assert not admitted
    assert sock.is_connection_dead
    assert sock.typed_death_reason == 'replay_send_stalled'
    match = _diagnostic(caplog)
    assert match
    assert match.group('subtype') == 'replay_send_stalled'
    assert int(match.group('packets')) == 1


def test_delivery_expiry_death_is_typed(monkeypatch, caplog):
    monkeypatch.setattr(soniox, 'recovery_enabled', lambda: True)

    async def main() -> SafeSonioxSocket:
        ws = BlockingWebSocket()
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())

        async def expired_write(data):
            raise AudioDeliveryExpired('live audio delivery expired')

        sock._write = expired_write
        try:
            assert sock.send(b'\x01\x00' * 160)
            for _ in range(100):
                if sock.is_connection_dead:
                    break
                await asyncio.sleep(0.01)
            return sock
        finally:
            await _settle(ws)

    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = asyncio.run(main())
    assert sock.is_connection_dead
    assert sock.typed_death_reason == 'delivery_expired'
    match = _diagnostic(caplog)
    assert match
    assert match.group('subtype') == 'delivery_expired'


class FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount: float = 1.0):
        self.parent.increments.append((self.labels, amount))


class FakeCounter:
    def __init__(self):
        self.increments: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return FakeCounterChild(self, labels)


def test_local_delivery_death_keeps_its_reason_on_omi_fallback_total(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    hop = PendingLiveFailover(from_mode='soniox', to_mode='parakeet', reason=LOCAL_DELIVERY_SEND_QUEUE_FULL)
    hop.note_failure(None)
    ((labels, amount),) = counter.increments
    assert labels['reason'] == 'send_queue_full'
    assert labels['from_mode'] == 'soniox' and labels['to_mode'] == 'parakeet'
    assert labels['outcome'] == 'exhausted'
    assert amount == 1.0


def test_queue_age_is_the_oldest_still_queued_packet_not_the_session():
    """A session that stays one packet ahead never empties the queue; the age
    must still be the oldest *queued* packet's wait, not time since the first."""

    async def main() -> tuple[float, float]:
        queue: AudioSendQueue = AudioSendQueue(maxsize=8)
        queue.put_nowait(b'\x01\x00')
        await asyncio.sleep(0.05)
        queue.put_nowait(b'\x02\x00')
        await queue.get()  # the first packet goes to the wire; the second is now the oldest queued
        return queue.oldest_queued_age(time.monotonic()), queue.oldest_queued_age(time.monotonic() + 10)

    age, later = asyncio.run(main())
    assert 0.0 <= age < 0.05
    assert later > 9.9
    assert AudioSendQueue(maxsize=1).oldest_queued_age(time.monotonic()) == -1.0


def test_exhausted_tail_terminate_forwards_only_local_tokens_never_a_circuit_vote():
    """The owner's exhausted-recovery terminate reported a fixed local token
    before the split and never benched the provider. A tail that died without
    latching a local cause (a residence-deadline write stall with the vendor
    socket open) resolves to connection_lost through the generic funnel; this
    site must not forward that into a serve-failure circuit vote."""
    from utils.stt import live_failure

    # What a ReplayTailSocket exposes after a residence-deadline stall: no local
    # reason latched, so its normalized_death_reason falls to the default.
    stalled = SimpleNamespace(
        typed_death_reason=None, death_reason=None, normalized_death_reason='connection_lost', is_connection_dead=True
    )
    assert live_failure.live_stt_terminal_reason(stalled, 'send_failed') == 'connection_lost'  # the generic funnel
    assert live_failure.local_tail_terminal_reason(stalled) == 'send_queue_full'
    assert live_failure.local_tail_terminal_reason(None) == 'send_queue_full'
    for token in LOCAL_DELIVERY_DEATH_REASONS:
        assert live_failure.local_tail_terminal_reason(SimpleNamespace(typed_death_reason=token)) == token
    # A provider token on the tail keeps its attribution through the death
    # monitor; this site reports the local bound it observed, as before.
    assert (
        live_failure.local_tail_terminal_reason(SimpleNamespace(typed_death_reason='provider_5xx')) == 'send_queue_full'
    )
    for token in LOCAL_DELIVERY_DEATH_REASONS:
        assert token not in live_failure._SERVE_FAILURE_REASONS
        assert token not in live_failure._CIRCUIT_OPENING_REASONS


def test_window_successor_replay_wall_expiry_is_replay_send_stalled():
    """``replay_chunks`` on a successor that implements ``fail`` (the Parakeet
    window) must latch the same local token as the socket-level wall path."""
    failed: list[str] = []
    window = SimpleNamespace(
        fail=lambda reason, **kw: failed.append(reason),
        is_connection_dead=False,
        replay_limits=ReplayLimits(),
        max_replay_rate=1.0,
    )
    ring = resilient_stream.ResilientAudio(16000, ring_seconds=10, strict_replay=True)

    async def main():
        return await resilient_stream.replay_chunks(
            window,
            ((0, b'\x01\x00' * 160),),
            source=ring,
            provider='soniox',
            soniox=None,
            deadline=resilient_stream.clock() - 1.0,  # the prefix wall has already passed
        )

    assert asyncio.run(main()) == 0
    assert failed == [LOCAL_DELIVERY_REPLAY_SEND_STALLED]
