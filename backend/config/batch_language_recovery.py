"""Controlled independent recognition; hard one-minute per-intent spend bound."""

import math
import os

from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
    normalized_stt_language,
)

PROVIDER = 'soniox'
MAX_AUDIO_SECONDS = 60.0
# Below one complete Silero frame (512 / 16000). Not a measured-language
# diagnosis; no full positive VAD frame can be reclassified by this rule.
SILENCE_THRESHOLD_SECONDS = 0.032
ESTIMATED_USD_PER_AUDIO_HOUR = 0.10


def inherited_language(conversation_language, user_language):
    """Prefer the bound conversation, then the user's configured language.

    Auto/multi/unknown and unrecognized codes are not language declarations.
    This applies to every piece, including short ambient-dominated WAL clips.
    """
    parakeet = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]]
    for value in (conversation_language, user_language):
        if isinstance(value, str):
            code = normalized_stt_language(value.strip())
            if code not in {'multi', 'und', 'unknown', 'auto'} and code in MODULATE_SUPPORTED_LANGUAGES | parakeet:
                return code
    return None


def enabled():
    return os.getenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false').strip().lower() == 'true'


def allowed(seconds):
    try:
        cap = float(os.getenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', str(MAX_AUDIO_SECONDS)))
        return enabled() and math.isfinite(cap) and 0 < seconds <= min(cap, MAX_AUDIO_SECONDS)
    except (TypeError, ValueError):
        return False


def language_guarded(job):
    # Both unsupported/blocked and unknown/blocked worker routes use this reason.
    return (job.get('worker_failure') or {}).get('reason') == 'unsupported_language'


def below_silence_threshold(seconds):
    # A late timestamp's subtraction must not round a full VAD frame down.
    return math.isfinite(seconds) and 0 <= round(seconds * 16000) < round(SILENCE_THRESHOLD_SECONDS * 16000)


def independent_attempted(job):
    receipt = ((job.get('recovery') or {}).get('recognizers') or {}).get(PROVIDER) or {}
    return receipt.get('outcome') in {'started', 'words', 'empty', 'error'}


def prior_modulate_empty(job):
    paid = job.get('speech_redrive') or {}
    if paid.get('provider') == PROVIDER:
        paid = paid.get('prior_speech_redrive') or {}
    for attempt in (job.get('recovery') or {}, paid):
        if attempt.get('provider') != 'modulate':
            continue
        receipt = (attempt.get('recognizers') or {}).get('modulate')
        if receipt is not None:
            if receipt.get('outcome') == 'empty' and receipt.get('word_count') == 0:
                return True
        elif attempt.get('failure') == {'stage': 'response_validation', 'reason': 'empty_asr'}:
            # Historical spent intents predate per-recognizer receipts. Their
            # closed validated-empty failure is bound to this same audio window.
            return True
    return False
