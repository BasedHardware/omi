from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import Response

from llm_gateway.gateway.config_loader import load_gateway_config
from routers import desktop_proactivity
from utils.subscription import (
    DESKTOP_ACCESS_TIER_ARCHITECT,
    DESKTOP_ACCESS_TIER_FREE,
    DESKTOP_ACCESS_TIER_FULL,
    NEO_DESKTOP_GRANDFATHER_CUTOFF,
)

# The provider ignores a cached prefix under 1024 tokens, so any test that expects
# explicit caching to engage must carry a stable block that clears that floor.
CACHEABLE_STABLE_PROMPT = "stable bucket instructions for the proactive director. " * 400


def request(
    operation: str = "proactive_extraction",
    *,
    cache_key: str | None = None,
    messages: list[dict] | None = None,
    max_completion_tokens: int | None = None,
):
    kwargs: dict[str, int] = {}
    if max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = max_completion_tokens
    return desktop_proactivity.ProactiveCompletionRequest(
        operation=operation,
        messages=messages or [{"role": "user", "content": "screen context"}],
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
        **kwargs,
    )


def test_operation_pins_lane_and_only_reasoning_enables_explicit_cache():
    extraction = desktop_proactivity._gateway_payload(request())
    reasoning = desktop_proactivity._gateway_payload(
        request(
            "proactive_reasoning",
            cache_key="bucket-7-version-3",
            messages=[{"role": "user", "content": CACHEABLE_STABLE_PROMPT}],
        )
    )

    assert extraction["model"] == "omi:auto:desktop-proactive-extraction"
    assert "prompt_cache_options" not in extraction
    assert reasoning["model"] == "omi:auto:desktop-proactive-reasoning"
    assert reasoning["prompt_cache_key"] == "bucket-7-version-3"
    assert reasoning["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    parts = reasoning["messages"][0]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["prompt_cache_breakpoint"] == {"mode": "explicit"}


def test_stable_block_under_provider_minimum_is_not_marked_for_cache():
    """A prefix the provider will never serve back must not be marked or keyed.

    The write is billed at a premium over fresh input, so paying for one that can
    never be read is strictly worse than not caching at all.
    """
    payload = desktop_proactivity._gateway_payload(
        request(
            "proactive_reasoning",
            cache_key="bucket-7-version-3",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "short stable block"},
                        {"type": "text", "text": "captured at: 2026-08-15T16:00:00Z"},
                    ],
                }
            ],
        )
    )

    assert "prompt_cache_key" not in payload
    assert "prompt_cache_options" not in payload
    parts = payload["messages"][0]["content"]
    assert not any(isinstance(part, dict) and "prompt_cache_breakpoint" in part for part in parts)


def test_reasoning_cache_breakpoint_precedes_volatile_text_and_image():
    def parts_for(captured_at: str):
        request_value = request("proactive_reasoning", cache_key="bucket-7-version-3")
        request_value.messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CACHEABLE_STABLE_PROMPT},
                    {"type": "text", "text": f"captured at: {captured_at}"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"}},
                ],
            }
        ]
        return desktop_proactivity._gateway_payload(request_value)["messages"][0]["content"]

    parts = parts_for("2026-08-13T16:00:00Z")
    later_parts = parts_for("2026-08-13T16:00:01Z")

    assert parts[0] == {"type": "text", "text": CACHEABLE_STABLE_PROMPT}
    assert parts[1]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert parts[2]["text"].startswith("captured at:")
    assert parts[3]["type"] == "image_url"
    assert parts[:2] == later_parts[:2]
    assert parts[2:] != later_parts[2:]


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
    assert invalid.value.status_code == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    assert invalid.value.detail == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_DETAIL


