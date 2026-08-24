"""Authenticated, read-only just-in-time rollout decision contract."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, ConfigDict

from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITRolloutDecision,
    TriState,
    resolve_jit_rollout,
)
from utils.other.endpoints import get_current_user_uid

router = APIRouter()
_DECISION_PATH = '/v1/jit/rollout-decision'


class JITRolloutDecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rollout: TriState
    kill_switch: TriState
    effective: TriState
    reason: JITDecisionReason
    error_class: JITErrorClass
    cache_hit: bool
    cache_ttl_seconds: int

    @classmethod
    def from_decision(cls, decision: JITRolloutDecision) -> 'JITRolloutDecisionEnvelope':
        return cls(
            rollout=decision.rollout,
            kill_switch=decision.kill_switch,
            effective=decision.effective,
            reason=decision.reason,
            error_class=decision.error_class,
            cache_hit=decision.cache_hit,
            cache_ttl_seconds=decision.cache_ttl_seconds,
        )


@router.get(_DECISION_PATH, response_model=JITRolloutDecisionEnvelope)
async def get_jit_rollout_decision(
    uid: str = Depends(get_current_user_uid),
) -> JITRolloutDecisionEnvelope:
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    return JITRolloutDecisionEnvelope.from_decision(decision)


def validate_jit_rollout_contract(app: FastAPI) -> None:
    """Fail startup if a factory omits, unauthenticates, or mutates this route."""

    matches = [route for route in app.routes if getattr(route, 'path', None) == _DECISION_PATH]
    if len(matches) != 1:
        raise RuntimeError('JIT rollout decision contract must expose exactly one read-only GET route')
    route = matches[0]
    dependencies = getattr(getattr(route, 'dependant', None), 'dependencies', [])
    dependency_calls = {getattr(dependency, 'call', None) for dependency in dependencies}
    if (
        getattr(route, 'methods', set()) != {'GET'}
        or getattr(route, 'response_model', None) is not JITRolloutDecisionEnvelope
        or get_current_user_uid not in dependency_calls
    ):
        raise RuntimeError('JIT rollout decision contract must be authenticated, typed, and read-only')


__all__ = ['JITRolloutDecisionEnvelope', 'router', 'validate_jit_rollout_contract']
