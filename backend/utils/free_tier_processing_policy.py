"""Fail-closed free-tier processing policy for the conversation coordinator.

When ``FREE_TIER_LOCAL_PROCESSING`` is on, the coordinator asks this module
whether a desktop conversation may spend managed compute. The policy is pure:
it never raises, never looks up a plan itself, and consults S1's ``Decision``
exactly once via the injected ``decision_for`` callable.

``decision_for`` is ``(feature: str) -> Decision``. The coordinator closes
funding-owner resolution inside that callable so any exception in owner
resolution or authorization is caught here and becomes
``deterministic_minimum`` / ``policy_unavailable``. This module imports
``Decision`` and ``DECISION_REASONS`` from ``utils.managed_compute`` and does
not call ``authorize_managed_compute``.

``defer_first_open`` is kept on the mode enum for the entrypoint matrix's
legacy column. With the flag on this policy never produces it: identified
basic is terminal (projection or deterministic minimum), not first-open luna.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from utils.managed_compute import DECISION_REASONS, Decision

logger = logging.getLogger(__name__)

# Boolean rollout flag only. Plan quotas and allowlists never come from the env.
FREE_TIER_LOCAL_PROCESSING = os.getenv('FREE_TIER_LOCAL_PROCESSING', 'false').lower() == 'true'

# Coordinator structure spend: ``_get_structured`` → ``get_conversation_notes`` /
# ``get_transcript_structure`` → ``get_llm('conv_structure')``. Provider: openai.
STRUCTURE_FEATURE = 'conv_structure'

DESKTOP_SOURCE = 'desktop'

ProcessingMode = Literal['process_normally', 'defer_first_open', 'store_projection', 'deterministic_minimum']

# S6-owned reasons (not an S1 Decision.reason). ``plan_identification_fail_open``
# is the remapped form of S1's ``plan_unknown_fail_open``.
_S6_PROCESSING_REASONS: frozenset[str] = frozenset(
    {
        'non_desktop_source',
        'plan_identification_fail_open',
        'policy_unavailable',
    }
)

# Closed vocabulary: S6-specific reasons ∪ S1's DECISION_REASONS (imported, not copied).
PROCESSING_REASONS: frozenset[str] = _S6_PROCESSING_REASONS | DECISION_REASONS

_IDENTIFICATION_FAIL_OPEN = 'plan_unknown_fail_open'
_BASIC_PLAN = 'basic'

DecisionFor = Callable[[str], Decision]


def free_tier_local_processing_enabled() -> bool:
    """Read the rollout flag. Tests monkeypatch this (or the module constant)."""
    return FREE_TIER_LOCAL_PROCESSING


@dataclass(frozen=True)
class FreeTierProcessingPlan:
    """One server-owned processing decision for a captured conversation."""

    mode: ProcessingMode
    reason: str
    decision: Decision | None

    @property
    def managed_calls_allowed(self) -> bool:
        return self.mode == 'process_normally'


def resolve_free_tier_processing_plan(
    *,
    uid: str,
    source: str | None,
    force_process: bool,
    is_reprocess: bool,
    has_projection: bool,
    decision_for: DecisionFor,
) -> FreeTierProcessingPlan:
    """Resolve how the coordinator should process this conversation.

    Flag-agnostic (pure). The coordinator reads ``FREE_TIER_LOCAL_PROCESSING``
    and does not call this when the flag is off.

    ``decision_for`` is called once, inside this function's exception guard,
    with ``STRUCTURE_FEATURE``. The coordinator closes funding-owner
    resolution inside that callable ('byok' if the request carries a
    validated key for the feature's provider, else 'omi') so a raise there
    becomes ``policy_unavailable`` rather than escaping to luna.

    ``force_process`` / ``is_reprocess`` do not rescue identified-basic: a
    basic user's first-open or reprocess is still a managed call and is
    denied the same way. ``uid`` is part of the coordinator contract; plan
    identity comes only from the injected Decision.
    """
    try:
        return _resolve(
            uid=uid,
            source=source,
            force_process=force_process,
            is_reprocess=is_reprocess,
            has_projection=has_projection,
            decision_for=decision_for,
        )
    except Exception as exc:
        logger.warning('free-tier processing policy unavailable: %s', type(exc).__name__)
        return FreeTierProcessingPlan(
            mode='deterministic_minimum',
            reason='policy_unavailable',
            decision=None,
        )


def _resolve(
    *,
    uid: str,
    source: str | None,
    force_process: bool,
    is_reprocess: bool,
    has_projection: bool,
    decision_for: DecisionFor,
) -> FreeTierProcessingPlan:
    # Signature is the coordinator contract. These inputs do not change the
    # flag-on answer: uid is closed over by decision_for, and force/reprocess
    # must not rescue an identified-basic deny (§1.2).
    _ = (uid, force_process, is_reprocess)

    if not _is_desktop_source(source):
        return FreeTierProcessingPlan(
            mode='process_normally',
            reason='non_desktop_source',
            decision=None,
        )

    decision = decision_for(STRUCTURE_FEATURE)
    if decision.allowed and decision.reason == _IDENTIFICATION_FAIL_OPEN:
        return FreeTierProcessingPlan(
            mode='process_normally',
            reason='plan_identification_fail_open',
            decision=decision,
        )
    if decision.allowed:
        return FreeTierProcessingPlan(
            mode='process_normally',
            reason=decision.reason,
            decision=decision,
        )
    if decision.plan_resolved and decision.plan == _BASIC_PLAN:
        mode: ProcessingMode = 'store_projection' if has_projection else 'deterministic_minimum'
        return FreeTierProcessingPlan(
            mode=mode,
            reason=decision.reason,
            decision=decision,
        )
    return FreeTierProcessingPlan(
        mode='deterministic_minimum',
        reason=decision.reason,
        decision=decision,
    )


def is_desktop_source(source: str | None) -> bool:
    """True for the one source that can carry a client projection today.

    S3 reads this to decide whether the §1.7 minimum is ``local_pending`` (a
    capable client is expected to deliver) or ``none`` (nothing is coming), so
    the two answers cannot drift from the policy's own source test.
    """
    if source is None:
        return False
    return str(source).strip().lower() == DESKTOP_SOURCE


# Historic private name; kept so the policy's own call sites read unchanged.
_is_desktop_source = is_desktop_source


def minimum_processing_state(source: Any, *, has_projection: bool) -> str | None:
    """Why a conversation's ``structured`` is the §1.7 deterministic minimum.

    Returns ``ConversationProcessingState``'s raw values (the model coerces) so
    this module keeps importing nothing but the policy's own vocabulary.

    Takes projection *presence* as a bool, never the projection itself: the
    answer depends only on whether one exists, so this stays outside the
    display-only trust boundary and the pinned reference set does not have to
    grow to admit it.

    A projection already in hand means nothing is pending, so the field stays
    absent. Otherwise the answer is whether a capable client is expected to
    deliver one, which today is exactly the desktop source — read through this
    module's own source test so the two cannot drift.

    This is not re-derived when a projection arrives later: the existing-row
    stamp writes ``client_processing`` alone (its single-key payload is pinned
    by the trust-boundary test), so a projected conversation can still read
    ``local_pending``. Clients resolve that by checking ``client_processing``
    first; ``ConversationProcessingState``'s docstring is the contract.
    """
    if has_projection:
        return None
    # ``source`` arrives as either the raw string or a ``ConversationSource``;
    # unwrap here so ``str(enum)`` never becomes the literal
    # ``'conversationsource.desktop'`` and silently answer ``none``.
    raw_source = getattr(source, 'value', source)
    return 'local_pending' if is_desktop_source(raw_source) else 'none'


__all__ = [
    'DESKTOP_SOURCE',
    'FREE_TIER_LOCAL_PROCESSING',
    'PROCESSING_REASONS',
    'STRUCTURE_FEATURE',
    'FreeTierProcessingPlan',
    'ProcessingMode',
    'free_tier_local_processing_enabled',
    'is_desktop_source',
    'minimum_processing_state',
    'resolve_free_tier_processing_plan',
]
