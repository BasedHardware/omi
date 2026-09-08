import pytest
from pydantic import ValidationError

from models.goal import GoalCreate, GoalSource, GoalType


@pytest.mark.parametrize('source', list(GoalSource))
def test_goal_create_accepts_canonical_sources(source):
    request = GoalCreate(title='Ship the release', source=source.value)

    assert request.source == source


@pytest.mark.parametrize(
    ('legacy_source', 'canonical_source'),
    [
        ('ai', GoalSource.ai_suggested),
        ('onboarding_step_flow', GoalSource.user),
        ('onboarding_typed', GoalSource.user),
        ('onboarding_selected', GoalSource.user),
    ],
)
def test_goal_create_normalizes_released_desktop_sources(legacy_source, canonical_source):
    request = GoalCreate(title='Ship the release', source=legacy_source)

    assert request.source == canonical_source


def test_goal_create_rejects_unknown_source():
    with pytest.raises(ValidationError):
        GoalCreate(title='Ship the release', source='unknown-client-source')


def test_goal_create_accepts_complete_released_desktop_request_shape():
    request = GoalCreate.model_validate(
        {
            'title': 'Ship the release',
            'description': 'Deliver a stable desktop build',
            'goal_type': 'numeric',
            'target_value': 10,
            'current_value': 2,
            'min_value': 0,
            'max_value': 20,
            'unit': 'builds',
            'source': 'ai',
        }
    )

    assert request.desired_outcome == 'Deliver a stable desktop build'
    assert request.source == GoalSource.ai_suggested
    assert request.metric is not None
    assert request.metric.type == GoalType.numeric
    assert request.metric.current == 2
    assert request.metric.target == 10
    assert request.metric.min == 0
    assert request.metric.max == 20
    assert request.metric.unit == 'builds'
    assert 'description' not in request.model_dump()


def test_goal_create_prefers_canonical_desired_outcome_over_legacy_description():
    request = GoalCreate.model_validate(
        {
            'title': 'Ship the release',
            'desired_outcome': 'Canonical outcome',
            'description': 'Conflicting legacy outcome',
        }
    )

    assert request.desired_outcome == 'Canonical outcome'
