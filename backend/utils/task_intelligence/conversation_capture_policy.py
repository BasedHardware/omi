"""Pure action-item capture scoring for conversation extraction.

This module is deliberately free of database and persistence imports so production
capture and hermetic evaluation use one supported policy boundary.
"""

from dataclasses import dataclass
from typing import Any

from models.action_item import TaskOwner
from utils.llm.wake_word_adjudication import WakeWordAdjudication
from utils.task_intelligence.backend_capture import BackendCaptureSignals
from utils.task_intelligence.capture_policy import CapturePolicyResult, run_capture_policy

_ACCEPTED_EXPLICIT_VERDICTS = frozenset({'task_command', 'memory_command'})


@dataclass(frozen=True)
class WakeWordCaptureGate:
    matched_segment_ids: frozenset[str]
    adjudication: WakeWordAdjudication


@dataclass(frozen=True)
class ActionItemCapturePolicyEvaluation:
    signals: BackendCaptureSignals
    policy: CapturePolicyResult


def _concrete_deliverable(action_item: Any) -> bool:
    """Fail closed: only treat as concrete when extraction supplies an explicit True."""

    return getattr(action_item, 'concrete_deliverable', None) is True


def capture_signals_for_action_item(
    action_item: Any,
    wake_word_gate: WakeWordCaptureGate | None = None,
) -> BackendCaptureSignals:
    """Translate one extracted action item into the shared capture-policy signals."""

    capture_kind = getattr(action_item, 'capture_kind', None)
    raw_candidate_action = getattr(action_item, 'candidate_action', None)
    candidate_action = raw_candidate_action if isinstance(raw_candidate_action, str) else 'create'
    raw_target_task_id = getattr(action_item, 'target_task_id', None)
    target_task_id = raw_target_task_id if isinstance(raw_target_task_id, str) else None
    raw_capture_confidence = getattr(action_item, 'capture_confidence', None)
    capture_confidence = float(raw_capture_confidence) if isinstance(raw_capture_confidence, (int, float)) else 0.5
    raw_ownership_confidence = getattr(action_item, 'ownership_confidence', None)
    ownership_confidence = (
        float(raw_ownership_confidence) if isinstance(raw_ownership_confidence, (int, float)) else 0.5
    )
    source_segment_ids = set(getattr(action_item, 'source_segment_ids', None) or [])
    if wake_word_gate is not None and source_segment_ids.intersection(wake_word_gate.matched_segment_ids):
        relevant_verdicts = [
            invocation.verdict
            for invocation in wake_word_gate.adjudication.invocations
            if source_segment_ids.intersection(invocation.segment_ids)
        ]
        if capture_kind == 'explicit_command':
            # Only an explicit adverse verdict demotes. An empty adjudication
            # (timeout, provider blip, or no overlapping invocation) leaves the
            # extractor's explicit_command intact.
            if any(verdict not in _ACCEPTED_EXPLICIT_VERDICTS for verdict in relevant_verdicts):
                capture_kind = 'direct_request'
        elif relevant_verdicts and all(verdict == 'task_command' for verdict in relevant_verdicts):
            capture_kind = 'explicit_command'
    return BackendCaptureSignals(
        explicit_command=capture_kind == 'explicit_command',
        clear_commitment=capture_kind == 'clear_commitment',
        direct_request=capture_kind == 'direct_request' or capture_kind is None,
        inferred_next_step=capture_kind == 'inferred_next_step',
        concrete_deliverable=_concrete_deliverable(action_item),
        owner=getattr(action_item, 'capture_owner', None) or TaskOwner.unknown,
        already_done=candidate_action == 'complete',
        refines_task=target_task_id if candidate_action in {'update', 'complete'} else None,
        capture_confidence=capture_confidence,
        ownership_confidence=ownership_confidence,
    )


def evaluate_action_item_capture_policy(
    action_item: Any,
    wake_word_gate: WakeWordCaptureGate | None = None,
) -> ActionItemCapturePolicyEvaluation:
    """Score one extracted item through the exact production signal and policy path."""

    signals = capture_signals_for_action_item(action_item, wake_word_gate)
    return ActionItemCapturePolicyEvaluation(
        signals=signals,
        policy=run_capture_policy(signals.policy_signals()),
    )


__all__ = [
    'ActionItemCapturePolicyEvaluation',
    'WakeWordCaptureGate',
    'capture_signals_for_action_item',
    'evaluate_action_item_capture_policy',
]
