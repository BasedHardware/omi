"""Listen session exit custody: every exit bookkeeping step owns its fault.

A listen session ends through one long teardown envelope: the no-audio
observation close, the WebSocket-close record, the routing-cohort finish,
the session unregister, the live-transcription close, the transcript
outcome book, the lane meter, the live-demand tail publish, the final
usage flush, the disconnect finalization, the multi-channel tail, the
onboarding and language summaries, the supervisor drain, the speaker
ordinals, the idle arm and the three buffer clears -- plus the
pre-session cohort warm in front of the session. Most of those steps had
no fault owner of their own: they ran bare inside ``try/finally`` blocks
whose ``finally`` only *ran*, never *contained*, so one fault on any of
them aborted every later exit step (the conversation could stay stuck
in-progress, the pusher socket never closed cleanly) and escaped the
supervision envelope. On the deployed build each escape surfaced as
uvicorn's ``Exception in ASGI application`` traceback at the
``websockets_impl.py`` ``run_asgi`` frame -- the prod error sensor's top
``backend-listen`` family. The observed arms walk
``_teardown_components`` -> ``_flush_usage`` -> ``persistence.call`` and
``conversations.prepare`` -> ``create_new_in_progress_conversation``
straight out to that frame, plus the bare ``try/finally`` tail.

The contract, owned here so every exit site reads one table:

- ``SESSION_EXIT_STEPS`` is the closed step table. Each row names the
  step key, its exit-line outcome token, the phase the step belongs to
  (``pre_session`` for the cohort warm in front of the session,
  ``record`` for pure post-exit telemetry, ``exit`` for the teardown
  envelope), and its attempt budget: the final usage flush replays --
  a contention wave is seconds-wide and the metering tail is worth an
  in-process wait -- every other row is report-only.
- ``exit_fault_is_contention`` is the closed contention class, the same
  one the teardown-custody family replays under:
  ``FirestoreContentionExhausted`` including the Postgres job-store
  subclass, plus any exception whose cause chain classifies as atomic
  transaction contention. Everything else is a real fault.
- ``report_exit_step_fault`` books one exit fault on its row's honest
  channel: a closed contention loss reports at WARNING -- losing the
  race is not a fault, the durable fallback (the recovery lane, the
  session census, the client reconnect) owns the unit -- carrying the
  losing store label, the sanitized attempt, the storm window the
  damper had armed and the static source site. Any other fault keeps
  the ERROR channel: same line shape, race fields omitted. The
  exception name and the source file:line are the only payloads a line
  carries; no uid, segment or conversation token ever interpolates.
- ``run_exit_step`` drives one report-only row's function to its
  budget of one: a fault books the row's line once and the teardown
  continues with the next step. ``run_exit_step_replay`` drives a
  replayable row: a closed contention loss replays on
  ``exit_replay_delay``'s doubling ladder with every wait raised to the
  stamped storm window (``exit_storm_after``, clamped at the store
  damper's own 4.0s cap), so the replay lands after the armed window
  instead of colliding inside it; the replays stay silent, so a storm
  that converges logs nothing. Past the budget the loss is reported
  once and the exit continues -- the periodic in-body usage flush and
  the durable usage provenance own the metering tail exactly as
  before. A non-contention fault reports once immediately without
  replaying -- re-striking a real failure only replays the same
  refusal. The step's own return value is bookkeeping and is
  discarded; the caller at the exit site already ignores it.
- ``run_exit_step_sync`` is the synchronous twin for the pure telemetry
  rows (the close record, the cohort finish, the ordinal ledger, the
  idle arms, the no-audio counter), where a fault must never mask the
  session's real terminal outcome -- these rows are the reason the
  post-supervision ``finally`` blocks are raise-proof.

Cancellation is ``BaseException``: an exit step never swallows its own
shutdown, so the deletion fence and ASGI shutdown stay observable. With
every row owned, the teardown envelope cannot raise an ``Exception``
past itself: the admission guard's ``listen session failed before
supervision`` label becomes truthful, and no session bookkeeping fault
reaches uvicorn's ASGI-crash channel.

Failure-Class: FC-listen-session-exit-custody-faults-escape-as-asgi-crashes
"""

import asyncio
import logging
import os
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from utils.batch_pipeline.teardown_custody import (
    contention_operation_field,
    teardown_loss_is_contention,
    teardown_replay_delay,
    teardown_storm_after,
)

# The final usage flush is the one exit step whose bounded contention
# budget replays in-process: the first fenced call plus two bounded
# replays, the same total the teardown refunds carry.
SESSION_EXIT_REPLAY_ATTEMPTS = 3

