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
        if signals.get('concrete_deliverable') and _capture_confidence(signals) >= MINIMUM_CAPTURE_CONFIDENCE:
            return CapturePolicyResult('auto_accept_silent', 'none')
        # Clear commitments that fail deliverable or confidence stay quiet pending review.
        return CapturePolicyResult('pending_candidate', 'none')
    if signals.get('direct_request') or signals.get('inferred_next_step'):
        return CapturePolicyResult('pending_candidate', 'none')
    return CapturePolicyResult('ignore', 'none')


__all__ = ['CapturePolicyResult', 'MINIMUM_CAPTURE_CONFIDENCE', 'run_capture_policy']
