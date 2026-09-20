# LIFECYCLE: permanent
"""Dark-by-default controls for managed, single-channel live STT."""

import hashlib
import os
from typing import TypedDict

from config.stt_provider_policy import STTServingSurface, normalized_stt_language, parakeet_supports_language


def configured_chain_enabled() -> bool:
    return os.getenv('STT_CONNECT_ORDER_FROM_CONFIG', 'false').lower() == 'true'


def window_allocation(uid: str | None) -> bool:
    if not configured_chain_enabled() or not uid:
        return False
    percent = min(100.0, max(0.0, float(os.getenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0'))))
    bucket = int.from_bytes(hashlib.sha256(('parakeet-window:' + uid).encode()).digest()[:8], 'big')
    return bucket / 2**64 * 100 < percent


def window_language_supported(requested: str | None, resolved: str) -> bool:
    language = normalized_stt_language(requested if resolved == 'multi' else resolved)
    return language not in ('', 'multi', 'auto') and parakeet_supports_language(STTServingSurface.PRERECORDED, language)


def managed_chain_enabled(host: object) -> bool:
    from utils.byok import get_byok_keys

    return (
        configured_chain_enabled()
        and not getattr(host, 'is_multi_channel', False)
        and not getattr(host, 'use_custom_stt', False)
        and not get_byok_keys()
    )


class WindowSelection(TypedDict, total=False):
    window_uid: str


def window_selection_kwargs(host: object, uid: str) -> WindowSelection:
    """Selector kwargs for managed sessions; empty keeps the legacy call shape while dark."""
    return {'window_uid': uid} if managed_chain_enabled(host) else {}
