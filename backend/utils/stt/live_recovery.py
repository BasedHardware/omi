"""Bounded re-eligibility for a previously used live rescue provider."""

from typing import Any, Callable

from config.live_stt_replay import session_local_exclusion_release_enabled

from config.stt_provider_policy import provider_for_service
from utils.stt import streaming as st
from utils.stt.live_rollout import window_selection_kwargs
from utils.stt.live_failure import MAX_STT_FAILOVERS, live_stt_terminal_reason, note_typed_provider_death
from utils.stt import live_health
from utils.stt.live_health import bounded_language
from utils.stt.live_metrics import SAME_TARGET_RETRIES, SESSION_LOCAL_EXCLUSION_RELEASES
from utils.stt.live_retry import retry_jitter_seconds, same_target_retry_allowed
from utils.stt.pod_drain import is_draining
from utils.stt.live_router import note_failed_route
from utils.stt.recovery_state import RecoveryState
from utils.stt.recovery_state import MAX_RECOVERY_TARGETS
from config.live_stt_registry import routing_on


def _router_active(managed: bool, receiver: Any) -> bool:
    """Router-on eligibility for the rebuild cap; malformed rollout percent
    must not abort legacy failover — it degrades to the router-off cap."""
    if not managed:
        return False
    try:
        return routing_on(receiver.host.request.uid)
    except ValueError:
        return False


# Deaths that are evidence about this session's replay bookkeeping, not about
# the provider: the leg was serving and transcribing when the ring overflowed.
SESSION_LOCAL_DEATHS = frozenset({'replay_ring_overflow'})


def note_session_local_exclusion(receiver: Any, dead_provider: str | None, reason: str) -> None:
    """Remember an exclusion that only a session-local death justified.

    The replacement must still differ from the leg that just overflowed, so the
    exclusion stands for this selection. Any later provider-evidence death of
    the same family keeps it excluded.
    """
    if not dead_provider:
        return
    held = getattr(receiver, '_stt_session_local_exclusions', None)
    if not isinstance(held, dict):
        held = receiver._stt_session_local_exclusions = {}
    if reason in SESSION_LOCAL_DEATHS and session_local_exclusion_release_enabled():
        held[dead_provider] = getattr(receiver.stt_socket, 'routing_target', None)
    else:
        held.pop(dead_provider, None)


def release_session_local_exclusions(receiver: Any, serving_family: str) -> None:
    """Re-admit families excluded only by replay overflow once a successor serves.

    Without this, a healthy Soniox leg that overflowed its replay ring stayed
    excluded for the whole session, so the successor's next ordinary death
    found no candidate and exhausted (prod 2026-10-20: about 40 per 10 min,
    logged as selection soniox->unavailable). The recovery controller's dial
    ledger still bounds re-dials within an unproven episode.
    """
    held = getattr(receiver, '_stt_session_local_exclusions', None)
    if not isinstance(held, dict) or not held or not session_local_exclusion_release_enabled():
        return
    for family, target in list(held.items()):
        if family == serving_family:
            continue
        del held[family]
        released = family in receiver._stt_failed_providers
        receiver._stt_failed_providers.discard(family)
        if isinstance(target, str) and target in receiver._stt_failed_targets:
            receiver._stt_failed_targets.discard(target)
            released = True
        if receiver._stt_failed_reasons.get(family) in SESSION_LOCAL_DEATHS:
            receiver._stt_failed_reasons.pop(family, None)
        if released:
            SESSION_LOCAL_EXCLUSION_RELEASES.labels(provider=family).inc()


