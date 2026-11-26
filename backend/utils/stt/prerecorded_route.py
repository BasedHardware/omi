"""One recording's pre-recorded provider selection, resolved once and reusable for several pieces."""

from typing import Any, Optional, Tuple

from config.prerecorded_language import language_class, language_guard_enabled


def prerecorded_bytes_route(
    audio_bytes: bytes,
    language: Optional[str],
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    encoding: Optional[str] = None,
) -> Tuple[Any, Optional[str]]:
    """The selected service and the language to construct its provider with, for these bytes.

    ``prerecorded_from_bytes`` resolves this for every call; a caller that sends several pieces of one
    recording (the v3 fast finish's chunks) resolves it once and passes it back as ``route``.
    """
    from utils.stt.batch_language import resolve_language, select_decision
    from utils.stt.pre_recorded import get_prerecorded_service

    decision = resolve_language(language, audio_bytes, sample_rate=sample_rate, channels=channels, encoding=encoding)
    resolved = decision.language if decision.parakeet_safe else language
    if not language_guard_enabled() or language_class(language) != 'unknown':
        resolved = language
    selected = select_decision(language, decision, get_prerecorded_service)
    return selected, resolved
