"""Pinned pre-recovery receiver paths (STT_FAILOVER_RECOVERY_ENABLED off).

Bodies are the pinned main versions of the gated ``ListenReceiver`` methods,
held as unbound functions taking ``self``. Module-level helpers resolve through
the ``receiver`` module object so existing monkeypatches keep applying; ``self``
calls go back through the receiver's gated dispatch.
"""

from __future__ import annotations

import asyncio
from typing import Any

from routers.listen import receiver as owner
from utils.stt import legacy_replay
from utils.stt.live_failure import MAX_STT_FAILOVERS
from utils.stt.replay_capture_accounting import record_replay_sends


def _finishing(socket: Any) -> bool:
    """main's socket_is_finishing also honored the raw ``_finishing`` latch."""
    try:
        return owner.socket_is_finishing(socket, include_unmanaged_finishing=True)
    except TypeError:
        return owner.socket_is_finishing(socket)


async def failover_stt_socket(self: Any) -> bool:
    """Serialize monitor/send-path failover so only one replacement is adopted."""
    async with self._stt_failover_lock:
        if self._stt_recovery_exhausted:
            return False
        # Soniox drain_and_close() sets this before its final flush.  Treat a
        # finishing socket as receiver teardown even if its dead latch was
        # already set; opening a replacement here races the zero-audio close.
        if _finishing(self.stt_socket):
            return False
        if self.stt_socket is not None and not owner.live_stt_socket_is_dead(self.stt_socket):
            return True
        if await self._reconnect_stt_socket_locked():
            return True
        recovered = await self._rebuild_stt_socket_locked()
        self._stt_recovery_exhausted = not recovered
        return recovered


async def rebuild_stt_socket_locked(self: Any) -> bool:
    rebuild = getattr(self, '_stt_rebuild', None)
    if rebuild is None or self.host.is_multi_channel or self.host.use_custom_stt:
        return False
    if not self.host.state.active or self.host.state.stt_terminal_failure:
        return False

    dead_provider = owner.provider_for_service(self.host.stt_service)
    service, language, model = owner.select_live_replacement(
        self, dead_provider, owner.get_stt_service_for_language, managed=owner.managed_chain_enabled(self.host)
    )
    if service is None:
        return False
    # A failed hop is degraded while the chain continues; exhausted means no replacement path.
    self._settle_pending_live_failover_failure(continuing=True)
    parakeet_callback, modulate_callback, epoch = rebuild[0]()
    sample_rate = rebuild[1]
    previous = self.stt_socket
    previous_selection = (self.host.stt_service, self.host.stt_language, self.host.stt_model)
    window_ring = self._window_ring()
    owner.trim_window_replay_to_anchor(window_ring, previous)
    replay = window_ring.snapshot() if window_ring is not None else ()
    if window_ring is not None:
        self._window_replay_cutoff_sample = window_ring.finalized_sample
    retire = getattr(previous, 'retire_for_replay', None)
    if window_ring is not None and callable(retire):
        retire()
    if replay and epoch is not None:
        epoch.replay_origin_sample = replay[0][0]
    self.host.stt_service, self.host.stt_language, self.host.stt_model = service, language, model
    hop = owner.PendingLiveFailover.from_socket(previous, dead_provider or 'unknown', service.value)
    hop.capture_window_failure_details(previous)
    try:
        raw = await self._create_stt_socket(
            parakeet_callback,
            sample_rate,
            modulate_callback=modulate_callback,
            epoch=epoch,
        )
    except asyncio.CancelledError:
        hop.note_failure(None)
        raise
    except owner.ProviderChainUnavailable as error:
        if owner.managed_chain_enabled(self.host):
            self.host.stt_service, self.host.stt_language, self.host.stt_model = previous_selection
        hop.note_failure(None)
        await owner.terminate_live_stt_backoff(
            self.host.request.websocket,
            self.host.state,
            reason='provider_unavailable',
            retry_after=error.retry_after,
        )
        return False
    except Exception:
        if owner.managed_chain_enabled(self.host):
            self.host.stt_service, self.host.stt_language, self.host.stt_model = previous_selection
        owner.logger.exception('STT failover connect raised')
        hop.note_failure(None)
        return False
    if raw is None:
        hop.note_failure(None)
        if owner.managed_chain_enabled(self.host):
            self.host.stt_service, self.host.stt_language, self.host.stt_model = previous_selection
        return False
    if epoch is not None:
        epoch.provider_label = owner.audio_timeline_provider_label(getattr(self.host.stt_service, 'value', None))
    hop.to_mode = self.host.stt_service.value
    # A provider can reject shortly after upgrade; never adopt a dead leg.
    if not await owner.fallback_socket_is_serving(raw):
        return await legacy_replay.retry_failed_replacement(self, raw, epoch, hop, previous)
    self._pending_live_failover = hop
    # Replay capture positions after the last emitted segment.
    rejected_sample = legacy_replay.replay_chunks(
        record_replay_sends(raw, epoch),
        replay,
        source=window_ring,
        provider=dead_provider or 'parakeet',
        soniox=self._resilient_audio if self.host.stt_service == owner.STTService.soniox else None,
    )
    if rejected_sample is not None and window_ring is not None:
        # Accepted bytes have not necessarily produced text. The next
        # candidate needs the entire remaining span, including that prefix.
        return await legacy_replay.retry_failed_replacement(self, raw, epoch, hop, previous)
    self.stt_socket = self._wrap_legacy_stt_socket(raw, epoch)
    if window_ring is not None:
        window_ring.reserve_replacement_headroom()
    self._record_selected_epoch(epoch, self.stt_socket)
    owner.record_live_connection(self.host, self._serving_provider())
    self._pending_live_failover = None if hop.settled else hop
    owner.record_live_stt_failover_accepted(provider=self.host.stt_service.value, platform=self._telemetry_platform())
    owner.logger.info(f'STT failover mid-session: {dead_provider} -> {self.host.stt_service.value}')
    if previous is not None:
        try:
            previous.finish()
        except Exception:
            owner.logger.warning('Failed to close the STT socket that died before failover')
        finally:
            owner.release_live_stt_socket(previous)
    return True


