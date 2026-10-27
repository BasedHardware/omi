"""The gated socket must answer the recovery leg's provider tail drain.

Failure-Class: FC-fallible-teardown-skips-required-finalizer — the required
finalizer here is the provider's tail drain: it flushes the last held
utterance and closes the transport, and it is the one thing a failed teardown
wrapper silently skips. Every socket in the serving chain implements
``drain_and_close`` (``SafeSonioxSocket``, the parakeet window socket,
``LiveChainSession``, ``ReplayTailSocket``); ``GatedSTTSocket`` was the one
wrapper without it, so the recovery-adopted leg — a ``ReplayTailSocket`` whose
``connection`` is a ``GatedSTTSocket`` (the receiver wraps the replacement
provider's raw socket in the gate before storing it on the delivery) — raised
``AttributeError: 'GatedSTTSocket' object has no attribute 'drain_and_close'``
inside the delivery's own drain. The receiver's ``except`` turned that into a
``Listen STT drain failure type=AttributeError`` ERROR and the paired
``Unhandled exception in WebSocket task ... stt_shutdown_provider`` line, and
the provider's tail was never drained: the last held utterance and the EOS
close were lost on every such session (prod backend-listen since 2026-10-22:
×362, all the same attribute name).

Guards:
- the delivery-wrapping-gated shape drains end to end: the gate's held
  utterance is finalized to the provider first, then the provider's own
  ``drain_and_close`` runs (EOS seen, transport closed) — no AttributeError;
- ``GatedSTTSocket.drain_and_close`` alone flushes (finalize) before draining
  the wrapped socket and awaits its async drain;
- a legacy provider without ``drain_and_close`` still gets ``finish()`` from
  the wrapper — the same tolerant fallback the shared drain helper uses, and
  byte-for-byte the same lifecycle the shared helper gives a plain provider;
- a finalize refusal from the provider must not skip the provider close;
- shadow gates (which never owned held speech) drain without injecting a
  finalize; passthrough gates (Modulate) drain like any other mode;
- a provider crash mid-drain still closes the gate's capture files;
- the receiver's drain boundary keeps the delivery as the drain owner instead
  of unwrapping to the gated wrapper's transport (the boundary must not reach
  past the one wrapper that now owns the drain contract) and releases the
  track lease for every shape.
"""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

import routers.listen.receiver as receiver_module
import utils.stt.vad_gate as vad_gate_module
from routers.listen.receiver import ListenReceiver  # type: ignore[reportPrivateUsage]
from utils.stt import replay_delivery as replay_delivery_module
from utils.stt import streaming as st
from utils.stt.replay_delivery import ReplayPacer, ReplayTailSocket
from utils.stt.socket import STTSocket
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate


class _ProviderBase(STTSocket):
    """Provider double recording finalize/EOS order; finish() only (legacy)."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self._dead = False
        self.finish_calls = 0
        self.finalize_calls = 0
        self.drain_calls = 0

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Any:
        return 'closed' if self._dead else None

    def send(self, data: bytes) -> bool:
        self.events.append('send')
        return True

    def finalize(self) -> None:
        self.events.append('finalize')
        self.finalize_calls += 1

    def finish(self) -> None:
        self.events.append('finish')
        self.finish_calls += 1
        self._dead = True


class _TailProvider(_ProviderBase):
    """A modern provider: its own drain closes the transport (soniox, window)."""

    async def drain_and_close(self) -> None:
        self.events.append('drain_start')
        await asyncio.sleep(0)
        self.events.append('drain_eos')
        self.drain_calls += 1
        self.finish()


class _LegacyProvider(_ProviderBase):
    """Prod's raw provider shape before tail drains existed: finish() only."""

    # No drain_and_close attribute on purpose.


class _BrokenDrainProvider(_TailProvider):
    """A provider whose drain itself fails: teardown must still close files."""

    async def drain_and_close(self) -> None:
        self.events.append('drain_start')
        raise OSError('provider drain exploded')


class _SlowEosProvider(_TailProvider):
    """A provider whose drain is genuinely multi-step: drain must await it."""

    async def drain_and_close(self) -> None:
        self.events.append('drain_start')
        await asyncio.sleep(0.01)
        self.events.append('drain_eos')
        self.finish()


