from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from routers import desktop_proactivity
from utils.subscription import NEO_DESKTOP_GRANDFATHER_CUTOFF


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
    parts = reasoning["messages"][0]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["prompt_cache_breakpoint"] == {"mode": "explicit"}


def test_request_requires_strict_valid_nested_json_schema():
    payload = request().model_dump(mode="json")
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": "result",
            "strict": False,
            "schema": {"type": "object"},
        },
    }
    with pytest.raises(ValueError, match="strict must be true"):
        desktop_proactivity.ProactiveCompletionRequest(**payload)

    payload["response_format"]["json_schema"]["strict"] = True
    payload["response_format"]["json_schema"]["schema"] = {"type": "not-a-json-schema-type"}
    with pytest.raises(ValueError, match="schema is invalid"):
        desktop_proactivity.ProactiveCompletionRequest(**payload)


def test_extraction_rejects_cache_key():
    with pytest.raises(ValueError, match="only for proactive_reasoning"):
        request(cache_key="not-allowed")


def test_facade_rejects_gateway_content_that_breaks_requested_schema():
    with pytest.raises(desktop_proactivity.HTTPException) as invalid:
        desktop_proactivity._validate_gateway_output(
            {
                "choices": [{"message": {"content": '{"summary": 3}'}}],
            },
            request(),
        )
    assert invalid.value.status_code == 502


@pytest.mark.asyncio
async def test_quota_is_allowed_based_and_fails_closed(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda _uid: None)
    monkeypatch.setattr(desktop_proactivity.redis_db, "reserve_rate_limit", lambda *_: (False, 0, 19))
    with pytest.raises(desktop_proactivity.HTTPException) as exhausted:
        await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    assert exhausted.value.status_code == 429
    assert exhausted.value.headers == {"Retry-After": "19"}

    monkeypatch.setattr(
        desktop_proactivity.redis_db,
        "reserve_rate_limit",
        lambda *_: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.REASONING)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_limit"),
    [
        (desktop_proactivity.ProactiveOperation.EXTRACTION, 200),
        (desktop_proactivity.ProactiveOperation.REASONING, 100),
    ],
)
async def test_quota_matches_expanded_director_budget(monkeypatch, operation, expected_limit):
    observed = {}

    async def run_blocking(_, function, *args):
        return function(*args)

    def reserve_rate_limit(uid, key, limit, window_seconds):
        observed.update(uid=uid, key=key, limit=limit, window_seconds=window_seconds)
        return True, 1, 0

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda _uid: None)
    monkeypatch.setattr(desktop_proactivity.redis_db, "reserve_rate_limit", reserve_rate_limit)

    await desktop_proactivity._consume_quota("user-1", operation)

    assert observed["uid"] == "user-1"
    assert observed["key"] == f"desktop_{operation.value}"
    assert observed["limit"] == expected_limit
    assert observed["window_seconds"] == 24 * 60 * 60


@pytest.mark.parametrize(
    ("plan", "reasoning_limit", "extraction_limit"),
    [
        (desktop_proactivity.PlanType.basic, 100, 200),
        (desktop_proactivity.PlanType.operator, 200, 400),
        (desktop_proactivity.PlanType.architect, 400, 800),
    ],
)
def test_quota_limit_scales_from_server_verified_subscription(plan, reasoning_limit, extraction_limit):
    subscription = SimpleNamespace(plan=plan)
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.REASONING, subscription
        )
        == reasoning_limit
    )
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.EXTRACTION, subscription
        )
        == extraction_limit
    )


def test_post_cutoff_neo_uses_free_quota_while_grandfathered_neo_keeps_full_quota():
    cutoff = NEO_DESKTOP_GRANDFATHER_CUTOFF
    post_cutoff = SimpleNamespace(plan=desktop_proactivity.PlanType.unlimited, current_period_start=cutoff)
    grandfathered = SimpleNamespace(plan=desktop_proactivity.PlanType.unlimited, current_period_start=cutoff - 1)

    assert (
        desktop_proactivity._quota_limit_for_subscription(desktop_proactivity.ProactiveOperation.REASONING, post_cutoff)
        == 100
    )
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.REASONING, grandfathered
        )
        == 200
    )


