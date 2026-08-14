"""Fail-closed, reusable server authority for universal Chat-first access."""

from dataclasses import dataclass
from typing import Callable

import database.task_intelligence_control as task_control_db
from models.task_intelligence import TaskIntelligenceRolloutDecision, TaskWorkflowControl
from utils.observability.fallback import record_fallback
from utils.task_intelligence.rollout import resolve_chat_first_ui, resolve_task_intelligence_for_user


@dataclass(frozen=True)
class ChatFirstEligibility:
    """Fresh server-side capability resolution for one authenticated account."""

    enabled: bool
    account_generation: int | None = None


def resolve_chat_first_eligibility(
    uid: str,
    *,
    load_control: Callable[[str], TaskWorkflowControl] = task_control_db.get_task_workflow_control,
    resolve_rollout: Callable[..., TaskIntelligenceRolloutDecision] = resolve_task_intelligence_for_user,
) -> ChatFirstEligibility:
    """Resolve the generation-bound universal capability without fallback state.

    This is intentionally the only reusable server authority for chat-first
    ingress. Callers must invoke it before touching feature-specific stores,
    metrics, or providers. Any task-control failure fails closed.
    """

    try:
        control = load_control(uid)
        rollout = resolve_rollout(
            uid=uid,
            workflow_mode=control.workflow_mode,
            account_generation=control.account_generation,
        )
        if not resolve_chat_first_ui(rollout):
            return ChatFirstEligibility(enabled=False)
        return ChatFirstEligibility(enabled=True, account_generation=control.account_generation)
    except Exception:
        record_fallback(
            component='other',
            from_mode='chat_first',
            to_mode='capability_unavailable',
            reason='other',
            outcome='exhausted',
        )
        return ChatFirstEligibility(enabled=False)


__all__ = ['ChatFirstEligibility', 'resolve_chat_first_eligibility']