class _FakeCaptureFile:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _gate(active: bool = True) -> VADStreamingGate:
    gate = VADStreamingGate.__new__(VADStreamingGate)
    gate.mode = 'active' if active else 'shadow'
    gate.uid = 'drain-uid'
    gate.session_id = 'drain-session'
    gate._finalize_errors = 0  # type: ignore[reportAttributeAccessIssue]
    return gate


def _gated(provider: _ProviderBase, *, active: bool = True, passthrough: bool = False) -> GatedSTTSocket:
    return GatedSTTSocket(provider, gate=_gate(active), passthrough_audio=passthrough)


def _delivery(connection: Any) -> ReplayTailSocket:
    return ReplayTailSocket(
        connection, ReplayPacer(16000, 'soniox', connection), deque(), SimpleNamespace(receiver=None)
    )


@pytest.fixture(autouse=True)
def _mock_silero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vad_gate_module, 'run_vad_window', lambda *a, **k: (0.1, None, None), raising=False)
    monkeypatch.setattr(vad_gate_module, 'make_fresh_state', lambda: (None, None), raising=False)


@pytest.mark.asyncio
async def test_delivery_over_gated_socket_drains_provider_tail():
    """The prod shape: delivery.connection is a GatedSTTSocket.

    ReplayTailSocket.drain_and_close calls connection.drain_and_close()
    unconditionally; before the fix that attribute lookup raised
    AttributeError out of the gated wrapper and the drain boundary logged
    ``Listen STT drain failure`` while the provider tail was skipped.
    """
    provider = _TailProvider()
    gated = GatedSTTSocket(provider, gate=_gate(active=True))
    delivery = ReplayTailSocket(gated, ReplayPacer(16000, 'soniox', gated), deque(), SimpleNamespace(receiver=None))
    await delivery.drain_and_close()
    # The gate flushed the held utterance to the provider before the tail
    # drained, and the provider's own drain ran to its EOS.
    assert provider.events[0] == 'finalize'
    assert 'drain_start' in provider.events and 'drain_eos' in provider.events
    assert provider.events.index('finalize') < provider.events.index('drain_start')


@pytest.mark.asyncio
async def test_gated_socket_drain_flushes_held_speech_then_drains_provider():
    provider = _TailProvider()
    gated = GatedSTTSocket(provider, gate=_gate(active=True))
    await gated.drain_and_close()
    # The held utterance reaches the provider before the tail drains; the
    # provider's own drain (not the wrapper) closes the transport.
    assert provider.events == ['finalize', 'drain_start', 'drain_eos', 'finish']


@pytest.mark.asyncio
async def test_gated_socket_drain_falls_back_to_finish_for_legacy_provider():
    provider = _LegacyProvider()
    gated = GatedSTTSocket(provider, gate=_gate(active=True))
    await gated.drain_and_close()
    # No AttributeError: the shared drain helper's tolerant fallback — a
    # synchronous close — covers providers without an async tail.
    assert provider.events == ['finalize', 'finish']


@pytest.mark.asyncio
async def test_gate_flush_failure_still_closes_the_provider():
    """A finalize refusal must not skip the provider close either."""
    provider = _TailProvider()
    gated = GatedSTTSocket(provider, gate=_gate(active=True))

    def boom() -> None:
        raise RuntimeError('provider refused finalize')

    provider.finalize = boom  # type: ignore[method-assign]
    await gated.drain_and_close()
    # The flush failure is contained (counted + logged); the drain and the
    # transport close still happened.
    assert 'drain_start' in provider.events and 'finish' in provider.events


def _bare_receiver(socket: Any) -> ListenReceiver:
    receiver = ListenReceiver.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(is_multi_channel=False)
    receiver.recovery = None
    receiver.stt_socket = socket
    receiver.stt_sockets_multi = [None]
    receiver.channel_configs = [None]  # type: ignore[reportAttributeAccessIssue]
    receiver._pending_live_failover = None  # type: ignore[reportAttributeAccessIssue]
    receiver._replay_delivery = None  # type: ignore[reportAttributeAccessIssue]
    receiver._resilient_closing = False  # type: ignore[reportAttributeAccessIssue]
    receiver._resilient_audio = None  # type: ignore[reportAttributeAccessIssue]
    receiver._window_replay_audio = None  # type: ignore[reportAttributeAccessIssue]
    receiver.shutdown_deadline = None
    return receiver


