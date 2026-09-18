"""Pure universal task-intelligence decisions.

Authenticated ownership is the entitlement. Workflow controls remain persisted
generation fences and diagnostics, not memory-cohort rollout gates.
"""

# LIFECYCLE: permanent

from typing import Any

from models.task_intelligence import TaskIntelligenceRolloutDecision, TaskWorkflowControl, TaskWorkflowMode


def resolve_task_intelligence_rollout(
    *,
    uid: str,
    workflow_mode: TaskWorkflowMode | str,
    memory_cohort_eligible: bool | None = None,
    account_generation: int = 0,
) -> TaskIntelligenceRolloutDecision:
    mode = workflow_mode if isinstance(workflow_mode, TaskWorkflowMode) else TaskWorkflowMode(workflow_mode)
    if not uid:
        raise ValueError('uid is required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')

    # ``memory_cohort_eligible`` is accepted only for released-call-site and
    # response compatibility. It is intentionally ignored as authority.
    del memory_cohort_eligible
    return TaskIntelligenceRolloutDecision(
        uid=uid,
        workflow_mode=mode,
        memory_cohort_eligible=True,
        account_generation=account_generation,
        legacy_reads_authoritative=False,
        legacy_writes_enabled=False,
        intelligence_evaluation_enabled=True,
        canonical_sidecar_writes_enabled=True,
        canonical_reads_authoritative=True,
        compatibility_projection_required=False,
        intelligence_product_enabled=True,
    )


def resolve_task_intelligence_for_user(
    *,
    uid: str,
    workflow_mode: TaskWorkflowMode | str,
    account_generation: int = 0,
    db_client: Any | None = None,
) -> TaskIntelligenceRolloutDecision:
    """Resolve one universal task decision for any authenticated UID."""

    # Keep ``db_client`` in the released signature; task entitlement no longer
    # consults a memory selector or any per-UID allowlist.
    del db_client
    return resolve_task_intelligence_rollout(
        uid=uid,
        workflow_mode=workflow_mode,
        account_generation=account_generation,
    )


def resolve_chat_first_ui(rollout: TaskIntelligenceRolloutDecision) -> bool:
    """Return the server-owned Chat-first capability for one resolved user.

    The persisted UI flag and workflow mode are intentionally ignored: neither
    may suppress an authenticated account.
    """

    return rollout.intelligence_product_enabled


def effective_task_workflow_control(
    control: TaskWorkflowControl,
    rollout: TaskIntelligenceRolloutDecision,
) -> TaskWorkflowControl:
    """Project persisted control metadata onto the sole entitlement decision.

    ``account_generation`` remains the persisted concurrency fence. The
    workflow value in an API projection is effective state only: code-enrolled
    users are read-capable and every other user remains legacy/off.
    """

    return control.model_copy(
        update={
            'workflow_mode': TaskWorkflowMode.read,
            'chat_first_ui': resolve_chat_first_ui(rollout),
        }
    )


__all__ = [
    'effective_task_workflow_control',
    'resolve_chat_first_ui',
    'resolve_task_intelligence_for_user',
    'resolve_task_intelligence_rollout',
]
