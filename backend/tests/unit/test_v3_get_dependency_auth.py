"""GET /v3/memories auth dependency and legacy read behavior under router stubs."""

from __future__ import annotations

import pytest

from tests.unit.v3_router_probes.in_process import probe_get_dependency_auth_under_stubs

try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as exc:  # pragma: no cover
    pytest.skip(f"FastAPI/TestClient required: {exc}", allow_module_level=True)


@pytest.fixture
def probe():
    result = probe_get_dependency_auth_under_stubs()
    if not result.get("testclient_ok"):
        pytest.skip(result.get("blocked_reason", "GET dependency/auth probe unavailable"))
    return result


def test_get_without_auth_override_is_blocked(probe):
    assert probe["without_auth_override"]["blocked"] is True
    assert probe["without_auth_override"]["status_code"] == 500
    assert probe["without_auth_override"]["stubbed_auth_call_count"] == 1


def test_auth_override_reaches_stubbed_legacy_get_memories(probe):
    assert probe["with_auth_override"]["status_code"] == 200
    assert probe["with_auth_override"]["observed_legacy_call"] == {
        "uid": "stubbed-auth-uid",
        "limit": 5000,
        "offset": 0,
    }
    assert probe["stubbed_legacy_get_memories_call_count"] == 1


def test_get_route_uses_expected_auth_dependency_without_rate_limit(probe):
    route = probe["route_dependency_evidence"]
    assert route["route"] == "GET /v3/memories"
    assert route["handler"] == "get_memories"
    assert route["auth_dependency_equivalent"] == "routers.memories.auth.get_current_user_uid"
    assert any("get_current_user_uid" in name for name in route["dependency_names"])
    assert route["has_rate_limit_dependency"] is False
    assert probe["rate_limit_call_count"] == 0
    assert probe["dependency_calls"] == ["auth.get_current_user_uid"]


def test_no_memory_control_dependency_and_legacy_body_preserved(probe):
    body = probe["with_auth_override"]["body"][0]
    assert body["id"] == "legacy-default"
    assert body["uid"] == "stubbed-auth-uid"
    assert probe["memory_control_dependency_present"] is False
    assert probe["memory_control_dependency_invoked"] is False
    assert probe["stubbed_legacy_get_memories_call_count"] == 1
