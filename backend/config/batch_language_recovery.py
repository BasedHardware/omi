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


REPAIR_EPOCH = 4
REPAIR_PROVIDER = 'modulate'


def words_repair_eligible(job):
    """Lead rulings 7fa3d2/a3af50: a spent guarded intent whose Modulate words were
    rejected only for zero strict CPU VAD, whose capped Soniox call settled with a
    validated answer (empty, or words that met the same rejection), and whose bound
    worker VAD receipt measured speech. Its operator repair buys exactly one explicit
    Modulate call; the spent intent and both receipts stay untouched. Neither
    recognizer's words were persisted, so no zero-call re-settle exists.
    """
    from utils.batch_pipeline.contracts import worker_vad_speech

    recovery = job.get('recovery') or {}
    receipts = recovery.get('recognizers') or {}
    modulate, soniox = receipts.get('modulate') or {}, receipts.get(PROVIDER) or {}
    return (
        language_guarded(job)
        and recovery.get('provider') == 'modulate'
        and recovery.get('failure') == {'stage': 'payload_validation', 'reason': 'invalid_payload'}
        and modulate.get('outcome') == 'words'
        and type(modulate.get('word_count')) is int
        and modulate['word_count'] > 0
        and (
            (soniox.get('outcome') == 'empty' and soniox.get('word_count') == 0)
            or (soniox.get('outcome') == 'words' and type(soniox.get('word_count')) is int and soniox['word_count'] > 0)
        )
        # Malformed jobs fail closed here, never inside a retention transaction.
        and isinstance(job.get('audio_uri'), str)
        and type(job.get('duration_seconds')) in {int, float}
        and 0 < job['duration_seconds'] <= MAX_AUDIO_SECONDS
        and worker_vad_speech(job) is not None
    )


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


def guarded_exhausted(job):
    """Guarded no-speech evidence: both recognizers attempted and validated empty.

    Receipts, never the shared ``empty_asr`` failure shape, are the evidence: an
    operator take-over of a prepared intent can settle that same failure with
    Soniox alone, and its unattempted Modulate side must keep blocking a
    guarded terminal outcome.
    """
    receipts = (job.get('recovery') or {}).get('recognizers') or {}
    return all(
        (receipts.get(provider) or {}).get('outcome') == 'empty'
        and (receipts.get(provider) or {}).get('word_count') == 0
        for provider in ('modulate', 'soniox')
    )


def duration_limited(job):
    """The exact shape RecoveryStore.hold_duration_limit settles (#23795): a
    guarded epoch-1 intent held only by the >60s independent bound, never
    started, with no provider call, receipt or failure. Only this shape may be
    reopened for an operator take-over; a spent intent never reopens."""
    recovery = job.get('recovery') or {}
    refusal = recovery.get('refusal') or {}
    return (
        job.get('recovery_state') == 'failed_held'
        and refusal.get('reason') == 'independent_duration_limit'
        and refusal.get('max_audio_seconds') == MAX_AUDIO_SECONDS
        and not recovery.get('started_at')
        and not recovery.get('provider')
        and not recovery.get('recognizers')
        and not recovery.get('failure')
    )
