"""Ship-on protection for speech-bearing empty ASR. Read the kill switch per call."""

import os


def safety_net_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true').strip().lower() != 'false'


def empty_ladder_handoff(
    reason: str, *, recovery_enabled: bool, disposition_enabled: bool, safety_enabled: bool
) -> bool:
    """The empty ladder's closed handoff disposition for one worker reason.

    The GPU worker evaluates this twice per empty unit — when selecting the
    terminal ``RecoveryWork`` handoff at the assemble_words boundary, and when
    deciding whether a skipped retry keeps raw custody (hold) or settles
    through the same handoff. The two boundaries historically re-implemented
    the identical expression inline; any drift between them misroutes a unit
    to the wrong ladder rung (held forever, retried blind on byte-identical
    audio, or terminally quarantined with the recovery handoff it was
    entitled to). Both call sites now share this one predicate.

    ``safety_enabled`` dominates: with the ship-on safety net on, both family
    reasons always ride the handoff. Kill-switching the safety net restores
    the pre-safety behavior exactly as each boundary answered before the
    extraction: ``empty_asr`` rides when either the recovery or the
    disposition flag is on (the reason sits in both arms), while
    ``no_owned_words`` rides on the disposition flag alone. Flags are
    arguments, not reads: callers evaluate them at the call boundary
    (``config`` policy stays read-per-call), so this stays pure and the flag
    matrix is testable without environment surgery.
    """
    empty_asr = reason == 'empty_asr'
    empty_family = reason in {'empty_asr', 'no_owned_words'}
    return (empty_asr and (recovery_enabled or safety_enabled)) or (
        empty_family and (disposition_enabled or safety_enabled)
    )


def terminal_empty_allowed(spans) -> bool:
    # A recognizer returning blanks cannot establish that VAD-positive audio is
    # disposable, including sub-second speech. Strict-VAD silence is separate.
    return not safety_net_enabled() or not spans
