import pytest

from models.task_intelligence import TaskWorkflowMode
from utils.task_intelligence import rollout as rollout_module
from utils.task_intelligence.rollout import (
    resolve_chat_first_ui,
    resolve_task_intelligence_for_user,
    resolve_task_intelligence_rollout,
)
from utils.memory.memory_system import MemorySystem


@pytest.mark.parametrize('mode', list(TaskWorkflowMode))
@pytest.mark.parametrize('memory_eligible', [False, True])
def test_rollout_matrix_uses_memory_membership_as_the_only_eligibility_input(mode, memory_eligible):
    decision = resolve_task_intelligence_rollout(
        uid='user-1', workflow_mode=mode, memory_cohort_eligible=memory_eligible, account_generation=7
    )

    assert decision.workflow_mode == mode
    assert decision.memory_cohort_eligible is memory_eligible
    assert decision.account_generation == 7
    assert decision.legacy_reads_authoritative is (not memory_eligible)
    assert decision.legacy_writes_enabled is (not memory_eligible)
    assert decision.canonical_sidecar_writes_enabled is memory_eligible
    assert decision.canonical_reads_authoritative is memory_eligible
    assert decision.compatibility_projection_required is memory_eligible
    assert decision.intelligence_evaluation_enabled is memory_eligible
    assert decision.intelligence_product_enabled is memory_eligible


@pytest.mark.parametrize('mode', list(TaskWorkflowMode))
@pytest.mark.parametrize('memory_eligible', [False, True])
def test_chat_first_ui_uses_the_same_canonical_membership_decision(mode, memory_eligible):
    rollout = resolve_task_intelligence_rollout(
        uid='user-1', workflow_mode=mode, memory_cohort_eligible=memory_eligible, account_generation=7
    )

    assert resolve_chat_first_ui(rollout) is memory_eligible


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

    assert decision.canonical_reads_authoritative is False
    assert decision.memory_cohort_eligible is False
    assert decision.intelligence_evaluation_enabled is False
    assert decision.intelligence_product_enabled is False


def test_noncanonical_dev_fixture_cannot_bypass_the_code_owned_cohort(monkeypatch):
    monkeypatch.setattr(rollout_module, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)

    decision = resolve_task_intelligence_for_user(uid='fixture-user', workflow_mode='read')

    assert decision.memory_cohort_eligible is False
    assert decision.intelligence_product_enabled is False


def test_local_chat_first_harness_uses_the_same_static_membership_predicate():
    from config.canonical_memory_cohort import (
        LOCAL_CHAT_FIRST_E2E_ENABLED_UID,
        is_canonical_memory_user,
    )
    from config.chat_first_e2e_fixture import (
        CHAT_FIRST_E2E_ENABLED_PRINCIPAL,
        CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL,
    )

    assert CHAT_FIRST_E2E_ENABLED_PRINCIPAL == LOCAL_CHAT_FIRST_E2E_ENABLED_UID
    assert is_canonical_memory_user(CHAT_FIRST_E2E_ENABLED_PRINCIPAL) is True
    assert is_canonical_memory_user(CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL) is False


def test_rollout_rejects_invalid_identity_and_generation():
    with pytest.raises(ValueError, match='uid is required'):
        resolve_task_intelligence_rollout(uid='', workflow_mode='off', memory_cohort_eligible=False)
    with pytest.raises(ValueError, match='nonnegative'):
        resolve_task_intelligence_rollout(
            uid='user-1', workflow_mode='write', memory_cohort_eligible=True, account_generation=-1
        )
