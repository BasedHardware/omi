"""Seeded ordering contract for durable listen finalization (#9687)."""

from __future__ import annotations

import os
import random

import pytest

from utils.conversations.finalization_decision import (
    FinalizationDecisionState,
    FinalizationEvent,
    LifecyclePhase,
    decide_finalization,
)


def _fuzz_seed() -> int:
    raw_seed = os.getenv('OMI_FUZZ_SEED', '9687')
    try:
        return int(raw_seed)
    except ValueError as error:
        raise AssertionError('OMI_FUZZ_SEED must be an integer') from error


def _run_sequence(events: list[FinalizationEvent]) -> FinalizationDecisionState:
    state = FinalizationDecisionState()
    emitted_keys: set[str] = set()
    terminal_outcomes: list[LifecyclePhase] = []
    for event in events:
        previous = state
        decision = decide_finalization(state, event, conversation_id='conversation-1')
        state = decision.state
        if decision.fanout_key:
            assert decision.fanout_key not in emitted_keys
            emitted_keys.add(decision.fanout_key)
        if previous.terminal_outcome is None and state.terminal_outcome is not None:
            terminal_outcomes.append(state.terminal_outcome)
        if previous.is_terminal:
            assert state == previous

    assert len(terminal_outcomes) <= 1
    assert len(emitted_keys) <= 1
    assert state.terminal_outcome in {None, LifecyclePhase.COMPLETED, LifecyclePhase.FAILED, LifecyclePhase.DISCARDED}
    return state


@pytest.mark.parametrize(
    'events, expected_phase',
    [
        (
            [FinalizationEvent.DISCONNECT, FinalizationEvent.FINALIZE, FinalizationEvent.PROCESSING_COMPLETED],
            LifecyclePhase.COMPLETED,
        ),
        (
            [FinalizationEvent.FINALIZE, FinalizationEvent.DISCONNECT, FinalizationEvent.PROCESSING_COMPLETED],
            LifecyclePhase.COMPLETED,
        ),
        (
            [FinalizationEvent.FINALIZE, FinalizationEvent.REPROCESS, FinalizationEvent.PROCESSING_COMPLETED],
            LifecyclePhase.COMPLETED,
        ),
        (
            [FinalizationEvent.FINALIZE, FinalizationEvent.MERGE, FinalizationEvent.PROCESSING_COMPLETED],
            LifecyclePhase.COMPLETED,
        ),
        (
            [FinalizationEvent.RESTART, FinalizationEvent.FINALIZE, FinalizationEvent.RESTART],
            LifecyclePhase.PROCESSING,
        ),
    ],
    ids=[
        'disconnect-before-final',
        'final-before-disconnect',
        'concurrent-finalize-vs-reprocess',
        'merge-during-processing',
        'restart-mid-finalization',
    ],
)
def test_named_finalization_ordering_regressions(events, expected_phase):
    assert _run_sequence(events).phase == expected_phase


def test_duplicate_finalization_emits_one_fanout_key():
    state = _run_sequence(
        [
            FinalizationEvent.FINALIZE,
            FinalizationEvent.FINALIZE,
            FinalizationEvent.DISCONNECT,
            FinalizationEvent.PROCESSING_COMPLETED,
            FinalizationEvent.FINALIZE,
        ]
    )
    assert state.phase == LifecyclePhase.COMPLETED


def test_seeded_finalization_fuzzer_preserves_terminal_and_fanout_invariants():
    """Explore legal source events under a reproducible PR seed/corpus."""
    rng = random.Random(_fuzz_seed())
    corpus = [
        [FinalizationEvent.DISCONNECT, FinalizationEvent.FINALIZE, FinalizationEvent.PROCESSING_COMPLETED],
        [FinalizationEvent.FINALIZE, FinalizationEvent.RESTART, FinalizationEvent.FINALIZE],
        [FinalizationEvent.MERGE, FinalizationEvent.MERGE_COMPLETED, FinalizationEvent.REPROCESS],
        [FinalizationEvent.FINALIZE, FinalizationEvent.DISCARD, FinalizationEvent.PROCESSING_COMPLETED],
    ]
    source_events = tuple(FinalizationEvent)
    for sequence in corpus:
        _run_sequence(sequence)
    for _ in range(250):
        _run_sequence([rng.choice(source_events) for _ in range(rng.randint(1, 32))])
