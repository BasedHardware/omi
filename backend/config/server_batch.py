"""Platform-scoped, consented server batch capture with separate auto-language admission."""

import math
import os
from collections.abc import Mapping

from config.audio_outbox import enabled as audio_outbox_enabled
from config.policy import cohort_bucket
from config.policy.batch import parse_percent
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language

MARKER = 'server_batch_only'
AUTO_LANGUAGES = frozenset({'', 'auto', 'multi'})
SUPPORTED = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}
AUTO_COHORT_SALT = 'server_batch_auto_language_v1'


def undeclared(host) -> bool:
    params = getattr(getattr(host.request, 'websocket', None), 'query_params', None)
    return isinstance(params, Mapping) and 'language' not in params


def request_language(host) -> str:
    # FastAPI's English default is a live compatibility choice, not a user
    # declaration and never permission to label retained audio English.
    return '' if undeclared(host) else normalized_stt_language(getattr(host.request, 'language', None))


def capture_language(host):
    return 'multi' if request_language(host) in AUTO_LANGUAGES else host.language


def continuation_language(host, capture: Mapping | None = None):
    if request_language(host) in AUTO_LANGUAGES:
        if capture is None:
            return None  # Find the prior pointer before validating its owner/language.
        if owned(capture) and language_compatible(capture, request_language(host)):
            return capture.get('language')
    return getattr(host, 'language', None)


def auto_selected(owner_id: str, platform: str | None) -> bool:
    percent = parse_percent(os.getenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '0'))
    return bool(
        platform in {'ios', 'android'}
        and owner_id
        and percent > 0
        and cohort_bucket(owner_id, AUTO_COHORT_SALT) < percent
    )


def enabled() -> bool:
    return os.getenv('SERVER_BATCH_ONLY_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def selected(owner_id: str, platform: str | None, source: str | None) -> bool:
    if source == 'phone_call':
        return False
    platform = platform or ('macos' if source == 'desktop' else None)
    if platform in {'ios', 'android'}:
        percent = parse_percent(os.getenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '0'))
        return bool(owner_id and percent > 0 and cohort_bucket(owner_id, '') < percent)
    platforms = {
        value.strip().lower() for value in os.getenv('SERVER_BATCH_ONLY_PLATFORMS', 'macos,windows').split(',')
    }
    return platform in {'macos', 'windows', 'linux'} and platform in platforms and source == 'desktop'