@pytest.mark.asyncio
async def test_quota_is_allowed_based_and_fails_closed(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_proactivity.redis_db, "reserve_rate_limit", lambda *_: (False, 0, 19))
    with pytest.raises(desktop_proactivity.HTTPException) as exhausted:
        await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    assert exhausted.value.status_code == 429
    assert exhausted.value.headers == {
        "Retry-After": "19",
        "X-Proactive-Quota-Limit": "150",
        "X-Proactive-Quota-Remaining": "0",
        "X-Proactive-Quota-Reset": "19",
    }

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
        (desktop_proactivity.ProactiveOperation.EXTRACTION, 150),
        (desktop_proactivity.ProactiveOperation.REASONING, 60),
    ],
)
async def test_quota_reservation_uses_the_free_row_and_daily_window(monkeypatch, operation, expected_limit):
    observed = {}

    async def run_blocking(_, function, *args, **kwargs):
        return function(*args, **kwargs)

    def reserve_rate_limit(uid, key, limit, window_seconds):
        observed.update(uid=uid, key=key, limit=limit, window_seconds=window_seconds)
        return True, 1, 0

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_proactivity.redis_db, "reserve_rate_limit", reserve_rate_limit)

    await desktop_proactivity._consume_quota("user-1", operation)

    assert observed["uid"] == "user-1"
    assert observed["key"] == f"desktop_{operation.value}"
    assert observed["limit"] == expected_limit
    assert observed["window_seconds"] == 24 * 60 * 60


@pytest.mark.asyncio
async def test_quota_headers_present_on_success(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        desktop_proactivity.redis_db,
        "reserve_rate_limit",
        lambda *_: (True, 12, 3600),
    )

    state = await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    assert state == desktop_proactivity.ProactiveQuotaState(limit=150, remaining=12, reset_seconds=3600)

    response = Response()
    desktop_proactivity._apply_quota_headers(response, state)
    assert response.headers["X-Proactive-Quota-Limit"] == "150"
    assert response.headers["X-Proactive-Quota-Remaining"] == "12"
    assert response.headers["X-Proactive-Quota-Reset"] == "3600"
    assert "retry-after" not in {name.lower() for name in response.headers.keys()}


@pytest.mark.asyncio
async def test_completion_success_attaches_quota_headers(monkeypatch):
    class GatewayClient:
        async def post(self, url, *, headers, json):
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "model": "gpt-5.6-luna",
                    "choices": [{"message": {"content": '{"summary":"ok"}'}}],
                    "usage": {"prompt_tokens": 8},
                },
            )

    class Semaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    async def consume(*_):
        return desktop_proactivity.ProactiveQuotaState(limit=200, remaining=12, reset_seconds=3600)

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    response = Response()
    result = await desktop_proactivity.proactive_completion(request(), response, uid="user-1")
    assert result.provider_model == "gpt-5.6-luna"
    assert response.headers["X-Proactive-Quota-Limit"] == "200"
    assert response.headers["X-Proactive-Quota-Remaining"] == "12"
    assert response.headers["X-Proactive-Quota-Reset"] == "3600"


def test_release_after_delete_does_not_go_negative():
    import fakeredis

    client = fakeredis.FakeRedis()
    script = client.register_script(desktop_proactivity.redis_db._RATE_LIMIT_RELEASE_LUA_SOURCE)
    key = "rl:desktop_proactive_extraction:user-1"

    remaining = script(keys=[key], args=[])
    assert int(remaining) == 0
    stored = client.get(key)
    assert stored is None or int(stored) >= 0

    client.set(key, 3)
    remaining = script(keys=[key], args=[])
    assert int(remaining) == 2
    assert int(client.get(key)) == 2

    client.delete(key)
    remaining = script(keys=[key], args=[])
    assert int(remaining) == 0
    stored = client.get(key)
    if stored is not None:
        assert int(stored) >= 0


