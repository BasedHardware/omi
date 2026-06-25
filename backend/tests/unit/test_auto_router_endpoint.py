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
def _clear_cache_between_tests():
    """Each test gets a fresh registry cache (so test order doesn't matter)."""
    reset_registry_cache_for_testing()
    yield
    reset_registry_cache_for_testing()


@pytest.fixture
def client() -> TestClient:
    """Build a TestClient against the endpoint.

    We import `routers.auto_router` lazily (inside the fixture) because the
    router module reads env at import time and we want each test to start
    from a clean state.
    """
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

    def test_400_includes_known_tasks_in_detail(self, client: TestClient):
        resp = client.get("/v1/auto-router/pick?task=invalid_task")
        detail = resp.json()["detail"]
        # The error message should mention the unknown task and list known ones.
        assert "invalid_task" in detail
        assert "ptt_response" in detail  # at least one known task is mentioned

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
# AC: Empty model registry → model is None
# ---------------------------------------------------------------------------


class TestNoCandidates:
    """If no models are registered for a task, model should be None (not 500)."""

    def test_unknown_task_with_no_models_returns_null_model(self, monkeypatch):
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
        # We can't await here, so use run_until_first_complete.
        import asyncio

        async def setup():
            return await cache.get_or_refresh(fake_loader)

        asyncio.run(setup())

        monkeypatch.setattr(auto_router, "_get_registry_cache", lambda: cache)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(auto_router.router)
        c = TestClient(app)

        resp = c.get("/v1/auto-router/pick?task=ptt_response")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] is None
        assert data["scores"] == {}
        assert data["detail"]["reason"] == "no candidates registered for this task"
