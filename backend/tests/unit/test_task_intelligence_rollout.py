import pytest

from models.task_intelligence import TaskWorkflowMode
from config.what_matters_now_smoke_fixture import WHAT_MATTERS_NOW_SMOKE_UID
from utils.task_intelligence import rollout as rollout_module
from utils.task_intelligence.rollout import resolve_task_intelligence_for_user, resolve_task_intelligence_rollout
from utils.memory.memory_system import MemorySystem


@pytest.mark.parametrize('mode', list(TaskWorkflowMode))
@pytest.mark.parametrize('memory_eligible', [False, True])
def test_rollout_matrix_keeps_workflow_and_memory_axes_independent(mode, memory_eligible):
    decision = resolve_task_intelligence_rollout(
        uid='user-1', workflow_mode=mode, memory_cohort_eligible=memory_eligible, account_generation=7
    )

    assert decision.workflow_mode == mode
    assert decision.memory_cohort_eligible is memory_eligible
    assert decision.account_generation == 7
    assert decision.legacy_reads_authoritative is (mode != TaskWorkflowMode.read)
    assert decision.legacy_writes_enabled is (mode != TaskWorkflowMode.read)
    assert decision.canonical_sidecar_writes_enabled is (mode in {TaskWorkflowMode.write, TaskWorkflowMode.read})
    assert decision.canonical_reads_authoritative is (mode == TaskWorkflowMode.read)
    assert decision.compatibility_projection_required is (mode == TaskWorkflowMode.read)
    assert decision.intelligence_evaluation_enabled is (memory_eligible and mode != TaskWorkflowMode.off)
    assert decision.intelligence_product_enabled is (memory_eligible and mode == TaskWorkflowMode.read)


def test_production_resolver_uses_authoritative_memory_selector(monkeypatch):
    calls = []

    def fake_resolve_memory_system(uid, *, db_client=None):
        calls.append((uid, db_client))
        return MemorySystem.CANONICAL

    monkeypatch.setattr(rollout_module, 'resolve_memory_system', fake_resolve_memory_system)
    db_client = object()

    decision = resolve_task_intelligence_for_user(
        uid='user-1', workflow_mode='read', account_generation=3, db_client=db_client
    )

    assert calls == [('user-1', db_client)]
    assert decision.memory_cohort_eligible is True
    assert decision.intelligence_product_enabled is True


def test_production_resolver_fails_closed_for_legacy_memory_user(monkeypatch):
    monkeypatch.setattr(rollout_module, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)

    decision = resolve_task_intelligence_for_user(uid='user-1', workflow_mode='read')

    assert decision.canonical_reads_authoritative is True
    assert decision.memory_cohort_eligible is False
    assert decision.intelligence_evaluation_enabled is False
    assert decision.intelligence_product_enabled is False


def test_explicit_dev_runtime_allows_only_the_code_owned_smoke_fixture(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(rollout_module, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)

    decision = resolve_task_intelligence_for_user(uid=WHAT_MATTERS_NOW_SMOKE_UID, workflow_mode='read')

    assert decision.memory_cohort_eligible is True
    assert decision.intelligence_product_enabled is True
    other = resolve_task_intelligence_for_user(uid='another-user', workflow_mode='read')
    assert other.intelligence_product_enabled is False


@pytest.mark.parametrize('stage', ['', 'local', 'prod'])
def test_smoke_fixture_rollout_fails_closed_outside_explicit_dev_runtime(monkeypatch, stage):
    if stage:
        monkeypatch.setenv('OMI_ENV_STAGE', stage)
    else:
        monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.setattr(rollout_module, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)

    decision = resolve_task_intelligence_for_user(uid=WHAT_MATTERS_NOW_SMOKE_UID, workflow_mode='read')

    assert decision.memory_cohort_eligible is False
    assert decision.intelligence_product_enabled is False


def test_rollout_rejects_invalid_identity_and_generation():
    with pytest.raises(ValueError, match='uid is required'):
        resolve_task_intelligence_rollout(uid='', workflow_mode='off', memory_cohort_eligible=False)
    with pytest.raises(ValueError, match='nonnegative'):
        resolve_task_intelligence_rollout(
            uid='user-1', workflow_mode='write', memory_cohort_eligible=True, account_generation=-1
        )
