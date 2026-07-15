"""Pure task-intelligence rollout decisions.

Workflow migration mode and canonical-memory cohort eligibility are deliberately
separate axes. The pure composer accepts both for hermetic tests; the production
resolver obtains cohort membership from the canonical memory owner.
"""

# LIFECYCLE: permanent

from config.what_matters_now_smoke_fixture import is_development_smoke_fixture
from models.task_intelligence import TaskIntelligenceRolloutDecision, TaskWorkflowMode
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

    if mode == TaskWorkflowMode.off:
        return TaskIntelligenceRolloutDecision(
            uid=uid,
            workflow_mode=mode,
            memory_cohort_eligible=memory_cohort_eligible,
            account_generation=account_generation,
            legacy_reads_authoritative=True,
            legacy_writes_enabled=True,
            intelligence_evaluation_enabled=False,
            canonical_sidecar_writes_enabled=False,
            canonical_reads_authoritative=False,
            compatibility_projection_required=False,
            intelligence_product_enabled=False,
        )

    canonical_writes = mode in {TaskWorkflowMode.write, TaskWorkflowMode.read}
    canonical_reads = mode == TaskWorkflowMode.read
    return TaskIntelligenceRolloutDecision(
        uid=uid,
        workflow_mode=mode,
        memory_cohort_eligible=memory_cohort_eligible,
        account_generation=account_generation,
        legacy_reads_authoritative=not canonical_reads,
        legacy_writes_enabled=not canonical_reads,
        intelligence_evaluation_enabled=memory_cohort_eligible,
        canonical_sidecar_writes_enabled=canonical_writes,
        canonical_reads_authoritative=canonical_reads,
        compatibility_projection_required=canonical_reads,
        intelligence_product_enabled=canonical_reads and memory_cohort_eligible,
    )


def resolve_task_intelligence_for_user(
    *,
    uid: str,
    workflow_mode: TaskWorkflowMode | str,
    account_generation: int = 0,
    db_client=None,
) -> TaskIntelligenceRolloutDecision:
    """Compose workflow mode with the authoritative canonical-memory selector."""

    memory_cohort_eligible = is_development_smoke_fixture(uid) or (
        resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL
    )
    return resolve_task_intelligence_rollout(
        uid=uid,
        workflow_mode=workflow_mode,
        memory_cohort_eligible=memory_cohort_eligible,
        account_generation=account_generation,
    )


def resolve_chat_first_ui(rollout: TaskIntelligenceRolloutDecision, ui_flag_enabled: bool) -> bool:
    """Return the server-owned Chat-first capability for one resolved user.

    The explicit UI flag is necessary but never sufficient: only the canonical
    read-mode task-intelligence product cohort may receive the new shell.
    """

    return bool(rollout.intelligence_product_enabled and ui_flag_enabled)


__all__ = ['resolve_chat_first_ui', 'resolve_task_intelligence_for_user', 'resolve_task_intelligence_rollout']
