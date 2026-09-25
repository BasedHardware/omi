"""Shared rollout and account-generation authority for JIT frame requests.

Frame requests deliberately use the one backend JIT rollout flag and kill
switch owned by :mod:`utils.jit_rollout`. This adapter adds only the current
account-generation fence needed by the device queue; it never creates a second
PostHog control plane or performs synchronous provider IO on an async caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.account_cutover import get_account_cutover_record
from utils.executors import db_executor, run_blocking
from utils.jit_rollout import JITDecisionStage, resolve_jit_rollout


@dataclass(frozen=True)
class FrameRequestAuthorityDecision:
    enabled: bool
    account_generation: int | None = None
    kill_switch: bool = False


def _account_generation(uid: str) -> int:
    return get_account_cutover_record(uid).account_generation


async def resolve_frame_request_authority(
    uid: str,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
) -> FrameRequestAuthorityDecision:
    """Resolve shared bounded JIT control, then the current owner generation."""

    owner_uid = uid.strip()
    if not owner_uid:
        return FrameRequestAuthorityDecision(enabled=False)
    try:
        rollout = await resolve_jit_rollout(
            owner_uid,
            stage=stage,
            force_refresh=force_refresh,
        )
        if not rollout.permits_work:
            return FrameRequestAuthorityDecision(
                enabled=False,
                kill_switch=rollout.kill_switch.value == "enabled",
            )
        generation = await run_blocking(db_executor, _account_generation, owner_uid)
    except Exception:
        return FrameRequestAuthorityDecision(enabled=False, kill_switch=True)
    return FrameRequestAuthorityDecision(enabled=True, account_generation=generation)


async def authorize_frame_request(
    uid: str,
    account_generation: int,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
) -> FrameRequestAuthorityDecision:
    decision = await resolve_frame_request_authority(
        uid,
        stage=stage,
        force_refresh=force_refresh,
    )
    if not decision.enabled or decision.account_generation != account_generation:
        raise PermissionError("frame request rollout or account generation mismatch")
    return decision


__all__ = [
    "FrameRequestAuthorityDecision",
    "authorize_frame_request",
    "resolve_frame_request_authority",
]
