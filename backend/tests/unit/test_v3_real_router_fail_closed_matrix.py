"""Future route-planner fail-closed matrix plus current real-router legacy baseline."""

from __future__ import annotations

import pytest

from tests.unit.v3_router_probes.fail_closed_matrix import (
    _current_real_router_baseline,
    _future_matrix_cases,
)

try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as exc:  # pragma: no cover
    pytest.skip(f"FastAPI/TestClient required: {exc}", allow_module_level=True)


@pytest.fixture
def baseline():
    result = _current_real_router_baseline(execute=True)
    if not result.get("testclient_ok"):
        pytest.skip("real-router legacy baseline probe unavailable")
    return result


@pytest.fixture
def matrix_cases():
    return {case["case_id"]: case for case in _future_matrix_cases()}


def test_current_real_router_remains_legacy_only_under_stubs(baseline):
    assert baseline["behavior"] == "legacy_only_under_stubs"
    assert baseline["runtime_fail_closed_matrix_wired"] is False
    assert baseline["observed_get_memories_calls"] == [
        {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0},
        {"uid": "stubbed-test-uid", "limit": 17, "offset": 3},
    ]
    assert baseline["stubbed_legacy_get_memories_call_count"] == 2
    assert baseline["mutation_flags_clear"] is True


def test_future_matrix_legacy_and_projection_reader_selection(matrix_cases):
    assert matrix_cases["non_enrolled_offset_zero_legacy_primary"]["http_status"] == 200
    assert matrix_cases["non_enrolled_offset_zero_legacy_primary"]["body"] == [
        {"id": "legacy-5000", "source": "legacy"}
    ]
    assert matrix_cases["non_enrolled_offset_zero_legacy_primary"]["legacy_calls"] == [
        {"uid": "uid-matrix", "limit": 5000, "offset": 0}
    ]
    assert matrix_cases["non_enrolled_offset_zero_legacy_primary"]["projection_calls"] == []

    assert matrix_cases["enrolled_projection_success_projection_only"]["body"] == [
        {"id": "projection-1", "content": "projection memory"}
    ]
    assert matrix_cases["enrolled_projection_success_projection_only"]["legacy_calls"] == []
    assert matrix_cases["enrolled_projection_success_projection_only"]["projection_calls"] == [
        {"uid": "uid-matrix", "limit": 100, "cursor": None}
    ]

    assert matrix_cases["enrolled_enabled_empty_no_legacy_fallback"]["body"] == []
    assert matrix_cases["enrolled_enabled_empty_no_legacy_fallback"]["legacy_calls"] == []
    assert matrix_cases["enrolled_enabled_empty_no_legacy_fallback"]["projection_calls"] == []


def test_future_matrix_fail_closed_and_denied_states_never_call_readers(matrix_cases):
    expected_status = {
        "enrolled_missing_control_fail_closed": 503,
        "enrolled_malformed_control_fail_closed": 503,
        "enrolled_projection_not_ready_fail_closed": 503,
        "enrolled_write_convergence_not_ready_fail_closed": 503,
        "enrolled_account_generation_mismatch_fail_closed": 503,
        "enrolled_cursor_mismatch_fail_closed": 400,
        "enrolled_no_grant_denied": 403,
        "enrolled_archive_denied": 403,
    }

    for case_id, status in expected_status.items():
        case = matrix_cases[case_id]
        assert case["http_status"] == status, case_id
        assert case["legacy_calls"] == [], case_id
        assert case["projection_calls"] == [], case_id
        assert case["legacy_fallback_allowed"] is False, case_id
        assert case["body"] is None, case_id
        assert case["plan_kind"] in {"fail_closed", "deny"}, case_id
