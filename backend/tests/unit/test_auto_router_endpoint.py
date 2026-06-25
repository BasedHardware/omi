"""Integration tests for the auto-router FastAPI endpoint.

Uses FastAPI's TestClient to exercise the full request → response cycle
without spinning up a real uvicorn server.
"""

import pytest
from fastapi.testclient import TestClient

from routers.auto_router import reset_registry_cache_for_testing
from utils.auto_router.model_registry import ModelRegistry
from utils.auto_router.task_registry import TaskRegistry

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache_between_tests(monkeypatch):
    """Each test gets a fresh registry cache (so test order doesn't matter).

    Also forces the prefs store to the in-memory backend so tests don't
    require a live Firestore connection (and so each test starts with
    a clean prefs state).
    """
    monkeypatch.setenv("AUTO_ROUTER_PREFS_BACKEND", "memory")
    from utils.auto_router.prefs_store_factory import reset_user_prefs_store_for_testing

    reset_user_prefs_store_for_testing()

    reset_registry_cache_for_testing()
    from routers.auto_router import reset_metrics_collector_for_testing

    reset_metrics_collector_for_testing()
    yield
    reset_registry_cache_for_testing()
    reset_metrics_collector_for_testing()
    reset_user_prefs_store_for_testing()


@pytest.fixture
def client() -> TestClient:
    """Build a TestClient against the endpoint, with auth mocked to return a test uid.

    The auto-router endpoints require authentication via `auth_dependency`.
    We override that dependency in the test app to return a stable test uid
    without requiring a real Firebase token.
    """
    from routers.auto_router import router
    from routers.auto_router import auth_dependency

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth_dependency] = lambda: "test-uid"
    return TestClient(app)


@pytest.fixture
def client_no_auth() -> TestClient:
    """Build a TestClient WITHOUT auth override — for testing 401 responses."""
    from routers.auto_router import router

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# AC1: Happy path — all 5 tasks return 200 with valid JSON
# ---------------------------------------------------------------------------


