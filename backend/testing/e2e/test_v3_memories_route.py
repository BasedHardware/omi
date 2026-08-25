"""
Hermetic route/runtime coverage for memory GET /v3/memories wiring.

These tests exercise the real FastAPI route with the PR #8004 e2e harness and
only fake, local dependency overrides. They prove the production default remains
legacy/off while the route can be driven through fake memory runtime decisions.
"""

from contextlib import contextmanager

from fakes.firestore import seed_memory


def _memory_doc(memory_id: str, content: str, category: str = "manual") -> dict:
    return {
        "id": memory_id,
        "content": content,
        "category": category,
        "visibility": "public",
        "manually_added": category == "manual",
        "reviewed": False,
        "edited": False,
        "is_locked": False,
        "user_review": True,
    }


@contextmanager
def _override_memory_runtime(client, runtime):
    import routers.memories as memories_router

    client.app.dependency_overrides[memories_router.get_v3_get_runtime] = lambda: runtime
    try:
        yield
    finally:
        client.app.dependency_overrides.pop(memories_router.get_v3_get_runtime, None)


def _runtime(*, enabled: bool, source_decision: str, service=None):
    import routers.memories as memories_router

    return memories_router.V3GetRuntime(
        enabled=enabled,
        source_decision=source_decision,
        service=service,
        adapters=object(),
    )


def test_default_off_uses_legacy_memories_and_emits_no_memory_headers(client, auth_headers):
    """Default production dependency is hard off: legacy data is returned, memory headers are absent."""
    seed_memory("123", _memory_doc("legacy-default-off", "legacy default-off memory"))

    resp = client.get("/v3/memories?limit=1&offset=0&cursor=ignored", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert [item["id"] for item in resp.json()] == ["legacy-default-off"]
    assert "x-omi-memory-read-source" not in resp.headers
    assert "x-omi-memory-read-decision" not in resp.headers
    assert "x-omi-memory-next-cursor" not in resp.headers
    assert "link" not in resp.headers


def test_enabled_legacy_primary_decision_preserves_legacy_path(client, auth_headers):
    """A non-enrolled/fake legacy-primary runtime must still read legacy and never call memory service."""
    seed_memory("123", _memory_doc("legacy-primary", "legacy primary memory"))

    def should_not_be_called(_params, _adapters):  # pragma: no cover - assertion path
        raise AssertionError("legacy_primary must not invoke the memory read service")

    with _override_memory_runtime(
        client,
        _runtime(enabled=True, source_decision="legacy_primary", service=should_not_be_called),
    ):
        resp = client.get("/v3/memories?limit=1&offset=0", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert [item["id"] for item in resp.json()] == ["legacy-primary"]
    assert "x-omi-memory-read-source" not in resp.headers
    assert "x-omi-memory-read-decision" not in resp.headers


def test_enrolled_memory_fake_success_maps_body_cursor_and_allowlisted_headers(client, auth_headers):
    """An enrolled fake memory runtime can return MemoryDB JSON and only allowlisted route headers."""
    create = client.post(
        "/v3/memories",
        json={"content": "memory projected memory", "category": "manual", "visibility": "public"},
        headers=auth_headers,
    )
    assert create.status_code == 200, create.text
    memory_body = create.json()
    captured = []

    def fake_memory_service(params, _adapters):
        from utils.memory.v3.composed_get_service import V3ComposedResponse

        captured.append(params)
        composed_body = {
            **memory_body,
            "memory_tier": "short_term",
            "layer": "short_term",
            "memory_only": "internal-default",
        }
        response = V3ComposedResponse.success(
            body=[composed_body],
            next_cursor="cursor-next-1",
            source="memory_compatibility_projection",
            read_count=1,
            scanned_count=2,
        )
        response.headers["X-Not-Allowlisted"] = "must-not-leak"
        return response

    with _override_memory_runtime(
        client, _runtime(enabled=True, source_decision="memory_read", service=fake_memory_service)
    ):
        resp = client.get("/v3/memories?limit=2&offset=0&cursor=cursor-start", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()[0] == {**memory_body, "memory_tier": "short_term", "layer": "short_term"}
    assert resp.json()[0]["layer"] == "short_term"
    assert "memory_only" not in resp.json()[0]
    assert len(captured) == 1
    assert captured[0].limit == 2
    assert captured[0].offset == 0
    assert captured[0].cursor == "cursor-start"
    assert resp.headers["x-omi-memory-read-source"] == "memory_compatibility_projection"
    assert resp.headers["x-omi-memory-read-decision"] == "ok"
    assert resp.headers["x-omi-memory-next-cursor"] == "cursor-next-1"
    assert resp.headers["link"] == '<cursor-next-1>; rel="next"'
    assert resp.headers["cache-control"] == "no-store"
    assert "x-not-allowlisted" not in resp.headers


def test_enrolled_memory_fake_error_fails_closed_with_public_error_and_headers(client, auth_headers):
    """memory service errors fail closed instead of falling back to legacy data."""
    seed_memory("123", _memory_doc("legacy-not-fallback", "must not be returned"))

    def failing_memory_service(_params, _adapters):
        from utils.memory.v3.composed_get_service import V3ComposedResponse

        return V3ComposedResponse.error(503, "infrastructure_failure")

    with _override_memory_runtime(
        client, _runtime(enabled=True, source_decision="memory_read", service=failing_memory_service)
    ):
        resp = client.get("/v3/memories", headers=auth_headers)

    assert resp.status_code == 503
    assert resp.json() == {"detail": "infrastructure_failure"}
    assert resp.headers["x-omi-memory-read-source"] == "none"
    assert resp.headers["x-omi-memory-read-decision"] == "infrastructure_failure"
    assert resp.json() != [{"id": "legacy-not-fallback"}]


def test_malformed_memory_runtime_fails_closed_without_production_activation(client, auth_headers):
    """A memory_read decision without a fake service is a closed 503, not a production dependency lookup."""
    seed_memory("123", _memory_doc("legacy-malformed-runtime", "must not be returned"))

    with _override_memory_runtime(client, _runtime(enabled=True, source_decision="memory_read", service=None)):
        resp = client.get("/v3/memories", headers=auth_headers)

    assert resp.status_code == 503
    assert resp.json() == {"detail": "infrastructure_failure"}
    assert "x-omi-memory-read-source" not in resp.headers