@pytest.mark.parametrize(
    ("tier", "extraction_limit", "reasoning_limit"),
    [
        (DESKTOP_ACCESS_TIER_FREE, 150, 60),
        (DESKTOP_ACCESS_TIER_FULL, 1000, 500),
        (DESKTOP_ACCESS_TIER_ARCHITECT, 2000, 1000),
    ],
)
def test_each_tier_resolves_to_its_exact_limit_pair(monkeypatch, tier, extraction_limit, reasoning_limit):
    monkeypatch.setattr(desktop_proactivity, "effective_desktop_access_tier", lambda *_args, **_kwargs: tier)
    subscription = SimpleNamespace(plan=desktop_proactivity.PlanType.basic)
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.EXTRACTION, subscription
        )
        == extraction_limit
    )
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.REASONING, subscription
        )
        == reasoning_limit
    )


def test_unknown_tier_falls_back_to_free_row_without_raising(monkeypatch):
    monkeypatch.setattr(
        desktop_proactivity, "effective_desktop_access_tier", lambda *_args, **_kwargs: "desktop_does_not_exist"
    )
    subscription = SimpleNamespace(plan=desktop_proactivity.PlanType.basic)
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.EXTRACTION, subscription
        )
        == 150
    )
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.REASONING, subscription
        )
        == 60
    )


@pytest.mark.parametrize(
    ("plan", "reasoning_limit", "extraction_limit"),
    [
        (desktop_proactivity.PlanType.basic, 60, 150),
        (desktop_proactivity.PlanType.operator, 500, 1000),
        (desktop_proactivity.PlanType.architect, 1000, 2000),
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
        == 60
    )
    assert (
        desktop_proactivity._quota_limit_for_subscription(
            desktop_proactivity.ProactiveOperation.REASONING, grandfathered
        )
        == 500
    )


@pytest.mark.asyncio
async def test_offline_stub_honors_schema_without_gateway_or_quota(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("offline stub must bypass quota and gateway")

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: True)
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", forbidden)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", forbidden)

    result = await desktop_proactivity.proactive_completion(
        request("proactive_reasoning"), Response(), uid="offline-user"
    )

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
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

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


def test_dev_direct_keeps_cache_breakpoint_so_reads_can_hit(monkeypatch):
    """The direct path must not discard the only readable boundary in the prompt.

    The client packs the stable prompt, the volatile frame metadata and the
    screenshot into one user message. The provider serves a cache read only from a
    prefix ending on a message boundary or an explicit breakpoint, so dropping the
    breakpoint charges a full write per call that no later call can ever read.
    """
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: None)

    provider = desktop_proactivity._proactive_provider_request(
        request(
            "proactive_reasoning",
            cache_key="bucket-7-version-3",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": CACHEABLE_STABLE_PROMPT},
                        {"type": "text", "text": "captured at: 2026-08-15T16:00:00Z"},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"}},
                    ],
                }
            ],
        ),
        "user-1",
        "request-3",
    )

    parts = provider.payload["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": CACHEABLE_STABLE_PROMPT}
    assert parts[1]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert parts[2]["text"].startswith("captured at:")
    # prompt_cache_key is a real OpenAI request field; the options/metadata wrappers
    # are gateway-only extensions the provider would reject.
    assert provider.payload["prompt_cache_key"] == "bucket-7-version-3"
    assert "prompt_cache_options" not in provider.payload
    assert "metadata" not in provider.payload


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


