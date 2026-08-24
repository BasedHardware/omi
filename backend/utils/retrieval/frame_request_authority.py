"""Per-account rollout authority for just-in-time frame requests.

The queue is intentionally fail-closed.  Deployments may replace the adapter
with the product rollout service, while unit tests can inject a deterministic
decision.  There is deliberately no environment-wide opt-in here: a client
can never enrol itself by sending a header or setting a process variable.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

from database.account_cutover import get_account_cutover_record
from utils.integration_telemetry import get_posthog_client_for_decisions


@dataclass(frozen=True)
class FrameRequestAuthorityDecision:
    enabled: bool
    account_generation: int | None = None
    kill_switch: bool = False


class FrameRequestAuthority(Protocol):
    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        """Return the server-owned decision for one authenticated account."""

        ...


class DisabledFrameRequestAuthority:
    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        return FrameRequestAuthorityDecision(enabled=False)


class PostHogFrameRequestAuthority:
    """Resolve cohort and kill-switch flags from the server-side PostHog client."""

    def __init__(self, *, cohort_flag: str | None = None, kill_switch_flag: str | None = None) -> None:
        self.cohort_flag = cohort_flag or os.getenv("FRAME_REQUEST_POSTHOG_COHORT_FLAG", "jit-frame-requests-cohort")
        self.kill_switch_flag = kill_switch_flag or os.getenv(
            "FRAME_REQUEST_POSTHOG_KILL_SWITCH", "jit-frame-requests-kill-switch"
        )

    @staticmethod
    def _enabled(value: object) -> bool:
        return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "on", "enabled"})

    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        try:
            client = get_posthog_client_for_decisions()
            if client is None:
                return FrameRequestAuthorityDecision(enabled=False)
            kill_switch = self._enabled(client.get_feature_flag(self.kill_switch_flag, uid))
            cohort = self._enabled(client.get_feature_flag(self.cohort_flag, uid))
            generation = get_account_cutover_record(uid).account_generation
            return FrameRequestAuthorityDecision(
                enabled=cohort and not kill_switch,
                account_generation=generation,
                kill_switch=kill_switch,
            )
        except Exception:
            # A rollout read failure must not accidentally open a new pixel
            # path. Do not log or emit user/content identifiers here.
            return FrameRequestAuthorityDecision(enabled=False, kill_switch=True)


_authority: FrameRequestAuthority = PostHogFrameRequestAuthority()


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
            enabled=False, account_generation=decision.account_generation, kill_switch=decision.kill_switch
        )
    return decision


def authorize(uid: str, account_generation: int) -> FrameRequestAuthorityDecision:
    decision = decision_for(uid)
    if not decision.enabled or decision.account_generation != account_generation:
        raise PermissionError("frame request rollout or account generation mismatch")
    return decision


__all__ = [
    "DisabledFrameRequestAuthority",
    "PostHogFrameRequestAuthority",
    "FrameRequestAuthority",
    "FrameRequestAuthorityDecision",
    "authorize",
    "decision_for",
    "get_frame_request_authority",
    "set_frame_request_authority_for_tests",
]
