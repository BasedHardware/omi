"""Model-free process fencing shared by the worker and lease coordinator."""

import os
import traceback

from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values

WORKER_VALIDATION_STAGES = reason_values(WorkerValidationStage)
WORKER_VALIDATION_REASONS = reason_values(WorkerValidationReason)


def error_site_field(error: BaseException) -> str:
    """Return a static source file and line from an exception, never its payload."""
    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:
        return ''
    for frame in reversed(frames):
        if 'site-packages' not in frame.filename and 'dist-packages' not in frame.filename:
            return f' site={os.path.basename(frame.filename)}:{frame.lineno}'
    return ''


def validate_worker_failure(failure):
    """Durable diagnostics accept closed codes only, never an exception message."""
    if (
        not isinstance(failure, dict)
        or set(failure) != {'stage', 'reason'}
        or failure['stage'] not in WORKER_VALIDATION_STAGES
        or failure['reason'] not in WORKER_VALIDATION_REASONS
    ):
        raise ValueError('closed worker validation failure required')


WORKER_VALIDATION_REASON_TOKENS = frozenset(member.value for member in WorkerValidationReason)

# The GPU language barrier refuses a unit whose frozen language the word
# provider cannot serve. The refusal is typed (BatchValidationError with the
# closed reason), carries affirmative strict-VAD speech evidence, ends the
# chain terminally, and hands the unit to the fenced independent-recognizer
# recovery lane (modulate, then Soniox) which transcribes the retained audio.
# Nothing about the unit is lost and no retry can change the verdict, so the
# transition is designed platform behavior — not a worker fault. Logging it
# through the fault channels misbooks every guarded unit as a production
# error: the vad_windows unsupported_language family is a top sensor
# signature purely because the redrive handoff reuses the ERROR worker-fault
# lines. Both logging sites (the worker boundary and the scheduler's terminal
# quarantine line) consult this set so the guard demotes together and nothing
# else does.
LANGUAGE_GUARD_REDRIVE_REASONS = frozenset({'unsupported_language'})


def language_guard_redrive_failure(failure: object) -> bool:
    """True for a closed terminal diagnosis that is the language-guard redrive.

    Accepts exactly the closed shapes the scheduler stores on a job: the
    two-key ``{'stage', 'reason'}`` dicts the store validators admit. Anything
    anonymous (empty diagnosis, extra fields, foreign reason, off-vocabulary
    stage, non-string tokens, non-dict input) is not the guard and keeps its
    fault classification. Never raises on hostile input.
    """

    if not isinstance(failure, dict) or set(failure) != {'stage', 'reason'}:
        return False
    stage, reason = failure['stage'], failure['reason']
    return (
        isinstance(stage, str)
        and isinstance(reason, str)
        and stage in WORKER_VALIDATION_STAGES
        and reason in LANGUAGE_GUARD_REDRIVE_REASONS
    )


# The empty ladder's terminal empty verdict is the assemble_words sibling of
# the language barrier: a typed BatchValidationError the worker already
# resolved through its bounded context-bearing retry, a RecoveryWork handoff
# carrying the retry and VAD evidence, and the fenced quarantine-recovery
# lane waiting below. Nothing about the unit is faulted and no worker retry
# can change the verdict, so booking each held unit on the ERROR fault
# channels misbooks a designed platform outcome as a production error: the
# assemble_words empty_asr / no_owned_words family is a top sensor signature
# purely because the handoff reuses the ERROR worker-fault lines (the
# scheduler's ``batch_quarantined reason=worker_failed ... recovery=held
# stage=assemble_words worker_reason=empty_asr`` and the worker's
# ``batch_worker_failed error_class=BatchValidationError stage=assemble_words``
# fires for the same unit). Both logging sites (the worker boundary and the
# scheduler's terminal quarantine line) consult this family so the empty
# ladder demotes together and nothing else does. The demotion rechannels the
# report only: durable state, evidence, metrics, custody and the
# awaiting-fenced-recovery warning are unchanged.
#
# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
EMPTY_LADDER_RECOVERY_REASONS = frozenset({'empty_asr', 'no_owned_words'})

# The stage the empty ladder owns: EMPTY_ASR and NO_OWNED_WORDS raise nowhere
# else, so an empty-family token at any other stage keeps its fault
# classification.
EMPTY_LADDER_RECOVERY_STAGE = WorkerValidationStage.ASSEMBLE_WORDS.value


def empty_ladder_recovery_failure(failure: object) -> bool:
    """True for a closed terminal diagnosis that is the empty ladder's handoff.

    Accepts exactly the closed shapes the scheduler stores on a job: the
    two-key ``{'stage', 'reason'}`` dicts the store validators admit, with
    the stage the empty ladder owns. Anything anonymous (empty diagnosis,
    extra fields, foreign reason, off-vocabulary stage, non-string tokens,
    non-dict input) is not the ladder and keeps its fault classification.
    Never raises on hostile input.
    """

    if not isinstance(failure, dict) or set(failure) != {'stage', 'reason'}:
        return False
    stage, reason = failure['stage'], failure['reason']
    return (
        isinstance(stage, str)
        and isinstance(reason, str)
        and stage == EMPTY_LADDER_RECOVERY_STAGE
        and reason in EMPTY_LADDER_RECOVERY_REASONS
    )