def allow_healthy_soniox_rescue(receiver: Any, *, managed: bool) -> None:
    """One extra transport recovery on a currently healthy last rescue leg."""
    if (
        not managed
        or receiver.host.stt_service == st.STTService.soniox
        or 'soniox' not in receiver._stt_failed_providers
        or 'soniox' in receiver._stt_rescue_retries
        or receiver._stt_failed_reasons.get('soniox') not in {'connection_lost', 'send_failed'}
        or st._circuit_for_primary(st.STTService.soniox).state != 'closed'  # type: ignore[reportPrivateUsage] # shared circuit owner
        or ('deepgram' not in receiver._stt_failed_providers and st.deepgram_fallback_model(receiver.host.stt_language))
    ):
        return
    if receiver.recovery is not None and not receiver.recovery.grant_soniox_reentry('soniox'):
        return
    receiver._stt_rescue_retries.add('soniox')
    receiver._stt_failed_providers.remove('soniox')


def allow_same_target_retry(receiver: Any, dead_provider: str | None, reason: str, *, managed: bool) -> bool:
    """Re-admit the leg that just died once, when it died at the transport
    before its first text and its target is neither benched nor circuit-open.

    The retry is one per family per session (shared with the Soniox rescue),
    takes the controller's per-identity retry slot (never the rescue
    re-entry), and is dialed after a short jitter (see _attempt_dial).
    """
    if not managed or not dead_provider or is_draining():
        return False
    if getattr(receiver, '_pending_live_failover', None) is not None:
        # An unproven successor died: the recovery walk owns it; the retry
        # is for the serving primary only.
        return False
    retries = getattr(receiver, '_stt_same_target_retries', None)
    if not isinstance(retries, set):
        retries = receiver._stt_same_target_retries = set()
    socket = receiver.stt_socket
    outcome = getattr(socket, 'leg_outcome', None)
    probe = getattr(outcome, 'text_seen', None)
    try:
        text_seen = bool(probe()) if callable(probe) else None
    except Exception:
        text_seen = None
    identity = getattr(socket, 'routing_target', None)
    identity = identity if isinstance(identity, str) else dead_provider
    try:
        stage = live_health.health.cost_stage(identity, bounded_language(receiver.host.language))
    except Exception:
        stage = 100
    try:
        circuit_open = st._circuit_for_primary(st.STTService(dead_provider)).state == 'open'  # type: ignore[reportPrivateUsage] # shared circuit owner
    except Exception:
        circuit_open = True
    excluded = dead_provider in receiver._stt_failed_providers or identity in receiver._stt_failed_targets
    if not excluded or not same_target_retry_allowed(
        reason,
        text_seen=text_seen,
        stage=stage,
        circuit_open=circuit_open,
        # One repeat per family per session, shared with the Soniox rescue.
        already_retried=dead_provider in retries or dead_provider in getattr(receiver, '_stt_rescue_retries', ()),
        family=dead_provider,
    ):
        return False
    recovery = getattr(receiver, 'recovery', None)
    if recovery is not None and not recovery.grant_transient_retry(identity):
        SAME_TARGET_RETRIES.labels(provider=dead_provider, path='death', outcome='refused').inc()
        return False
    retries.add(dead_provider)
    rescues = getattr(receiver, '_stt_rescue_retries', None)
    if isinstance(rescues, set):
        rescues.add(dead_provider)
    receiver._stt_failed_providers.discard(dead_provider)
    receiver._stt_failed_targets.discard(identity)
    if recovery is not None:
        recovery.note_retry_jitter(identity, retry_jitter_seconds())
    SAME_TARGET_RETRIES.labels(provider=dead_provider, path='death', outcome='granted').inc()
    return True


