"""Account-generation authority for privacy-approved frame requests.

Frame delivery is bound to the authenticated account generation. Eligibility
comes from the locally admitted screen capture, storage/signer availability,
and the route's subscription checks; no rollout cohort or PostHog lookup is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.account_cutover import get_account_cutover_record
from utils.executors import db_executor, run_blocking


@dataclass(frozen=True)
class FrameRequestAuthorityDecision:
    enabled: bool
    account_generation: int | None = None
    kill_switch: bool = False


def _account_generation(uid: str) -> int:
    return get_account_cutover_record(uid).account_generation


async def resolve_frame_request_authority(
    uid: str,
) -> FrameRequestAuthorityDecision:
    """Resolve the current owner generation for an authenticated frame request."""

    owner_uid = uid.strip()
    if not owner_uid:
        return FrameRequestAuthorityDecision(enabled=False)
    try:
        generation = await run_blocking(db_executor, _account_generation, owner_uid)
    except Exception:
        return FrameRequestAuthorityDecision(enabled=False, kill_switch=True)
    return FrameRequestAuthorityDecision(enabled=True, account_generation=generation)


async def authorize_frame_request(
    uid: str,
    account_generation: int,
) -> FrameRequestAuthorityDecision:
    decision = await resolve_frame_request_authority(uid)
    if not decision.enabled or decision.account_generation != account_generation:
        raise PermissionError("frame request account generation mismatch")
    return decision


__all__ = [
    "FrameRequestAuthorityDecision",
    "authorize_frame_request",
    "resolve_frame_request_authority",
]