def test_length_retry_gate_is_shape_scoped_and_covers_reasoning():
    empty = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
    truncated = {"choices": [{"finish_reason": "length", "message": {"content": '{"summary":'}}]}
    truncated_scalar = {"choices": [{"finish_reason": "length", "message": {"content": '{"summary":1'}}]}
    truncated_literal = {"choices": [{"finish_reason": "length", "message": {"content": '{"summary":true'}}]}
    schema_mismatch = {"choices": [{"finish_reason": "length", "message": {"content": '{"summary":3}'}}]}
    malformed_shape = {"choices": [{"finish_reason": "length", "message": {"content": None}}]}
    refusal = {"choices": [{"finish_reason": "length", "message": {"content": None, "refusal": "not allowed"}}]}
    stop = {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}

    assert desktop_proactivity._should_retry_truncated_structured_output(
        empty, request(), attempted_max_completion_tokens=1024
    )
    assert desktop_proactivity._should_retry_truncated_structured_output(
        truncated, request(), attempted_max_completion_tokens=1024
    )
    assert desktop_proactivity._should_retry_truncated_structured_output(
        truncated_scalar, request(), attempted_max_completion_tokens=1024
    )
    assert desktop_proactivity._should_retry_truncated_structured_output(
        truncated_literal, request(), attempted_max_completion_tokens=1024
    )
    assert desktop_proactivity._should_retry_truncated_structured_output(
        empty, request("proactive_reasoning", max_completion_tokens=800), attempted_max_completion_tokens=2400
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        schema_mismatch, request(), attempted_max_completion_tokens=1024
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        malformed_shape, request(), attempted_max_completion_tokens=1024
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        refusal, request(), attempted_max_completion_tokens=1024
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        stop, request(), attempted_max_completion_tokens=1024
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        empty, request(), attempted_max_completion_tokens=2400
    )
    assert not desktop_proactivity._should_retry_truncated_structured_output(
        empty,
        request("proactive_reasoning", max_completion_tokens=800),
        attempted_max_completion_tokens=4096,
    )


@pytest.mark.asyncio
async def test_direct_extraction_retries_length_once_without_extra_quota_reservation(monkeypatch):
    calls = []
    consumed = []
    fallbacks = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            calls.append((url, headers, json))
            body = (
                {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
                if len(calls) == 1
                else {
                    "model": "gpt-5-nano",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                }
            )
            return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    class Semaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    async def consume(uid, operation):
        consumed.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())

    result = await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

    assert len(calls) == 2
    assert calls[0][2]["max_completion_tokens"] == 1024
    assert calls[1][2]["max_completion_tokens"] == 2400
    assert consumed == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
    assert result.response["choices"][0]["message"]["content"] == '{"summary":"ok"}'
    assert len(fallbacks) == 2
    assert fallbacks[0] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "gateway",
        "to_mode": "direct_openai",
        "reason": "config_incomplete",
        "outcome": "recovered",
        "log": None,
    }
    assert fallbacks[1] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "direct_openai",
        "to_mode": "direct_openai_retry",
        "reason": "capability_mismatch",
        "outcome": "recovered",
        "log": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("final_failure", ["invalid", "provider"])
async def test_direct_extraction_length_retry_releases_quota_once_after_final_failure(monkeypatch, final_failure):
    calls = []
    released = []
    fallbacks = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            calls.append(json)
            if len(calls) == 2 and final_failure == "provider":
                raise httpx.ConnectError("provider unavailable")
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
            )

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
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())

    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

    assert unavailable.value.status_code == (
        502 if final_failure == "provider" else desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    )
    assert [payload["max_completion_tokens"] for payload in calls] == [1024, 2400]
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
    assert len(fallbacks) == 2
    assert fallbacks[0]["from_mode"] == "gateway"
    assert fallbacks[0]["to_mode"] == "direct_openai"
    assert fallbacks[0]["outcome"] == "recovered"
    assert fallbacks[1]["component"] == "llm_gateway"
    assert fallbacks[1]["from_mode"] == "direct_openai"
    assert fallbacks[1]["to_mode"] == "direct_openai_retry"
    assert fallbacks[1]["reason"] == "capability_mismatch"
    assert fallbacks[1]["outcome"] == "exhausted"


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
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

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
        request("proactive_reasoning", cache_key="bucket-1"), Response(), uid="user-1"
    )

    assert seen["json"]["model"] == "omi:auto:desktop-proactive-reasoning"
    assert seen["json"]["max_completion_tokens"] == 2400
    assert seen["headers"]["X-Omi-User-Uid"] == "user-1"
    assert result.lane == "omi:auto:desktop-proactive-reasoning"
    assert result.provider_model == "gpt-5.6-luna-2026-08-01"
    assert result.usage.cached_tokens == 1024
    assert result.cache_write is False
    assert result.fallback_class == "none"


