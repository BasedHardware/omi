"""Authenticated, read-only just-in-time rollout decision contract."""

from __future__ import annotations

from datetime import datetime
import json
import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITRolloutDecision,
    TriState,
    resolve_jit_rollout,
)
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.executors import db_executor, run_blocking
from utils.memory.jit_trigger_contract import DEFAULT_TRIGGER_RUNTIME_POLICY, TriggerRuntimePolicy
from utils.memory.jit_trigger_contract import TriggerFeedback, TriggerFeedbackAction
from utils.memory.jit_trigger_snapshot import (
    read_authoritative_trigger_snapshot,
)
from utils.memory.canonical_memory_adapter import apply_canonical_trigger_feedback
from models.jit_proactivity import (
    JIT_CONTENT_FREE_ID_PATTERN,
    JITProactivityEventReceipt,
    JITProactivityOperation,
)
from models.jit_trigger_feedback import JITTriggerFeedbackAction, JITTriggerFeedbackReceipt
from database._client import get_data_plane_firestore_client
from database.jit_proactivity_store import JITProactivityReservationError, reserve_jit_proactivity_event
from database.memory_apply_store import MemoryFirestoreApplyError
from database.read_boundary import MalformedDocError

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


class JITTriggerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    feedback_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    event_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    trigger_memory_id: str = Field(min_length=1, max_length=256, pattern=r'^[^/]+$')
    account_generation: int = Field(ge=0)
    trigger_revision: int = Field(ge=1)
    action: JITTriggerFeedbackAction
    recorded_at: datetime
    snoozed_until: datetime | None = None

    @model_validator(mode='after')
    def validate_snooze(self) -> 'JITTriggerFeedbackRequest':
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError('recorded_at must be timezone-aware')
        if self.action == 'snooze':
            if self.snoozed_until is None or self.snoozed_until <= self.recorded_at:
                raise ValueError('snooze feedback requires a later snoozed_until')
        elif self.snoozed_until is not None:
            raise ValueError('snoozed_until is only valid for snooze feedback')
        return self


class JITTriggerFeedbackEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    applied: bool
    trigger_memory_id: str
    trigger_revision: int = Field(ge=1)
    trigger_status: str
    receipt: JITTriggerFeedbackReceipt


class JITProactivityReservationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    candidate_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    operation: JITProactivityOperation
    account_generation: int = Field(ge=0)
    device_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    trigger_memory_id: str | None = Field(default=None, min_length=1, max_length=256, pattern=r'^[^/]+$')
    trigger_revision: int | None = Field(default=None, ge=1)
    parent_event_id: str | None = Field(default=None, pattern=JIT_CONTENT_FREE_ID_PATTERN)

    @model_validator(mode='after')
    def validate_trigger_pair(self) -> 'JITProactivityReservationRequest':
        if (self.trigger_memory_id is None) != (self.trigger_revision is None):
            raise ValueError('trigger_memory_id and trigger_revision must be supplied together')
        if self.operation == 'planned_notification' and self.trigger_memory_id is None:
            raise ValueError('planned_notification requires trigger authority')
        if self.operation == 'full_turn':
            if self.parent_event_id is None:
                raise ValueError('full_turn requires parent notification admission')
        elif self.parent_event_id is not None:
            raise ValueError('parent_event_id is only valid for full_turn')
        return self


class JITProactivityReservationEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reserved: bool
    receipt: JITProactivityEventReceipt


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
async def get_jit_trigger_snapshot(
    response: Response,
    uid: str = Depends(get_current_user_uid),
) -> JITTriggerSnapshotEnvelope:
    """Return an exhaustive action-bearing watchlist only for admitted owners."""

    response.headers['Cache-Control'] = 'no-store'
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    if not decision.permits_work:
        return _disabled_trigger_snapshot(uid)
    snapshot = await run_blocking(db_executor, read_authoritative_trigger_snapshot, uid)
    # A flag or kill switch can flip while the blocking exhaustive scan is in
    # flight. Re-resolve uncached immediately before releasing an actionable
    # snapshot, matching the canonical prompt-snapshot authority fence.
    final_decision = await resolve_jit_rollout(
        uid,
        stage=JITDecisionStage.READ_ONLY,
        force_refresh=True,
    )
    if not final_decision.permits_work:
        return _disabled_trigger_snapshot(uid)
    return JITTriggerSnapshotEnvelope(
        owner_id=snapshot.owner_id,
        account_generation=snapshot.account_generation,
        head_commit_id=snapshot.head_commit_id,
        commit_sequence=snapshot.commit_sequence,
        snapshot_revision=snapshot.snapshot_revision,
        complete=snapshot.complete,
        rows=[
            JITTriggerSnapshotRowEnvelope(
                memory_id=row.memory_id,
                item_revision=row.item_revision,
                updated_at=row.updated_at,
                trigger_condition_json=json.dumps(row.trigger_condition, sort_keys=True, separators=(',', ':')),
                action=JITTriggerActionEnvelope.model_validate(row.action.model_dump()),
                wakeup_budget_per_day=row.wakeup_budget_per_day,
                snoozed_until=row.snoozed_until,
            )
            for row in snapshot.rows
        ],
        policy=snapshot.policy,
        failure_reason=snapshot.failure_reason,
        budget_day=snapshot.budget_day,
        budget_timezone=snapshot.budget_timezone,
    )


