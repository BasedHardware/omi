"""Authenticated, read-only just-in-time rollout decision contract."""

from __future__ import annotations

from datetime import datetime
import os

from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITRolloutDecision,
    TriState,
    resolve_jit_rollout,
)
from utils.other.endpoints import get_current_user_uid
from routers.retired_proactivity_contracts import PROACTIVITY_RESERVATION_OPENAPI, TRIGGER_FEEDBACK_OPENAPI
from utils.memory.jit_trigger_contract import DEFAULT_TRIGGER_RUNTIME_POLICY, TriggerRuntimePolicy

router = APIRouter()
_DECISION_PATH = '/v1/jit/rollout-decision'
_TRIGGER_SNAPSHOT_PATH = '/v1/jit/trigger-snapshot'
_TRIGGER_FEEDBACK_PATH = '/v1/jit/trigger-feedback'
_PROACTIVITY_RESERVATION_PATH = '/v1/jit/proactivity/reservations'
_JIT_BUDGET_CONTRACT_ENV = 'OMI_JIT_PROACTIVITY_BUDGET_CONTRACT'
_JIT_BUDGET_CONTRACT_VERSION = 'jit-cloud-qa-v1'


class JITRolloutDecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rollout: TriState
    kill_switch: TriState
    effective: TriState
    reason: JITDecisionReason
    error_class: JITErrorClass
    cache_hit: bool
    cache_ttl_seconds: int
    budget_contract_version: str | None = None

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
            budget_contract_version=(
                _JIT_BUDGET_CONTRACT_VERSION
                if os.getenv(_JIT_BUDGET_CONTRACT_ENV, '').strip() == _JIT_BUDGET_CONTRACT_VERSION
                else None
            ),
        )


class JITTriggerActionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    prompt: str


class JITTriggerSnapshotRowEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    memory_id: str
    item_revision: int
    updated_at: datetime
    trigger_condition_json: str
    action: JITTriggerActionEnvelope
    wakeup_budget_per_day: int = Field(ge=1)
    snoozed_until: datetime | None = None


class JITTriggerSnapshotEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    owner_id: str
    account_generation: int = Field(ge=0)
    head_commit_id: str
    commit_sequence: int = Field(ge=0)
    snapshot_revision: str
    complete: bool
    rows: list[JITTriggerSnapshotRowEnvelope]
    policy: TriggerRuntimePolicy = DEFAULT_TRIGGER_RUNTIME_POLICY
    failure_reason: str | None = None
    # Matches the timezone authority used by the reservation transaction. Both
    # are optional for old/synthetic user records; reservations still fail
    # closed when the profile has no usable timezone.
    budget_day: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    budget_timezone: str | None = Field(default=None, min_length=1, max_length=64)


def _disabled_trigger_snapshot(uid: str) -> JITTriggerSnapshotEnvelope:
    """Return a content-free receipt whenever trigger authority is absent."""

    return JITTriggerSnapshotEnvelope(
        owner_id=uid,
        account_generation=0,
        head_commit_id='',
        commit_sequence=0,
        snapshot_revision='',
        complete=False,
        rows=[],
        policy=DEFAULT_TRIGGER_RUNTIME_POLICY,
        failure_reason='rollout_not_enabled',
    )


@router.get(_DECISION_PATH, response_model=JITRolloutDecisionEnvelope)
async def get_jit_rollout_decision(
    uid: str = Depends(get_current_user_uid),
) -> JITRolloutDecisionEnvelope:
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    return JITRolloutDecisionEnvelope.from_decision(decision)


@router.get(_TRIGGER_SNAPSHOT_PATH, response_model=JITTriggerSnapshotEnvelope)
def get_jit_trigger_snapshot(
    response: Response,
    uid: str = Depends(get_current_user_uid),
) -> JITTriggerSnapshotEnvelope:
    """Retired proactivity surface; preserve the disabled client envelope."""
    response.headers['Cache-Control'] = 'no-store'
    return _disabled_trigger_snapshot(uid)


@router.post(_TRIGGER_FEEDBACK_PATH, status_code=410, openapi_extra=TRIGGER_FEEDBACK_OPENAPI)
def post_jit_trigger_feedback() -> JSONResponse:
    return _retired_proactivity_response()


@router.post(_PROACTIVITY_RESERVATION_PATH, status_code=410, openapi_extra=PROACTIVITY_RESERVATION_OPENAPI)
def reserve_jit_proactivity() -> JSONResponse:
    return _retired_proactivity_response()


def _retired_proactivity_response() -> JSONResponse:
    return JSONResponse(
        status_code=410,
        headers={'Cache-Control': 'no-store'},
        content={'detail': {'error': 'feature_retired', 'feature': 'jit_proactivity'}},
    )


def validate_jit_rollout_contract(app: FastAPI) -> None:
    """Fail startup if a factory omits, unauthenticates, or mutates this route."""

    # Local import avoids a router import cycle while keeping one startup
    # assertion for the complete JIT read contract in both app factories.
    from routers.jit_ledger_snapshot import LedgerMirrorSnapshotEnvelope

    expected = {
        _DECISION_PATH: (JITRolloutDecisionEnvelope, {'GET'}),
        _TRIGGER_SNAPSHOT_PATH: (JITTriggerSnapshotEnvelope, {'GET'}),
        '/v1/jit/knowledge-ledger/mirror-snapshot': (LedgerMirrorSnapshotEnvelope, {'GET'}),
    }

    def dependency_calls(dependant: object) -> set[object]:
        calls: set[object] = set()
        pending = list(getattr(dependant, 'dependencies', []))
        while pending:
            dependency = pending.pop()
            calls.add(getattr(dependency, 'call', None))
            pending.extend(getattr(dependency, 'dependencies', []))
        return calls

    for path, (response_model, methods) in expected.items():
        matches = [route for route in app.routes if getattr(route, 'path', None) == path]
        if len(matches) != 1:
            raise RuntimeError(f'JIT contract must expose exactly one authenticated route at {path}')
        route = matches[0]
        authenticated_dependencies = dependency_calls(getattr(route, 'dependant', None))
        if (
            getattr(route, 'methods', set()) != methods
            or getattr(route, 'response_model', None) is not response_model
            or get_current_user_uid not in authenticated_dependencies
        ):
            raise RuntimeError(f'JIT contract must be authenticated and typed with methods {methods} at {path}')


__all__ = [
    'JITRolloutDecisionEnvelope',
    'JITTriggerSnapshotEnvelope',
    'router',
    'validate_jit_rollout_contract',
]