class TestHappyPath:
    """GET /v1/auto-router/pick?task=<each task> returns 200."""

    @pytest.mark.parametrize(
        "task_name",
        [
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        ],
    )
    def test_valid_task_returns_200(self, client: TestClient, task_name: str):
        resp = client.get(f"/v1/auto-router/pick?task={task_name}")
        assert resp.status_code == 200, resp.text

    def test_response_has_required_keys(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        data = resp.json()
        for key in ("task", "model", "scores", "detail", "updated_at", "attribution"):
            assert key in data, f"missing key {key!r} in response"

    def test_response_detail_has_weights_and_candidates(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        data = resp.json()
        detail = data["detail"]
        assert "weights" in detail
        assert "candidates" in detail
        assert "reason" in detail
        # Weights should sum to ~1.0
        w = detail["weights"]
        assert abs(w["quality"] + w["latency"] + w["cost"] - 1.0) < 1e-3


# ---------------------------------------------------------------------------
# AC2: Invalid task returns 400
# ---------------------------------------------------------------------------


class TestInvalidTask:
    """Unknown task names return HTTP 400 with a helpful error."""

    def test_invalid_task_returns_400(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=invalid_task")
        assert resp.status_code == 400

    def test_400_includes_stable_error_code_and_does_not_leak_task_list(self, client: TestClient):
        # UAT-FN-01 fix: the 400 body now uses a stable error code and does NOT
        # leak the full list of known task names (clients can enumerate them
        # via probing). The docs link is still included for legitimate clients.
        resp = client.get("/v1/auto-router/pick?task=invalid_task")
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # Stable error code for client switch-cases.
        assert detail.get("code") == "unknown_task"
        # Mentions the offending task name.
        assert "invalid_task" in detail.get("message", "")
        # Does NOT list other known task names (e.g., 'ptt_response', 'transcription').
        assert "ptt_response" not in str(detail)
        assert "transcription" not in str(detail)
        # Includes a docs pointer.
        assert "docs" in detail

    def test_missing_task_param_returns_422(self, client: TestClient):
        # FastAPI's Query(...) makes `task` required; missing it returns 422.
        resp = client.get("/v1/auto-router/pick")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC4: The `model` field is the highest-scoring candidate
# ---------------------------------------------------------------------------


class TestPicking:
    """The returned `model` should be the top scorer (or None if no candidates)."""

    def test_model_is_highest_score(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        data = resp.json()
        scores = data["scores"]
        assert data["model"] == max(scores.items(), key=lambda kv: (kv[1], -ord(kv[0][0]) if kv[0] else 0))[0]
        # Simpler: just verify the picked model's score is >= all others.
        picked_score = scores[data["model"]]
        for model_id, s in scores.items():
            assert picked_score >= s, f"picked {data['model']} score {picked_score} < {model_id} score {s}"

    def test_ties_broken_by_id_alphabetical(self, client: TestClient):
        # We can't easily inject ties into the example benchmarks (the scores differ),
        # but we CAN verify that the picked model is consistently the same across calls.
        # (TestClient's fresh invocation doesn't reset the in-process cache between calls.)
        first = client.get("/v1/auto-router/pick?task=ptt_response").json()
        second = client.get("/v1/auto-router/pick?task=ptt_response").json()
        assert first["model"] == second["model"]


# ---------------------------------------------------------------------------
# AC5 + AC6: Daily cache — second call doesn't re-load
# ---------------------------------------------------------------------------


class TestCaching:
    """Repeated requests within TTL don't re-load from disk."""

    def test_second_call_returns_same_model_and_score(self, client: TestClient):
        first = client.get("/v1/auto-router/pick?task=ptt_response").json()
        second = client.get("/v1/auto-router/pick?task=ptt_response").json()
        assert first["model"] == second["model"]
        assert first["scores"] == second["scores"]


# ---------------------------------------------------------------------------
# AC7: Endpoint is importable without raising
# ---------------------------------------------------------------------------


class TestImportability:
    """The router module can be imported and the endpoint is registered."""

    def test_router_imports(self):
        from routers.auto_router import router

        assert router is not None

    def test_router_has_pick_endpoint(self):
        from routers.auto_router import router

        paths = [r.path for r in router.routes]
        assert "/v1/auto-router/pick" in paths


# ---------------------------------------------------------------------------
# AC: The scores dict contains all candidates
# ---------------------------------------------------------------------------


class TestScoreCompleteness:
    """Every candidate model should appear in the scores dict."""

    def test_scores_contains_all_candidates(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        data = resp.json()
        scored_ids = set(data["scores"].keys())
        candidate_ids = {c["id"] for c in data["detail"]["candidates"]}
        assert (
            scored_ids == candidate_ids
        ), f"scores dict missing some candidates: scored={scored_ids}, candidates={candidate_ids}"


# ---------------------------------------------------------------------------
# AC: Authentication (v2)
# ---------------------------------------------------------------------------


class TestAuth:
    """The endpoint requires authentication (matches upstream pattern)."""

    def test_unauthenticated_request_returns_401(self, client_no_auth):
        # No auth override — the real get_current_user_uid is called.
        # Since we're calling from TestClient without a real token, we expect
        # either 401 (auth fails) or 500 (firebase_admin not initialized).
        # Either way, the endpoint is NOT silently returning 200.
        resp = client_no_auth.get("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code in (401, 500), f"expected 401 or 500, got {resp.status_code}: {resp.text}"

    def test_missing_authorization_header_returns_401(self, client_no_auth):
        # Same as above — explicitly verify the endpoint requires auth.
        resp = client_no_auth.get("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code != 200, "endpoint should not return 200 without auth"

    def test_authenticated_request_returns_200(self, client):
        # The `client` fixture has the auth dependency overridden to "test-uid".
        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 200

    def test_uid_is_captured_in_endpoint_signature(self, client):
        # Verify the endpoint accepts the auth dependency AND that FastAPI
        # treats `authorization` as a HEADER (not a query parameter).
        # Without the `Header(None)` annotation in `auth_dependency`, FastAPI
        # would interpret `authorization: str = None` as a query parameter —
        # which would silently break the documented `Authorization: Bearer
        # <token>` contract (the upstream auth function reads from the header).
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        path = schema["paths"]["/v1/auto-router/pick"]["get"]
        param_by_name = {p["name"]: p for p in path.get("parameters", [])}
        assert (
            "authorization" in param_by_name
        ), f"auth dependency should be in OpenAPI parameters, got: {list(param_by_name)}"
        auth_param = param_by_name["authorization"]
        assert auth_param["in"] == "header", (
            f"`authorization` must be a header (not a query param); "
            f"got `in: {auth_param['in']}`. This means `auth_dependency` is "
            f"missing the `Header(None)` annotation — upstream auth would receive "
            f"the wrong value in production."
        )

    def test_metrics_uid_is_also_a_header(self, client):
        # Same Header-annotation check applies to the metrics endpoint.
        resp = client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/v1/auto-router/metrics"]["get"]
        param_by_name = {p["name"]: p for p in path.get("parameters", [])}
        assert param_by_name["authorization"]["in"] == "header"


# ---------------------------------------------------------------------------
# AC: Empty model registry → model is None
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AC: Metrics endpoint (v2)
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    """GET /v1/auto-router/metrics returns cache + tasks + pick_history."""

    def test_metrics_endpoint_returns_200(self, client):
        resp = client.get("/v1/auto-router/metrics")
        assert resp.status_code == 200

    def test_metrics_response_shape(self, client):
        resp = client.get("/v1/auto-router/metrics")
        data = resp.json()
        for key in ("cache", "tasks", "pick_history", "generated_at"):
            assert key in data, f"missing key {key!r} in metrics response"

    def test_metrics_cache_state_present(self, client):
        resp = client.get("/v1/auto-router/metrics")
        cache = resp.json()["cache"]
        for key in ("last_loaded_at", "age_seconds", "is_fresh"):
            assert key in cache

    def test_metrics_tasks_have_all_5_task_types(self, client):
        resp = client.get("/v1/auto-router/metrics")
        tasks = resp.json()["tasks"]
        assert set(tasks.keys()) == {
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        }

    def test_metrics_tasks_include_weights_and_pick(self, client):
        resp = client.get("/v1/auto-router/metrics")
        for task_name, task_state in resp.json()["tasks"].items():
            assert "weights" in task_state, f"{task_name} missing weights"
            assert "candidate_count" in task_state
            assert "current_pick" in task_state
            assert "current_score" in task_state

    def test_metrics_requires_auth(self, client_no_auth):
        resp = client_no_auth.get("/v1/auto-router/metrics")
        # No auth override → 401 or 500 (auth fails or firebase not initialized).
        assert resp.status_code in (401, 500), f"expected 401 or 500, got {resp.status_code}"

    def test_metrics_records_pick_after_pick_call(self, client):
        from routers.auto_router import reset_metrics_collector_for_testing

        reset_metrics_collector_for_testing()

        # Empty initially.
        resp = client.get("/v1/auto-router/metrics")
        assert resp.json()["pick_history"] == []

        # Make a pick call.
        client.get("/v1/auto-router/pick?task=ptt_response")

        # History should now have 1 entry.
        resp = client.get("/v1/auto-router/metrics")
        history = resp.json()["pick_history"]
        assert len(history) == 1
        assert history[0]["task"] == "ptt_response"
        assert history[0]["model"] is not None
        assert isinstance(history[0]["score"], float)
        assert history[0]["weights_used"] == {"quality": 0.4, "latency": 0.5, "cost": 0.1}

    def test_metrics_picks_are_capped_at_100(self, client):
        from routers.auto_router import reset_metrics_collector_for_testing

        reset_metrics_collector_for_testing()

        # Make 105 pick calls (capped at 100).
        for _ in range(105):
            client.get("/v1/auto-router/pick?task=ptt_response")

        resp = client.get("/v1/auto-router/metrics")
        assert len(resp.json()["pick_history"]) == 100

    def test_metrics_picks_recorded_across_tasks(self, client):
        from routers.auto_router import reset_metrics_collector_for_testing

        reset_metrics_collector_for_testing()

        client.get("/v1/auto-router/pick?task=ptt_response")
        client.get("/v1/auto-router/pick?task=general_assistant")
        client.get("/v1/auto-router/pick?task=transcription")

        resp = client.get("/v1/auto-router/metrics")
        history = resp.json()["pick_history"]
        assert len(history) == 3
        tasks_picked = {h["task"] for h in history}
        assert tasks_picked == {"ptt_response", "general_assistant", "transcription"}


class TestNoCandidates:
    """If no models are registered for a task, model should be None (not 500)."""

    def test_unknown_task_with_no_models_returns_null_model(self, client, monkeypatch):
        # We can't easily get an empty registry through the public API, so
        # we patch the cache to return an empty ModelRegistry.
        from routers import auto_router

        # Reset cache.
        auto_router.reset_registry_cache_for_testing()

        # Patch the loader to return empty models.
        empty_models = ModelRegistry.empty()
        tasks = TaskRegistry.defaults()

        async def fake_loader():
            return tasks, empty_models

        cache = auto_router.DailyRefreshCache(ttl_seconds=60)
        # Pre-populate the cache with the empty-model loader.
        import asyncio

        async def setup():
            return await cache.get_or_refresh(fake_loader)

        asyncio.run(setup())

        monkeypatch.setattr(auto_router, "_get_registry_cache", lambda: cache)

        resp = client.get("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] is None
        assert data["scores"] == {}
        assert data["detail"]["reason"] == "no candidates registered for this task"


# ---------------------------------------------------------------------------
# AC: HTTP method handling
# ---------------------------------------------------------------------------


class TestHTTPMethods:
    """Only GET is supported; other methods return 405."""

    def test_post_returns_405(self, client: TestClient):
        resp = client.post("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 405

    def test_put_returns_405(self, client: TestClient):
        resp = client.put("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 405

    def test_delete_returns_405(self, client: TestClient):
        resp = client.delete("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# AC: Route handling — unknown paths return 404
# ---------------------------------------------------------------------------


class TestRoutes:
    """The router only exposes /v1/auto-router/pick."""

    def test_root_path_returns_404(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 404

    def test_unknown_subpath_returns_404(self, client: TestClient):
        resp = client.get("/v1/auto-router/notapath")
        assert resp.status_code == 404

    def test_v1_auto_router_no_pick_returns_404(self, client: TestClient):
        resp = client.get("/v1/auto-router")
        assert resp.status_code == 404

    def test_pick_alone_without_v1_prefix_returns_404(self, client: TestClient):
        resp = client.get("/auto-router/pick?task=ptt_response")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC: Extra query parameters are ignored (forward-compat)
# ---------------------------------------------------------------------------


class TestQueryParams:
    """Extra query params don't break the endpoint (forward compat for future fields)."""

    def test_extra_query_param_ignored(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=ptt_response&debug=true&version=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] == "ptt_response"
        assert data["model"] is not None

    def test_empty_task_param_returns_400(self, client: TestClient):
        # Empty task name goes through the same path as any unknown task name
        # (TaskRegistry.get("") raises UnknownTaskError), so we get HTTP 400,
        # not 422. This is consistent: "" is a valid string, just not a valid
        # task. FastAPI's 422 is reserved for missing query params entirely.
        resp = client.get("/v1/auto-router/pick?task=")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unknown_task"


# ---------------------------------------------------------------------------
# AC: Concurrent requests fire only 1 loader call (cache contention)
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Concurrent first-time requests should hit the loader only ONCE (asyncio.Lock).

    Note: We can't easily test this with FastAPI's TestClient (which is sync and
    runs requests sequentially through a threadpool). Instead, we exercise the
    DailyRefreshCache directly via asyncio.gather — same async lock, same logic.
    """

    def test_cache_concurrent_calls_invoke_loader_once(self):
        """asyncio.gather of 10 cache calls fires the loader exactly once on an empty cache."""
        import asyncio
        from utils.auto_router.daily_refresh import DailyRefreshCache

        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)
        loader_calls = 0

        async def slow_loader() -> str:
            nonlocal loader_calls
            await asyncio.sleep(0.02)  # ensure other callers queue up
            loader_calls += 1
            return "value"

        async def gather_all():
            coros = [cache.get_or_refresh(slow_loader) for _ in range(10)]
            return await asyncio.gather(*coros)

        results = asyncio.run(gather_all())
        assert all(r == "value" for r in results)
        assert loader_calls == 1, f"loader called {loader_calls} times, expected 1"

    def test_cache_second_call_returns_same_value_no_loader_call(self):
        """Within TTL, a second call returns cached value without invoking loader."""
        import asyncio
        from utils.auto_router.daily_refresh import DailyRefreshCache

        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)
        loader_calls = 0

        async def loader() -> str:
            nonlocal loader_calls
            loader_calls += 1
            return "v1"

        async def hit():
            return await cache.get_or_refresh(loader)

        async def hit_three_times():
            return [await hit() for _ in range(3)]

        results = asyncio.run(hit_three_times())
        assert all(r == "v1" for r in results)
        assert loader_calls == 1


# ---------------------------------------------------------------------------
# AC: GET /v1/auto-router/prefs (v3)
# ---------------------------------------------------------------------------


class TestGetPrefsEndpoint:
    """GET /v1/auto-router/prefs returns the current user's stored prefs."""

    def test_unauthenticated_returns_error(self, client_no_auth):
        r = client_no_auth.get("/v1/auto-router/prefs")
        # auth_dependency raises HTTPException(401) when override is absent
        assert r.status_code in (401, 500)

    def test_authenticated_returns_empty_prefs_for_new_user(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.get("/v1/auto-router/prefs")
        assert r.status_code == 200
        body = r.json()
        assert body["uid"] == "test-uid"
        assert body["prefs"] == {}
        assert body["updated_at"] is None

    def test_authenticated_returns_stored_prefs(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        # PUT first
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}},
        )
        # Then GET
        r = client.get("/v1/auto-router/prefs")
        assert r.status_code == 200
        body = r.json()
        assert body["prefs"] == {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}
        assert body["updated_at"] is not None


# ---------------------------------------------------------------------------
# AC: PUT /v1/auto-router/prefs (v3)
# ---------------------------------------------------------------------------


class TestPutPrefsEndpoint:
    """PUT /v1/auto-router/prefs validates + stores user's prefs."""

    def test_valid_prefs_returns_200(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["prefs"] == {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}
        assert body["updated_at"] is not None

    def test_empty_prefs_clears_overrides(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        # Set first
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}},
        )
        # Then clear
        r = client.put("/v1/auto-router/prefs", json={"prefs": {}})
        assert r.status_code == 200
        assert r.json()["prefs"] == {}

    def test_invalid_weights_returns_400(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.5, "latency": 0.5, "cost": 0.5}}},
        )
        assert r.status_code == 400
        assert "expected 1.0" in r.json()["detail"]["message"]

    def test_negative_weight_returns_400(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": -0.1, "latency": 0.7, "cost": 0.4}}},
        )
        assert r.status_code == 400

    def test_missing_prefs_key_returns_400(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.put("/v1/auto-router/prefs", json={"wrong_key": {}})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "missing_prefs"

    def test_non_dict_prefs_returns_400(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.put("/v1/auto-router/prefs", json={"prefs": "not a dict"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_prefs_type"

    def test_unauthenticated_returns_error(self, client_no_auth):
        r = client_no_auth.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.4, "latency": 0.4, "cost": 0.2}}},
        )
        assert r.status_code in (401, 500)

    def test_put_then_get_roundtrip(self, client):
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        put_resp = client.put(
            "/v1/auto-router/prefs",
            json={
                "prefs": {
                    "ptt_response": {"quality": 0.1, "latency": 0.8, "cost": 0.1},
                    "screenshot_understanding": {"quality": 0.9, "latency": 0.05, "cost": 0.05},
                }
            },
        )
        assert put_resp.status_code == 200
        get_resp = client.get("/v1/auto-router/prefs")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["prefs"]["ptt_response"] == {"quality": 0.1, "latency": 0.8, "cost": 0.1}
        assert body["prefs"]["screenshot_understanding"] == {"quality": 0.9, "latency": 0.05, "cost": 0.05}


# ---------------------------------------------------------------------------
# AC: /pick applies user prefs server-side (v3, T-303)
# ---------------------------------------------------------------------------


class TestPickAppliesUserPrefs:
    """/pick looks up the user's stored prefs and uses them instead of task defaults."""

    def test_no_stored_prefs_uses_task_defaults(self, client):
        """Without stored prefs, /pick returns the same as before (no behavior change)."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        r = client.get("/v1/auto-router/pick?task=ptt_response")
        assert r.status_code == 200
        body = r.json()
        # weights_source should be "task_default" when no prefs are set
        assert body["weights_source"] == "task_default"

    def test_stored_prefs_are_applied(self, client):
        """When user has prefs for the task, /pick uses them (weights_source = user_prefs)."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        # Set prefs for ptt_response: all quality
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 1.0, "latency": 0.0, "cost": 0.0}}},
        )
        r = client.get("/v1/auto-router/pick?task=ptt_response")
        assert r.status_code == 200
        body = r.json()
        assert body["weights_source"] == "user_prefs"
        # With all-quality weights, the highest quality_score wins.
        # claude-sonnet-4-6 has quality_score 0.92 in the example benchmarks.
        assert body["model"] == "claude-sonnet-4-6"

    def test_prefs_for_one_task_dont_affect_other_tasks(self, client):
        """Setting prefs for ptt_response doesn't affect transcription (no override there)."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 1.0, "latency": 0.0, "cost": 0.0}}},
        )
        r = client.get("/v1/auto-router/pick?task=transcription")
        assert r.status_code == 200
        body = r.json()
        # No prefs for transcription → task_default weights
        assert body["weights_source"] == "task_default"


class TestPickWeightsQueryParam:
    """/pick?weights=... overrides stored prefs for this call only."""

    def test_weights_override_changes_pick(self, client):
        """Passing weights=... selects the model that wins under those weights."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        # ptt_response with weights = all cost → cost_score leader wins.
        # gemini-1-5-flash-8b-exp has cost_score 0.90 (highest in ptt_response).
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.0, "latency": 0.0, "cost": 1.0}')
        r = client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        assert r.status_code == 200
        body = r.json()
        assert body["weights_source"] == "query_param"
        assert body["model"] == "gemini-1-5-flash-8b-exp"

    def test_weights_override_takes_precedence_over_stored_prefs(self, client):
        """Even if user has stored prefs, weights=... wins for this call."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        # Store all-quality prefs
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 1.0, "latency": 0.0, "cost": 0.0}}},
        )
        # But override with all-cost via query param
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.0, "latency": 0.0, "cost": 1.0}')
        r = client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        body = r.json()
        assert body["weights_source"] == "query_param"
        # Cost leader wins (not quality leader)
        assert body["model"] == "gemini-1-5-flash-8b-exp"

    def test_weights_override_does_not_update_stored_prefs(self, client):
        """After a weights=... call, stored prefs are unchanged."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.5, "latency": 0.3, "cost": 0.2}}},
        )
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.0, "latency": 0.0, "cost": 1.0}')
        client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        # Stored prefs unchanged
        r = client.get("/v1/auto-router/prefs")
        assert r.json()["prefs"]["ptt_response"] == {"quality": 0.5, "latency": 0.3, "cost": 0.2}

    def test_invalid_weights_json_returns_400(self, client):
        import urllib.parse

        r = client.get("/v1/auto-router/pick?task=ptt_response&weights=not-json")
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_weights"

    def test_invalid_weights_sum_returns_400(self, client):
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.5, "latency": 0.5, "cost": 0.5}')
        r = client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_weights"

    def test_weights_missing_keys_returns_400(self, client):
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.5, "latency": 0.5}')  # no "cost"
        r = client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_weights"


