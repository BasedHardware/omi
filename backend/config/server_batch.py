"""Platform-scoped, consented server batch capture. Desktop on, mobile dark."""

import math
import os
from collections.abc import Mapping

from config.audio_outbox import enabled as audio_outbox_enabled
from config.policy import cohort_bucket
from config.policy.batch import parse_percent
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language

MARKER = 'server_batch_only'


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
        and normalized_stt_language(capture.get('language'))
        in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
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


def language_compatible(capture: Mapping, language: str | None) -> bool:
    return not owned(capture) or normalized_stt_language(capture.get('language')) == normalized_stt_language(language)


def capture_compatible(host, capture: Mapping) -> bool:
    return not owned(capture) or bool(
        language_compatible(capture, host.request.language) and request_eligible(host, existing_capture=True)
    )


def suppress_live(host) -> bool:
    capture = getattr(host, 'batch_record_capture', None) or {}
    return bool(
        audio_outbox_enabled()
        and owned(capture)
        and language_compatible(capture, host.request.language)
        and getattr(host, 'private_cloud_sync_enabled', False)
        and not getattr(host, 'use_custom_stt', False)
        and not getattr(host, 'is_multi_channel', False)
        and not getattr(host.request, 'onboarding_mode', False)
        and getattr(host, 'pusher_enabled', False)
        and request_eligible(host, existing_capture=True)
    )


def request_eligible(host, *, existing_capture: bool = False) -> bool:
    """No inferred English admission for multi/auto/unknown request languages."""
    language = normalized_stt_language(getattr(host.request, 'language', None))
    profile = getattr(host, 'language_profile', None)
    expected = getattr(profile, 'expected', ())
    supported = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}
    return bool(
        (enabled() or existing_capture)
        and (not getattr(host, 'server_batch_initialized', False) or getattr(host, 'server_batch_only', False))
        and audio_outbox_enabled()
        and getattr(host, 'private_cloud_sync_enabled', False)
        and getattr(host, 'pusher_enabled', False)
        and os.getenv('HOSTED_PUSHER_API_URL')
        and not host.use_custom_stt
        and not getattr(host, 'server_batch_byok', False)
        and not host.is_multi_channel
        and host.request.source != 'phone_call'
        and not host.request.onboarding_mode
        and (
            existing_capture
            or selected(
                host.request.uid,
                getattr(getattr(host, 'client_device_context', None), 'platform', None),
                host.request.source,
            )
        )
        and language == normalized_stt_language(host.language)
        and language in supported
        and getattr(profile, 'primary', None) == language
        and expected
        and all(normalized_stt_language(code) in supported for code in expected)
    )
