from __future__ import annotations

import httpx

from llm_gateway.gateway._private.benchmarks_fetcher import AA_UNCOVERED_TASKS, BenchmarksFetcher


async def test_fetch_uses_committed_default_when_aa_key_is_missing(monkeypatch):
    monkeypatch.delenv("AA_API_KEY", raising=False)

    data, source, refreshed_at = await BenchmarksFetcher().fetch()

    assert source == "example"
    assert refreshed_at is None
    assert {task["name"] for task in data["tasks"]} >= AA_UNCOVERED_TASKS
    assert data["models"]["transcription"]
    assert data["models"]["screenshot_embedding"]


async def test_fetch_merges_uncovered_tasks_from_committed_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AA_API_KEY", "test-key")

    def aa_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "aa-model",
                        "model_creator": {"name": "AA"},
                        "evaluations": [{"value": 0.8}],
                        "median_latency_seconds": 1.0,
                        "pricing": {"price_1m_input_tokens_usd": 2.0},
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(aa_response)) as client:
        data, source, refreshed_at = await BenchmarksFetcher(
            cache_path=tmp_path / "benchmarks.json", http_client=client
        ).fetch()

    assert source == "aa"
    assert refreshed_at is not None
    assert data["models"]["ptt_response"][0]["id"] == "aa-model"
    assert data["models"]["transcription"]
    assert data["models"]["screenshot_embedding"]
