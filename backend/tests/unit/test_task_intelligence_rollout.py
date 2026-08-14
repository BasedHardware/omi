import pytest
from pydantic import ValidationError

from models.task_intelligence import TaskIntelligenceRolloutDecision, TaskWorkflowControl, TaskWorkflowMode
from utils.task_intelligence.rollout import (
    effective_task_workflow_control,
    resolve_chat_first_ui,
    resolve_task_intelligence_for_user,
    resolve_task_intelligence_rollout,
)


@pytest.mark.parametrize('mode', list(TaskWorkflowMode))
@pytest.mark.parametrize('memory_eligible', [False, True, None])
def test_rollout_is_universal_and_ignores_retired_memory_diagnostic(mode, memory_eligible):
    decision = resolve_task_intelligence_rollout(
        uid='user-1', workflow_mode=mode, memory_cohort_eligible=memory_eligible, account_generation=7
    )

    assert decision.workflow_mode == mode
    assert decision.memory_cohort_eligible is True  # constant compatibility diagnostic
    assert decision.account_generation == 7
    assert decision.legacy_reads_authoritative is False
    assert decision.legacy_writes_enabled is False
    assert decision.canonical_sidecar_writes_enabled is True
    assert decision.canonical_reads_authoritative is True
    assert decision.compatibility_projection_required is False
    assert decision.intelligence_evaluation_enabled is True
    assert decision.intelligence_product_enabled is True
    assert resolve_chat_first_ui(decision) is True


@pytest.mark.parametrize('uid', ['former-cohort-user', 'new-user', 'fixture-user'])
def test_production_resolver_has_one_decision_for_every_authenticated_uid(uid):
    decision = resolve_task_intelligence_for_user(uid=uid, workflow_mode='off', account_generation=3)

    assert decision.intelligence_product_enabled is True
    assert decision.canonical_reads_authoritative is True
    assert decision.legacy_writes_enabled is False
    assert resolve_chat_first_ui(decision) is True


def test_effective_control_keeps_generation_fence_but_exposes_universal_capability():
    control = TaskWorkflowControl(workflow_mode='off', account_generation=4)
    rollout = resolve_task_intelligence_for_user(uid='user-1', workflow_mode='off', account_generation=4)

    effective = effective_task_workflow_control(control, rollout)

    assert effective.account_generation == 4
    assert effective.workflow_mode is TaskWorkflowMode.read
    assert effective.chat_first_ui is True


def test_rollout_rejects_invalid_identity_and_generation():
    with pytest.raises(ValueError, match='uid is required'):
        resolve_task_intelligence_rollout(uid='', workflow_mode='off')
    with pytest.raises(ValueError, match='nonnegative'):
        resolve_task_intelligence_rollout(uid='user-1', workflow_mode='write', account_generation=-1)


def test_compatibility_cohort_diagnostic_cannot_be_false():
    with pytest.raises(ValidationError):
        TaskIntelligenceRolloutDecision(
            uid='user-1',
            workflow_mode=TaskWorkflowMode.read,
            memory_cohort_eligible=False,
            legacy_reads_authoritative=False,
            legacy_writes_enabled=False,
            intelligence_evaluation_enabled=True,
            canonical_sidecar_writes_enabled=True,
            canonical_reads_authoritative=True,
            compatibility_projection_required=False,
            intelligence_product_enabled=True,
        )