async def monitor_stt_death(self: Any) -> None:
    """Terminate the client session promptly when the provider STT socket dies.

    The receive loop only observes provider death while flushing a client
    audio buffer (``_flush_stt_buffer`` → ``live_stt_socket_is_dead``), so a
    clean upstream close with no further client audio could hold the mobile
    socket in the "Listening" state until the 300s ``ws_receive_timeout``.
    This frame-independent poll drives the same idempotent terminal path
    (``stt_failed`` + WebSocket 1011) as soon as the death latch flips (#10028).
    """
    while self.host.state.active and not self.host.state.stt_terminal_failure:
        socket = self.stt_socket
        outcome = getattr(socket, 'leg_outcome', None)
        if outcome is not None and outcome.owner_closing:
            return
        if socket is not None and owner.live_stt_socket_is_dead(socket):
            if await self._failover_stt_socket():
                continue
            if outcome is not None and outcome.owner_closing:
                return
            if self.host.state.active and not self.host.state.stt_terminal_failure:
                owner.settle_terminal_socket(socket, self._serving_provider(), 'connection_lost')
            await owner.terminate_live_stt_session(
                self.host.request.websocket,
                self.host.state,
                failure=owner.live_stt_upstream_failure(self._serving_provider()),
                reason=owner.live_stt_terminal_reason(socket, 'connection_lost'),
                platform=self.host.client_device_context.platform,
            )
            return
        # Shutdown-aware sleep: wakes immediately on session shutdown, in
        # which case normal teardown owns termination and we simply exit.
        if await self.host.wait(owner.STT_DEATH_POLL_INTERVAL_SECONDS):
            return


async def flush_stt_buffer(self: Any, buffer: bytearray, *, force: bool = False) -> None:
    request = self.host.request
    # Bounded retry, not a single attempt: when the send path fails over to
    # the next provider the chunk is reported unsent with the buffer intact,
    # and it must reach the replacement socket now — the next client chunk
    # may be a VAD-gated silence away. `_failover_stt_socket` enforces
    # MAX_STT_FAILOVERS, so the bound here is a backstop, not the limit.
    for _ in range(MAX_STT_FAILOVERS + 2):
        socket_dead = self.stt_socket is not None and owner.live_stt_socket_is_dead(self.stt_socket)
        decision = owner.decide_stt_buffer_flush(
            buffer_len=len(buffer),
            flush_size=owner.stt_buffer_flush_size(request.sample_rate),
            force=force,
            socket_dead=socket_dead,
            socket_available=self.stt_socket is not None,
            fair_use_dg_budget_exhausted=self.host.state.fair_use_dg_budget_exhausted,
            fair_use_track_dg_usage=self.host.state.fair_use_track_dg_usage,
            sample_rate=request.sample_rate,
        )
        if not decision.should_flush:
            return
        if self.host.state.fair_use_dg_budget_exhausted:
            buffer.clear()
            # Fair use cleared queued STT bytes: the capture samples they
            # carried were never sent, so the next buffer starts at the
            # cursor and those samples simply have no provider mapping.
            self._stt_buffer_start_sample = None
            return
        outbound_audio = bytes(buffer)
        outbound_start_sample = self._stt_buffer_start_sample
        window_ring = self._window_ring()
        ring_action = owner.window_replay_action(window_ring, self.stt_socket, outbound_audio, outbound_start_sample)
        if ring_action == 'failover':
            if await self._failover_stt_socket():
                continue
            # Fall through to the idempotent terminal send path. The
            # recovery latch prevents it from rebuilding the same chain.
        sent = await owner.flush_live_stt_buffer(
            request.websocket,
            self.host.state,
            stt_socket=self.stt_socket,
            buffer=buffer,
            provider=self._serving_provider(),
            platform=self.host.client_device_context.platform,
            attempt_failover=self._failover_stt_socket,
            start_sample=self._stt_buffer_start_sample,
        )
        if sent:
            if self._resilient_audio is not None and self.host.stt_service == owner.STTService.soniox:
                self._resilient_audio.append(outbound_audio, outbound_start_sample)
            if (ring := self._window_ring()) is not None:
                ring.append(outbound_audio, outbound_start_sample)
            self._capture('capture_outbound_stt', outbound_audio)
            self.host.state.dg_usage_ms_pending += decision.dg_usage_ms
            self._stt_buffer_start_sample = None
            return
        if self.host.state.stt_terminal_failure:
            return
