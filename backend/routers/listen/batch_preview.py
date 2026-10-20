"""Select a cheap preview only after conversation prepare proves batch ownership."""

from config.batch_live_preview import covered, rollout_percent, selected
from utils.observability.demand_cohort import host_telemetry, telemetry_call
from utils.stt.live_rollout import managed_chain_enabled
from utils.stt.streaming import get_stt_service_for_language


def capture_batch_preview(host, *, select_provider: bool = True) -> bool:
    if not getattr(host, '_batch_preview_pinned', False):
        eligible = covered(host) and managed_chain_enabled(host)
        admitted = eligible and selected(host.request.uid)
        host.batch_preview_admitted = admitted
        host.batch_preview_isolated = eligible and rollout_percent() > 0
        host._batch_preview_pinned = True
        telemetry = host_telemetry(host)
        if host.batch_preview_isolated:
            # Both treatment and control belong exclusively to this experiment.
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
    if host.batch_preview_isolated and select_provider and not getattr(host, '_batch_preview_selection_applied', False):
        # No model/permission is added: selector and managed chain retain policy,
        # language, endpoint, circuit, capacity and paid failover checks.
        host.stt_service, host.stt_language, host.stt_model = get_stt_service_for_language(
            host.language,
            multi_lang_enabled=host.multi_lang_enabled,
            prefer_window=host.batch_preview_admitted,
            preferred_service=getattr(host.request, 'stt_service', None),
            window_uid=host.request.uid,
            language_profile=host.language_profile,
        )
        host.stt_service_selected = host.stt_service
        host._batch_preview_selection_applied = True
        capture = getattr(host, 'parity_capture', None)
        if capture is not None and getattr(capture, 'enabled', False):
            provider = getattr(host.stt_service, 'value', host.stt_service)
            telemetry_call(
                host,
                'parity_capture',
                'reselect',
                provider=provider,
                model=host.stt_model or '',
                request={
                    'codec': host.request.codec,
                    'sample_rate': host.request.sample_rate,
                    'channels': host.request.channels,
                    'language': host.stt_language,
                    'provider': provider,
                    'model': host.stt_model,
                },
            )
    return host.batch_preview_admitted