# The terminal worker-validation disposition is the bounded GPU chain's
# designed custody handoff for input no retry can repair. Two arms decide it
# at the worker boundary: the typed staged/retained/decoded-extent trio fails
# identically on the pinned bytes on every attempt and ends the chain
# unconditionally, and under the worker-validation disposition switch every
# closed vad/word validation verdict ends it the same way. Each hands the
# unit to the fenced independent-recognizer recovery lane with its measured
# VAD evidence and receipt intact. Nothing about the unit is faulted and no
# GPU retry can change the verdict, so booking each disposition on the ERROR
# fault channels misbooks a designed platform outcome as a production error:
# the vad_windows vad_bounds family and the word_clocks word_* family are top
# sensor signatures purely because the disposition handoff reuses the ERROR
# worker-fault lines (the worker's ``batch_worker_failed
# error_class=BatchValidationError stage=word_clocks`` and the scheduler's
# ``batch_quarantined reason=worker_failed ... recovery=held
# stage=word_clocks worker_reason=word_sequence`` fire for the same settled
# unit). Both logging sites consult this family so the disposition demotes
# together and nothing else does; the flagged arm demotes only while the
# same ``worker_validation_disposition_enabled`` switch that decided the
# durable disposition is on — a ladder still walking its retries keeps its
# fault lines — while the fetch_decode trio's chain end is unconditional on
# pinned bytes, so its demotion is too. The deliberately-retryable
# ``outside_admitted_source`` and every unclassified fault keep their ERROR
# lines. The demotion rechannels the report only: durable state, evidence,
# metrics, custody and the awaiting-fenced-recovery warning are unchanged.
#
# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE = WorkerValidationStage.FETCH_DECODE.value
VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS = frozenset(
    {
        WorkerValidationReason.STAGED_AUDIO_INVALID.value,
        WorkerValidationReason.RETAINED_AUDIO_INVALID.value,
        WorkerValidationReason.DECODED_DURATION_MISMATCH.value,
    }
)
VALIDATION_DISPOSITION_FLAGGED_REASONS = frozenset(
    {
        WorkerValidationReason.VAD_NONFINITE.value,
        WorkerValidationReason.VAD_ORDER.value,
        WorkerValidationReason.VAD_BOUNDS.value,
        WorkerValidationReason.WORD_SHAPE.value,
        WorkerValidationReason.WORD_CLOCK.value,
        WorkerValidationReason.WORD_SEQUENCE.value,
    }
)
VALIDATION_DISPOSITION_REASONS = VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS | VALIDATION_DISPOSITION_FLAGGED_REASONS


def validation_disposition_failure(failure: object, *, disposition_enabled: bool) -> bool:
    """True for a closed terminal diagnosis that is the disposition handoff.

    Accepts exactly the closed shapes the scheduler stores on a job: the
    two-key ``{'stage', 'reason'}`` dicts the store validators admit. The
    unconditional trio answers only at the fetch_decode stage the typed
    classes raise nowhere else; the flagged verdicts answer at any closed
    worker stage, mirroring the boundary's stage-agnostic flag-gated arm,
    and only while ``disposition_enabled`` carries the same switch the
    durable path read. Anything anonymous (empty diagnosis, extra fields,
    foreign reason, off-vocabulary stage, non-string tokens, non-dict
    input) is not the disposition and keeps its fault classification. Never
    raises on hostile input.
    """

    if not isinstance(failure, dict) or set(failure) != {'stage', 'reason'}:
        return False
    stage, reason = failure['stage'], failure['reason']
    if not isinstance(stage, str) or not isinstance(reason, str):
        return False
    if stage == VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE and reason in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS:
        return True
    return (
        disposition_enabled and stage in WORKER_VALIDATION_STAGES and reason in VALIDATION_DISPOSITION_FLAGGED_REASONS
    )


def validate_worker_failure_evidence(failure):
    """Evidence-only diagnostics from an ordinary retryable failure.

    The stage stays closed. The reason may additionally be the enum's own
    ``unknown`` token: an unclassified exception is still a diagnosed stage,
    and the evidence never decides a transition, so its vocabulary is the
    strict superset of the terminal gate's. Exception messages stay out.
    """
    if (
        not isinstance(failure, dict)
        or set(failure) != {'stage', 'reason'}
        or failure['stage'] not in WORKER_VALIDATION_STAGES
        or failure['reason'] not in WORKER_VALIDATION_REASON_TOKENS
    ):
        raise ValueError('closed worker failure evidence required')


class FatalGpuError(RuntimeError):
    """GPU process must restart; never turn this flight into a segment failure."""
