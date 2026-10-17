"""Select a cheap preview only after conversation prepare proves batch ownership."""

from config.batch_live_preview import covered, selected
from utils.observability.demand_cohort import host_telemetry
from utils.stt.live_rollout import managed_chain_enabled
from utils.stt.streaming import get_stt_service_for_language


def capture_batch_preview(host) -> bool:
    eligible = covered(host) and managed_chain_enabled(host)
    admitted = eligible and selected(host.request.uid)
    host.batch_preview_admitted = admitted
    telemetry = host_telemetry(host)
    try:
        if telemetry is not None:
            telemetry.batch_cohort = ('admitted' if admitted else 'eligible_control') if eligible else 'ineligible'
    except Exception:
        pass  # Optional telemetry must not interrupt serving.
    if admitted:
        # No model/permission is added: selector and managed chain retain policy,
        # language, endpoint, circuit, capacity and paid failover checks.
        host.stt_service, host.stt_language, host.stt_model = get_stt_service_for_language(
            host.language,
            multi_lang_enabled=host.multi_lang_enabled,
            preferred_service='parakeet',
            language_profile=host.language_profile,
        )
        host.stt_service_selected = host.stt_service
    return admitted