def test_reasoning_floors_an_undersized_client_budget_and_leaves_extraction_alone():
    reasoning = desktop_proactivity._gateway_payload(request("proactive_reasoning", max_completion_tokens=800))
    extraction = desktop_proactivity._gateway_payload(request(max_completion_tokens=800))

    assert reasoning["max_completion_tokens"] == 2400
    assert extraction["max_completion_tokens"] == 800
    assert (
        desktop_proactivity._effective_max_completion_tokens(request("proactive_reasoning", max_completion_tokens=3000))
        == 3000
    )


def test_direct_reasoning_effort_tracks_the_gateway_lane(monkeypatch):
    config = load_gateway_config(prod_mode=True)
    lane = config.lanes["omi:auto:desktop-proactive-reasoning"]
    route = config.route_artifacts[lane.active_route]
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: None)

    provider = desktop_proactivity._proactive_provider_request(request("proactive_reasoning"), "user-1", "request-1")

    assert provider.payload["reasoning_effort"] == route.provider_options["reasoning_effort"]
    assert provider.payload["reasoning_effort"] == "low"


class _ImmediateSemaphore:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


@pytest.mark.asyncio
async def test_truncated_reasoning_retries_once_without_extra_quota(monkeypatch):
    calls = []
    consumed = []
    fallbacks = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            calls.append((url, headers, json))
            body = (
                {"choices": [{"finish_reason": "length", "message": {"content": '{"summary":'}}]}
                if len(calls) == 1
                else {
                    "model": "gpt-5.6-luna",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                }
            )
            return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    async def consume(uid, operation):
        consumed.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())

    result = await desktop_proactivity.proactive_completion(
        request("proactive_reasoning", max_completion_tokens=800), Response(), uid="user-1"
    )

    assert len(calls) == 2
    assert calls[0][2]["max_completion_tokens"] == 2400
    assert calls[1][2]["max_completion_tokens"] == 4096
    assert calls[0][2]["reasoning_effort"] == "low"
    assert consumed == [("user-1", desktop_proactivity.ProactiveOperation.REASONING)]
    assert result.response["choices"][0]["message"]["content"] == '{"summary":"ok"}'
    assert fallbacks[-1] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "direct_openai",
        "to_mode": "direct_openai_retry",
        "reason": "capability_mismatch",
        "outcome": "recovered",
        "log": None,
    }


@pytest.mark.asyncio
async def test_upstream_http_error_is_not_retried_and_stays_502(monkeypatch):
    calls = []
    released = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            calls.append(json)
            return httpx.Response(
                400,
                request=httpx.Request("POST", url),
                json={"error": {"message": "bad request"}},
            )

    async def allow(*_):
        return None

    async def release(uid, operation):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: None)
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())

    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(
            request("proactive_reasoning", max_completion_tokens=800), Response(), uid="user-1"
        )

    assert unavailable.value.status_code == 502
    assert unavailable.value.detail == "Proactive model unavailable"
    assert len(calls) == 1
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.REASONING)]


@pytest.mark.asyncio
async def test_complete_invalid_json_returns_422_without_retry(monkeypatch):
    calls = []
    released = []

    class GatewayClient:
        async def post(self, url, *, headers, json):
            calls.append(json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "model": "gpt-5.6-luna",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":3}'}}],
                },
            )

    async def allow(*_):
        return None

    async def release(uid, operation):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    with pytest.raises(desktop_proactivity.HTTPException) as invalid:
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

    assert invalid.value.status_code == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    assert invalid.value.detail == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_DETAIL
    assert len(calls) == 1
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
