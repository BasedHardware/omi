"""Deterministic shared capture policy used by every extraction surface."""

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
    if signals.get('public_broadcast') and not signals.get('direct_mention'):
        return CapturePolicyResult('ignore', 'none')
    if signals.get('explicit_command'):
        return CapturePolicyResult('create_direct', 'invoking_surface_only')
    if signals.get('clear_commitment') and signals.get('owner') == 'user':
        if signals.get('concrete_deliverable') is not True:
            return CapturePolicyResult('ignore', 'none')
        if _meets_user_capture_floor(signals):
            return CapturePolicyResult('auto_accept_silent', 'none')
        # A concrete first-person commitment may remain in the canonical sidecar at low confidence,
        # but product projections apply the same confidence floors before showing it.
        return CapturePolicyResult('pending_candidate', 'none')
    if signals.get('direct_request') and _meets_user_capture_floor(signals):
        return CapturePolicyResult('pending_candidate', 'none')
    # Inferred work has no weaker path than a directly addressed request. This deliberately rejects
    # vague, unowned, or low-confidence model suggestions before they become Candidate noise.
    if signals.get('inferred_next_step') and _meets_user_capture_floor(signals):
        return CapturePolicyResult('pending_candidate', 'none')
    return CapturePolicyResult('ignore', 'none')


__all__ = ['CapturePolicyResult', 'MINIMUM_CAPTURE_CONFIDENCE', 'run_capture_policy']
