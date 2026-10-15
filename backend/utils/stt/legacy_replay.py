"""Pinned pre-recovery replay/failover helpers (STT_FAILOVER_RECOVERY_ENABLED off).

Bodies are the pinned main versions; module-level helpers resolve through the
``resilient_stream`` module object so existing monkeypatches keep applying.
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils.stt import resilient_stream as owner

from utils.stt.provider_resilience import close_rejected_socket
from utils.stt.live_failure import live_stt_terminal_reason
from utils.stt.resilient_stream import ResilientAudio


def _finishing(socket: Any) -> bool:
    """main's socket_is_finishing also honored the raw ``_finishing`` latch."""
    return owner.socket_is_finishing(socket, include_unmanaged_finishing=True)


async def reconnect_live_stt_socket(receiver: Any) -> bool:
    """Use the complete window obligation, with the existing reconnect budget."""
    ring = receiver._resilient_audio
    socket = receiver.stt_socket
    if (
        ring is None
        or socket is None
        or owner.provider_for_service(receiver.host.stt_service) != 'soniox'
        or receiver.host.is_multi_channel
        or receiver.host.use_custom_stt
        or not receiver.host.state.active
        or receiver.host.state.stt_terminal_failure
        or receiver._stt_rebuild is None
        or getattr(receiver, '_resilient_closing', False)
        or _finishing(socket)
    ):
        return False
    reason = getattr(socket, 'typed_death_reason', None)
    if reason not in {'soniox_rotation', 'provider_5xx', 'connection_lost'}:
        return False
    if reason == 'connection_lost' and not str(getattr(socket, 'death_reason', '')).startswith('ws '):
        return False
    replay_ring = receiver._window_ring() or ring
    if not ring.admit('soniox', reason, samples=replay_ring.buffered_bytes // 2):
        return False
    receiver._settle_pending_live_failover_failure(continuing=True)
    hop = owner.PendingLiveFailover.from_socket(socket, 'soniox', 'soniox')
    replacement = None
    owner.retire_window_replay_socket(receiver, socket)
    try:
        socket.finish()
    except Exception:
        pass
    finally:
        # Direct sockets carry a lease here; managed sockets release their
        # own gauge in finish(), and release_live_stt_socket is idempotent.
        owner.release_live_stt_socket(socket)
    await asyncio.sleep(0)  # deliver the dead socket's last finalized callback
    if not receiver.host.state.active or receiver.host.state.stt_terminal_failure:
        hop.note_failure(None)
        owner.RECONNECT.labels(provider='soniox', reason=reason, outcome='teardown').inc()
        return False
    replay = replay_ring.snapshot()
    parakeet_callback, modulate_callback, epoch = receiver._stt_rebuild[0]()
    if epoch is not None:
        epoch.replay_origin_sample = replay[0][0] if replay else replay_ring.finalized_sample
    try:
        raw = await receiver._create_stt_socket(
            parakeet_callback,
            receiver._stt_rebuild[1],
            modulate_callback=modulate_callback,
            epoch=epoch,
            same_provider=True,
            replay_start_sample=replay[0][0] if replay else replay_ring.finalized_sample,
        )
        if raw is None or not await owner.fallback_socket_is_serving(raw):
            if raw is not None:
                owner.retire_window_replay_socket(receiver, raw)
                if receiver.host.state.active and not receiver.host.state.stt_terminal_failure:
                    owner.settle_terminal_socket(raw, 'soniox', 'connection_lost')
                close_rejected_socket(raw)
            raise RuntimeError('Soniox reconnect refused')
        replacement = receiver._wrap_legacy_stt_socket(raw, epoch)
        cutoff = replay_ring.finalized_sample
        replay_send = getattr(replacement, 'replay_send', None)
        for start, data in replay:
            accepted = replay_send(data, start) if callable(replay_send) else replacement.send(data, start_sample=start)
            if not accepted:
                raise RuntimeError('Soniox replay send failed')
            ring.record_replay('soniox', len(data) // 2)
        if not receiver.host.state.active or receiver.host.state.stt_terminal_failure:
            replacement.finish()
            hop.note_failure(None)
            owner.RECONNECT.labels(provider='soniox', reason=reason, outcome='teardown').inc()
            return False
    except asyncio.CancelledError:
        hop.note_failure(None)
        raise
    except Exception:
        if replacement is not None:
            owner.retire_window_replay_socket(receiver, replacement)
            if receiver.host.state.active and not receiver.host.state.stt_terminal_failure:
                owner.settle_terminal_socket(replacement, 'soniox', 'send_failed')
            replacement.finish()
        hop.note_failure(None, continuing=True)
        owner.RECONNECT.labels(provider='soniox', reason=reason, outcome='failed').inc()
        return False
    receiver._window_replay_cutoff_sample = cutoff
    receiver._replay_cutoff_sample = cutoff
    receiver.stt_socket = replacement
    receiver._record_selected_epoch(epoch, replacement)
    receiver._pending_live_failover = hop
    owner.RECONNECT.labels(provider='soniox', reason=reason, outcome='connected').inc()
    return True


async def retry_failed_replacement(receiver: Any, raw: Any, epoch: Any, hop: Any, previous: Any) -> bool:
    """Walk past a late rejection without discarding its un-emitted replay."""
    retire = getattr(raw, 'retire_for_replay', None)
    if receiver._window_ring() is not None and callable(retire):
        retire()
    receiver.stt_socket = receiver._wrap_legacy_stt_socket(raw, epoch)
    receiver._pending_live_failover = hop
    # Keep the actual selected provider on host: the connector may already
    # have walked past the initially requested candidate.
    outcome = getattr(raw, 'leg_outcome', None)
    if outcome is not None:
        outcome.claim(live_stt_terminal_reason(raw, 'connection_lost'))
    close_rejected_socket(raw)
    try:
        rebuilt = await receiver._rebuild_stt_socket_locked()
        if not rebuilt:
            owner.settle_terminal_socket(raw, receiver.host.stt_service.value, 'connection_lost')
        return rebuilt
    except asyncio.CancelledError:
        owner.settle_terminal_socket(raw, receiver.host.stt_service.value, 'connection_lost')
        raise
    finally:
        if previous is not None:
            try:
                previous.finish()
            finally:
                owner.release_live_stt_socket(previous)


def replay_chunks(
    socket: Any,
    chunks: tuple[tuple[int, bytes], ...],
    *,
    source: ResilientAudio | None,
    provider: str,
    soniox: ResilientAudio | None,
) -> int | None:
    """Return the first rejected sample, or None when the snapshot was accepted."""
    if source is None:
        return None
    accepted_chunks: list[tuple[int, bytes]] = []
    for start, data in chunks:
        replay_send = getattr(socket, 'replay_send', None)
        accepted = replay_send(data, start) if callable(replay_send) else socket.send(data, start_sample=start)
        if not accepted:
            return start
        accepted_chunks.append((start, data))
        source.record_replay(provider, len(data) // 2)
    if soniox is not None:
        for start, data in accepted_chunks:
            soniox.append(data, start)
    return None