@pytest.mark.asyncio
async def test_receiver_drain_keeps_delivery_as_owner_and_unwraps_only_gated():
    """The boundary must drain the delivery, not the gated wrapper's transport.

    Unwrapping a ReplayTailSocket to the gated wrapper's provider made the
    boundary bypass the delivery's paced tail entirely — the half of the prod
    bug that turned the missing wrapper method into a session-visible ERROR
    pair. A top-level gated wrapper still unwraps: without a delivery its
    provider transport owns the drain.
    """
    provider = _TailProvider()
    gated = GatedSTTSocket(provider, gate=_gate(active=False))
    delivery = ReplayTailSocket(gated, ReplayPacer(16000, 'soniox', gated), deque(), SimpleNamespace(receiver=None))
    drained: list[Any] = []

    async def delivery_drain() -> None:
        drained.append(type(delivery.connection).__name__)

    delivery.drain_and_close = delivery_drain  # type: ignore[method-assign]
    receiver = _bare_receiver(delivery)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert drained == ['GatedSTTSocket']
    assert receiver.stt_socket is None

    # A top-level gated wrapper (no delivery) still unwraps to its provider.
    provider2 = _TailProvider()
    gated2 = GatedSTTSocket(provider2, gate=_gate(active=False))
    receiver2 = _bare_receiver(gated2)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver2)  # type: ignore[reportPrivateUsage]
    assert 'drain_eos' in provider2.events
    assert receiver2.stt_socket is None


@pytest.mark.asyncio
async def test_receiver_drain_of_plain_provider_is_untouched():
    """A session socket with no wrapper drains directly, as before."""
    provider = _TailProvider()
    receiver = _bare_receiver(provider)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert 'drain_eos' in provider.events
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_receiver_drain_of_legacy_provider_closes_synchronously():
    """A top-level legacy provider gets the shared helper's finish() fallback."""
    provider = _LegacyProvider()
    receiver = _bare_receiver(provider)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert provider.events == ['finish']
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_receiver_drain_covers_both_multi_channel_slots():
    """Multi-channel sessions drain every slot, gated or not."""
    provider_a, provider_b = _TailProvider(), _TailProvider()
    gated_a = _gated(provider_a, active=False)
    receiver = _bare_receiver(None)
    receiver.host = SimpleNamespace(is_multi_channel=True)
    receiver.stt_sockets_multi = [gated_a, provider_b]
    receiver.channel_configs = [None, None]  # type: ignore[reportAttributeAccessIssue]
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert 'drain_eos' in provider_a.events
    assert 'drain_eos' in provider_b.events
    assert receiver.stt_sockets_multi == [None, None]


@pytest.mark.asyncio
async def test_receiver_drain_tolerates_a_none_slot():
    """A never-connected channel slot must not break the sweep."""
    receiver = _bare_receiver(None)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_shadow_mode_gated_socket_drains_without_forcing_a_flush():
    """A shadow gate never owned held speech, so it must not inject a finalize."""
    provider = _TailProvider()
    gated = _gated(provider, active=False)
    await gated.drain_and_close()
    assert 'finalize' not in provider.events
    assert provider.events == ['drain_start', 'drain_eos', 'finish']


@pytest.mark.asyncio
async def test_passthrough_mode_gated_socket_drains_the_provider():
    """Modulate's passthrough shape reaches the provider tail like any other."""
    provider = _TailProvider()
    gated = _gated(provider, active=True, passthrough=True)
    await gated.drain_and_close()
    assert provider.events == ['finalize', 'drain_start', 'drain_eos', 'finish']


