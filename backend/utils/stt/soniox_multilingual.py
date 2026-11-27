"""Soniox first for legacy sync's multilingual audio; Velma stays the fallback (SCA-4917).

Legacy sync sends Velma every file its language check did not hand to Parakeet: unknown,
code-switched, or a language Parakeet cannot transcribe (Mandarin, Japanese, Korean, Hindi ...).
Velma publishes English-only accuracy and mislabels short Chinese clips; Soniox benchmarks at or
near the top on those languages, and was the owner's pick on code-switched Mandarin/English
(SCA-4810 lab, 2026-11-26). Our own public eval (2026-11-27) has Soniox ahead on every language but English. So for those calls Soniox runs first and any Soniox failure falls back
to Velma on the same audio. Legacy sync passes ``multi`` for every user not in single-language mode, so in
practice every Velma-bound file (including low-confidence English, where code-switching lands) goes to Soniox;
English keeps Velma first when it reaches the provider (single-language users): there Velma matches Soniox.

Scope: only calls made inside a legacy sync attempt (``current_parakeet_caller()`` is ``sync_*``).
Voice messages, push-to-talk, speaker verification and held recovery keep their current engines.
"""

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
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

# Velma stays first only where it matches Soniox at half the price. Public eval, 2026-11-27 (FLEURS dev, 60 s
# blocks, production clients; omi-workspace data/run-2026-11-26-multilang-stt-lab/eval): English WER Soniox 4.5%
# vs Velma 4.7%; Soniox won every other language (es 3.8 vs 5.3, zh CER 8.4 vs 21.8, ja 4.1 vs 12.8, hi 8.3 vs
# 33.6, code-switched zh-en 11.3 vs 16.9).
VELMA_FIRST_LANGUAGES = frozenset({'en'})
# Soniox async (upload, queue, transcribe, poll) must finish inside soniox_batch.DEADLINE_SECONDS (120 s); a
# timeout after the paid POST bills Soniox and then Velma. Longer files stay on Velma.
MAX_SECONDS = 300.0
# Soniox-first calls in flight per process. A full process sends the file to Velma instead of waiting, which bounds
# the create rate and the transcriptions held against Soniox's 2,000 stored-transcription cap (soniox_batch).
MAX_IN_FLIGHT = 8
_IN_FLIGHT = threading.BoundedSemaphore(MAX_IN_FLIGHT)
# Audio Soniox already had (answered, empty or failed) in the last TRIED_SECONDS: legacy sync's bounded empty
# retry calls again with attempts=0 moments later, and that retry must run Velma, never Soniox a second time.
# The memo expires, so a later redelivery of the same bytes gets Soniox again.
TRIED_SECONDS = 600.0
_TRIED: 'OrderedDict[str, float]' = OrderedDict()
_TRIED_LOCK = threading.Lock()
# transcribe() result when Soniox was attempted and failed: the caller runs Velma, and must not hand the same audio
# to Soniox again through the Modulate credit-refusal hop.
FAILED = object()


def _claim(digest: str) -> bool:
    """Record an attempt on this audio; False when it was already attempted recently. One lock: two concurrent
    calls with the same audio cannot both claim it."""
    now = time.monotonic()
    with _TRIED_LOCK:
        while _TRIED and next(iter(_TRIED.values())) < now - TRIED_SECONDS:
            _TRIED.popitem(last=False)
        if digest in _TRIED:
            return False
        _TRIED[digest] = now
        while len(_TRIED) > 2048:
            _TRIED.popitem(last=False)
        return True


def _release(digest: str) -> None:
    with _TRIED_LOCK:
        _TRIED.pop(digest, None)


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


def transcribe(audio_bytes: bytes, *, language: Optional[str], diarize: bool) -> Any:
    """Soniox's (words, detected language); ``FAILED`` when Soniox was attempted and failed (run Velma, no second
    Soniox submission); or None when Soniox was not attempted (run Velma exactly as before)."""
    duration = wav_duration_seconds(audio_bytes)
    digest = hashlib.sha256(audio_bytes).hexdigest()
    if not 0 < duration <= MAX_SECONDS:
        return None
    if not _claim(digest):
        # Soniox already has (or had) this audio: run Velma, and never let a failover hop resubmit it.
        logger.info('event=prerecorded_soniox_multilingual outcome=skipped reason=already_attempted')
        return FAILED
    if not _IN_FLIGHT.acquire(blocking=False):
        _release(digest)  # never attempted: a later call may still try Soniox
        logger.info('event=prerecorded_soniox_multilingual outcome=skipped reason=in_flight_cap')
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
        if isinstance(error, SonioxBatchError) and error.submitted:
            # Only an accepted or uncertain transcription POST may be billed.
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
        return FAILED
    finally:
        _IN_FLIGHT.release()
    record_vendor_burn(ENDPOINT_STT, 'ok', duration, provider=SONIOX_PROVIDER)
    logger.info('event=prerecorded_soniox_multilingual outcome=served words=%s', len(words))
    return words, detected
