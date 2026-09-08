"""Regression: a drifted legacy goal row must not 500 every goal read.

database.goals._metric_from_storage and normalize_goal_storage project stored rows into the
canonical shape. current/target/latest_progress_sequence were coerced with raw float()/int(),
and goal_type with a raw GoalType(...), so a null or non-numeric stored value, or a bad enum,
raised out of every goal read (get_user_goal, get_all_goals, get_goal_by_id, progress writes).
The guards coerce each field defensively and degrade a still-inconsistent metric to absent.
"""

from database.goals import _metric_from_storage, _safe_float, _safe_int, normalize_goal_storage
from models.goal import GoalType


def test_safe_float_and_int_fall_back_on_bad_values():
    assert _safe_float(None, 0.0) == 0.0
    assert _safe_float('abc', 0.0) == 0.0
    assert _safe_float('3.5', 0.0) == 3.5
    assert _safe_int(None, 0) == 0
    assert _safe_int('3.5', 0) == 0
    assert _safe_int(4, 0) == 4


def test_metric_from_storage_tolerates_malformed_legacy_row():
    metric = _metric_from_storage(
        {'goal_type': 'bogus', 'current_value': None, 'target_value': 'abc', 'min_value': 'xyz'}
    )
    assert metric is not None
    assert metric.type is GoalType.scale  # bad enum falls back to the existing default
    assert metric.current == 0.0
    assert metric.target == 0.0
    assert metric.min == 0.0


def test_metric_from_storage_preserves_valid_row():
    metric = _metric_from_storage(
        {'goal_type': 'numeric', 'current_value': 3, 'target_value': 10, 'min_value': 0, 'max_value': 20, 'unit': 'kg'}
    )
    assert metric is not None
    assert metric.type is GoalType.numeric
    assert metric.current == 3.0
    assert metric.target == 10.0
    assert metric.max == 20.0
    assert metric.unit == 'kg'


def test_metric_from_storage_degrades_inconsistent_bounds_to_none():
    # min > max trips the model bounds validator; degrade to no metric instead of 500ing.
    metric = _metric_from_storage({'goal_type': 'scale', 'target_value': 5, 'min_value': 100, 'max_value': 1})
    assert metric is None


def test_normalize_goal_storage_survives_malformed_sequence_and_metric():
    normalized = normalize_goal_storage(
        {'goal_type': 'bogus', 'current_value': None, 'target_value': 'abc', 'latest_progress_sequence': '3.5'}
    )
    assert normalized['latest_progress_sequence'] == 0
    assert normalized['metric'] is not None
    assert normalized['metric']['current'] == 0.0