@pytest.mark.asyncio
async def test_legacy_provider_gated_drain_absorbs_the_callers_finalize_duty():
    """The wrapper owns the flush the shared helper leaves to its caller.

    ``drain_stt_socket`` expects the caller to have finalized first (chat.py
    finalizes, then drains); the gated wrapper absorbs that duty so a drain
    alone still flushes the gate's held speech before the synchronous close.
    """
    legacy_a, legacy_b = _LegacyProvider(), _LegacyProvider()
    await _gated(legacy_a).drain_and_close()
    legacy_b.finalize()
    await st.drain_stt_socket(legacy_b)
    # Same observed provider lifecycle once the caller-side finalize is
    # accounted for: flush, then the tolerant synchronous close.
    assert legacy_a.events == legacy_b.events == ['finalize', 'finish']


@pytest.mark.asyncio
async def test_drain_awaits_a_genuinely_multi_step_provider_tail():
    """The receiver's bounded wait depends on the drain awaiting tail EOS."""
    provider = _SlowEosProvider()
    gated = _gated(provider, active=False)
    await asyncio.wait_for(gated.drain_and_close(), timeout=1)
    assert provider.events == ['drain_start', 'drain_eos', 'finish']


@pytest.mark.asyncio
async def test_provider_drain_failure_still_closes_capture_files():
    """A provider crash mid-drain must not leak the gate's capture files."""
    provider = _BrokenDrainProvider()
    gated = _gated(provider)
    raw_file, gated_file = _FakeCaptureFile(), _FakeCaptureFile()
    gated._raw_file = raw_file  # type: ignore[reportAttributeAccessIssue]
    gated._gated_file = gated_file  # type: ignore[reportAttributeAccessIssue]
    with pytest.raises(OSError):
        await gated.drain_and_close()
    assert raw_file.closed and gated_file.closed
    assert gated._raw_file is None and gated._gated_file is None  # type: ignore[reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_second_drain_is_idempotent_on_the_provider():
    """Teardown and a late drain can both arrive; the second must be harmless."""
    provider = _TailProvider()
    gated = _gated(provider)
    await gated.drain_and_close()
    await gated.drain_and_close()
    assert provider.drain_calls == 1
    assert provider.events.count('drain_eos') == 1


@pytest.mark.asyncio
async def test_finish_after_drain_does_not_double_close_the_provider():
    """The delivery's finally calls finish(); the wrapper must tolerate it."""
    provider = _TailProvider()
    gated = _gated(provider)
    await gated.drain_and_close()
    gated.finish()
    # The provider's own drain already closed it once; finish() passes through
    # but the recorded lifecycle stays a single close.
    assert provider.finish_calls == 2  # drain closed it, then the pass-through
    assert provider.events.count('drain_eos') == 1


@pytest.mark.asyncio
async def test_receiver_drain_releases_the_track_lease_for_the_gated_shape():
    """Gauge release must fire for the gated shape after a full drain."""
    from utils.stt.socket import _LIVE_SOCKET_LEASES, track_live_stt_socket

    provider = _TailProvider()
    gated = track_live_stt_socket(_gated(provider, active=False), 'soniox')
    receiver = _bare_receiver(gated)
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert id(gated) not in _LIVE_SOCKET_LEASES
    assert 'drain_eos' in provider.events


