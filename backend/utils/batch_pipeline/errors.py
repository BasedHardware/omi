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
