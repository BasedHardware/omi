"""Select a cheap preview only after conversation prepare proves batch ownership."""

from config.batch_live_preview import covered, selected
from utils.observability.demand_cohort import host_telemetry
from utils.stt.live_rollout import managed_chain_enabled
from utils.stt.streaming import get_stt_service_for_language


def capture_batch_preview(host, *, select_provider: bool = True) -> bool:
    if not getattr(host, '_batch_preview_pinned', False):
        eligible = covered(host) and managed_chain_enabled(host)
        admitted = eligible and selected(host.request.uid)
        host.batch_preview_admitted = admitted
        host._batch_preview_pinned = True
        telemetry = host_telemetry(host)
        if admitted:
            # Treatment belongs exclusively to the batch preview experiment.
            # This runs before decoded capture, sockets or lane-meter transitions.
            host._demand_cohort = 'ineligible'
            try:
                if telemetry is not None:
                    telemetry.cohort = 'ineligible'
                meter = getattr(getattr(host, 'receiver', None), 'lane_meter', None)
                if meter is not None:
                    meter.demand_cohort = 'ineligible'
            except Exception:
                pass  # Optional telemetry must not interrupt serving.
        try:
            if telemetry is not None:
                telemetry.batch_cohort = ('admitted' if admitted else 'eligible_control') if eligible else 'ineligible'
        except Exception:
            pass
    if host.batch_preview_admitted and select_provider:
        # No model/permission is added: selector and managed chain retain policy,
        # language, endpoint, circuit, capacity and paid failover checks.
        host.stt_service, host.stt_language, host.stt_model = get_stt_service_for_language(
            host.language,
            multi_lang_enabled=host.multi_lang_enabled,
            prefer_window=True,
            window_uid=host.request.uid,
            language_profile=host.language_profile,
        )
        host.stt_service_selected = host.stt_service
    return host.batch_preview_admitted
