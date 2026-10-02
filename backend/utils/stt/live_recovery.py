"""Bounded re-eligibility for a previously used live rescue provider."""

from typing import Any

from utils.stt import streaming as st
from utils.stt.live_rollout import managed_chain_enabled


def allow_healthy_soniox_rescue(receiver: Any) -> None:
    """One extra transport recovery on a currently healthy last rescue leg."""
    if (
        not managed_chain_enabled(receiver.host)
        or receiver.host.stt_service == st.STTService.soniox
        or 'soniox' not in receiver._stt_failed_providers
        or 'soniox' in receiver._stt_rescue_retries
        or receiver._stt_failed_reasons.get('soniox') not in {'connection_lost', 'send_failed'}
        or st._circuit_for_primary(st.STTService.soniox).state != 'closed'
        or ('deepgram' not in receiver._stt_failed_providers and st.deepgram_fallback_model(receiver.host.stt_language))
    ):
        return
    receiver._stt_rescue_retries.add('soniox')
    receiver._stt_failed_providers.remove('soniox')
