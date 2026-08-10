"""Pure task-intelligence entitlement decisions.

Canonical-memory membership is the only eligibility input. Workflow controls
remain persisted generation fences and diagnostics, not rollout gates.
"""

# LIFECYCLE: permanent

from models.task_intelligence import TaskIntelligenceRolloutDecision, TaskWorkflowControl, TaskWorkflowMode
from utils.memory.memory_system import MemorySystem, resolve_memory_system


def resolve_task_intelligence_rollout(
    *,
    uid: str,
    workflow_mode: TaskWorkflowMode | str,
    memory_cohort_eligible: bool,
    account_generation: int = 0,
) -> TaskIntelligenceRolloutDecision:
    mode = workflow_mode if isinstance(workflow_mode, TaskWorkflowMode) else TaskWorkflowMode(workflow_mode)
    if not uid:
        raise ValueError('uid is required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')

    canonical_entitled = memory_cohort_eligible
    return TaskIntelligenceRolloutDecision(
        uid=uid,
        workflow_mode=mode,
        memory_cohort_eligible=memory_cohort_eligible,
        account_generation=account_generation,
        legacy_reads_authoritative=not canonical_entitled,
        legacy_writes_enabled=not canonical_entitled,
        intelligence_evaluation_enabled=canonical_entitled,
        canonical_sidecar_writes_enabled=canonical_entitled,
        canonical_reads_authoritative=canonical_entitled,
        compatibility_projection_required=canonical_entitled,
        intelligence_product_enabled=canonical_entitled,
    )


def resolve_task_intelligence_for_user(
    *,
    uid: str,
    workflow_mode: TaskWorkflowMode | str,
    account_generation: int = 0,
    db_client=None,
) -> TaskIntelligenceRolloutDecision:
    """Compose workflow mode with the authoritative canonical-memory selector."""

    memory_cohort_eligible = resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL
    return resolve_task_intelligence_rollout(
        uid=uid,
        workflow_mode=workflow_mode,
        memory_cohort_eligible=memory_cohort_eligible,
        account_generation=account_generation,
    )


def resolve_chat_first_ui(rollout: TaskIntelligenceRolloutDecision) -> bool:
    """Return the server-owned Chat-first capability for one resolved user.

    The canonical-memory entitlement is already composed into the rollout. The
    persisted UI flag and workflow mode are intentionally ignored: neither may
    suppress an enrolled account.
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
            'workflow_mode': TaskWorkflowMode.read if rollout.intelligence_product_enabled else TaskWorkflowMode.off,
        }
    )


__all__ = [
    'effective_task_workflow_control',
    'resolve_chat_first_ui',
    'resolve_task_intelligence_for_user',
    'resolve_task_intelligence_rollout',
]
