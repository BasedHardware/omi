# LIFECYCLE: permanent
"""Dark-by-default controls for managed, single-channel live STT."""

from typing import TypedDict

from config.policy.listen import window_allocation as window_allocation

from config.stt_provider_policy import STTServingSurface, normalized_stt_language, parakeet_supports_language


def configured_chain_enabled() -> bool:
    return True


def window_language_supported(requested: str | None, resolved: str) -> bool:
    language = normalized_stt_language(requested if resolved == 'multi' else resolved)
    return language not in ('', 'multi', 'auto') and parakeet_supports_language(STTServingSurface.PRERECORDED, language)


def managed_chain_enabled(host: object) -> bool:
    from utils.byok import get_byok_keys

    return (
        not getattr(host, 'is_multi_channel', False)
        and not getattr(host, 'use_custom_stt', False)
        and not get_byok_keys()
    )


class WindowSelection(TypedDict, total=False):
    window_uid: str


def window_selection_kwargs(host: object, uid: str) -> WindowSelection:
    """Selector kwargs for managed sessions; empty keeps the legacy call shape while dark."""
    demand = getattr(getattr(host, 'receiver', None), 'live_demand', None)
    if demand is not None and demand.eligible and not demand.window_permitted:
        return {}
    return {'window_uid': uid} if managed_chain_enabled(host) else {}