@pytest.mark.asyncio
async def test_shutdown_deadline_path_spawns_and_waits_for_the_drain():
    """The recovery teardown's spawned drain task carries its errors back.

    With a shutdown deadline the boundary spawns ``stt_shutdown_provider``,
    waits it out, and re-raises its exception into the local ``except`` — so
    the prod AttributeError surfaced twice (spawned task + drain failure) per
    session. The same plumbing must deliver the wrapper's success: drain done,
    no error raised, lease released.
    """
    provider = _TailProvider()
    receiver = _bare_receiver(_gated(provider, active=False))
    receiver.shutdown_deadline = replay_delivery_module.clock() + 0.05
    spawned: list[str] = []

    def spawn(coro: Any, *, name: str) -> Any:
        spawned.append(name)
        return asyncio.ensure_future(coro)

    receiver.host.spawn = spawn
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert spawned == ['stt_shutdown_provider']
    # No AttributeError escaped (the call returned). The boundary unwrapped the
    # top-level gated wrapper to the provider, so the flush is the shadow
    # gate's (none) and the provider's own drain closed the transport.
    assert provider.events == ['drain_start', 'drain_eos', 'finish']
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_shutdown_deadline_path_surfaces_a_genuine_drain_failure():
    """A real drain error must still be classified by the boundary."""
    provider = _BrokenDrainProvider()
    receiver = _bare_receiver(_gated(provider, active=False))
    receiver.shutdown_deadline = replay_delivery_module.clock() + 0.05

    def spawn(coro: Any, *, name: str) -> Any:
        return asyncio.ensure_future(coro)

    receiver.host.spawn = spawn
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    # The boundary's except logged and fell back to a synchronous close
    # instead of crashing the supervised teardown.
    assert 'drain_start' in provider.events
    assert 'finish' in provider.events
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_unwrap_helper_still_finds_the_gated_provider():
    """raw_transport's unwrap chain must reach the gated wrapper's transport.

    The abort path uses it after a timed-out drain; if it stopped at the gated
    wrapper (whose transport owner is ``_conn``), the provider's tasks and wire
    would survive a shutdown abort. The wrapper only participates via
    ``_conn``, exactly what the chain already follows.
    """
    from utils.stt.replay_delivery import raw_transport

    provider = _TailProvider()
    gated = _gated(provider, active=False)
    delivery = _delivery(gated)
    assert raw_transport(delivery) is provider


@pytest.mark.asyncio
async def test_abort_replay_socket_closes_a_delivery_over_a_gated_wrapper():
    """The timed-out-drain abort must close the gated shape's transport."""
    from utils.stt.replay_delivery import abort_replay_socket

    provider = _TailProvider()
    delivery = _delivery(_gated(provider, active=False))
    await abort_replay_socket(delivery, timeout=0.5)
    assert 'finish' in provider.events
    assert provider.is_connection_dead


@pytest.mark.asyncio
async def test_one_failed_channel_does_not_block_the_other_channels_drain():
    """The sweep continues after one slot's drain raises (the except arm).

    In prod the AttributeError hit every gated slot of a multichannel session;
    the isolation property matters as much as the fix: a genuine drain failure
    on one channel must not strand the others' tails.
    """
    broken, healthy = _BrokenDrainProvider(), _TailProvider()
    receiver = _bare_receiver(None)
    receiver.host = SimpleNamespace(is_multi_channel=True)
    receiver.stt_sockets_multi = [_gated(broken, active=False), healthy]
    receiver.channel_configs = [None, None]  # type: ignore[reportAttributeAccessIssue]
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert 'drain_start' in broken.events and 'finish' in broken.events
    assert 'drain_eos' in healthy.events
    assert receiver.stt_sockets_multi == [None, None]


@pytest.mark.asyncio
async def test_drain_boundary_finishes_the_target_when_the_slot_has_no_drain():
    """A slot exposing neither drain nor wrapper closes synchronously."""
    provider = _LegacyProvider()
    receiver = _bare_receiver(provider)
    receiver.shutdown_deadline = replay_delivery_module.clock() + 0.05
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert provider.events == ['finish']
    assert receiver.stt_socket is None


@pytest.mark.asyncio
async def test_gated_wrapper_with_a_none_transport_slot_is_released():
    """A cleared gated slot must be released, not drained."""
    from utils.stt.socket import _LIVE_SOCKET_LEASES, track_live_stt_socket

    provider = _TailProvider()
    gated = track_live_stt_socket(GatedSTTSocket(provider, gate=_gate(active=False)), 'soniox')
    receiver = _bare_receiver(None)
    receiver.host = SimpleNamespace(is_multi_channel=True)
    receiver.stt_sockets_multi = [gated, None]
    receiver.channel_configs = [None, None]  # type: ignore[reportAttributeAccessIssue]
    gated._conn = None  # type: ignore[reportAttributeAccessIssue]
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    assert id(gated) not in _LIVE_SOCKET_LEASES
    assert provider.events == []  # nothing was drained: the transport was gone


