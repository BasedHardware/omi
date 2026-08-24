"""Fail-closed first-open policy for just-in-time conversation processing.

This module is intentionally a pure policy seam.  The rollout authority supplies
``feature_enabled``; this file does not read PostHog, Firebase, or client-provided
enrolment state.  That keeps the decision testable and prevents a stale client
configuration from turning an optimization into a data-loss path.

When the policy is enabled, the capture path may write cheap summary/index
projections, but expensive derived work (folder assignment, goal progress, and
app fan-out) is owed to the first-open worker.  The existing processing path
remains the fallback when the policy is disabled or cannot identify a supported
source/tier.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class FirstOpenClientTier(str, Enum):
    """Supported rollout cohorts; values are wire-stable and content-free."""

    FREE = "free"
    PAID = "paid"
    BYOK = "byok"
    MOBILE = "mobile"
    DESKTOP = "desktop"


class FirstOpenOutcome(str, Enum):
    """The result of one idempotent first-open state transition."""

    CLAIMED = "claimed"
    ALREADY_IN_FLIGHT = "already_in_flight"
    ALREADY_COMPLETE = "already_complete"
    RETRY_READY = "retry_ready"
    INVALID = "invalid"


class FirstOpenState(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    COMPLETE = "complete"


@dataclass(frozen=True)
class FirstOpenPlan:
    """One server-owned processing decision for a captured conversation."""

    enabled: bool
    client_tier: FirstOpenClientTier | None
    source: str
    summary_eager: bool
    retrieval_index_eager: bool
    folder_assignment_on_first_open: bool
    goal_progress_on_first_open: bool
    app_fanout_on_first_open: bool
    reason: Literal[
        "rollout_disabled",
        "kill_switch",
        "unsupported_tier",
        "unsupported_source",
        "enabled",
    ]

    @property
    def defer_derived_work(self) -> bool:
        return (
            self.enabled
            and self.folder_assignment_on_first_open
            and self.goal_progress_on_first_open
            and self.app_fanout_on_first_open
        )


@dataclass(frozen=True)
class FirstOpenStateTransition:
    outcome: FirstOpenOutcome
    state: FirstOpenState
    attempt: int


SUPPORTED_SOURCES = frozenset({"desktop", "mobile", "phone", "omi", "web", "windows"})


def resolve_first_open_plan(
    *,
    feature_enabled: bool,
    client_tier: FirstOpenClientTier | str | None,
    source: str | None,
    kill_switch: bool = False,
) -> FirstOpenPlan:
    """Resolve an all-or-nothing first-open plan without inspecting content.

    The two booleans are deliberately explicit inputs from the backend rollout
    authority.  A kill switch or unknown cohort never partially defers work,
    because a partial plan can strand a downstream consumer expecting a derived
    field that was intentionally not produced at capture time.
    """

    normalized_source = (source or "").strip().lower()
    try:
        normalized_tier = (
            client_tier
            if isinstance(client_tier, FirstOpenClientTier)
            else FirstOpenClientTier(str(client_tier).strip().lower()) if client_tier is not None else None
        )
    except (TypeError, ValueError):
        normalized_tier = None

    if kill_switch:
        return _disabled_plan(normalized_tier, normalized_source, reason="kill_switch")
    if not feature_enabled:
        return _disabled_plan(normalized_tier, normalized_source, reason="rollout_disabled")
    if normalized_tier is None:
        return _disabled_plan(None, normalized_source, reason="unsupported_tier")
    if normalized_source not in SUPPORTED_SOURCES:
        return _disabled_plan(normalized_tier, normalized_source, reason="unsupported_source")

    return FirstOpenPlan(
        enabled=True,
        client_tier=normalized_tier,
        source=normalized_source,
        # These two projections are deliberately eager so lists and cheap
        # retrieval remain useful before the expensive first-open work runs.
        summary_eager=True,
        retrieval_index_eager=True,
        folder_assignment_on_first_open=True,
        goal_progress_on_first_open=True,
        app_fanout_on_first_open=True,
        reason="enabled",
    )


def _disabled_plan(
    client_tier: FirstOpenClientTier | None,
    source: str,
    *,
    reason: Literal["rollout_disabled", "kill_switch", "unsupported_tier", "unsupported_source"],
) -> FirstOpenPlan:
    return FirstOpenPlan(
        enabled=False,
        client_tier=client_tier,
        source=source,
        summary_eager=False,
        retrieval_index_eager=False,
        folder_assignment_on_first_open=False,
        goal_progress_on_first_open=False,
        app_fanout_on_first_open=False,
        reason=reason,
    )


def transition_first_open(
    state: FirstOpenState | str,
    *,
    event: Literal["open", "succeeded", "failed"],
    attempt: int = 0,
) -> FirstOpenStateTransition:
    """Apply one retry-safe transition for a durable first-open claim.

    ``open`` claims only ``pending`` work.  Repeated opens while work is running
    are no-ops, while a failed attempt returns to ``pending`` so a later open can
    retry.  Attempts are bounded to a non-negative integer but are not capped:
    the durable worker/lease owns operational retry limits, not this projection.
    """

    try:
        current = state if isinstance(state, FirstOpenState) else FirstOpenState(str(state))
    except (TypeError, ValueError):
        return FirstOpenStateTransition(FirstOpenOutcome.INVALID, FirstOpenState.PENDING, 0)
    safe_attempt = attempt if type(attempt) is int and attempt >= 0 else 0

    if event == "open":
        if current is FirstOpenState.PENDING:
            return FirstOpenStateTransition(FirstOpenOutcome.CLAIMED, FirstOpenState.IN_FLIGHT, safe_attempt + 1)
        if current is FirstOpenState.IN_FLIGHT:
            return FirstOpenStateTransition(FirstOpenOutcome.ALREADY_IN_FLIGHT, current, safe_attempt)
        return FirstOpenStateTransition(FirstOpenOutcome.ALREADY_COMPLETE, current, safe_attempt)

    if event == "succeeded":
        if current is FirstOpenState.IN_FLIGHT:
            return FirstOpenStateTransition(FirstOpenOutcome.ALREADY_COMPLETE, FirstOpenState.COMPLETE, safe_attempt)
        return FirstOpenStateTransition(FirstOpenOutcome.INVALID, current, safe_attempt)

    if event == "failed":
        if current is FirstOpenState.IN_FLIGHT:
            return FirstOpenStateTransition(FirstOpenOutcome.RETRY_READY, FirstOpenState.PENDING, safe_attempt)
        return FirstOpenStateTransition(FirstOpenOutcome.INVALID, current, safe_attempt)

    return FirstOpenStateTransition(FirstOpenOutcome.INVALID, current, safe_attempt)


__all__ = [
    "FirstOpenClientTier",
    "FirstOpenOutcome",
    "FirstOpenPlan",
    "FirstOpenState",
    "FirstOpenStateTransition",
    "SUPPORTED_SOURCES",
    "resolve_first_open_plan",
    "transition_first_open",
]
