"""Pinned pre-recovery replay/failover helpers (STT_FAILOVER_RECOVERY_ENABLED off).

These helpers preserve the legacy cross-provider replay path.
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils.stt.provider_resilience import close_rejected_socket
from utils.stt.live_failure import live_stt_terminal_reason, settle_terminal_socket
from utils.stt.provider_stream_end import US_FAILOVER, note_stream_close_intent
from utils.stt.resilient_stream import ResilientAudio
from utils.stt.socket import release_live_stt_socket


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
            settle_terminal_socket(raw, receiver.host.stt_service.value, 'connection_lost')
        return rebuilt
    except asyncio.CancelledError:
        settle_terminal_socket(raw, receiver.host.stt_service.value, 'connection_lost')
        raise
    finally:
        if previous is not None:
            note_stream_close_intent(previous, US_FAILOVER)
            try:
                previous.finish()
            finally:
                release_live_stt_socket(previous)


def replay_chunks(
    socket: Any,
    chunks: tuple[tuple[int, bytes], ...],
    *,
    source: ResilientAudio | None,
    provider: str,
) -> int | None:
    """Return the first rejected sample, or None when the snapshot was accepted."""
    if source is None:
        return None
    for start, data in chunks:
        replay_send = getattr(socket, 'replay_send', None)
        accepted = replay_send(data, start) if callable(replay_send) else socket.send(data, start_sample=start)
        if not accepted:
            return start
        source.record_replay(provider, len(data) // 2)
    return None
