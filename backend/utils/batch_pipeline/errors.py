"""Model-free process fencing shared by the worker and lease coordinator."""

import os
import traceback

from config.batch_pipeline import worker_validation_disposition_enabled
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
# lines. All three logging sites (the worker boundary, the scheduler's
# verdict terminal and the recover sweep's lease-expiry cap terminal, which
# share ``report_terminal_quarantine``) consult this set so the guard demotes
# together and nothing else does.
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
# fires for the same unit). All three logging sites (the worker boundary,
# the scheduler's verdict terminal and the recover sweep's lease-expiry cap
# terminal, which share ``report_terminal_quarantine``) consult this family
# so the empty ladder demotes together and nothing else does. The demotion
# rechannels the
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
# closed vad/word validation verdict ends it the same way. The fetch_decode
# bare-ValueError poison joins the unconditional arm beside the trio: the
# payload or admitted metadata itself cannot be parsed or decoded, identical
# input reproduces the fault on every attempt, and the worker ends the chain
# at its first occurrence with custody retained for the fenced recovery lane
# (see ``diarizer.batch_pipeline.decode_payload_is_deterministic``). Each
# hands the unit to the fenced independent-recognizer recovery lane with its
# measured VAD evidence and receipt intact. Nothing about the unit is faulted
# and no GPU retry can change the verdict, so booking each disposition on the
# ERROR fault channels misbooks a designed platform outcome as a production
# error: the vad_windows vad_bounds family, the word_clocks word_* family and
# the bare ``error_class=ValueError stage=fetch_decode`` cohort are top
# sensor signatures purely because the disposition handoff reuses the ERROR
# worker-fault lines (the worker's ``batch_worker_failed
# error_class=BatchValidationError stage=word_clocks`` and the scheduler's
# ``batch_quarantined reason=worker_failed ... recovery=held
# stage=word_clocks worker_reason=word_sequence`` fire for the same settled
# unit). All three logging sites consult this family so the disposition
# demotes
# together and nothing else does; the flagged arm demotes only while the
# same ``worker_validation_disposition_enabled`` switch that decided the
# durable disposition is on — a ladder still walking its retries keeps its
# fault lines — while the fetch_decode trio's chain end is unconditional on
# pinned bytes, so its demotion is too — and the poison arm's chain end is
# equally unconditional, because the bare ValueError is the pinned bytes'
# own parse failure. The deliberately-retryable
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
        WorkerValidationReason.DECODE_PAYLOAD_INVALID.value,
    }
)
# The persist tail's deterministic refusal is the persist sibling of the
# fetch_decode trio: the storage/register API refused the unit's request
# payload (a 400-class ``InvalidArgument`` that is not the expired-chain
# contention shape), identical input reproduces it on every attempt, and
# the worker ends the chain at its first occurrence with custody retained
# for the fenced recovery lane. The pair is stage-scoped like the trio:
# the persist refusal raises nowhere else, so the same token at another
# stage keeps its fault classification, and a foreign reason at the
# persist stage (the transport/contention families, ``unknown``) stays a
# real fault — a storage outage is not a designed handoff.
#
# Failure-Class: FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument
VALIDATION_DISPOSITION_PERSIST_STAGE = WorkerValidationStage.PERSIST.value
# The persist tail's second deterministic refusal is the privacy fence: the
# transactional privacy authority refuses a unit whose owner's account,
# data-protection setting, privacy generation or conversation state changed
# while its GPU window ran (``BatchPrivacyBlocked``). Identical input
# reproduces the refusal on every attempt — the fence reads the same live
# documents the replay's identity fields name — and it is user intent, not a
# worker fault, so the boundary ends the chain with the typed
# ``persist_privacy_refused`` custody handoff and the fenced recovery lane
# settles it through its own fence-first privacy check without
# re-recognition. The pair stays stage-scoped like the payload refusal: the
# privacy authority raises inside the persist register's transaction, so the
# same token at any other stage — and a foreign shape at persist (the
# transport/contention families, ``unknown``) — keeps its fault
# classification.
#
# Failure-Class: FC-privacy-refusal-at-persist-walks-gpu-retry-ladder-as-unclassified-worker-fault
VALIDATION_DISPOSITION_PERSIST_REASONS = frozenset(
    {WorkerValidationReason.PERSIST_PAYLOAD_INVALID.value, WorkerValidationReason.PERSIST_PRIVACY_REFUSED.value}
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
    unconditional fetch_decode family — the typed trio and the bare
    ValueError poison — answers only at the stage its classes raise; the
    persist refusal answers only at the persist stage its API raises at; the
    flagged verdicts answer at any
    closed worker stage, mirroring the boundary's stage-agnostic flag-gated
    arm, and only while ``disposition_enabled`` carries the same switch the
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
    if stage == VALIDATION_DISPOSITION_PERSIST_STAGE and reason in VALIDATION_DISPOSITION_PERSIST_REASONS:
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


def report_terminal_quarantine(logger, *, attempt, diagnosis) -> None:
    """Book one terminal-quarantine report for either scheduler terminal.

    The worker-verdict terminal (``Scheduler.fail``) and the recover sweep's
    lease-expiry cap terminal (``expire_lease`` -> ``observe_recovery``) end
    the same durable transition -- state=quarantined, recovery_state=held,
    the fenced recovery lane waiting below -- so both book the same report:
    the designed-handoff families answer on their INFO transition events, a
    real worker fault keeps the attributed worker-fault ERROR line naming
    the stage and reason the ladder actually collected, and the
    awaiting-recovery warning follows every booking. Before the shared
    report the expiry terminal booked every cap-reached unit -- designed
    handoffs included -- on a bare anonymous ``reason=lease_expired`` ERROR
    line that contradicted the ``quarantine_reason='worker_failed'`` the
    same transition had just written and carried no diagnosis at all, so
    the family demotions stopped at the verdict terminal and the sensor saw
    one fault class as two, one of them unattributable. Durable state,
    evidence, metrics and custody are written by the callers; this helper
    only rechannels the report. ``diagnosis`` may be any hostile shape
    (evidence rides on the job across ladder attempts and an older worker's
    write is read back unvalidated here): the classifiers never raise and a
    non-dict falls back to the anonymous unknown/unclassified attribution.

    Failure-Class: FC-lease-expiry-cap-quarantine-misbooked-as-anonymous-worker-fault
    """
    if not isinstance(diagnosis, dict):
        diagnosis = {}
    terminal_stage = diagnosis.get('stage', 'unknown')
    terminal_reason = diagnosis.get('reason', 'unclassified')
    if language_guard_redrive_failure(diagnosis):
        # The language guard is the designed redrive handoff: a typed,
        # evidence-backed terminal hold that the fenced
        # independent-recognizer lane settles. It keeps the same durable
        # state and the awaiting-recovery warning below, but it is not a
        # worker fault, so it leaves the ERROR quarantine channel to
        # faults -- at the expiry terminal exactly as at the verdict
        # terminal.
        logger.info(
            'event=batch_language_guard outcome=held_for_redrive attempt=%d recovery=held stage=%s worker_reason=%s',
            attempt,
            terminal_stage,
            terminal_reason,
        )
    elif empty_ladder_recovery_failure(diagnosis):
        # The empty ladder's handoff is the designed recovery hold: a typed
        # empty recognition the bounded context-bearing retry already ran,
        # booked with the worker_empty_evidence the ladder kept, and the
        # fenced quarantine-recovery lane waiting below. It keeps the same
        # durable state and the awaiting-recovery warning below, but it is
        # not a worker fault, so it leaves the ERROR quarantine channel to
        # faults -- at the expiry terminal exactly as at the verdict
        # terminal.
        logger.info(
            'event=batch_empty_ladder outcome=held_for_recovery attempt=%d recovery=held stage=%s worker_reason=%s',
            attempt,
            terminal_stage,
            terminal_reason,
        )
    elif validation_disposition_failure(diagnosis, disposition_enabled=worker_validation_disposition_enabled()):
        # The terminal worker-validation disposition is the designed
        # recovery hold: typed deterministic faults and closed vad/word
        # verdicts no GPU retry can repair, booked with the preserved
        # evidence and the fenced quarantine-recovery lane waiting below.
        # It keeps the same durable state and the awaiting-recovery warning
        # below, but it is not a worker fault, so it leaves the ERROR
        # quarantine channel to faults. The flagged verdicts demote only
        # under the same disposition switch that decided the durable chain
        # end; a ladder still walking its retries keeps its ERROR line --
        # at the expiry terminal under the same switch, so both terminals
        # demote together and nothing else does.
        logger.info(
            'event=batch_validation_disposition outcome=held_for_disposition attempt=%d recovery=held stage=%s worker_reason=%s',
            attempt,
            terminal_stage,
            terminal_reason,
        )
    else:
        logger.error(
            'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s',
            attempt,
            terminal_stage,
            terminal_reason,
        )
    logger.warning('event=batch_recovery outcome=held reason=awaiting_fenced_recovery')


class FatalGpuError(RuntimeError):
    """GPU process must restart; never turn this flight into a segment failure."""