# The exit lines' shared event token.
SESSION_EXIT_EVENT = 'event=listen_session_exit'


@dataclass(frozen=True)
class SessionExitStep:
    """One listen session exit step: its exit line and its channel."""

    key: str
    event: str
    outcome: str
    phase: str
    contention_level: int
    attempts: int


SESSION_EXIT_STEPS = {
    'no_audio_observation_close': SessionExitStep(
        key='no_audio_observation_close',
        event=SESSION_EXIT_EVENT,
        outcome='observation_close_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'ws_close_record': SessionExitStep(
        key='ws_close_record',
        event=SESSION_EXIT_EVENT,
        outcome='ws_close_record_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'cohort_finish': SessionExitStep(
        key='cohort_finish',
        event=SESSION_EXIT_EVENT,
        outcome='cohort_finish_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'unregister_session': SessionExitStep(
        key='unregister_session',
        event=SESSION_EXIT_EVENT,
        outcome='unregister_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'finish_live_transcription': SessionExitStep(
        key='finish_live_transcription',
        event=SESSION_EXIT_EVENT,
        outcome='live_transcription_close_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'transcript_outcome': SessionExitStep(
        key='transcript_outcome',
        event=SESSION_EXIT_EVENT,
        outcome='transcript_outcome_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'lane_meter': SessionExitStep(
        key='lane_meter',
        event=SESSION_EXIT_EVENT,
        outcome='lane_meter_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'demand_publish': SessionExitStep(
        key='demand_publish',
        event=SESSION_EXIT_EVENT,
        outcome='demand_publish_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'usage_flush': SessionExitStep(
        key='usage_flush',
        event=SESSION_EXIT_EVENT,
        outcome='usage_flush_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=SESSION_EXIT_REPLAY_ATTEMPTS,
    ),
    'multi_channel_tail': SessionExitStep(
        key='multi_channel_tail',
        event=SESSION_EXIT_EVENT,
        outcome='multi_channel_tail_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'onboarding_cleanup': SessionExitStep(
        key='onboarding_cleanup',
        event=SESSION_EXIT_EVENT,
        outcome='onboarding_cleanup_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'language_summary': SessionExitStep(
        key='language_summary',
        event=SESSION_EXIT_EVENT,
        outcome='language_summary_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'final_drain': SessionExitStep(
        key='final_drain',
        event=SESSION_EXIT_EVENT,
        outcome='final_drain_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'speaker_ordinals': SessionExitStep(
        key='speaker_ordinals',
        event=SESSION_EXIT_EVENT,
        outcome='speaker_ordinals_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'idle_arm_record': SessionExitStep(
        key='idle_arm_record',
        event=SESSION_EXIT_EVENT,
        outcome='idle_arm_record_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'receiver_clear': SessionExitStep(
        key='receiver_clear',
        event=SESSION_EXIT_EVENT,
        outcome='receiver_clear_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'transcripts_clear': SessionExitStep(
        key='transcripts_clear',
        event=SESSION_EXIT_EVENT,
        outcome='transcripts_clear_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'speakers_clear': SessionExitStep(
        key='speakers_clear',
        event=SESSION_EXIT_EVENT,
        outcome='speakers_clear_failed',
        phase='exit',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'idle_arm_session': SessionExitStep(
        key='idle_arm_session',
        event=SESSION_EXIT_EVENT,
        outcome='idle_arm_session_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'no_audio_record': SessionExitStep(
        key='no_audio_record',
        event=SESSION_EXIT_EVENT,
        outcome='no_audio_record_failed',
        phase='record',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'warm_cohorts': SessionExitStep(
        key='warm_cohorts',
        event=SESSION_EXIT_EVENT,
        outcome='cohort_warm_failed',
        phase='pre_session',
        contention_level=logging.WARNING,
        attempts=1,
    ),
}

# The steps whose bounded budget replays a closed contention loss.
SESSION_EXIT_REPLAY_STEPS = frozenset(key for key, row in SESSION_EXIT_STEPS.items() if row.attempts > 1)


def exit_fault_is_contention(error: BaseException) -> bool:
    """True for exactly the closed contention class an exit row may absorb.

    The teardown family's own closed class, reused verbatim: an
    exhaustion instance at the top of the chain (``FirestoreContentionExhausted``
    including the Postgres job-store subclass), or a cause chain that
    classifies as atomic transaction contention -- and nothing else. A
    ``ValueError`` wrapping an exhaustion is not a lost race. Never
    raises on hostile input.
    """
    return teardown_loss_is_contention(error)


def exit_step_site_field(error: BaseException) -> str:
    """A static source file and line from the fault, never its payload."""
    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:
        return ''
    for frame in reversed(frames):
        if 'site-packages' not in frame.filename and 'dist-packages' not in frame.filename:
            return f' site={os.path.basename(frame.filename)}:{frame.lineno}'
    return ''


def exit_replay_delay(replay_index: object) -> float:
    """One ladder step of the bounded exit replay schedule, in seconds.

    The teardown family's documented ladder: ``min(max, base * 2 ** (index - 1))``
    over a sanitized index, so a hostile shape collapses to the first
    step instead of raising inside a never-raise boundary.
    """
    return teardown_replay_delay(replay_index)


def exit_storm_after(error: BaseException | None) -> float:
    """The measured storm window an exit replay must land after.

    Read from the chain exhaustion's ``retry_after`` stamp exactly the
    way the teardown family reads it; only a positive finite number on
    the exhaustion class counts, everything else keeps the ladder.
    """
    return teardown_storm_after(error)


def _exit_attempt(attempt: object) -> int:
    """The attempt count an exit line renders, sanitized for ``%d``."""
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        return 1
    return attempt


def report_exit_step_fault(logger, *, step: SessionExitStep, error: BaseException, attempt: object = 1) -> None:
    """Book one exit fault on its row's honest channel.

    A closed contention loss reports at the row's WARNING level with
    the losing store label, the sanitized attempt, the armed storm
    window and the static source site; any other fault keeps the ERROR
    channel with the same line shape minus the race fields. Never
    raises: a hostile exception shape reports the fault class only.
    """
    error_type = type(error).__name__
    if exit_fault_is_contention(error):
        logger.log(
            step.contention_level,
            '%s outcome=%s phase=%s step=%s fault_type=%s%s attempt=%d retry_after_ms=%d%s',
            step.event,
            step.outcome,
            step.phase,
            step.key,
            error_type,
            contention_operation_field(error),
            _exit_attempt(attempt),
            round(exit_storm_after(error) * 1000),
            exit_step_site_field(error),
        )
        return
    logger.error(
        '%s outcome=%s phase=%s step=%s fault_type=%s%s',
        step.event,
        step.outcome,
        step.phase,
        step.key,
        error_type,
        exit_step_site_field(error),
    )


async def run_exit_step(
    step: SessionExitStep,
    function: Callable[..., Any],
    *args: Any,
    logger: logging.Logger,
    **kwargs: Any,
) -> int:
    """Drive one report-only exit step; a fault books its line and exits clean.

    Cancellation propagates: an exit step never swallows its own
    shutdown. Any ``Exception`` the step raises books the row's line
    once -- the fault type, the static site and, for the closed
    contention class, the losing store label and the armed storm
    window -- and the teardown continues with the next step. Returns
    the attempts spent (always 1). The step's return value is
    bookkeeping and is discarded.
    """
    try:
        await function(*args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report_exit_step_fault(logger, step=step, error=error, attempt=1)
    return 1


async def run_exit_step_replay(
    step: SessionExitStep,
    function: Callable[..., Any],
    *args: Any,
    logger: logging.Logger,
    sleep: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> int:
    """Drive one exit step to its row's budget, replaying contention only.

    A closed contention loss replays on ``exit_replay_delay``'s ladder
    with every wait raised to ``exit_storm_after``'s measured window;
    the waits run on the event loop this exit already occupies and the
    replays stay silent, so a storm that converges logs nothing. A
    non-contention fault reports once immediately without replaying --
    re-striking a real failure only replays the same refusal. Past the
    budget the loss is reported once and the exit continues. Returns
    the attempts spent.
    """
    # Resolve asyncio.sleep at call time: a default argument would bind
    # the function once and hide it from tests that patch asyncio.sleep.
    wait = sleep if sleep is not None else asyncio.sleep
    attempts = 0
    while attempts < step.attempts:
        attempts += 1
        try:
            await function(*args, **kwargs)
            return attempts
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if attempts >= step.attempts or not exit_fault_is_contention(error):
                report_exit_step_fault(logger, step=step, error=error, attempt=attempts)
                return attempts
            await wait(max(exit_replay_delay(attempts), exit_storm_after(error)))
    return attempts


def run_exit_step_sync(
    step: SessionExitStep,
    function: Callable[..., Any],
    *args: Any,
    logger: logging.Logger,
    **kwargs: Any,
) -> int:
    """The synchronous twin for the pure telemetry exit rows.

    Same contract as ``run_exit_step`` for a sync function: one fault,
    one line, the teardown continues, and the post-supervision
    ``finally`` the row runs in can no longer raise.
    """
    try:
        function(*args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report_exit_step_fault(logger, step=step, error=error, attempt=1)
    return 1
