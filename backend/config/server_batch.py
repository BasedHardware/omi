"""Platform-scoped, consented server batch capture with separate auto-language admission."""

import math
import os
from collections.abc import Mapping

from config.audio_outbox import enabled as audio_outbox_enabled
from config.policy import cohort_bucket
from config.policy.batch import parse_percent
from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    normalized_stt_language,
    canonical_language,
)

MARKER = 'server_batch_only'
PREVIEW_CUSTODY_MARKER = 'listen_preview_batch_custody'
AUTO_LANGUAGES = frozenset({'', 'auto', 'multi'})
SUPPORTED = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}
AUTO_COHORT_SALT = 'server_batch_auto_language_v1'
WEB_COHORT_SALT = 'server_batch_web_v1'
# Fixed policy vocabulary, independent of operator input; Japanese is measured
# but can never enter the experiment.
UNSUPPORTED = MODULATE_SUPPORTED_LANGUAGES - SUPPORTED - AUTO_LANGUAGES


def unsupported_languages() -> frozenset[str]:
    codes = {
        normalized_stt_language(code.strip()) for code in os.getenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', '').split(',')
    }
    return frozenset(codes & UNSUPPORTED - {'ja'})


def bounded_language(language: str | None) -> str:
    code = normalized_stt_language(language)
    return code if code in UNSUPPORTED else 'other'


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
        platform in {'ios', 'android', 'web'}
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
    if platform == 'web':
        percent = parse_percent(os.getenv('SERVER_BATCH_ONLY_WEB_PERCENT', '0'))
        return bool(owner_id and percent > 0 and cohort_bucket(owner_id, WEB_COHORT_SALT) < percent)
    platforms = {
        value.strip().lower() for value in os.getenv('SERVER_BATCH_ONLY_PLATFORMS', 'macos,windows').split(',')
    }
    return platform in {'macos', 'windows', 'linux'} and platform in platforms and source == 'desktop'


def eligible(capture: Mapping, owner_id: str, *, batch_admitted: bool = False) -> bool:
    """Desktop and web use their own admission; mobile stays nested in batch."""
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
            normalized_stt_language(capture.get('language')) in SUPPORTED | unsupported_languages()
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


def proven_empty(capture: Mapping) -> bool:
    """A closed, received-empty server archive owes no recording obligation."""
    return (
        owned(capture)
        and capture.get('server_batch_audio_closed') is True
        and capture.get('server_batch_audio_received') is False
        and not capture.get('record_upload_failed')
        and not capture.get('record_upload_sessions')
        and not has_audio(capture)
    )


def language_compatible(capture: Mapping, language: str | None) -> bool:
    stored, requested = normalized_stt_language(capture.get('language')), normalized_stt_language(language)
    return not owned(capture) or stored == requested or (stored in AUTO_LANGUAGES and requested in AUTO_LANGUAGES)


def capture_compatible(host, capture: Mapping) -> bool:
    return not owned(capture) or bool(
        language_compatible(capture, request_language(host))
        and request_reason(host, existing_capture=True, capture=capture) is None
    )


def suppress_live(host) -> bool:
    from utils.metrics import OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL
    from utils.observability.reasons import ReasonFamily, ServerBatchSuppressionReason, reason_label
    from utils.observability.transcription import bounded_client_platform

    capture = getattr(host, 'batch_record_capture', None) or {}
    reason = request_reason(host, existing_capture=owned(capture), capture=capture)
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
            language=bounded_language(request_language(host)),
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


def request_reason(host, *, existing_capture: bool = False, capture: Mapping | None = None) -> str | None:
    """A learned profile selects the cohort, never the recognizer language proof."""
    # Cap-paused bootstrap has no request yet and cannot own batch custody.
    if getattr(host, 'request', None) is None:
        return 'not_enabled'
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
    # A preview promotion is its own durable admission, independent of the
    # learned-profile/cohort gates for newly selected server-batch sessions.
    if owned(capture or {}) and (capture or {}).get(PREVIEW_CUSTODY_MARKER):
        return None
    if owned(capture or {}) and ((capture or {}).get('external_data') or {}).get(PREVIEW_CUSTODY_MARKER):
        return None
    # This grants only lookup permission. Once loaded, capture_compatible checks
    # the durable marker and language rather than admitting an unowned row.
    if existing_capture and capture is None and getattr(host.request, 'local_preview', False):
        return None
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
    elif language not in SUPPORTED and language not in unsupported_languages():
        return 'language_unsupported'
    # Only the newly admitted declared-language path may have unsupported
    # expected codes. Supported declarations and auto retain their old gates.
    profile_languages = SUPPORTED
    profile_primary = primary
    declared_primary = language
    if language in UNSUPPORTED:
        allowed = unsupported_languages()
        profile_languages = SUPPORTED | allowed | {canonical_language(code) for code in allowed}
        profile_primary = canonical_language(primary)
        declared_primary = canonical_language(language)
    if (
        (not auto and profile_primary not in profile_languages)
        or (not auto and profile_primary != declared_primary)
        or not expected
        or not all(normalized_stt_language(code) in profile_languages for code in expected)
    ):
        return 'profile_mismatch'
    return None
