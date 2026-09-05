"""Decision 9, first half: stop SERVER-side memory formation for basic.

Spec: `10-backend-plumbing.md` §1.8. Flag: `FREE_TIER_MEMORY_SUPPRESSION`
(`50-rollout-and-verification.md`) — its own flag, not S6's, because turning
off the deterministic-minimum store must not silently restart managed memory
formation, and vice versa. No flag gates two workstreams.

The module is pure and never raises: it consults S1's ``Decision`` exactly once
through an injected ``decision_for`` and returns a verdict. Callers read the
flag; this module does not, so a test can exercise the decision table without
touching the environment.

**What it never does is delete.** A basic user keeps every memory formed while
they were paid, and keeps reading them. Only *formation* stops. Downgrade is
not a data event.

**The asymmetry worth knowing.** A conversation denied the managed summary still
exists and still shows a title — the user can see what happened. A memory that
was never formed is invisible and, per the flag's own rollout note, is never
backfilled. So suppression is a permanent, silent loss when it fires on the
wrong account, which is why an *unidentified* plan fails open here exactly as it
does in `free_tier_processing_policy`: we decline to punish a user we could not
identify. A broken authorization path still fails closed, because the
alternative is spending on a provider we could not authorize.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from utils.managed_compute import Decision, managed_compute_decision_for

logger = logging.getLogger(__name__)

# Boolean rollout flag only. Plan quotas and allowlists never come from the env.
FREE_TIER_MEMORY_SUPPRESSION = os.getenv('FREE_TIER_MEMORY_SUPPRESSION', 'false').lower() == 'true'

# Eager per-conversation extraction spends `get_llm('memories')`
# (`utils/llm/memories.py`). That literal is the feature this gate authorizes.
MEMORY_FORMATION_FEATURE = 'memories'

_POLICY_UNAVAILABLE = 'policy_unavailable'

DecisionFor = Callable[[str], Decision]


def free_tier_memory_suppression_enabled() -> bool:
    """Read the rollout flag. Tests monkeypatch this (or the module constant)."""
    return FREE_TIER_MEMORY_SUPPRESSION


@dataclass(frozen=True)
class MemoryFormationVerdict:
    """Whether managed memory formation may run for one account."""

    allowed: bool
    reason: str
    decision: Decision | None

    @property
    def suppressed(self) -> bool:
        return not self.allowed


def memory_formation_verdict(*, decision_for: DecisionFor) -> MemoryFormationVerdict:
    """May managed memory formation run for this account?

    Flag-agnostic (pure): the coordinator and the sweep each read
    ``free_tier_memory_suppression_enabled()`` and do not call this when the
    flag is off, so the flag-off path is byte-identical to today.

    ``decision_for`` closes over the uid and the funding owner, so a raising
    owner lookup is caught here and becomes ``policy_unavailable`` — suppressed
    — rather than escaping into finalization.
    """
    try:
        decision = decision_for(MEMORY_FORMATION_FEATURE)
    except Exception as exc:
        logger.warning('free-tier memory policy unavailable: %s', type(exc).__name__)
        return MemoryFormationVerdict(allowed=False, reason=_POLICY_UNAVAILABLE, decision=None)

    if decision.allowed:
        # Includes `plan_unknown_fail_open`: an account we could not identify
        # keeps forming memories. See the module docstring on why this one
        # fails open while a broken authorization path does not.
        return MemoryFormationVerdict(allowed=True, reason=decision.reason, decision=decision)

    return MemoryFormationVerdict(allowed=False, reason=decision.reason, decision=decision)


def managed_memory_formation_suppressed(uid: str, source: str) -> bool:
    """§1.8 producer gate: should this managed memory-formation producer skip?

    The one shared gate shape for the sibling producers the coordinator's
    extraction boundary does not cover (app-integration text, the twitter
    persona, the X connector — flip-review F-3). Read the rollout flag first
    so the flag-off path performs no lookups at all, then consult
    ``memory_formation_verdict`` through the one shared
    ``managed_compute_decision_for`` closure so BYOK keeps forming and a
    raising lookup is suppressed by the policy instead of escaping into a
    sync. Suppression is a skip, never a delete: memories formed while the
    user was paid stay.

    The coordinator (``process_conversation.extract_memories``) keeps its own
    copy of this shape at its boundary because its log carries the
    conversation id; every other producer funnels through here so the gate
    shape, logging, and fail-closed behavior cannot drift between them.
    """
    if not free_tier_memory_suppression_enabled():
        return False
    verdict = memory_formation_verdict(decision_for=managed_compute_decision_for(uid))
    if verdict.suppressed:
        logger.info(
            'memory extraction skipped: plan denies managed formation uid=%s source=%s reason=%s',
            uid,
            source,
            verdict.reason,
        )
        return True
    return False


__all__ = [
    'FREE_TIER_MEMORY_SUPPRESSION',
    'MEMORY_FORMATION_FEATURE',
    'MemoryFormationVerdict',
    'free_tier_memory_suppression_enabled',
    'managed_memory_formation_suppressed',
    'memory_formation_verdict',
]
