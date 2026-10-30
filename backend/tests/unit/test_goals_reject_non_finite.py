"""Regression: goal metric inputs must reject NaN and +/-Infinity at the API boundary.

Pydantic floats accept "nan", "inf" and "-inf" by default, and so do FastAPI float query params.
`PATCH /v1/goals/{id}/progress?current_value=nan` (and the developer-API twin) therefore wrote NaN
into the goal metric and progress history: database.goals.update_goal_progress applies the value via
GoalMetric.model_copy, which does not re-validate. Every later read then serialized the metric as
`null` in fields the response schemas declare as required numbers. Create/update bodies accepted
`Infinity`/`NaN` the same way.

The goal request models, GoalMetric and both progress query params now set allow_inf_nan=False, so
a non-finite value is a 422 before anything is persisted.
"""

import math

import pytest
from pydantic import ValidationError

import routers.developer as developer
import routers.goals as goals_router
from database.goals import _metric_from_storage
from models.goal import GoalCreate, GoalMetric, GoalType, GoalUpdate

NON_FINITE = [math.nan, math.inf, -math.inf]


@pytest.mark.parametrize('value', NON_FINITE)
def test_goal_metric_rejects_non_finite_values(value):
    with pytest.raises(ValidationError):
        GoalMetric(type=GoalType.numeric, current=value, target=10)
    with pytest.raises(ValidationError):
        GoalMetric(type=GoalType.numeric, current=0, target=value)


@pytest.mark.parametrize('field', ['target_value', 'current_value', 'min_value', 'max_value'])
@pytest.mark.parametrize('value', NON_FINITE)
def test_goal_create_rejects_non_finite_legacy_fields(field, value):
    payload = {'title': 'run', 'goal_type': 'numeric', 'target_value': 10, field: value}
    with pytest.raises(ValidationError):
        GoalCreate.model_validate(payload)


@pytest.mark.parametrize('field', ['target_value', 'current_value', 'min_value', 'max_value'])
@pytest.mark.parametrize('value', NON_FINITE)
def test_goal_update_rejects_non_finite_legacy_fields(field, value):
    with pytest.raises(ValidationError):
        GoalUpdate.model_validate({field: value})


def test_goal_update_rejects_non_finite_metric():
    with pytest.raises(ValidationError):
        GoalUpdate.model_validate({'metric': {'type': 'numeric', 'current': 'NaN', 'target': 10}})


def test_finite_values_still_accepted():
    created = GoalCreate.model_validate(
        {'title': 'run', 'goal_type': 'numeric', 'target_value': 10, 'current_value': 2.5}
    )
    assert created.metric is not None
    assert created.metric.current == 2.5
    assert GoalUpdate.model_validate({'current_value': -3}).current_value == -3


def test_stored_non_finite_metric_degrades_to_absent():
    # A row already corrupted before this fix must not project NaN back out; the existing
    # ValidationError backstop in _metric_from_storage now turns it into "no metric".
    assert _metric_from_storage({'metric': {'type': 'numeric', 'current': math.nan, 'target': 10}}) is None


def _progress_query_field(router, path):
    route = next(r for r in router.routes if getattr(r, 'path', None) == path and 'PATCH' in r.methods)
    return next(p for p in route.dependant.query_params if p.name == 'current_value')


@pytest.mark.parametrize(
    'module,path',
    [
        (goals_router, '/v1/goals/{goal_id}/progress'),
        (developer, '/v1/dev/user/goals/{goal_id}/progress'),
    ],
    ids=['goals', 'developer'],
)
@pytest.mark.parametrize('raw', ['nan', 'NaN', 'inf', '-inf', 'Infinity'])
def test_progress_query_param_rejects_non_finite(module, path, raw):
    field = _progress_query_field(module.router, path)
    _, errors = field.validate(raw, {}, loc=('query', 'current_value'))
    assert errors, f'{path} accepted current_value={raw}'
    value, errors = field.validate('4.5', {}, loc=('query', 'current_value'))
    assert not errors and value == 4.5


@pytest.mark.parametrize('model_name', ['CreateGoalRequest', 'UpdateGoalRequest'])
@pytest.mark.parametrize('value', NON_FINITE)
def test_developer_goal_request_models_reject_non_finite(model_name, value):
    model = getattr(developer, model_name)
    with pytest.raises(ValidationError):
        model.model_validate({'title': 'run', 'target_value': value})
