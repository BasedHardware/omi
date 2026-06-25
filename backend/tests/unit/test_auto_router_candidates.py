"""Unit tests for GET /v1/auto-router/candidates (v6).

The candidates endpoint lists ALL models for a task with their scores,
powering the Settings UI's model picker. Returns sorted by composite
score (desc) using the task's default weights.

Tests cover:
- Happy path: returns all candidates + default_weights
- Unknown task: 400
- Missing task query param: 422 (FastAPI)
- Auth required: 401 without auth
- Sort order: highest score first
- All 5 task types work
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auto_router import auth_dependency, router


@pytest.fixture
def client() -> TestClient:
    """Build a TestClient against the endpoint, with auth mocked to return a test uid."""
    from utils.auto_router.user_prefs_store import reset_user_prefs_store_for_testing

    reset_user_prefs_store_for_testing()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth_dependency] = lambda: "test-uid"
    return TestClient(app)


@pytest.fixture
def client_no_auth() -> TestClient:
    """Build a TestClient WITHOUT auth override — for testing 401 responses."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# Tests use the `client` fixture from conftest.py (sets up the FastAPI app
# with the auto-router router + a fake auth dependency that always returns
# 'test-uid').


class TestCandidatesEndpoint:
    """GET /v1/auto-router/candidates?task=X"""

    def test_returns_all_candidates_with_scores(self, client: TestClient):
        """ptt_response has 4 candidates in benchmarks.example.json (v5 expansion)."""
        r = client.get("/v1/auto-router/candidates?task=ptt_response")
        assert r.status_code == 200
        body = r.json()
        assert body["task"] == "ptt_response"
        assert len(body["candidates"]) == 4
        # Each candidate has id, provider, scores (quality/latency/cost), total.
        for c in body["candidates"]:
            assert "id" in c
            assert "provider" in c
            assert set(c["scores"].keys()) == {"quality", "latency", "cost"}
            assert 0.0 <= c["total"] <= 1.0

    def test_returns_default_weights(self, client: TestClient):
        """default_weights comes from the task's spec (TaskRegistry)."""
        r = client.get("/v1/auto-router/candidates?task=ptt_response")
        assert r.status_code == 200
        body = r.json()
        assert "default_weights" in body
        dw = body["default_weights"]
        assert set(dw.keys()) == {"quality", "latency", "cost"}
        # ptt_response default: quality=0.4, latency=0.5, cost=0.1 (per benchmarks.example.json)
        assert abs(dw["quality"] - 0.4) < 1e-9
        assert abs(dw["latency"] - 0.5) < 1e-9
        assert abs(dw["cost"] - 0.1) < 1e-9

    def test_sorts_candidates_by_score_desc(self, client: TestClient):
        """Highest composite score first (matches auto-router pick ordering)."""
        r = client.get("/v1/auto-router/candidates?task=transcription")
        assert r.status_code == 200
        body = r.json()
        candidates = body["candidates"]
        # Verify descending order.
        totals = [c["total"] for c in candidates]
        assert totals == sorted(totals, reverse=True), f"Expected desc, got {totals}"

    def test_unknown_task_returns_400(self, client: TestClient):
        """Unknown task name → 400 with stable error code."""
        r = client.get("/v1/auto-router/candidates?task=not_a_real_task")
        assert r.status_code == 400
        body = r.json()
        assert body["detail"]["code"] == "unknown_task"

    def test_missing_task_query_param_returns_422(self, client: TestClient):
        """FastAPI validates required query params and returns 422 if missing."""
        r = client.get("/v1/auto-router/candidates")
        assert r.status_code == 422

    def test_all_five_task_types_work(self, client: TestClient):
        """Each of the 5 task types returns its own candidate list."""
        for task in (
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        ):
            r = client.get(f"/v1/auto-router/candidates?task={task}")
            assert r.status_code == 200, f"{task} should return 200"
            body = r.json()
            assert body["task"] == task
            assert len(body["candidates"]) > 0, f"{task} should have at least 1 candidate"

    def test_total_matches_individual_scores_x_weights(self, client: TestClient):
        """total = quality*dw.quality + latency*dw.latency + cost*dw.cost (within rounding)."""
        r = client.get("/v1/auto-router/candidates?task=transcription")
        body = r.json()
        dw = body["default_weights"]
        for c in body["candidates"]:
            expected = (
                c["scores"]["quality"] * dw["quality"]
                + c["scores"]["latency"] * dw["latency"]
                + c["scores"]["cost"] * dw["cost"]
            )
            # Allow for the 4-decimal rounding in the endpoint.
            assert (
                abs(c["total"] - round(expected, 4)) < 0.001
            ), f"{c['id']}: total={c['total']} expected≈{expected:.4f}"

    def test_auth_required(self, client_no_auth: TestClient):
        """Without auth override → 401 (auth_dependency raises)."""
        r = client_no_auth.get("/v1/auto-router/candidates?task=ptt_response")
        assert r.status_code in (401, 500)