def eligible(capture: Mapping, owner_id: str, *, batch_admitted: bool = False) -> bool:
    """Desktop bypasses mobile cohorts; mobile admission stays nested in batch."""
    external = capture.get('external_data') or {}
    return bool(
        enabled()
        and audio_outbox_enabled()
        and os.getenv('HOSTED_PUSHER_API_URL')
        and selected(owner_id, capture.get('client_platform'), capture.get('source'))
        and (capture.get('client_platform') not in {'ios', 'android'} or batch_admitted)
        and capture.get('private_cloud_sync_enabled')
        and not capture.get('uses_custom_stt')
        and not any(capture.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        and not external.get('onboarding_session_id')
        and capture.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and (
            normalized_stt_language(capture.get('language')) in SUPPORTED
            or (
                normalized_stt_language(capture.get('language')) in AUTO_LANGUAGES
                and auto_selected(owner_id, capture.get('client_platform'))
            )
        )
    )


def owned(capture: Mapping) -> bool:
    """A durable admission survives a policy rollback until batch finishes."""
    return bool(
        capture.get('record_lane_owner') == 'batch_live_v1'
        and (capture.get(MARKER) is True or (capture.get('external_data') or {}).get(MARKER) is True)
    )


def visible_restore_selected(host) -> bool:
    """New paid preview cohort is nested in durable mobile batch custody."""
    percent = parse_percent(os.getenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', '0'))
    return bool(
        getattr(host, 'server_batch_only', False) is True
        and owned(getattr(host, 'batch_record_capture', None) or {})
        and getattr(getattr(host, 'client_device_context', None), 'platform', None) in {'ios', 'android'}
        and not getattr(host.request, 'local_preview', False)
        and not getattr(host, 'use_custom_stt', False)
        and not getattr(host, 'is_multi_channel', False)
        and host.request.uid
        and percent > 0
        and cohort_bucket(host.request.uid, '') < percent
    )


def has_audio(capture: Mapping) -> bool:
    start, end = capture.get('server_batch_audio_start'), capture.get('server_batch_audio_end')
    return bool(
        capture.get('has_content')
        and isinstance(start, (int, float))
        and isinstance(end, (int, float))
        and math.isfinite(start)
        and math.isfinite(end)
        and start < end
    )


def language_compatible(capture: Mapping, language: str | None) -> bool:
    stored, requested = normalized_stt_language(capture.get('language')), normalized_stt_language(language)
    return not owned(capture) or stored == requested or (stored in AUTO_LANGUAGES and requested in AUTO_LANGUAGES)


def capture_compatible(host, capture: Mapping) -> bool:
    return not owned(capture) or bool(
        language_compatible(capture, request_language(host)) and request_eligible(host, existing_capture=True)
    )


def suppress_live(host) -> bool:
    from utils.metrics import OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL
    from utils.observability.reasons import ReasonFamily, ServerBatchSuppressionReason, reason_label
    from utils.observability.transcription import bounded_client_platform

    capture = getattr(host, 'batch_record_capture', None) or {}
    reason = request_reason(host, existing_capture=owned(capture))
    if not owned(capture) and not enabled():
        reason = 'not_enabled'
    if reason is None and not language_compatible(capture, request_language(host)):
        reason = 'profile_mismatch'
    if reason is None and not owned(capture):
        reason = 'capture_not_owned' if enabled() else 'not_enabled'
    suppressed = reason is None
    try:
        OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL.labels(
            decision='suppressed' if suppressed else 'live',
            reason=reason_label(ReasonFamily.LIVE_STT, reason or 'suppressed', ServerBatchSuppressionReason),
            client_platform=bounded_client_platform(
                getattr(getattr(host, 'client_device_context', None), 'platform', None)
            ),
        ).inc()
    except Exception:
        pass  # Telemetry cannot interrupt provider admission.
    return suppressed


def request_eligible(host, *, existing_capture: bool = False) -> bool:
    return request_reason(host, existing_capture=existing_capture) is None


def request_reason(host, *, existing_capture: bool = False) -> str | None:
    """A learned profile selects the cohort, never the recognizer language proof."""
    language = request_language(host)
    profile = getattr(host, 'language_profile', None)
    primary = getattr(profile, 'primary', None)
    expected = getattr(profile, 'expected', ())
    platform = getattr(getattr(host, 'client_device_context', None), 'platform', None)
    if not enabled() and not existing_capture:
        return 'not_enabled'
    if getattr(host, 'server_batch_initialized', False) and not getattr(host, 'server_batch_only', False):
        return 'not_enabled'
    if not getattr(host, 'private_cloud_sync_enabled', False):
        return 'private_sync_off'
    if host.use_custom_stt or getattr(host, 'server_batch_byok', False):
        return 'custom_stt'
    if host.is_multi_channel:
        return 'multi_channel'
    if host.request.source == 'phone_call':
        return 'phone_call'
    if host.request.onboarding_mode:
        return 'onboarding'
    if (
        not audio_outbox_enabled()
        or not getattr(host, 'pusher_enabled', False)
        or not os.getenv('HOSTED_PUSHER_API_URL')
    ):
        return 'pusher_unavailable'
    # Lookup callers do not have the stored capture yet. Allow them to find a
    # prior durable owner across rollback; suppress_live separately requires it.
    if not existing_capture and not selected(host.request.uid, platform, host.request.source):
        return 'platform_unselected'
    resolved = normalized_stt_language(host.language)
    if (
        not undeclared(host)
        and language != resolved
        and not (language in AUTO_LANGUAGES and resolved in AUTO_LANGUAGES)
    ):
        return 'profile_mismatch'
    auto = language in AUTO_LANGUAGES
    if auto:
        if not (existing_capture or auto_selected(host.request.uid, platform)):
            return 'language_auto'
        if getattr(profile, 'source', None) != 'learned':
            return 'profile_mismatch'
    elif language not in SUPPORTED:
        return 'language_unsupported'
    if (
        (not auto and primary not in SUPPORTED)
        or (not auto and primary != language)
        or not expected
        or not all(normalized_stt_language(code) in SUPPORTED for code in expected)
    ):
        return 'profile_mismatch'
    return None