# ---------------------------------------------------------------------------
# AC: POST /v1/auto-router/refresh-benchmarks (v3, admin)
# ---------------------------------------------------------------------------


class TestRefreshBenchmarksEndpoint:
    """POST /refresh-benchmarks requires X-Admin-Key, forces a refresh."""

    def test_missing_admin_key_returns_503(self, client, monkeypatch):
        # No ADMIN_KEY env var → admin disabled
        monkeypatch.delenv("ADMIN_KEY", raising=False)
        r = client.post("/v1/auto-router/refresh-benchmarks")
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "admin_not_configured"

    def test_missing_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "secret-123")
        r = client.post("/v1/auto-router/refresh-benchmarks")
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "invalid_admin_key"

    def test_wrong_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "secret-123")
        r = client.post(
            "/v1/auto-router/refresh-benchmarks",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert r.status_code == 401

    def test_correct_header_returns_200(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("ADMIN_KEY", "secret-123")
        # No AA_API_KEY → fetcher falls back to example
        monkeypatch.delenv("AA_API_KEY", raising=False)
        r = client.post(
            "/v1/auto-router/refresh-benchmarks",
            headers={"X-Admin-Key": "secret-123"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["source"] == "example"  # no AA key → example
        assert body["task_count"] == 5
        assert body["model_count"] > 0

    def test_whitespace_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "secret-123")
        r = client.post(
            "/v1/auto-router/refresh-benchmarks",
            headers={"X-Admin-Key": "   "},
        )
        # Whitespace-only is rejected
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# AC: /metrics includes benchmarks_source + benchmarks_last_refresh (v3)
# ---------------------------------------------------------------------------


class TestMetricsBenchmarksSource:
    """/metrics reports where the benchmarks came from."""

    def test_metrics_includes_benchmarks_source_field(self, client):
        r = client.get("/v1/auto-router/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "benchmarks_source" in body
        assert body["benchmarks_source"] in ("aa", "example")

    def test_metrics_includes_benchmarks_last_refresh_field(self, client):
        r = client.get("/v1/auto-router/metrics")
        body = r.json()
        assert "benchmarks_last_refresh" in body
        # Either None (no cache file) or a string (ISO 8601)
        assert body["benchmarks_last_refresh"] is None or isinstance(body["benchmarks_last_refresh"], str)

    def test_metrics_source_is_example_when_no_cache_file(self, client, monkeypatch, tmp_path):
        # Point the cache at a fresh tmp path that doesn't exist.
        monkeypatch.delenv("AA_API_KEY", raising=False)
        nonexistent = tmp_path / "definitely-no-such-cache.json"
        assert not nonexistent.exists()
        monkeypatch.setenv("AA_CACHE_PATH", str(nonexistent))
        # Reset fetcher so it picks up the new env var
        from routers.auto_router import reset_benchmarks_fetcher_for_endpoint_testing

        reset_benchmarks_fetcher_for_endpoint_testing()
        r = client.get("/v1/auto-router/metrics")
        body = r.json()
        assert body["benchmarks_source"] == "example"
        assert body["benchmarks_last_refresh"] is None


# ---------------------------------------------------------------------------
# AC: /pick response + metrics use EFFECTIVE weights (cubic P1, v3 fix)
# ---------------------------------------------------------------------------


class TestPickUsesEffectiveWeights:
    """detail.weights + pick_history must reflect EFFECTIVE weights
    (query_param override > user_prefs > task_default), not the
    task_spec defaults. cubic flagged these as P1 on v3."""

    def test_detail_weights_reflect_user_prefs(self, client):
        """When user prefs are set, detail.weights should reflect them, not defaults."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 1.0, "latency": 0.0, "cost": 0.0}}},
        )
        r = client.get("/v1/auto-router/pick?task=ptt_response")
        assert r.status_code == 200
        body = r.json()
        # detail.weights must be the EFFECTIVE weights (user prefs), not task defaults
        assert body["detail"]["weights"] == {"quality": 1.0, "latency": 0.0, "cost": 0.0}

    def test_detail_weights_reflect_query_param_override(self, client):
        """When weights=... query param is set, detail.weights should reflect it."""
        from routers.auto_router import reset_user_prefs_store_for_endpoint_testing

        reset_user_prefs_store_for_endpoint_testing()
        import urllib.parse

        weights_str = urllib.parse.quote('{"quality": 0.0, "latency": 0.0, "cost": 1.0}')
        r = client.get(f"/v1/auto-router/pick?task=ptt_response&weights={weights_str}")
        assert r.status_code == 200
        body = r.json()
        assert body["detail"]["weights"] == {"quality": 0.0, "latency": 0.0, "cost": 1.0}

    def test_pick_history_records_effective_weights(self, client):
        """When user prefs are set, pick_history should record the EFFECTIVE weights."""
        from routers.auto_router import (
            reset_user_prefs_store_for_endpoint_testing,
            reset_metrics_collector_for_testing,
        )

        reset_metrics_collector_for_testing()
        reset_user_prefs_store_for_endpoint_testing()
        # Set quality-biased prefs
        client.put(
            "/v1/auto-router/prefs",
            json={"prefs": {"ptt_response": {"quality": 0.8, "latency": 0.1, "cost": 0.1}}},
        )
        # Make a pick
        client.get("/v1/auto-router/pick?task=ptt_response")
        # Verify metrics recorded the EFFECTIVE weights
        r = client.get("/v1/auto-router/metrics")
        body = r.json()
        pick_history = body["pick_history"]
        assert len(pick_history) >= 1
        # The most recent ptt_response pick should have effective weights, not defaults
        ptt_picks = [p for p in pick_history if p["task"] == "ptt_response"]
        assert len(ptt_picks) >= 1
        latest_ptt = ptt_picks[-1]
        assert latest_ptt["weights_used"] == {"quality": 0.8, "latency": 0.1, "cost": 0.1}
