"""Controlled FastAPI/TestClient GET /v3/memories response-model behavior."""

from __future__ import annotations

import json

import pytest

from tests.unit.v3_router_probes.fastapi_route_contract import run_route_contract_proof

try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as exc:  # pragma: no cover
    pytest.skip(f"FastAPI/TestClient required: {exc}", allow_module_level=True)


def _cases():
    return {case["case_id"]: case for case in run_route_contract_proof()}


def test_legacy_compatible_item_serializes_memorydb_fields():
    case = _cases()["legacy_compatible_item"]
    assert case["status_code"] == 200
    body = case["body"][0]
    assert body["id"] == "mem-legacy-1"
    assert body["content"] == "User likes tea"
    assert body["category"] == "system"
    assert body["reviewed"] is True
    assert body["manually_added"] is False


def test_additive_headers_do_not_mutate_response_body():
    case = _cases()["additive_headers_no_body_mutation"]
    assert case["status_code"] == 200
    assert case["headers"]["x-omi-memory-source"] == "memory-default-projection"
    assert case["headers"]["x-omi-memory-policy"] == "default_memory"
    assert "x-omi-memory-source" not in json.dumps(case["body"])
    assert case["body"][0]["id"] == "mem-header-1"


def test_enabled_empty_returns_empty_list_without_legacy_marker():
    case = _cases()["enabled_empty"]
    assert case["status_code"] == 200
    assert case["body"] == []
    assert case["legacy_fallback_marker_present"] is False


def test_fail_closed_denied_returns_no_body_data():
    case = _cases()["fail_closed_denied_no_body_data"]
    assert case["status_code"] == 403
    assert case["body_text"] == ""
    assert case["json_body"] is None
    assert case["legacy_fallback_marker_present"] is False
    assert case["memory_body_data_present"] is False


def test_memory_only_fields_filtered_from_memorydb_body():
    case = _cases()["memory_only_fields_filtered_from_memorydb_body"]
    assert case["status_code"] == 200
    body_text = json.dumps(case["body"], sort_keys=True)
    assert "memory_source" not in body_text
    assert "account_generation" not in body_text
    assert "projection_generation" not in body_text
    assert "archive_default_visible" not in body_text
    assert case["body"][0]["id"] == "mem-filter-1"
