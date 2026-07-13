from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from models.task_intelligence import TaskIntelligenceAttributionEvent
from utils.task_intelligence.contracts import load_contract_manifest


def _event(**overrides):
    payload = {
        'schema_version': 1,
        'event_id': 'event-1',
        'event_type': 'intervention_presented',
        'source_class': 'screen',
        'confidence_band': 'high',
        'intervention_id': 'intervention-1',
        'candidate_id': 'candidate-1',
        'occurred_at': datetime(2026, 7, 9, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return TaskIntelligenceAttributionEvent(**payload)


def test_attribution_event_contains_only_bounded_identifiers_and_enums():
    event = _event()

    assert event.model_dump(mode='json') == {
        'schema_version': 1,
        'event_id': 'event-1',
        'event_type': 'intervention_presented',
        'source_class': 'screen',
        'confidence_band': 'high',
        'attribution_chain_id': None,
        'intervention_id': 'intervention-1',
        'candidate_id': 'candidate-1',
        'task_id': None,
        'workstream_id': None,
        'artifact_id': None,
        'decision_id': None,
        'resolution_code': None,
        'feedback_action': None,
        'feedback_reason': None,
        'outcome_code': None,
        'occurred_at': '2026-07-09T00:00:00Z',
    }


@pytest.mark.parametrize('private_field', ['task_text', 'evidence_excerpt', 'prompt', 'model_reasoning', 'metadata'])
def test_attribution_event_rejects_private_or_free_form_fields(private_field):
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        _event(**{private_field: 'private content'})


def test_attribution_event_requires_stable_subject_identifier():
    with pytest.raises(ValidationError, match='intervention_id and subject'):
        _event(intervention_id=None, candidate_id=None)


def test_outcome_code_is_bounded_and_machine_readable():
    event = _event(
        event_type='outcome_recorded',
        intervention_id=None,
        attribution_chain_id='chain-1',
        candidate_id=None,
        artifact_id='artifact-1',
        outcome_code='artifact_approved',
    )
    assert event.outcome_code == 'artifact_approved'
    with pytest.raises(ValidationError):
        _event(outcome_code='User approved the full private draft text')


def test_identifier_fields_reject_content_smuggling_and_unbounded_values():
    with pytest.raises(ValidationError):
        _event(task_id='raw private title with spaces')
    with pytest.raises(ValidationError):
        _event(task_id='a' * 129)


def test_schema_version_is_required_and_identifiers_are_not_normalized():
    without_version = _event().model_dump()
    without_version.pop('schema_version')
    with pytest.raises(ValidationError):
        TaskIntelligenceAttributionEvent.model_validate(without_version)
    with pytest.raises(ValidationError):
        _event(event_id=' event-1 ')


@pytest.mark.parametrize(
    ('mutation', 'expected_valid'),
    [
        (lambda payload: None, True),
        (lambda payload: payload.pop('schema_version'), False),
        (lambda payload: payload.update(event_id=' event-1 '), False),
        (lambda payload: payload.update(intervention_id=None), False),
        (lambda payload: payload.update(event_type='outcome_recorded', outcome_code='private free text'), False),
    ],
)
def test_json_schema_and_pydantic_share_attribution_wire_acceptance(mutation, expected_valid):
    payload = _event().model_dump(mode='json')
    mutation(payload)
    manifest = load_contract_manifest()
    validator = Draft202012Validator(
        {
            '$schema': manifest['$schema'],
            '$defs': manifest['$defs'],
            '$ref': '#/$defs/attribution_event',
        },
        format_checker=FormatChecker(),
    )
    json_valid = not list(validator.iter_errors(payload))
    try:
        TaskIntelligenceAttributionEvent.model_validate(payload)
        pydantic_valid = True
    except ValidationError:
        pydantic_valid = False

    assert json_valid is expected_valid
    assert pydantic_valid is expected_valid


def test_attribution_timestamp_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        _event(occurred_at=datetime(2026, 7, 9))


def test_candidate_resolution_requires_candidate_and_resolution_code():
    with pytest.raises(ValidationError, match='candidate_id and resolution_code'):
        _event(event_type='candidate_resolved', intervention_id=None)

    with pytest.raises(ValidationError, match='requires a task_id or workstream_id'):
        _event(
            event_type='candidate_resolved',
            intervention_id=None,
            candidate_id='candidate-1',
            resolution_code='accepted',
        )

    event = _event(
        event_type='candidate_resolved',
        intervention_id=None,
        candidate_id='candidate-1',
        task_id='task-1',
        resolution_code='accepted',
    )
    assert event.task_id == 'task-1'


@pytest.mark.parametrize('resolution_code', ['rejected', 'expired'])
def test_candidate_resolution_without_result_is_valid_when_not_accepted(resolution_code):
    event = _event(
        event_type='candidate_resolved',
        intervention_id=None,
        candidate_id='candidate-1',
        resolution_code=resolution_code,
    )

    assert event.resolution_code == resolution_code
    assert event.task_id is None
    assert event.workstream_id is None


def test_feedback_requires_intervention_subject_action_and_bounded_reason():
    with pytest.raises(ValidationError, match='feedback_action'):
        _event(event_type='feedback_recorded')

    event = _event(event_type='feedback_recorded', feedback_action='dismiss', feedback_reason='not_mine')
    assert event.feedback_reason == 'not_mine'
    with pytest.raises(ValidationError, match='only valid for dismiss'):
        _event(event_type='feedback_recorded', feedback_action='later', feedback_reason='not_useful')


def test_attribution_event_is_frozen():
    event = _event()
    with pytest.raises(ValidationError):
        event.task_id = 'task-1'
