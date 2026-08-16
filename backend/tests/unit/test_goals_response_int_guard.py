"""Defense-in-depth: the goal response projection helper must coerce the sequence field like its floats.

utils.goals_response.normalize_goal_response defensively re-coerces every field it projects
(response_float for the numbers, response_bool for is_active, parse_response_datetime for the dates),
but latest_progress_sequence used a raw int(). A response_int helper makes the standalone projection
helper uniformly defensive so a null or non-numeric sequence coerces to the fallback instead of raising.
"""

from utils.goals_response import normalize_goal_response, response_int


def test_response_int_falls_back_on_bad_values():
    assert response_int(None, 0) == 0
    assert response_int('3.5', 0) == 0
    assert response_int(True, 0) == 0
    assert response_int(4, 0) == 4
    assert response_int('7', 0) == 7
    assert response_int(2.9, 0) == 2


def test_normalize_goal_response_tolerates_bad_sequence():
    result = normalize_goal_response({'id': 'g1', 'latest_progress_sequence': None})
    assert result['latest_progress_sequence'] == 0


def test_normalize_goal_response_preserves_valid_sequence():
    result = normalize_goal_response({'id': 'g1', 'latest_progress_sequence': 5})
    assert result['latest_progress_sequence'] == 5
