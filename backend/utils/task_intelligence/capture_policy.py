"""Deterministic shared capture policy used by every extraction surface.

INVARIANT I1: an automatically extracted task is NEVER written to the user's
task list. Every capture outcome that would create work is a proposal the user
must explicitly accept ("Add to Tasks"). There is deliberately no outcome here
meaning "write a task now" — surfaces that carry a real user gesture (manual
create, chat/MCP tool invocation, the developer API) do not run this policy.
"""

from dataclasses import dataclass
from typing import Any

# Shared with What Matters Now shortlist eligibility (recommendations.MINIMUM_CAPTURE_CONFIDENCE).
MINIMUM_CAPTURE_CONFIDENCE = 0.8


@dataclass(frozen=True)
class CapturePolicyResult:
    outcome: str
    interruption: str


def _capture_confidence(signals: dict[str, Any]) -> float:
    raw = signals.get('capture_confidence')
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


def _ownership_confidence(signals: dict[str, Any]) -> float:
    raw = signals.get('ownership_confidence')
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


def _meets_user_capture_floor(signals: dict[str, Any]) -> bool:
    return (
        signals.get('owner') == 'user'
        and signals.get('concrete_deliverable') is True
        and _capture_confidence(signals) >= MINIMUM_CAPTURE_CONFIDENCE
        and _ownership_confidence(signals) >= MINIMUM_CAPTURE_CONFIDENCE
    )


def run_capture_policy(signals: dict[str, Any]) -> CapturePolicyResult:
    if signals.get('already_done'):
        return CapturePolicyResult('propose_completion', 'inline_review')
    if signals.get('duplicate_of'):
        return CapturePolicyResult('propose_enrichment', 'none')
    if signals.get('refines_task'):
        return CapturePolicyResult('propose_update', 'none')
    # A spoken explicit command is not ambient channel noise. Evaluate it before
    # public_broadcast so the first producer of that signal cannot drop a command
    # that already cleared the extractor.
    if signals.get('explicit_command'):
        # A command heard in ambient audio is still a model's reading of speech,
        # not a user gesture against a surface. It proposes; it does not create.
        if _meets_user_capture_floor(signals):
            return CapturePolicyResult('pending_candidate', 'none')
        return CapturePolicyResult('ignore', 'none')
    if signals.get('public_broadcast') and not signals.get('direct_mention'):
        return CapturePolicyResult('ignore', 'none')
    # Every admitted kind below clears the same floor, because a proposal the
    # Suggested surface will not show is indistinguishable from a dropped one and
    # merely accumulates. Admit it and the user sees it, or ignore it outright.
    if signals.get('clear_commitment') and signals.get('owner') == 'user':
        if signals.get('concrete_deliverable') is not True:
            return CapturePolicyResult('ignore', 'none')
        # A concrete first-person commitment is the strongest signal this policy has, and it
        # still only earns a suggestion. Confidence decides whether the proposal is worth
        # surfacing, never whether it may bypass the user (I1).
        if _meets_user_capture_floor(signals):
            return CapturePolicyResult('pending_candidate', 'none')
        return CapturePolicyResult('ignore', 'none')
    if signals.get('direct_request') and _meets_user_capture_floor(signals):
        return CapturePolicyResult('pending_candidate', 'none')
    # Inferred work has no weaker path than a directly addressed request. This deliberately rejects
    # vague, unowned, or low-confidence model suggestions before they become Candidate noise.
    if signals.get('inferred_next_step') and _meets_user_capture_floor(signals):
        return CapturePolicyResult('pending_candidate', 'none')
    return CapturePolicyResult('ignore', 'none')


__all__ = ['CapturePolicyResult', 'MINIMUM_CAPTURE_CONFIDENCE', 'run_capture_policy']