def _select_live_replacement_legacy(
    receiver: Any,
    dead_provider: str | None,
    select: Callable[..., tuple[Any, Any, Any]],
    *,
    managed: bool,
) -> tuple[Any, Any, Any]:
    """Bound rebuild attempts separately from provider exclusions before selecting."""
    failures = note_failed_route(receiver, dead_provider)
    receiver._stt_rebuild_attempts += 1
    if dead_provider:
        receiver._stt_failed_reasons[dead_provider] = live_stt_terminal_reason(receiver.stt_socket, 'connection_lost')
        note_session_local_exclusion(receiver, dead_provider, receiver._stt_failed_reasons[dead_provider])
    router_active = _router_active(managed, receiver)
    cap = MAX_RECOVERY_TARGETS if router_active else (3 if managed else MAX_STT_FAILOVERS)
    if max(failures, receiver._stt_rebuild_attempts) > cap:
        receiver._settle_pending_live_failover_failure()
        return None, None, None
    note_typed_provider_death(receiver.stt_socket, dead_provider)
    allow_healthy_soniox_rescue(receiver, managed=managed)
    allow_same_target_retry(
        receiver, dead_provider, receiver._stt_failed_reasons.get(dead_provider, ''), managed=managed
    )
    service, language, model = select(
        receiver.host.language,
        multi_lang_enabled=receiver.host.multi_lang_enabled,
        language_profile=receiver.host.language_profile,
        exclude=frozenset(receiver._stt_failed_providers),
        **window_selection_kwargs(receiver.host, receiver.host.request.uid),
    )
    if service is None or provider_for_service(service) in receiver._stt_failed_providers:
        receiver._settle_pending_live_failover_failure()
        return None, None, None
    return service, language, model


def select_live_replacement(
    receiver: Any,
    dead_provider: str | None,
    select: Callable[..., tuple[Any, Any, Any]],
    *,
    managed: bool,
) -> tuple[Any, Any, Any]:
    """Walk the remaining permitted candidates inside the recovery episode."""
    if getattr(receiver, 'recovery', None) is None:
        return _select_live_replacement_legacy(receiver, dead_provider, select, managed=managed)
    recovery = receiver.recovery
    if recovery.state in (RecoveryState.exhausted, RecoveryState.client_leaving) or recovery.client_has_left():
        receiver._settle_pending_live_failover_failure()
        return None, None, None
    session = getattr(receiver, '_managed_live_chain', None)
    rescue = getattr(session, 'no_text_rescue', None)
    reason = live_stt_terminal_reason(receiver.stt_socket, 'connection_lost')
    if rescue is not None and rescue.enabled:
        if rescue.deadline is None and reason in {'first_text_deadline', 'empty_streak'}:
            interval = receiver._window_ring().capture_bounds
            pending = receiver.stt_socket.window_replay_pending_sample()
            if pending is not None:
                interval = (max(interval[0], pending), interval[1])
            rescue.start(reason, capture_interval=interval)
        if reason == 'no_text_rescue_complete' and rescue.active:
            rescue.complete()
            receiver._stt_failed_providers.discard('parakeet')
            receiver._stt_failed_targets.discard('parakeet-window')
            if not recovery.grant_cheap_reentry('parakeet-window'):
                receiver._settle_pending_live_failover_failure()
                return None, None, None
            # Policy retirement is not a paid-provider failure/exclusion.
            return st.STTService.parakeet, receiver.host.stt_language, 'parakeet-window'
    note_failed_route(receiver, dead_provider)
    receiver._stt_rebuild_attempts += 1
    if dead_provider:
        receiver._stt_failed_reasons[dead_provider] = live_stt_terminal_reason(receiver.stt_socket, 'connection_lost')
        note_session_local_exclusion(receiver, dead_provider, receiver._stt_failed_reasons[dead_provider])
    note_typed_provider_death(receiver.stt_socket, dead_provider)
    allow_healthy_soniox_rescue(receiver, managed=managed)
    allow_same_target_retry(
        receiver, dead_provider, receiver._stt_failed_reasons.get(dead_provider, ''), managed=managed
    )
    service, language, model = select(
        receiver.host.language,
        multi_lang_enabled=receiver.host.multi_lang_enabled,
        language_profile=receiver.host.language_profile,
        exclude=frozenset(receiver._stt_failed_providers),
        **window_selection_kwargs(receiver.host, receiver.host.request.uid),
    )
    if (
        service is None
        or provider_for_service(service) in receiver._stt_failed_providers
        or not recovery.admission_open()
    ):
        receiver._settle_pending_live_failover_failure()
        return None, None, None
    return service, language, model