@pytest.mark.asyncio
async def test_offline_stub_honors_schema_without_gateway_or_quota(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("offline stub must bypass quota and gateway")

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: True)
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", forbidden)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", forbidden)

    result = await desktop_proactivity.proactive_completion(request("proactive_reasoning"), uid="offline-user")

    assert result.provider_model == "omi-offline-stub"
    assert result.fallback_class == "offline_stub"
    content = json.loads(result.response["choices"][0]["message"]["content"])
    assert content == {"summary": ""}


@pytest.mark.asyncio
async def test_gateway_failure_releases_reserved_quota(monkeypatch):
    released = []

    class GatewayClient:
        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("gateway unavailable")

    class Semaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    async def allow(*_):
        return None

    async def release(uid, operation):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(request(), uid="user-1")

    assert unavailable.value.status_code == 502
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]


def test_dev_direct_provider_fallback_is_scoped_to_proactivity(monkeypatch):
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    fallbacks = []
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))

    provider = desktop_proactivity._proactive_provider_request(request("proactive_extraction"), "user-1", "request-1")

    assert provider.url == "https://api.openai.com/v1/chat/completions"
    assert provider.headers == {"Authorization": "Bearer dev-provider-key", "Content-Type": "application/json"}
    assert provider.payload["model"] == "gpt-5-nano"
    assert "prompt_cache_key" not in provider.payload
    assert "prompt_cache_options" not in provider.payload
    assert "metadata" not in provider.payload
    assert provider.payload["reasoning_effort"] == "minimal"
    assert provider.fallback_class == "dev_direct_openai"
    assert fallbacks[0]["component"] == "llm_gateway"

    reasoning_provider = desktop_proactivity._proactive_provider_request(
        request("proactive_reasoning"), "user-1", "request-2"
    )
    assert reasoning_provider.payload["model"] == "gpt-5.6-luna"
    assert reasoning_provider.payload["reasoning_effort"] == "low"


def test_direct_provider_fallback_fails_closed_outside_dev(monkeypatch):
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "prod")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "prod-provider-key")

    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        desktop_proactivity._proactive_provider_request(request(), "user-1", "request-1")

    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "Proactive model gateway is not configured"


def test_development_release_channel_allows_direct_recovery_without_env_stage(monkeypatch):
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.setenv("OMI_DESKTOP_BACKEND_RELEASE_CHANNEL", "development")

    assert desktop_proactivity._dev_direct_provider_allowed() is True


def test_configured_gateway_remains_authoritative(monkeypatch):
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://172.16.63.232/")
    monkeypatch.setattr(
        desktop_proactivity,
        "llm_gateway_headers",
        lambda **_: {"Authorization": "Bearer gateway"},
    )

    provider = desktop_proactivity._proactive_provider_request(request("proactive_reasoning"), "user-1", "request-1")

    assert provider.url == "http://172.16.63.232/v1/chat/completions"
    assert provider.headers["X-Omi-User-Uid"] == "user-1"
    assert provider.headers["X-Omi-Request-ID"] == "request-1"
    assert provider.payload["model"] == "omi:auto:desktop-proactive-reasoning"
    assert provider.fallback_class == "none"


@pytest.mark.asyncio
async def test_provider_configuration_failure_releases_reserved_quota(monkeypatch):
    released = []

    async def allow(*_):
        return None

    async def release(uid, operation):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(
        desktop_proactivity,
        "_proactive_provider_request",
        lambda *_: (_ for _ in ()).throw(desktop_proactivity.HTTPException(status_code=503, detail="missing")),
    )

    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(request(), uid="user-1")

    assert unavailable.value.status_code == 503
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]


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

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
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
    assert result.fallback_class == "none"
