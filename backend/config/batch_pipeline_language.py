"""Language eligibility before new sync batch custody; independent of legacy mode."""

import os
from dataclasses import dataclass

from config.prerecorded_language import language_class
from config.refactor_switches import default_on
from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
    normalized_stt_language,
)


def admission_language_exclusion_enabled() -> bool:
    """Ship-on; explicit false restores the former admission and LID inputs."""
    return default_on(
        'BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED',
        os.getenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'true').strip().lower() != 'false',
    )


def admission_language_sample_enabled() -> bool:
    """Ship-on; an unknown-multilingual upload is admitted only after its first unit's LID is Parakeet-safe.

    Explicit false restores the full exclusion (every such upload stays on legacy).
    """
    return default_on(
        'BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED',
        os.getenv('BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED', 'true').strip().lower() != 'false',
    )


def batch_admission_language(user: dict, conversation: dict) -> tuple[str | None, str | None]:
    """Return the declared language or a bounded exclusion reason.

    A non-single-language preference requires a supported bound conversation.
    Recognized conversation context outranks the user's preference, matching
    language inheritance. Unknown strings never establish model capability.
    """
    parakeet = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]] - {
        'multi'
    }

    def code(value):
        return normalized_stt_language(value.strip()) if isinstance(value, str) else ''

    conversation_language = code(conversation.get('language'))
    user_language = code(user.get('language'))
    known = (MODULATE_SUPPORTED_LANGUAGES | parakeet) - {'multi'}
    effective = next((value for value in (conversation_language, user_language) if value in known), '')
    if effective and effective not in parakeet:
        return None, 'known_unsupported_language'
    single = (user.get('transcription_preferences') or {}).get('single_language_mode')
    if not single or user_language not in known:
        if conversation_language not in parakeet:
            return None, 'unknown_multilingual_conversation'
        return conversation_language, None
    return effective or user_language, None


INTAKE_UNIT_LANES = frozenset({'parakeet', 'multilingual'})

# Closed plan reasons: every admission lane decision names the cell that produced it,
# so a new input cannot silently blend into an existing outcome.
INTAKE_UNIT_PLAN_REASONS = frozenset(
    {
        'guard_disabled',
        'decision_parakeet_safe',
        'unknown_speech',
        'detected_unsupported_speech',
        'silent_or_unresolved_barrier',
    }
)


@dataclass(frozen=True)
class IntakeUnitLanguagePlan:
    """One admitted unit's serving lane and frozen language, decided once on CPU.

    ``lane='parakeet'`` keeps the GPU compute admission; ``lane='multilingual'``
    moves the whole request to the provider lane (the C8 fenced Modulate path)
    because this unit's speech provably cannot be served by the GPU words
    engine. ``frozen_language`` is the staging code both the worker's language
    barrier and the provider stage read.

    Failure-Class: FC-nonaffirmative-language-speech-admitted-to-gpu-barrier-as-guaranteed-failed-attempt
    """

    lane: str
    reason: str
    frozen_language: str

    def __post_init__(self):
        if self.lane not in INTAKE_UNIT_LANES:
            raise ValueError('closed intake unit lane required')
        if self.reason not in INTAKE_UNIT_PLAN_REASONS:
            raise ValueError('closed intake unit plan reason required')
        if len(self.frozen_language) > 16:
            raise ValueError('bounded frozen language required')


def intake_unit_language_plan(
    *,
    decision_language: str | None,
    parakeet_safe: bool,
    strict_speech: bool | None,
    input_language: str,
    language_guard: bool,
) -> IntakeUnitLanguagePlan:
    """Decide one unit's lane and frozen language from its CPU evidence.

    The GPU worker's language barrier raises ``unsupported_language`` for any
    speech whose frozen language is not a Parakeet-supported code, so a unit
    admitted to the compute lane with a non-affirmative language decision and
    strict-CPU speech evidence is a guaranteed failed attempt: full decode,
    a terminal quarantine, and a fenced recovery pass that re-runs the same
    recognition the provider lane would have run directly. Such units take
    the provider lane here instead. Strict silence or unavailable evidence
    keeps the compute lane — the worker's own strict inspector disposes
    silence with no ASR and stays the authority for unresolved answers, and
    routing unproven speech to a paid recognizer would spend recognition on
    possible silence. An affirmative (Parakeet-safe) decision always wins,
    whatever the strict inspector says, and the guard kill switch restores
    today's freeze-as-input behavior for unresolved answers wholesale.
    """
    decision_class = language_class(decision_language)
    if parakeet_safe:
        return IntakeUnitLanguagePlan('parakeet', 'decision_parakeet_safe', decision_language or input_language)
    if decision_class == 'unsupported':
        # A confident unsupported answer freezes the detected code in every
        # mode; only proven speech flips the lane.
        if strict_speech is True:
            return IntakeUnitLanguagePlan('multilingual', 'detected_unsupported_speech', decision_language or 'und')
        return IntakeUnitLanguagePlan('parakeet', 'silent_or_unresolved_barrier', decision_language or 'und')
    if not language_guard:
        return IntakeUnitLanguagePlan('parakeet', 'guard_disabled', input_language)
    if strict_speech is True:
        return IntakeUnitLanguagePlan('multilingual', 'unknown_speech', 'und')
    # Silent or unmeasured: the worker's strict inspector stays the
    # authority, exactly as before.
    return IntakeUnitLanguagePlan('parakeet', 'silent_or_unresolved_barrier', 'und')


@dataclass(frozen=True)
class IntakeRequestLanguagePlan:
    """The request-level lane after every unit's plan is known.

    ``provider_lane`` mirrors the C8 route fields intake stamps today: the
    request's policy flips to the provider lane with
    ``provider_reason='unsupported_language'`` and the modulate service, so
    its units stage with no GPU compute admission and the provider stage owns
    funding, privacy and at-most-once recognition. A request already on the
    provider route keeps it untouched.
    """

    provider_lane: bool
    reason: str | None
    language: str


def intake_request_language_lane(plans, *, stt_route: str) -> IntakeRequestLanguagePlan:
    """Flip the request to the provider lane when any unit's plan demands it."""
    for plan in plans:
        if plan.lane == 'multilingual':
            if stt_route == 'provider':
                return IntakeRequestLanguagePlan(False, None, plan.frozen_language)
            return IntakeRequestLanguagePlan(True, plan.reason, plan.frozen_language)
    return IntakeRequestLanguagePlan(False, None, '')
