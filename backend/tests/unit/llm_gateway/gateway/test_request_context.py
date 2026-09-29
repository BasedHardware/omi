import uuid
import pytest
from dataclasses import dataclass

from fastapi import Request
from starlette.datastructures import Headers

from llm_gateway.gateway.request_context import (
    JIT_BUDGET_CONTRACT_ENV,
    JIT_CLOUD_QA_CONTRACT_VERSION,
    JITBudgetHeaders,
    jit_budget_forward_headers,
    jit_budget_headers_for,
    request_id_for,
    resolve_request_id,
    validated_jit_budget_values,
)


@pytest.fixture
def enable_jit_budget(monkeypatch):
    monkeypatch.setenv(JIT_BUDGET_CONTRACT_ENV, JIT_CLOUD_QA_CONTRACT_VERSION)


def test_validated_jit_budget_values_all_none(enable_jit_budget):
    assert validated_jit_budget_values(None, None, None, None, None, None) is None


def test_validated_jit_budget_values_unavailable(monkeypatch):
    monkeypatch.setenv(JIT_BUDGET_CONTRACT_ENV, "different-version")
    with pytest.raises(ValueError, match="JIT budget capability is unavailable"):
        validated_jit_budget_values("contract", "run_id", "1", "10", "10", "10")


def test_validated_jit_budget_values_invalid_contract(enable_jit_budget):
    with pytest.raises(ValueError, match="invalid JIT budget contract"):
        validated_jit_budget_values("invalid-contract", "run_id", "1", "10", "10", "10")


def test_validated_jit_budget_values_invalid_run_id(enable_jit_budget):
    with pytest.raises(ValueError, match="invalid JIT budget contract"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "invalid run id!", "1", "10", "10", "10")

    with pytest.raises(ValueError, match="invalid JIT budget contract"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "", "1", "10", "10", "10")


def test_validated_jit_budget_values_invalid_int(enable_jit_budget):
    with pytest.raises(ValueError, match="invalid JIT budget header"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "run-1", "not-an-int", "10", "10", "10")


def test_validated_jit_budget_values_zero_or_negative(enable_jit_budget):
    with pytest.raises(ValueError, match="invalid JIT budget header"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "run-1", "0", "10", "10", "10")

    with pytest.raises(ValueError, match="invalid JIT budget header"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "run-1", "1", "-10", "10", "10")


def test_validated_jit_budget_values_exceeds_ceiling(enable_jit_budget):
    # max_attempts ceiling is 3
    with pytest.raises(ValueError, match="JIT budget exceeds qualification ceiling"):
        validated_jit_budget_values(JIT_CLOUD_QA_CONTRACT_VERSION, "run-1", "4", "10", "10", "10")


def test_validated_jit_budget_values_valid(enable_jit_budget):
    result = validated_jit_budget_values(
        JIT_CLOUD_QA_CONTRACT_VERSION,
        "run-123",
        "2",
        "1000",
        "5000",
        "20000"
    )
    assert result == (JIT_CLOUD_QA_CONTRACT_VERSION, "run-123", 2, 1000, 5000, 20000)


def test_jit_budget_forward_headers_none(enable_jit_budget):
    assert jit_budget_forward_headers(None, None, None, None, None, None) == {}


def test_jit_budget_forward_headers_valid(enable_jit_budget):
    headers = jit_budget_forward_headers(
        JIT_CLOUD_QA_CONTRACT_VERSION,
        "run-123",
        "2",
        "1000",
        "5000",
        "20000"
    )
    assert headers == {
        "X-Omi-Jit-Contract-Version": JIT_CLOUD_QA_CONTRACT_VERSION,
        "X-Omi-Jit-Run-Id": "run-123",
        "X-Omi-Jit-Max-Attempts": "2",
        "X-Omi-Jit-Max-Output-Tokens": "1000",
        "X-Omi-Jit-Max-Input-Tokens": "5000",
        "X-Omi-Jit-Max-Spend-Micro-Usd": "20000",
    }


class MockRequestState:
    def __init__(self, request_id=None):
        if request_id is not None:
            self.request_id = request_id


def build_mock_request(headers_dict, state_request_id=None):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in headers_dict.items()],
        "state": {"request_id": state_request_id} if state_request_id is not None else {},
    }
    req = Request(scope)
    # mock state attribute
    class MockState:
        pass
    mock_state = MockState()
    if state_request_id is not None:
        mock_state.request_id = state_request_id
    # workaround for fastapi Request state property
    object.__setattr__(req, "_state", mock_state)
    return req


def test_jit_budget_headers_for_none(enable_jit_budget):
    req = build_mock_request({})
    assert jit_budget_headers_for(req) is None


def test_jit_budget_headers_for_valid(enable_jit_budget):
    req = build_mock_request({
        "x-omi-jit-contract-version": JIT_CLOUD_QA_CONTRACT_VERSION,
        "x-omi-jit-run-id": "run-123",
        "x-omi-jit-max-attempts": "2",
        "x-omi-jit-max-output-tokens": "1000",
        "x-omi-jit-max-input-tokens": "5000",
        "x-omi-jit-max-spend-micro-usd": "20000",
    })

    result = jit_budget_headers_for(req, owner_uid="user-123")
    assert isinstance(result, JITBudgetHeaders)
    assert result.contract_version == JIT_CLOUD_QA_CONTRACT_VERSION
    assert result.run_id == "run-123"
    assert result.max_attempts == 2
    assert result.max_output_tokens == 1000
    assert result.max_input_tokens == 5000
    assert result.max_spend_micro_usd == 20000
    assert result.owner_uid == "user-123"


def test_request_id_for():
    req = build_mock_request({}, "test-req-id")
    assert request_id_for(req) == "test-req-id"

    req_empty = build_mock_request({}, "")
    assert request_id_for(req_empty) == "unknown"

    req_none = build_mock_request({})
    assert request_id_for(req_none) == "unknown"


def test_resolve_request_id():
    valid_uuid = str(uuid.uuid4())
    # Should keep valid UUID
    assert resolve_request_id(valid_uuid) == valid_uuid

    # Should fix case of UUID
    assert resolve_request_id(valid_uuid.upper()) == valid_uuid

    # Invalid UUID generates new one
    invalid_res = resolve_request_id("not-a-uuid")
    assert invalid_res != "not-a-uuid"
    assert uuid.UUID(invalid_res)  # Should not raise

    # None generates new one
    none_res = resolve_request_id(None)
    assert uuid.UUID(none_res)

    # Too long generates new one
    too_long = "a" * 100
    long_res = resolve_request_id(too_long)
    assert uuid.UUID(long_res)
