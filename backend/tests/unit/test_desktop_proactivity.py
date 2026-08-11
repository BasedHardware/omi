from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from routers import desktop_proactivity


def request(operation: str = "proactive_extraction", *, cache_key: str | None = None):
    return desktop_proactivity.ProactiveCompletionRequest(
        operation=operation,
        messages=[{"role": "user", "content": "screen context"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            },
        },
        cache_key=cache_key,
    )


def test_operation_pins_lane_and_only_reasoning_enables_explicit_cache():
    extraction = desktop_proactivity._gateway_payload(request())
    reasoning = desktop_proactivity._gateway_payload(request("proactive_reasoning", cache_key="bucket-7-version-3"))

    assert extraction["model"] == "omi:auto:desktop-proactive-extraction"
    assert "prompt_cache_options" not in extraction
    assert reasoning["model"] == "omi:auto:desktop-proactive-reasoning"
    assert reasoning["prompt_cache_key"] == "bucket-7-version-3"
    assert reasoning["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}


def test_extraction_rejects_cache_key():
    with pytest.raises(ValueError, match="only for proactive_reasoning"):
        request(cache_key="not-allowed")


@pytest.mark.asyncio
async def test_quota_is_allowed_based_and_fails_closed(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity.redis_db, "check_rate_limit", lambda *_: (False, 0, 19))
    with pytest.raises(desktop_proactivity.HTTPException) as exhausted:
        await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    assert exhausted.value.status_code == 429
    assert exhausted.value.headers == {"Retry-After": "19"}

    monkeypatch.setattr(
        desktop_proactivity.redis_db,
        "check_rate_limit",
        lambda *_: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.REASONING)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_facade_adds_provenance_and_cache_envelope(monkeypatch):
    seen = {}

    class GatewayClient:
        async def post(self, url, *, headers, json):
            seen.update(url=url, headers=headers, json=json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "model": "gpt-5.6-luna-2026-08-01",
                    "choices": [{"message": {"content": '{"summary":"ok"}'}}],
                    "usage": {
                        "prompt_tokens": 1200,
                        "prompt_tokens_details": {"cached_tokens": 1024, "cache_write_tokens": 0},
                    },
                },
            )

    class Semaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    async def allow(*_):
        return None

    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_base_url", lambda: "http://gateway")
    monkeypatch.setattr(
        desktop_proactivity,
        "llm_gateway_headers",
        lambda **_: {"Authorization": "Bearer service", "X-Omi-Service-Caller": "backend"},
    )

    result = await desktop_proactivity.proactive_completion(
        request("proactive_reasoning", cache_key="bucket-1"), uid="user-1"
    )

    assert seen["json"]["model"] == "omi:auto:desktop-proactive-reasoning"
    assert seen["headers"]["X-Omi-User-Uid"] == "user-1"
    assert result.lane == "omi:auto:desktop-proactive-reasoning"
    assert result.provider_model == "gpt-5.6-luna-2026-08-01"
    assert result.usage.cached_tokens == 1024
    assert result.cache_write is False
    assert result.fallback_class == "unknown"