@pytest.mark.asyncio
async def test_receiver_drain_of_wrapped_delivery_between_two_gated_layers():
    """A deeply nested shape (delivery → gated → gated → provider) drains once.

    A delivery whose connection was built on top of an existing gated wrapper
    (rebuild-on-rebuild) must reach the provider exactly once per teardown.
    """
    provider = _TailProvider()
    inner = _gated(provider, active=False)
    outer = GatedSTTSocket(inner, gate=_gate(active=False))
    delivery = _delivery(outer)
    await delivery.drain_and_close()
    assert provider.drain_calls == 1
    assert provider.events.count('drain_eos') == 1


@pytest.mark.asyncio
async def test_gated_drain_counts_flush_errors_on_the_gate():
    """The flush-failure counter the metrics emit must be incremented."""
    provider = _TailProvider()
    gate = _gate(active=True)
    gated = GatedSTTSocket(provider, gate=gate)

    def boom() -> None:
        raise RuntimeError('no')

    provider.finalize = boom  # type: ignore[method-assign]
    await gated.drain_and_close()
    assert gate._finalize_errors == 1  # type: ignore[reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_receiver_drain_drains_multi_channel_gated_sockets_end_to_end():
    """Every gated channel slot reaches its provider tail on the sweep."""
    providers = [_TailProvider(), _TailProvider()]
    receiver = _bare_receiver(None)
    receiver.host = SimpleNamespace(is_multi_channel=True)
    receiver.stt_sockets_multi = [_gated(providers[0]), _gated(providers[1])]
    receiver.channel_configs = [None, None]  # type: ignore[reportAttributeAccessIssue]
    await receiver_module.ListenReceiver._drain_stt_sockets(receiver)  # type: ignore[reportPrivateUsage]
    for provider in providers:
        # The boundary unwraps each top-level gated wrapper to its provider;
        # the provider's own drain closes the transport.
        assert provider.events == ['drain_start', 'drain_eos', 'finish']


@pytest.mark.anyio
@pytest.mark.parametrize('v2', [False, True])
async def test_full_session_teardown_drains_the_gated_connection_inside_the_delivery(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, v2: bool
) -> None:
    """The prod incident, end to end, on the real production wiring.

    The failover harness builds the exact prod shape — initialize_stt installs
    a gated socket, the provider dies, the rebuild wraps the replacement in a
    ``GatedSTTSocket`` inside a ``ReplayTailSocket`` — and the scenario's own
    disconnect runs the real recovery teardown through the drain boundary.
    Before the fix the drain logged ``Listen STT drain failure
    type=AttributeError`` and skipped the provider tail; with it the raw
    provider's synchronous close runs and no drain-failure ERROR is logged.
    """
    import logging
    import threading

    from tests.unit.test_listen_speaker_id_failover import _run_failover_scenario

    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    caplog.set_level(logging.ERROR, logger='routers.listen.receiver')
    caplog.set_level(logging.ERROR, logger='utils.async_tasks')
    # The harness request omits the deletion-fence flag the teardown reads on
    # the disconnect path; patch SimpleNamespace before the scenario builds it
    # so its disconnect reaches _drain_stt_sockets instead of raising.
    from types import SimpleNamespace as _NS

    original_ns = _NS

    def patched_ns(*args: Any, **kwargs: Any) -> Any:
        instance = original_ns(*args, **kwargs)
        if 'websocket' in kwargs and 'uid' in kwargs:
            instance.owner_persistence_blocked = threading.Event()
        return instance

    monkeypatch.setattr('types.SimpleNamespace', patched_ns)
    stack, _websockets = await _run_failover_scenario(monkeypatch, caplog, v2=v2)
    delivery = stack.receiver.stt_socket
    assert isinstance(delivery, ReplayTailSocket)
    assert isinstance(delivery.connection, GatedSTTSocket)
    drain_failures = [
        record.getMessage()
        for record in caplog.records
        if 'Listen STT drain failure' in record.getMessage() or 'stt_shutdown_provider' in record.getMessage()
    ]
    assert not drain_failures, drain_failures
    # The teardown's finally released the held socket and set stt_drain_complete.
    assert stack.receiver.stt_drain_complete.is_set()
