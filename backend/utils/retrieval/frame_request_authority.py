"""Per-account rollout authority for just-in-time frame requests.

The queue is intentionally fail-closed.  Deployments may replace the adapter
with the product rollout service, while unit tests can inject a deterministic
decision.  There is deliberately no environment-wide opt-in here: a client
can never enrol itself by sending a header or setting a process variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FrameRequestAuthorityDecision:
    enabled: bool
    account_generation: int | None = None
    kill_switch: bool = False


class FrameRequestAuthority(Protocol):
    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        """Return the server-owned decision for one authenticated account."""


class DisabledFrameRequestAuthority:
    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        return FrameRequestAuthorityDecision(enabled=False)


_authority: FrameRequestAuthority = DisabledFrameRequestAuthority()


def get_frame_request_authority() -> FrameRequestAuthority:
    return _authority


def set_frame_request_authority_for_tests(authority: FrameRequestAuthority) -> None:
    """Inject a rollout seam in tests or an integration composition root."""

    global _authority
    _authority = authority


def decision_for(uid: str) -> FrameRequestAuthorityDecision:
    if not uid.strip():
        return FrameRequestAuthorityDecision(enabled=False)
    decision = get_frame_request_authority().decide(uid.strip())
    if decision.kill_switch or not decision.enabled or decision.account_generation is None:
        return FrameRequestAuthorityDecision(
            enabled=False, account_generation=decision.account_generation, kill_switch=True
        )
    return decision


def authorize(uid: str, account_generation: int) -> FrameRequestAuthorityDecision:
    decision = decision_for(uid)
    if not decision.enabled or decision.account_generation != account_generation:
        raise PermissionError("frame request rollout or account generation mismatch")
    return decision


__all__ = [
    "DisabledFrameRequestAuthority",
    "FrameRequestAuthority",
    "FrameRequestAuthorityDecision",
    "authorize",
    "decision_for",
    "get_frame_request_authority",
    "set_frame_request_authority_for_tests",
]
