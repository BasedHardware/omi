import math
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from routers.desktop_prompts import (
    DesktopPromptSpec,
    DesktopPromptsResponse,
    _safe_int,
    get_desktop_prompts,
    prompt_matches_audience,
    rollout_bucket,
    spec_from_doc,
)


class MockSnapshot:
    def __init__(self, doc_id, data=None, raise_exc=False):
        self.id = doc_id
        self._data = data
        self._raise_exc = raise_exc

    def to_dict(self):
        if self._raise_exc:
            raise RuntimeError("Corrupted document stream")
        return self._data


# 1. _safe_int resilience tests
def test_safe_int_none_returns_default():
    assert _safe_int(None, 42) == 42


def test_safe_int_bool_rejected():
    assert _safe_int(True, 0) == 0
    assert _safe_int(False, 10) == 10


def test_safe_int_valid_int():
    assert _safe_int(123, 0) == 123
    assert _safe_int(-45, 0) == -45


def test_safe_int_valid_float():
    assert _safe_int(12.9, 0) == 12
    assert _safe_int(-3.2, 0) == -3


def test_safe_int_non_finite_float():
    assert _safe_int(float("nan"), 7) == 7
    assert _safe_int(float("inf"), 7) == 7
    assert _safe_int(float("-inf"), 7) == 7


def test_safe_int_numeric_string():
    assert _safe_int("12000", 0) == 12000
    assert _safe_int("  42  ", 0) == 42
    assert _safe_int("99.8", 0) == 99


def test_safe_int_invalid_string():
    assert _safe_int("", 5) == 5
    assert _safe_int("   ", 5) == 5
    assert _safe_int("not_a_number", 5) == 5


def test_safe_int_invalid_types():
    assert _safe_int([], 8) == 8
    assert _safe_int({}, 8) == 8


# 2. prompt_matches_audience resilience tests
def test_prompt_matches_audience_non_dict_doc():
    assert not prompt_matches_audience("not-a-dict", "uid-1", "stable", 100)
    assert not prompt_matches_audience(None, "uid-1", "stable", 100)


def test_prompt_matches_audience_non_dict_audience():
    # String or list audience should not crash with AttributeError
    doc = {"id": "p1", "audience": "beta"}
    assert isinstance(prompt_matches_audience(doc, "uid-1", "stable", 100), bool)
    doc_list = {"id": "p1", "audience": [1, 2, 3]}
    assert isinstance(prompt_matches_audience(doc_list, "uid-1", "stable", 100), bool)


def test_prompt_matches_audience_malformed_channels_rejected():
    # String channels (e.g. 'stable-beta') must not substring-match; should reject match
    doc = {"id": "p1", "audience": {"channels": "stable-beta"}}
    assert not prompt_matches_audience(doc, "uid-1", "stable", 100)
    # Int or bool channel should also reject match without TypeError
    doc_int = {"id": "p1", "audience": {"channels": 123}}
    assert not prompt_matches_audience(doc_int, "uid-1", "stable", 100)
    doc_bool = {"id": "p1", "audience": {"channels": True}}
    assert not prompt_matches_audience(doc_bool, "uid-1", "stable", 100)


def test_prompt_matches_audience_valid_channels():
    doc = {"id": "p1", "audience": {"channels": ["beta", "nightly"]}}
    assert prompt_matches_audience(doc, "uid-1", "beta", 100)
    assert not prompt_matches_audience(doc, "uid-1", "stable", 100)


def test_prompt_matches_audience_string_min_build_coerced():
    doc = {"id": "p1", "audience": {"min_build": "12000"}}
    assert prompt_matches_audience(doc, "uid-1", "stable", 12500)
    assert not prompt_matches_audience(doc, "uid-1", "stable", 11500)


def test_prompt_matches_audience_bool_min_build_ignored():
    # Boolean min_build must not compare True < build
    doc = {"id": "p1", "audience": {"min_build": True}}
    assert prompt_matches_audience(doc, "uid-1", "stable", 100)


def test_prompt_matches_audience_rollout_pct_bool_or_invalid():
    # Non-numeric rollout_pct defaults to 100
    doc = {"id": "p1", "audience": {"rollout_pct": "invalid"}}
    assert prompt_matches_audience(doc, "uid-1", "stable", 100)
    doc_bool = {"id": "p1", "audience": {"rollout_pct": True}}
    assert prompt_matches_audience(doc_bool, "uid-1", "stable", 100)


def test_prompt_matches_audience_missing_id_rejected():
    doc = {"audience": {"rollout_pct": 100}}
    assert not prompt_matches_audience(doc, "uid-1", "stable", 100)


# 3. spec_from_doc resilience tests
def test_spec_from_doc_non_dict():
    assert spec_from_doc("bad-doc") is None
    assert spec_from_doc(None) is None


def test_spec_from_doc_whitespace_id_or_question():
    assert spec_from_doc({"id": "   ", "type": "stars", "question": "Rate us"}) is None
    assert spec_from_doc({"id": "p1", "type": "stars", "question": "   "}) is None


def test_spec_from_doc_non_dict_trigger_and_cta():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "trigger": "invalid-trigger",
        "cta": ["invalid-cta"],
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.trigger_kind == "app_launch"
    assert spec.trigger_count == 0
    assert spec.cta_label is None
    assert spec.cta_url is None


