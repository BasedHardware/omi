"""Regression: shared Levenshtein helper (ids.edit_distance) used by pipeline + verify_output."""

from utils.memory_ingestion.ids import edit_distance
from utils.memory_ingestion.pipeline import _edit_distance as pipeline_edit_distance
from utils.memory_ingestion.stages.verify_output import _edit_distance as verify_edit_distance


def test_edit_distance_basic_cases():
    assert edit_distance("hello", "hello") == 0
    assert edit_distance("abc", "xyz") == 3
    assert edit_distance("hello", "helllo") == 1
    assert edit_distance("cat", "bat") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3


def test_pipeline_and_verify_share_same_edit_distance_implementation():
    assert pipeline_edit_distance is edit_distance
    assert verify_edit_distance is edit_distance
