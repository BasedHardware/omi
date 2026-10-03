"""Bounded re-eligibility for a previously used live rescue provider."""

from typing import Any, Callable

from config.stt_provider_policy import provider_for_service
from utils.stt import streaming as st
from utils.stt.live_rollout import window_selection_kwargs
from utils.stt.live_failure import live_stt_terminal_reason, note_typed_provider_death
from utils.stt.live_router import note_failed_route
from utils.stt.recovery_state import RecoveryState


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
    if not receiver.recovery.grant_soniox_reentry('soniox'):
        return
    receiver._stt_rescue_retries.add('soniox')
    receiver._stt_failed_providers.remove('soniox')


def select_live_replacement(
    receiver: Any,
    dead_provider: str | None,
    select: Callable[..., tuple[Any, Any, Any]],
    *,
    managed: bool,
) -> tuple[Any, Any, Any]:
    """Walk the remaining permitted candidates inside the recovery episode."""
    recovery = receiver.recovery
    if recovery.state in (RecoveryState.exhausted, RecoveryState.client_leaving) or recovery.client_has_left():
        receiver._settle_pending_live_failover_failure()
        return None, None, None
    note_failed_route(receiver, dead_provider)
    receiver._stt_rebuild_attempts += 1
    if dead_provider:
        receiver._stt_failed_reasons[dead_provider] = live_stt_terminal_reason(receiver.stt_socket, 'connection_lost')
    note_typed_provider_death(receiver.stt_socket, dead_provider)
    allow_healthy_soniox_rescue(receiver, managed=managed)
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
