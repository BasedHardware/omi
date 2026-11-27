"""Soniox first for legacy sync's multilingual audio; Velma stays the fallback (SCA-4917).

Legacy sync sends Velma every file its language check did not hand to Parakeet: unknown,
code-switched, or a language Parakeet cannot transcribe (Mandarin, Japanese, Korean, Hindi ...).
Velma publishes English-only accuracy and mislabels short Chinese clips; Soniox benchmarks at or
near the top on those languages, and was the owner's pick on code-switched Mandarin/English
(SCA-4810 lab, 2026-11-26). So for those calls Soniox runs first and any Soniox failure falls back
to Velma on the same audio. English and the major European languages keep Velma first.

Scope: only calls made inside a legacy sync attempt (``current_parakeet_caller()`` is ``sync_*``).
Voice messages, push-to-talk, speaker verification and held recovery keep their current engines.
"""

import logging
import os
from typing import Any, Optional

from config.prerecorded_vendor import soniox_multilingual_enabled
from config.stt_provider_policy import (
    MODULATE_PROVIDER,
    SONIOX_PROVIDER,
    STTServingSurface,
    normalized_stt_language,
    provider_is_enabled,
    soniox_accepts_language_hint,
)
from utils.observability.fallback import record_fallback
from utils.stt.modulate_batch import wav_duration_seconds
from utils.stt.parakeet_request_metrics import current_parakeet_caller
from utils.stt.soniox_batch import SonioxBatchError, transcribe as soniox_transcribe
from utils.stt.vendor_guard import ENDPOINT_STT, record_vendor_burn

logger = logging.getLogger(__name__)

# Velma stays first where its batch model is strongest; every other language, and unknown or
# code-switched audio ('multi'), goes to Soniox first.
VELMA_FIRST_LANGUAGES = frozenset({'en', 'es', 'fr', 'de', 'it', 'pt', 'nl'})
# Soniox async must finish inside soniox_batch.DEADLINE_SECONDS; longer files stay on Velma.
MAX_SECONDS = 600.0

_REASON_BY_KIND = {
    'credit_refusal': 'provider_budget_exhausted',
    'rate_limited': 'provider_rate_limited',
    'timeout': 'timeout',
}


def applies(language: Optional[str]) -> bool:
    """Whether this pre-recorded call should try Soniox before Velma."""
    code = normalized_stt_language(language)
    if code in VELMA_FIRST_LANGUAGES:
        return False
    if code not in {'', 'multi'} and not soniox_accepts_language_hint(code):
        return False
    return (
        soniox_multilingual_enabled()
        and current_parakeet_caller().startswith('sync_')
        and provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.PRERECORDED)
        and bool(os.environ.get('SONIOX_API_KEY'))
    )


def transcribe(audio_bytes: bytes, *, language: Optional[str], diarize: bool) -> Optional[tuple[list[Any], str]]:
    """Soniox's (words, detected language), or None when the caller should run Velma as before."""
    duration = wav_duration_seconds(audio_bytes)
    if not 0 < duration <= MAX_SECONDS:
        return None
    try:
        words, detected = soniox_transcribe(
            audio_bytes,
            duration,
            language=language,
            failover=True,  # the pre-recorded surface's admission, bounded like the failover hop
            diarize=diarize,
            retry_rate_limits=False,
        )
    except Exception as error:
        kind = error.kind if isinstance(error, SonioxBatchError) else 'error'
        if kind != 'refused':
            # A refusal is local (no vendor call); anything else may have been billed.
            record_vendor_burn(ENDPOINT_STT, 'error', duration, provider=SONIOX_PROVIDER)
        record_fallback(
            component='stt_prerecorded',
            from_mode=SONIOX_PROVIDER,
            to_mode=MODULATE_PROVIDER,
            reason=_REASON_BY_KIND.get(kind, 'other'),
            outcome='degraded',
            log=logger,
        )
        logger.warning('event=prerecorded_soniox_multilingual outcome=fallback kind=%s', kind)
        return None
    record_vendor_burn(ENDPOINT_STT, 'ok', duration, provider=SONIOX_PROVIDER)
    logger.info('event=prerecorded_soniox_multilingual outcome=served words=%s', len(words))
    return words, detected
