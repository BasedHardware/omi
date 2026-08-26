"""Failure telemetry coverage for the shared Chat-first capability boundary."""

from types import SimpleNamespace

from models.task_intelligence import TaskWorkflowControl
import utils.task_intelligence.chat_first_eligibility as eligibility


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
