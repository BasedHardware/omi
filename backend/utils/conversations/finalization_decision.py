"""Pure, deterministic decisions for a conversation finalization generation.

The lifecycle service is the runtime owner.  This reducer deliberately has no
Firestore, clock, or queue dependency so its ordering contract can be fuzzed
before the runtime callers are migrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LifecyclePhase(str, Enum):
    IN_PROGRESS = 'in_progress'
    PROCESSING = 'processing'
    MERGING = 'merging'
    COMPLETED = 'completed'
    FAILED = 'failed'
    DISCARDED = 'discarded'


class FinalizationEvent(str, Enum):
    DISCONNECT = 'disconnect'
    FINALIZE = 'finalize'
    REPROCESS = 'reprocess'
    MERGE = 'merge'
    MERGE_COMPLETED = 'merge_completed'
    PROCESSING_COMPLETED = 'processing_completed'
    DISCARD = 'discard'
    RESTART = 'restart'


TERMINAL_PHASES = frozenset({LifecyclePhase.COMPLETED, LifecyclePhase.FAILED, LifecyclePhase.DISCARDED})


@dataclass(frozen=True)
class FinalizationDecisionState:
    """The complete reducer state for one immutable lifecycle generation."""

    phase: LifecyclePhase = LifecyclePhase.IN_PROGRESS
    terminal_outcome: LifecyclePhase | None = None
    emitted_fanout_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_terminal(self) -> bool:
        return self.phase in TERMINAL_PHASES


@dataclass(frozen=True)
class FinalizationDecision:
    state: FinalizationDecisionState
    fanout_key: str | None = None
    reason: str = 'accepted'


def _terminal(state: FinalizationDecisionState, phase: LifecyclePhase) -> FinalizationDecisionState:
    if state.terminal_outcome is not None:
        return state
    return FinalizationDecisionState(
        phase=phase,
        terminal_outcome=phase,
        emitted_fanout_keys=state.emitted_fanout_keys,
    )


def _admit_finalization(
    state: FinalizationDecisionState,
    conversation_id: str,
    fanout_key: str | None,
) -> FinalizationDecision:
    key = fanout_key or f'conversation:{conversation_id}:finalization'
    if key in state.emitted_fanout_keys:
        return FinalizationDecision(state=state, reason='duplicate_finalization')
    return FinalizationDecision(
        state=FinalizationDecisionState(
            phase=LifecyclePhase.PROCESSING,
            emitted_fanout_keys=state.emitted_fanout_keys | {key},
        ),
        fanout_key=key,
    )


def decide_finalization(
    state: FinalizationDecisionState,
    event: FinalizationEvent,
    *,
    conversation_id: str,
    fanout_key: str | None = None,
) -> FinalizationDecision:
    """Return the one allowed transition and, at most, one durable fanout key.

    A ``FinalizationDecisionState`` represents exactly one lifecycle
    generation. Reprocessing therefore needs a new generation rather than an
    escape hatch out of a terminal state. This is what lets duplicate events
    and reclaimed workers share a single idempotency key.
    """
    if state.is_terminal:
        return FinalizationDecision(state=state, reason='terminal')

    if event in {FinalizationEvent.DISCONNECT, FinalizationEvent.FINALIZE}:
        if state.phase == LifecyclePhase.IN_PROGRESS:
            return _admit_finalization(state, conversation_id, fanout_key)
        return FinalizationDecision(state=state, reason='already_finalizing')

    if event == FinalizationEvent.PROCESSING_COMPLETED and state.phase == LifecyclePhase.PROCESSING:
        return FinalizationDecision(state=_terminal(state, LifecyclePhase.COMPLETED))

    if event == FinalizationEvent.DISCARD and state.phase in {
        LifecyclePhase.IN_PROGRESS,
        LifecyclePhase.PROCESSING,
        LifecyclePhase.MERGING,
    }:
        return FinalizationDecision(state=_terminal(state, LifecyclePhase.DISCARDED))

    if event == FinalizationEvent.MERGE and state.phase == LifecyclePhase.IN_PROGRESS:
        return FinalizationDecision(
            state=FinalizationDecisionState(
                phase=LifecyclePhase.MERGING,
                emitted_fanout_keys=state.emitted_fanout_keys,
            )
        )

    if event == FinalizationEvent.MERGE_COMPLETED and state.phase == LifecyclePhase.MERGING:
        return FinalizationDecision(state=_terminal(state, LifecyclePhase.COMPLETED))

    if event == FinalizationEvent.RESTART:
        return FinalizationDecision(state=state, reason='restart_replays_state')

    if event == FinalizationEvent.REPROCESS:
        return FinalizationDecision(state=state, reason='reprocess_requires_new_generation')

    return FinalizationDecision(state=state, reason='invalid_transition')