def test_spec_from_doc_trigger_count_coercion():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "trigger": {"count": "5"},
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.trigger_count == 5


def test_spec_from_doc_trigger_count_bool_or_nan():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "trigger": {"count": True},
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.trigger_count == 0

    doc_nan = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "trigger": {"count": float("nan")},
    }
    assert spec_from_doc(doc_nan).trigger_count == 0


def test_spec_from_doc_options_string_not_split():
    # If options is a string (e.g. 'yes,no'), it must not be split into characters
    doc = {
        "id": "p1",
        "type": "choice",
        "question": "Choose one",
        "options": "yes,no",
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.options == []


def test_spec_from_doc_options_non_sequence():
    doc = {
        "id": "p1",
        "type": "choice",
        "question": "Choose one",
        "options": 123,
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.options == []


def test_spec_from_doc_options_capped_at_6():
    doc = {
        "id": "p1",
        "type": "choice",
        "question": "Choose one",
        "options": ["opt1", "opt2", "opt3", "opt4", "opt5", "opt6", "opt7", "opt8"],
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert len(spec.options) == 6
    assert spec.options == ["opt1", "opt2", "opt3", "opt4", "opt5", "opt6"]


def test_spec_from_doc_max_per_day_coercion():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "max_per_day": "3",
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.max_per_day == 3


def test_spec_from_doc_max_per_day_minimum_1():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "max_per_day": -5,
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.max_per_day == 1


def test_spec_from_doc_max_per_day_bool_defaults_to_1():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "max_per_day": False,
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.max_per_day == 1


# 4. Router store error boundary & per-snapshot isolation tests
@patch("routers.desktop_prompts.list_active_desktop_prompt_snapshots")
def test_get_desktop_prompts_store_error_boundary(mock_snapshots):
    mock_snapshots.side_effect = RuntimeError("Firestore unavailable")
    with pytest.raises(HTTPException) as exc_info:
        get_desktop_prompts(channel="stable", build=100, uid="uid-1")
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to load desktop prompts"


@patch("routers.desktop_prompts.list_active_desktop_prompt_snapshots")
def test_get_desktop_prompts_corrupted_snapshot_skipped(mock_snapshots):
    # One broken snapshot, one valid snapshot
    s_broken = MockSnapshot("bad-doc", raise_exc=True)
    s_valid = MockSnapshot("good-doc", {
        "type": "stars",
        "question": "Rate us",
        "audience": {"rollout_pct": 100},
    })
    mock_snapshots.return_value = [s_broken, s_valid]

    res = get_desktop_prompts(channel="stable", build=100, uid="uid-1")
    assert isinstance(res, DesktopPromptsResponse)
    assert len(res.prompts) == 1
    assert res.prompts[0].id == "good-doc"


@patch("routers.desktop_prompts.list_active_desktop_prompt_snapshots")
def test_get_desktop_prompts_none_snapshot_dict_skipped(mock_snapshots):
    s_none = MockSnapshot("none-doc", data=None)
    s_valid = MockSnapshot("valid-doc", {
        "type": "banner",
        "question": "New update available",
        "audience": {"rollout_pct": 100},
    })
    mock_snapshots.return_value = [s_none, s_valid]

    res = get_desktop_prompts(channel="stable", build=100, uid="uid-1")
    assert len(res.prompts) == 1
    assert res.prompts[0].id == "valid-doc"


@patch("routers.desktop_prompts.list_active_desktop_prompt_snapshots")
def test_get_desktop_prompts_sorted_by_id(mock_snapshots):
    s_b = MockSnapshot("b-prompt", {
        "type": "stars",
        "question": "Question B",
        "audience": {"rollout_pct": 100},
    })
    s_a = MockSnapshot("a-prompt", {
        "type": "stars",
        "question": "Question A",
        "audience": {"rollout_pct": 100},
    })
    mock_snapshots.return_value = [s_b, s_a]

    res = get_desktop_prompts(channel="stable", build=100, uid="uid-1")
    assert len(res.prompts) == 2
    assert res.prompts[0].id == "a-prompt"
    assert res.prompts[1].id == "b-prompt"


def test_spec_from_doc_cta_coercion():
    doc = {
        "id": "p1",
        "type": "banner",
        "question": "Click here",
        "cta": {"label": 12345, "url": "https://omi.me"},
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.cta_label == "12345"
    assert spec.cta_url == "https://omi.me"


def test_spec_from_doc_trigger_kind_coercion():
    doc = {
        "id": "p1",
        "type": "stars",
        "question": "Rate us",
        "trigger": {"kind": "custom_event"},
    }
    spec = spec_from_doc(doc)
    assert spec is not None
    assert spec.trigger_kind == "custom_event"


def test_prompt_matches_audience_rollout_pct_clamped():
    doc_neg = {"id": "p1", "audience": {"rollout_pct": -50}}
    assert not prompt_matches_audience(doc_neg, "uid-1", "stable", 100)
    doc_high = {"id": "p1", "audience": {"rollout_pct": 150}}
    assert prompt_matches_audience(doc_high, "uid-1", "stable", 100)

