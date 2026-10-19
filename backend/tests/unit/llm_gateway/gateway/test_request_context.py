"""Exercise the gateway's current request-ID contract.

The JIT qualification-budget wire contract was retired in #22209. Request-ID
resolution remains the production boundary; these tests import the real module.
"""

import uuid

import pytest
from fastapi import Request

from llm_gateway.gateway import request_context


def build_mock_request(state=None):
    return Request({"type": "http", "headers": [], "state": state or {}})


@pytest.mark.parametrize("request_id", ["test-req-id", str(uuid.UUID(int=1))])
def test_request_id_for_uses_middleware_state(request_id):
    assert request_context.request_id_for(build_mock_request({"request_id": request_id})) == request_id


@pytest.mark.parametrize(
    "state", [{}, {"request_id": ""}, {"request_id": None}, {"request_id": 42}, {"request_id": False}]
)
def test_request_id_for_missing_or_non_string_state_is_unknown(state):
    assert request_context.request_id_for(build_mock_request(state)) == "unknown"


@pytest.mark.parametrize("shape", [str, str.upper, lambda value: f" \t{value}\n"])
def test_resolve_request_id_preserves_canonical_uuid_and_normalizes_case_and_space(shape, monkeypatch):
    valid_uuid = "123e4567-e89b-42d3-a456-426614174000"

    def unexpected_generation():
        pytest.fail("A valid request ID must not be replaced")

    monkeypatch.setattr(request_context.uuid, "uuid4", unexpected_generation)
    assert request_context.resolve_request_id(shape(valid_uuid)) == valid_uuid


@pytest.mark.parametrize(
    "raw_request_id",
    [
        None,
        "",
        " \t\n",
        "not-a-uuid",
        "a" * (request_context.REQUEST_ID_MAX_LENGTH + 1),
        "123e4567e89b42d3a456426614174000",
        "{123e4567-e89b-42d3-a456-426614174000}",
        "urn:uuid:123e4567-e89b-42d3-a456-426614174000",
        "123e4567-e89b-42d3-a456-426614174000-untrusted-suffix" * 2,
    ],
)
def test_resolve_request_id_replaces_invalid_or_noncanonical_input(raw_request_id, monkeypatch):
    generated = uuid.UUID("6ba7b810-9dad-41d1-80b4-00c04fd430c8")
    monkeypatch.setattr(request_context.uuid, "uuid4", lambda: generated)

    assert request_context.resolve_request_id(raw_request_id) == str(generated)


def test_resolve_request_id_generates_uuid4_without_echoing_untrusted_input():
    request_id = request_context.resolve_request_id("untrusted-customer-content")

    assert str(uuid.UUID(request_id)) == request_id
    assert uuid.UUID(request_id).version == 4
    assert len(request_id) <= request_context.REQUEST_ID_MAX_LENGTH
    assert "untrusted-customer-content" not in request_id
