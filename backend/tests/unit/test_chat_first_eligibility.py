"""Failure telemetry coverage for the shared Chat-first capability boundary."""

from types import SimpleNamespace

import pytest

from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
import utils.task_intelligence.chat_first_eligibility as eligibility


@pytest.mark.parametrize('mode', list(TaskWorkflowMode))
def test_universal_decision_entitles_every_authenticated_uid(mode):
    decision = eligibility.resolve_task_intelligence_for_user(uid='user-1', workflow_mode=mode, account_generation=7)

    assert decision.uid == 'user-1'
    assert decision.workflow_mode is mode
    assert decision.memory_cohort_eligible is True
    assert decision.account_generation == 7
    assert decision.legacy_reads_authoritative is False
    assert decision.legacy_writes_enabled is False
    assert decision.intelligence_evaluation_enabled is True
    assert decision.canonical_sidecar_writes_enabled is True
    assert decision.canonical_reads_authoritative is True
    assert decision.compatibility_projection_required is False
    assert decision.intelligence_product_enabled is True


def test_universal_decision_coerces_workflow_mode_strings():
    decision = eligibility.resolve_task_intelligence_for_user(uid='user-1', workflow_mode='read', account_generation=3)

    assert decision.workflow_mode is TaskWorkflowMode.read
    assert decision.account_generation == 3


def test_universal_decision_rejects_invalid_identity_and_generation():
    with pytest.raises(ValueError, match='uid is required'):
        eligibility.resolve_task_intelligence_for_user(uid='', workflow_mode='off')
    with pytest.raises(ValueError, match='nonnegative'):
        eligibility.resolve_task_intelligence_for_user(uid='user-1', workflow_mode='write', account_generation=-1)


def test_control_read_failure_records_shared_fallback_and_fails_closed(monkeypatch):
    events = []
    monkeypatch.setattr(eligibility, 'record_fallback', lambda **event: events.append(event))

    result = eligibility.resolve_chat_first_eligibility(
        'user-1',
        load_control=lambda _uid: (_ for _ in ()).throw(RuntimeError('control unavailable')),
    )

    assert result == eligibility.ChatFirstEligibility(enabled=False)
    assert events == [
        {
            'component': 'other',
            'from_mode': 'chat_first',
            'to_mode': 'capability_unavailable',
            'reason': 'other',
            'outcome': 'exhausted',
        }
    ]


def test_rollout_resolution_failure_records_shared_fallback_and_fails_closed(monkeypatch):
    events = []
    monkeypatch.setattr(eligibility, 'record_fallback', lambda **event: events.append(event))

    result = eligibility.resolve_chat_first_eligibility(
        'user-1',
        load_control=lambda _uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
        resolve_rollout=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('rollout unavailable')),
    )

    assert result == eligibility.ChatFirstEligibility(enabled=False)
    assert events == [
        {
            'component': 'other',
            'from_mode': 'chat_first',
            'to_mode': 'capability_unavailable',
            'reason': 'other',
            'outcome': 'exhausted',
        }
    ]


def test_disabled_capability_does_not_emit_fallback(monkeypatch):
    events = []
    monkeypatch.setattr(eligibility, 'record_fallback', lambda **event: events.append(event))

    result = eligibility.resolve_chat_first_eligibility(
        'user-1',
        load_control=lambda _uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
        resolve_rollout=lambda **_kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )

    assert result == eligibility.ChatFirstEligibility(enabled=False)
    assert events == []
