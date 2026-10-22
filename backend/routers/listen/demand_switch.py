"""Healthy demand handovers use the ordinary capture-ring replay/adoption pump.

Dial and admission happen while the old leg serves. After the capture fence,
all new audio enters the existing ordered tail; failures use normal recovery.
Policy handovers do not consume transport-failure episode allowances.
"""

import asyncio

from config.live_demand import resolve_live_demand
from config.live_stt_replay import replay_prefix_margin_seconds
from config.rollout_cohorts import warm_rollout_cohorts
from utils.observability.fallback import record_fallback
from utils.stt.live_failure import PendingLiveFailover, live_stt_socket_is_dead, live_stt_terminal_reason
from utils.stt.recovery_state import LiveRecoveryController, RecoveryState, current_recovery
from utils.stt.replay_delivery import abort_replay_socket, socket_replay_limits
from utils.stt import replay_delivery
from utils.stt.resilient_stream import trim_window_replay_to_anchor
from utils.stt.provider_stream_end import US_FAILOVER, note_stream_close_intent
from utils.stt.socket import release_live_stt_socket


def fallback(receiver, cause: str, *, target: str | None = None) -> None:
    record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode=target or receiver.host.stt_service.value,
        reason=cause,
        outcome='degraded',
    )


async def switch_live_demand(receiver, lane: str) -> bool:
    demand = receiver.live_demand
    host = receiver.host
    async with receiver._stt_failover_lock:
        if (
            receiver.recovery is None
            or receiver.recovery.state not in (RecoveryState.serving, RecoveryState.recovered)
            or receiver.recovery.client_has_left()
            or receiver.stt_socket is None
            or live_stt_socket_is_dead(receiver.stt_socket)
            or receiver._replay_ingesting
        ):
            return False
        current = 'parakeet' if host.stt_model == 'parakeet-window' else 'vendor'
        if current == lane or lane == 'parakeet' and not demand.window_permitted:
            return False
        session = receiver._managed_live_chain
        previous = receiver.stt_socket
        old_selection = host.stt_service, host.stt_language, host.stt_model
        old_generation = session.generation
        old_speaker = receiver.speaker_provider_epoch
        old_target = session._routing_target_entry
        old_recovery = receiver.recovery
        candidate_recovery = LiveRecoveryController(host)
        candidate_recovery.episode_count = old_recovery.episode_count
        # A handover has the same bounded wall/replay budget as a failure, but
        # switching tabs must not exhaust the session's failure episode count.
        candidate_recovery.begin(family=host.stt_service.value)
        candidate_recovery.episode_count = old_recovery.episode_count
        _, _, epoch = receiver._build_stt_callbacks()
        raw = None
        token = current_recovery.set(candidate_recovery)
        try:
            async with asyncio.timeout(10):
                raw = await session.connect(host.request.sample_rate, epoch=epoch, demand_lane=lane)
            selected = host.stt_service, host.stt_language, host.stt_model
            selected_generation = session.generation
            selected_speaker = receiver.speaker_provider_epoch
            selected_target = session._routing_target_entry
        except asyncio.CancelledError:
            if raw is not None:
                raw.retire_for_replay()
                await abort_replay_socket(raw)
            raise
        except Exception as error:
            fallback(receiver, getattr(error, 'reason', 'config_incomplete'), target=old_selection[0].value)
            demand.policy.fallback = lane == 'parakeet'
            return False
        finally:
            current_recovery.reset(token)
            host.stt_service, host.stt_language, host.stt_model = old_selection
            session.generation = old_generation
            receiver.speaker_provider_epoch = old_speaker
            session._routing_target_entry = old_target
        # Demand may change during the dial; do not install a cheap candidate
        # after a visible report or rollback.
        try:
            if lane == 'parakeet':
                await warm_rollout_cohorts(host.request.uid)
            if lane == 'parakeet' and (
                not demand.window_permitted
                or demand.policy.state != 'hidden'
                or not resolve_live_demand().admits(host.request.uid)
                or not await demand.can_admit_window()
            ):
                raw.retire_for_replay()
                await abort_replay_socket(raw)
                return False
            if not host.state.active or live_stt_socket_is_dead(previous):
                raw.retire_for_replay()
                await abort_replay_socket(raw)
                return False
            if live_stt_socket_is_dead(raw):
                reason = live_stt_terminal_reason(raw, 'connection_lost')
                if lane == 'parakeet':
                    demand.policy.fallback = True
                    demand.policy.window_permitted = False
                raw.retire_for_replay()
                await abort_replay_socket(raw)
                fallback(receiver, reason)
                return False
        except asyncio.CancelledError:
            raw.retire_for_replay()
            await abort_replay_socket(raw)
            raise
        demand.meter()
        ring = receiver._window_ring()
        trim_window_replay_to_anchor(ring, previous)
        limits = socket_replay_limits(raw)
        replay = ring.snapshot() if ring is not None else ()
        replay_seconds = sum(len(data) for _, data in replay) / (2 * host.request.sample_rate)
        prefix_budget = min(replay_delivery.REPLAY_PREFIX_SECONDS, candidate_recovery.remaining() or 0)
        # A handover replays the whole unanswered ring uncut, so the same
        # margin the failure path holds back from its snapshot bounds what a
        # healthy source may hand over; past it, keep serving rather than cut.
        prefix_budget = max(0.0, prefix_budget - replay_prefix_margin_seconds())
        if replay_seconds > prefix_budget * limits.rate:
            raw.retire_for_replay()
            await abort_replay_socket(raw)
            fallback(receiver, 'capacity_full')
            demand.policy.fallback = lane == 'parakeet'
            return False
        # No await between the snapshot and fence: queued old callbacks cannot
        # emit the replay prefix; new receive frames go into the ordered tail.
        previous.retire_for_replay()
        receiver._replay_ingesting = True
        receiver.recovery = candidate_recovery
        # The retired healthy source is owner-closing. Expose the live
        # candidate to the receive loop's ingestion guard before closing that
        # source, so capture/disconnect observation never waits on prefix replay.
        receiver.stt_socket = raw
        host.stt_service, host.stt_language, host.stt_model = selected
        session.generation = selected_generation
        receiver.speaker_provider_epoch = selected_speaker
        session._routing_target_entry = selected_target
        if epoch is not None and replay:
            epoch.replay_origin_sample = replay[0][0]
        if ring is not None:
            receiver._window_replay_cutoff_sample = ring.finalized_sample
        hop = PendingLiveFailover(from_mode=old_selection[0].value, to_mode=selected[0].value, reason='normal_close')
        note_stream_close_intent(previous, US_FAILOVER)
        try:
            await abort_replay_socket(previous)
            release_live_stt_socket(previous)
            if await receiver._pump_replacement(
                raw,
                epoch,
                hop,
                replay,
                ring,
                None,
                sample_rate=host.request.sample_rate,
                limits=limits,
                dead_provider=old_selection[0].value,
                soniox=receiver._resilient_audio if selected[0].value == 'soniox' else None,
            ):
                return True
            # Replay failed after the fence. The ring still owns unanswered
            # capture; deny cheap re-admission and walk the normal vendor chain.
            demand.policy.fallback = True
            demand.policy.window_permitted = False
            fallback(receiver, 'send_failed')
            await receiver._rebuild_stt_socket_locked()
            return False
        except asyncio.CancelledError:
            raw.retire_for_replay()
            await abort_replay_socket(raw)
            raise
        finally:
            receiver._replay_delivery = None
            receiver._replay_ingesting = False
