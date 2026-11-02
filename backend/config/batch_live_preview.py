"""Dark, batch-hash live vendor retirement; final transcript ownership is durable."""

from config.batch_pipeline import record_capture_eligible
from config.server_batch import MARKER
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language


def rollout_percent() -> float:
    from config.policy import resolve_batch_policy

    return resolve_batch_policy('').retire_percent


def selected(uid: str) -> bool:
    from config.policy import resolve_batch_policy

    return resolve_batch_policy(uid).live_stt_retired


def language_qualified(host, capture: dict) -> bool:
    supported = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}
    language = normalized_stt_language(host.request.language)
    profile = getattr(host, 'language_profile', None)
    return bool(
        language in supported
        and normalized_stt_language(host.language) == language
        and normalized_stt_language(capture.get('language')) == language
        and profile is not None
        and profile.primary == language
        and profile.expected
        and set(profile.expected).issubset(supported)
    )


def covered(host) -> bool:
    capture = getattr(host, 'batch_record_capture', None)
    return bool(
        capture
        and capture.get('record_lane_owner') == 'batch_live_v1'
        and capture.get('id') == host.state.current_conversation_id
        and record_capture_eligible(host.request.uid, capture)
        and host.private_cloud_sync_enabled
        and not host.is_multi_channel
        and not host.use_custom_stt
        and not host.request.onboarding_mode
        and host.request.source != 'phone_call'
        and host.pusher_enabled
        and language_qualified(host, capture)
    )


def capture_snapshot(capture: dict) -> dict:
    """Retain only scalar eligibility evidence, never decoded content/photos."""
    snapshot = {
        key: capture.get(key)
        for key in (
            'id',
            'record_lane_owner',
            'private_cloud_sync_enabled',
            'uses_custom_stt',
            'deleted',
            'discarded',
            'data_protection_level',
            'language',
        )
    }
    if (capture.get('external_data') or {}).get(MARKER) is True:
        snapshot[MARKER] = True
    return snapshot


def local_preview_batch_owned(uid: str) -> bool:
    """The uid's recordings belong to the batch record lane (allowlist or batch percent)."""
    from config.policy import resolve_batch_policy

    return bool(uid) and resolve_batch_policy(uid).batch_enabled