def _apply_trigger_feedback_on_data_plane(uid: str, memory_id: str, **kwargs):
    """Apply trigger feedback against the plane the trigger snapshot reads.

    The canonical adapter defaults to the compute-plane client. This router is
    mounted on desktop-backend, whose compute project differs from the customer
    data plane in development, so that default would look for the trigger row
    in the wrong project and fail every retraction.

    Resolving the client here rather than in the route keeps the (blocking)
    first-use client construction off the event loop.
    """

    return apply_canonical_trigger_feedback(uid, memory_id, db_client=get_data_plane_firestore_client(), **kwargs)


@router.post(_TRIGGER_FEEDBACK_PATH, response_model=JITTriggerFeedbackEnvelope)
async def post_jit_trigger_feedback(
    request: JITTriggerFeedbackRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, 'memories:modify')),
) -> JITTriggerFeedbackEnvelope:
    """Persist one explicit, content-free user feedback event.

    This privacy/user-authority path intentionally remains available while the
    proactive rollout is disabled or killed. It performs no matching, model
    work, notification, or automatic trigger rewrite.
    """

    try:
        action = TriggerFeedbackAction(request.action)
        feedback = TriggerFeedback(
            feedback_id=request.feedback_id,
            action=action,
            recorded_at=request.recorded_at,
            snoozed_until=request.snoozed_until,
        )
        result = await run_blocking(
            db_executor,
            _apply_trigger_feedback_on_data_plane,
            uid,
            request.trigger_memory_id,
            event_id=request.event_id,
            expected_account_generation=request.account_generation,
            expected_item_revision=request.trigger_revision,
            feedback=feedback,
        )
    except (ValueError, RuntimeError, MemoryFirestoreApplyError) as exc:
        raise HTTPException(status_code=409, detail='Trigger feedback authority changed or is unavailable') from exc
    return JITTriggerFeedbackEnvelope(
        applied=result.applied,
        trigger_memory_id=result.item.memory_id,
        trigger_revision=result.item.item_revision,
        trigger_status=result.item.status.value,
        receipt=result.receipt,
    )


@router.post(_PROACTIVITY_RESERVATION_PATH, response_model=JITProactivityReservationEnvelope)
async def reserve_jit_proactivity(
    request: JITProactivityReservationRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, 'agent:execute_tool')),
) -> JITProactivityReservationEnvelope:
    """Reserve one content-free cross-device budget immediately before work."""

    decision = await resolve_jit_rollout(
        uid,
        stage=JITDecisionStage.PAID_BOUNDARY,
        force_refresh=True,
    )
    if not decision.permits_work:
        raise HTTPException(status_code=403, detail='JIT proactive work is disabled')
    try:
        receipt, reserved = await run_blocking(
            db_executor,
            reserve_jit_proactivity_event,
            uid,
            event_id=request.event_id,
            candidate_id=request.candidate_id,
            operation=request.operation,
            account_generation=request.account_generation,
            device_id=request.device_id,
            trigger_memory_id=request.trigger_memory_id,
            trigger_revision=request.trigger_revision,
            parent_event_id=request.parent_event_id,
        )
    except (ValueError, JITProactivityReservationError) as exc:
        raise HTTPException(status_code=409, detail='JIT proactive budget or authority is unavailable') from exc
    except MalformedDocError as exc:
        raise HTTPException(status_code=503, detail='JIT proactive authority is temporarily unavailable') from exc
    return JITProactivityReservationEnvelope(reserved=reserved, receipt=receipt)


def validate_jit_rollout_contract(app: FastAPI) -> None:
    """Fail startup if a factory omits, unauthenticates, or mutates this route."""

    # Local import avoids a router import cycle while keeping one startup
    # assertion for the complete JIT read contract in both app factories.
    from routers.jit_ledger_snapshot import LedgerMirrorSnapshotEnvelope

    expected = {
        _DECISION_PATH: (JITRolloutDecisionEnvelope, {'GET'}),
        _TRIGGER_SNAPSHOT_PATH: (JITTriggerSnapshotEnvelope, {'GET'}),
        _TRIGGER_FEEDBACK_PATH: (JITTriggerFeedbackEnvelope, {'POST'}),
        _PROACTIVITY_RESERVATION_PATH: (JITProactivityReservationEnvelope, {'POST'}),
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
    'JITTriggerFeedbackEnvelope',
    'JITProactivityReservationEnvelope',
    'router',
    'validate_jit_rollout_contract',
]
