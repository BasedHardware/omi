from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import Response

from llm_gateway.gateway.config_loader import load_gateway_config
from routers import desktop_proactivity
from utils.observability import journeys
from utils.subscription import (
    DESKTOP_ACCESS_TIER_ARCHITECT,
    DESKTOP_ACCESS_TIER_FREE,
    DESKTOP_ACCESS_TIER_FULL,
    NEO_DESKTOP_GRANDFATHER_CUTOFF,
)

# The provider ignores a cached prefix under 1024 tokens, so any test that expects
# explicit caching to engage must carry a stable block that clears that floor.
CACHEABLE_STABLE_PROMPT = "stable bucket instructions for the proactive director. " * 400


@pytest.fixture(autouse=True)
def _stub_quota_lease(monkeypatch):
    # Most route tests use an in-memory quota state rather than Redis. Keep
    # their provider-path assertions focused while dedicated lease tests below
    # exercise renew/finalize failure semantics explicitly.
    async def renew(*_args, **_kwargs):
        return None

    async def finalize(*_args, **_kwargs):
        return 3600

    monkeypatch.setattr(desktop_proactivity, '_renew_quota', renew)
    monkeypatch.setattr(desktop_proactivity, '_finalize_quota', finalize)


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


def _test_quota_state(
    *,
    limit: int = 150,
    remaining: int = 149,
    reset_seconds: int = 86400,
) -> desktop_proactivity.ProactiveQuotaState:
    return desktop_proactivity.ProactiveQuotaState(
        limit=limit,
        remaining=remaining,
        reset_seconds=reset_seconds,
        reservation_token="test-reservation-token",
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
    monkeypatch.setattr(
        desktop_proactivity.redis_db,
        "reserve_proactive_rate_limit",
        lambda *_args, **_kwargs: (False, 0, 19, None),
    )
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
        "reserve_proactive_rate_limit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis down")),
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

    def reserve_rate_limit(uid, key, limit, window_seconds, **kwargs):
        observed.update(uid=uid, key=key, limit=limit, window_seconds=window_seconds, **kwargs)
        return True, 1, 0, "reservation-token"

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_proactivity.redis_db, "reserve_proactive_rate_limit", reserve_rate_limit)

    await desktop_proactivity._consume_quota("user-1", operation)

    assert observed["uid"] == "user-1"
    assert observed["key"] == f"desktop_{operation.value}"
    assert observed["limit"] == expected_limit
    assert observed["window_seconds"] == 24 * 60 * 60
    assert observed["lease_seconds"] == desktop_proactivity._QUOTA_LEASE_SECONDS


@pytest.mark.asyncio
async def test_quota_headers_present_on_success(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        desktop_proactivity.redis_db,
        "reserve_proactive_rate_limit",
        lambda *_args, **_kwargs: (True, 12, 3600, "reservation-token"),
    )

    state = await desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    assert state == desktop_proactivity.ProactiveQuotaState(
        limit=150,
        remaining=12,
        reset_seconds=3600,
        reservation_token="reservation-token",
    )

    response = Response()
    desktop_proactivity._apply_quota_headers(response, state)
    assert response.headers["X-Proactive-Quota-Limit"] == "150"
    assert response.headers["X-Proactive-Quota-Remaining"] == "12"
    assert response.headers["X-Proactive-Quota-Reset"] == "3600"
    assert "retry-after" not in {name.lower() for name in response.headers.keys()}


@pytest.mark.asyncio
async def test_cancellation_before_reservation_response_leaves_server_lease_to_expire(monkeypatch):
    started = asyncio.Event()
    finish_reservation = asyncio.Event()
    late_result_task = None
    release_calls = []

    async def delayed_reservation():
        started.set()
        await finish_reservation.wait()
        return True, 149, 90, "late-reservation-token"

    async def run_blocking(_, function, *args, **kwargs):
        nonlocal late_result_task
        if function is desktop_proactivity.redis_db.reserve_proactive_rate_limit:
            del args, kwargs
            late_result_task = asyncio.create_task(delayed_reservation())
            # This mirrors a Redis executor call: cancellation stops observing
            # the await, but cannot stop the already-running server operation.
            return await asyncio.shield(late_result_task)
        return function(*args, **kwargs)

    async def release(*args):
        release_calls.append(args)

    monkeypatch.setattr(desktop_proactivity, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_customer_firestore_client", MagicMock())
    monkeypatch.setattr(desktop_proactivity.users_db, "get_user_valid_subscription", lambda *_args, **_kwargs: None)

    reservation_task = asyncio.create_task(
        desktop_proactivity._consume_quota("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)
    )
    await started.wait()
    reservation_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reservation_task

    finish_reservation.set()
    assert late_result_task is not None
    assert await late_result_task == (True, 149, 90, "late-reservation-token")
    assert release_calls == []


@pytest.mark.asyncio
async def test_completion_success_attaches_quota_headers(monkeypatch):
    observed_headers = {}

    class GatewayClient:
        async def post(self, url, *, headers, json):
            observed_headers.update(headers)
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
        return _test_quota_state(limit=200, remaining=12, reset_seconds=3600)

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})
    monkeypatch.setattr(desktop_proactivity, "uuid4", lambda: "request-for-accounting-join")

    response = Response()
    result = await desktop_proactivity.proactive_completion(request(), response, uid="user-1")
    assert result.provider_model == "gpt-5.6-luna"
    assert response.headers["X-Proactive-Quota-Limit"] == "200"
    assert response.headers["X-Proactive-Quota-Remaining"] == "12"
    assert response.headers["X-Proactive-Quota-Reset"] == "3600"
    assert response.headers["X-Omi-Request-ID"] == "request-for-accounting-join"
    assert observed_headers["X-Omi-Request-ID"] == response.headers["X-Omi-Request-ID"]


@pytest.mark.asyncio
async def test_provider_boundaries_renew_each_attempt_and_finalize_after_validation(monkeypatch):
    events = []

    class GatewayClient:
        def __init__(self):
            self.calls = 0

        async def post(self, url, *, headers, json):
            del url, headers, json
            events.append("provider")
            self.calls += 1
            if self.calls == 1:
                body = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
            else:
                body = {
                    "model": "gpt-5-nano",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                }
            return httpx.Response(200, request=httpx.Request("POST", "http://gateway"), json=body)

    async def consume(*_args):
        return _test_quota_state()

    async def renew(uid, operation, token):
        events.append("renew")
        assert uid == "user-1"
        assert operation == desktop_proactivity.ProactiveOperation.EXTRACTION
        assert token == "test-reservation-token"

    async def finalize(uid, operation, token):
        events.append("finalize")
        assert uid == "user-1"
        assert operation == desktop_proactivity.ProactiveOperation.EXTRACTION
        assert token == "test-reservation-token"
        return 41

    client = GatewayClient()
    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_renew_quota", renew)
    monkeypatch.setattr(desktop_proactivity, "_finalize_quota", finalize)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: client)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    response = Response()
    result = await desktop_proactivity.proactive_completion(request(), response, uid="user-1")

    assert result.response["choices"][0]["message"]["content"] == '{"summary":"ok"}'
    assert events == ["renew", "provider", "renew", "provider", "finalize"]
    assert response.headers["X-Proactive-Quota-Reset"] == "41"


@pytest.mark.asyncio
async def test_expired_lease_fails_closed_before_provider_and_releases_once(monkeypatch):
    provider_calls = []
    released = []

    class GatewayClient:
        async def post(self, *_args, **_kwargs):
            provider_calls.append(True)
            raise AssertionError("provider must not run after lease renewal failure")

    async def consume(*_args):
        return _test_quota_state()

    async def renew(*_args):
        raise desktop_proactivity.HTTPException(status_code=503, detail="Proactive metering lease expired")

    async def release(uid, operation, token):
        released.append((uid, operation, token))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_renew_quota", renew)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    with pytest.raises(desktop_proactivity.HTTPException) as expired:
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

    assert expired.value.status_code == 503
    assert provider_calls == []
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION, "test-reservation-token")]


@pytest.mark.asyncio
async def test_gateway_queue_wait_does_not_renew_expiring_lease_until_slot(monkeypatch):
    entered = asyncio.Event()
    release_slot = asyncio.Event()
    renew_calls = []
    provider_calls = []
    released = []

    class QueuedSemaphore:
        async def __aenter__(self):
            entered.set()
            await release_slot.wait()
            return self

        async def __aexit__(self, *_):
            return None

    class GatewayClient:
        async def post(self, *_args, **_kwargs):
            provider_calls.append(True)
            raise AssertionError("provider must not run after lease expiry")

    async def consume(*_args):
        return _test_quota_state()

    async def renew(*_args):
        renew_calls.append(True)
        raise desktop_proactivity.HTTPException(status_code=503, detail="Proactive metering lease expired")

    async def release(uid, operation, token):
        released.append((uid, operation, token))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_renew_quota", renew)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: QueuedSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    task = asyncio.create_task(desktop_proactivity.proactive_completion(request(), Response(), uid="user-1"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    await asyncio.sleep(0)
    assert renew_calls == []
    assert provider_calls == []

    release_slot.set()
    with pytest.raises(desktop_proactivity.HTTPException) as expired:
        await task

    assert expired.value.status_code == 503
    assert renew_calls == [True]
    assert provider_calls == []
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION, "test-reservation-token")]


@pytest.mark.asyncio
async def test_missing_finalize_fails_closed_without_rolling_back_successful_provider_work(monkeypatch):
    released = []

    class GatewayClient:
        async def post(self, url, *, headers, json):
            del url, headers, json
            return httpx.Response(
                200,
                request=httpx.Request("POST", "http://gateway"),
                json={
                    "model": "gpt-5-nano",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                },
            )

    async def consume(*_args):
        return _test_quota_state()

    async def renew(*_args):
        return None

    async def finalize(*_args):
        raise desktop_proactivity.HTTPException(status_code=503, detail="Proactive metering lease expired")

    async def release(*args):
        released.append(args)

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_renew_quota", renew)
    monkeypatch.setattr(desktop_proactivity, "_finalize_quota", finalize)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    with pytest.raises(desktop_proactivity.HTTPException) as missing:
        await desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")

    assert missing.value.status_code == 503
    # Finalization's Redis result is ambiguous: releasing here could erase a
    # committed success if the response was lost after Redis finalized it.
    assert released == []


@pytest.mark.asyncio
async def test_cancellation_after_validation_retains_finalize_behind_saturated_executor(monkeypatch):
    from utils.executors import critical_executor

    executor_gate = threading.Event()
    blockers = [critical_executor.submit(executor_gate.wait, 5) for _ in range(critical_executor._max_workers)]
    for _ in range(100):
        if critical_executor.active_count >= critical_executor._max_workers:
            break
        await asyncio.sleep(0.001)
    assert critical_executor.active_count == critical_executor._max_workers
    finalize_started = asyncio.Event()
    finalized = []

    async def consume(*_args):
        return _test_quota_state()

    async def renew(*_args):
        return None

    def finalize_in_executor():
        finalized.append(True)
        return True, 37

    async def finalize(*_args):
        finalize_started.set()
        admitted, reset_seconds = await desktop_proactivity.run_blocking(critical_executor, finalize_in_executor)
        assert admitted
        return reset_seconds

    class GatewayClient:
        async def post(self, url, *, headers, json):
            del url, headers, json
            return httpx.Response(
                200,
                request=httpx.Request("POST", "http://gateway"),
                json={
                    "model": "gpt-5-nano",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                },
            )

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_renew_quota", renew)
    monkeypatch.setattr(desktop_proactivity, "_finalize_quota", finalize)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    try:
        request_task = asyncio.create_task(
            desktop_proactivity.proactive_completion(request(), Response(), uid="user-1")
        )
        await asyncio.wait_for(finalize_started.wait(), timeout=1)
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

        executor_gate.set()
        for blocker in blockers:
            await asyncio.to_thread(blocker.result)
        for _ in range(100):
            if not desktop_proactivity._pending_proactive_finalizations:
                break
            await asyncio.sleep(0.001)
        assert finalized == [True]
        assert not desktop_proactivity._pending_proactive_finalizations
    finally:
        executor_gate.set()
        for blocker in blockers:
            if not blocker.done():
                await asyncio.to_thread(blocker.result)


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


def _proactive_quota_scripts(client):
    redis_db = desktop_proactivity.redis_db
    return {
        "reserve": client.register_script(redis_db._PROACTIVE_QUOTA_RESERVE_LUA_SOURCE),
        "renew": client.register_script(redis_db._PROACTIVE_QUOTA_RENEW_LUA_SOURCE),
        "finalize": client.register_script(redis_db._PROACTIVE_QUOTA_FINALIZE_LUA_SOURCE),
        "release": client.register_script(redis_db._PROACTIVE_QUOTA_RELEASE_LUA_SOURCE),
    }


def test_proactive_quota_uses_redis_clock_when_host_clock_is_skewed(monkeypatch):
    from database import redis_db

    observed = {}

    class RedisClockScript:
        def __call__(self, *, keys, args):
            observed.update(keys=keys, args=args)
            # This fixed value stands in for the authoritative Redis TIME
            # result; the host clock is intentionally not consulted.
            return [1, 1, 90, b"skew-safe-token"]

    monkeypatch.setattr(redis_db, "_PROACTIVE_QUOTA_RESERVE_LUA", RedisClockScript())
    monkeypatch.setattr(redis_db.secrets, "token_urlsafe", lambda _bytes: "skew-safe-token")
    import time as host_time

    monkeypatch.setattr(host_time, "time", lambda: -(10**12))
    result = redis_db.reserve_proactive_rate_limit("user-1", "desktop_test", 2, 86_400)

    assert result == (True, 1, 90, "skew-safe-token")
    assert observed["args"] == [90_000, 86_400, 2, "skew-safe-token"]
    for source in (
        redis_db._PROACTIVE_QUOTA_RESERVE_LUA_SOURCE,
        redis_db._PROACTIVE_QUOTA_RENEW_LUA_SOURCE,
        redis_db._PROACTIVE_QUOTA_FINALIZE_LUA_SOURCE,
    ):
        assert "redis.call('TIME')" in source


def test_proactive_quota_reservations_are_atomic_and_fail_closed_at_limit():
    import fakeredis

    client = fakeredis.FakeRedis()
    scripts = _proactive_quota_scripts(client)
    key = "rl:proactive_lease:desktop_proactive_extraction:user-1"

    def reserve(index):
        return scripts["reserve"](
            keys=[key],
            args=[90_000, 86_400, 2, f"token-{index}"],
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve, range(8)))

    admitted = [result for result in results if int(result[0]) == 1]
    denied = [result for result in results if int(result[0]) == 0]
    assert len(admitted) == 2
    assert len(denied) == 6
    assert client.zcard(key) == 2
    assert all(result[3] == b"" for result in denied)


def test_proactive_quota_lease_renew_finalize_release_and_process_expiry():
    import fakeredis

    client = fakeredis.FakeRedis()
    scripts = _proactive_quota_scripts(client)
    key = "rl:proactive_lease:desktop_proactive_reasoning:user-1"
    token = "opaque-token"
    committed = f"committed:{token}"

    server_seconds, server_micros = client.time()
    server_now_ms = int(server_seconds) * 1000 + int(server_micros) // 1000
    client.zadd(key, {"older-active": server_now_ms + 30_000})

    admitted = scripts["reserve"](keys=[key], args=[90_000, 86_400, 2, token])
    assert admitted[0:2] == [1, 2]
    assert 28 <= admitted[2] <= 31
    assert admitted[3] == token.encode()

    renewed = scripts["renew"](
        keys=[key],
        args=[90_000, 86_400, token, "committed:"],
    )
    assert renewed[0] == 1
    assert 28 <= renewed[1] <= 31
    assert scripts["renew"](keys=[key], args=[90_000, 86_400, "missing", "committed:"]) == [0, 0]

    finalized = scripts["finalize"](
        keys=[key],
        args=[86_400_000, 86_400, token, "committed:"],
    )
    assert finalized[0] == 1
    assert 28 <= finalized[1] <= 31
    assert client.zscore(key, token) is None
    assert client.zscore(key, committed) is not None
    # A duplicate completion acknowledgement must not create a second slot or
    # extend the committed window.
    assert (
        scripts["finalize"](
            keys=[key],
            args=[86_400_000, 86_400, token, "committed:"],
        )
        == finalized
    )
    # Release only removes a pending token. A late failure cleanup cannot
    # erase a successful committed result, so both calls are harmless here.
    assert scripts["release"](keys=[key], args=[token]) == 0
    assert scripts["release"](keys=[key], args=[token]) == 0
    assert client.zscore(key, committed) is not None

    # Model cancellation/process death: with no observer, the expired member is
    # pruned by the next reservation and never becomes a daily commitment.
    orphan_key = f"{key}:orphan"
    orphan = "orphan-token"
    assert scripts["reserve"](keys=[orphan_key], args=[90_000, 86_400, 1, orphan])[0:2] == [1, 1]
    # Inject passage of time on the Redis member itself; the script's TIME is
    # still the sole clock used to decide whether this lease is expired.
    client.zadd(orphan_key, {orphan: 1})
    after_expiry = scripts["reserve"](keys=[orphan_key], args=[90_000, 86_400, 1, "replacement"])
    assert after_expiry[0:2] == [1, 1]
    assert client.zscore(orphan_key, orphan) is None

    pending_key = f"{key}:pending"
    scripts["reserve"](keys=[pending_key], args=[90_000, 86_400, 1, "pending-token"])
    assert scripts["release"](keys=[pending_key], args=["pending-token"]) == 1
    assert scripts["release"](keys=[pending_key], args=["pending-token"]) == 0


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
        return _test_quota_state()

    async def release(uid, operation, *_args):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})
    monkeypatch.setattr(desktop_proactivity, "uuid4", lambda: "request-id-upstream-502")

    response = Response()
    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(request(), response, uid="user-1")

    assert unavailable.value.status_code == 502
    assert unavailable.value.detail == "Proactive model unavailable"
    assert unavailable.value.headers == {
        "X-Omi-Request-ID": "request-id-upstream-502",
        "X-Proactive-Quota-Limit": "150",
        "X-Proactive-Quota-Remaining": "149",
        "X-Proactive-Quota-Reset": "86400",
    }
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]


@pytest.mark.asyncio
async def test_cancellation_during_provider_retry_releases_quota_once_without_retry_telemetry(monkeypatch):
    calls = []
    released = []
    telemetry = []

    class GatewayClient:
        async def post(self, url, *, headers, json):
            calls.append(json)
            if len(calls) == 2:
                raise asyncio.CancelledError()
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"choices": [{"finish_reason": "length", "message": {"content": '{"summary":'}}]},
            )

    class Semaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    async def consume(*_args):
        return _test_quota_state()

    async def release(uid, operation, *_args):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: telemetry.append(values))
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: Semaphore())
    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", lambda **_: {})

    with pytest.raises(asyncio.CancelledError):
        await desktop_proactivity._proactive_completion_unobserved(request(), Response(), uid="user-1")

    assert [payload["max_completion_tokens"] for payload in calls] == [1024, 2400]
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
    assert telemetry == []


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
    # Selection is side-effect free. Fallback telemetry is emitted only after
    # the per-invocation paid-boundary rollout refresh permits the request.
    assert fallbacks == []

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
    events = []

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
        return _test_quota_state()

    async def finalize(*_args):
        events.append("finalize")
        return 3600

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(
        desktop_proactivity,
        "record_fallback",
        lambda **values: (fallbacks.append(values), events.append(values["to_mode"])),
    )
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_finalize_quota", finalize)
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
        "from_mode": "direct_openai",
        "to_mode": "direct_openai_retry",
        "reason": "capability_mismatch",
        "outcome": "recovered",
        "log": None,
    }
    assert fallbacks[1] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "gateway",
        "to_mode": "direct_openai",
        "reason": "config_incomplete",
        "outcome": "recovered",
        "log": None,
    }
    assert events == ["finalize", "direct_openai_retry", "direct_openai"]


@pytest.mark.asyncio
async def test_length_retry_recovery_waits_for_successful_quota_finalization(monkeypatch):
    calls = []
    fallbacks = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            del headers, json
            calls.append(True)
            body = (
                {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
                if len(calls) == 1
                else {
                    "model": "gpt-5-nano",
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok"}'}}],
                }
            )
            return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    async def finalize(*_args):
        raise desktop_proactivity.HTTPException(status_code=503, detail="Proactive metering lease expired")

    async def consume(*_args):
        return _test_quota_state()

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", consume)
    monkeypatch.setattr(desktop_proactivity, "_finalize_quota", finalize)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())

    with pytest.raises(desktop_proactivity.HTTPException) as failed:
        await asyncio.wait_for(
            desktop_proactivity.proactive_completion(request(), Response(), uid="user-1"),
            timeout=1,
        )

    assert failed.value.status_code == 503
    assert len(calls) == 2
    assert fallbacks == []


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
        return _test_quota_state()

    async def release(uid, operation, *_args):
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
    monkeypatch.setattr(desktop_proactivity, "uuid4", lambda: f"request-id-retry-{final_failure}")

    response = Response()
    with pytest.raises(desktop_proactivity.HTTPException) as unavailable:
        await desktop_proactivity.proactive_completion(request(), response, uid="user-1")

    assert unavailable.value.status_code == (
        502 if final_failure == "provider" else desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    )
    assert unavailable.value.headers["X-Omi-Request-ID"] == f"request-id-retry-{final_failure}"
    assert unavailable.value.headers["X-Proactive-Quota-Limit"] == "150"
    assert unavailable.value.headers["X-Proactive-Quota-Remaining"] == "149"
    assert unavailable.value.headers["X-Proactive-Quota-Reset"] == "86400"
    assert [payload["max_completion_tokens"] for payload in calls] == [1024, 2400]
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
    assert len(fallbacks) == 1
    assert fallbacks[0]["component"] == "llm_gateway"
    assert fallbacks[0]["from_mode"] == "direct_openai"
    assert fallbacks[0]["to_mode"] == "direct_openai_retry"
    assert fallbacks[0]["reason"] == "capability_mismatch"
    assert fallbacks[0]["outcome"] == "exhausted"


@pytest.mark.asyncio
async def test_direct_provider_invalid_output_does_not_emit_recovered_fallback(monkeypatch):
    fallbacks = []
    direct_surfaces = []
    released = []

    class DirectClient:
        async def post(self, url, *, headers, json):
            del headers, json
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"summary": 7}'}}],
                },
            )

    async def allow(*_):
        return _test_quota_state()

    async def release(uid, operation, *_args):
        released.append((uid, operation))

    monkeypatch.setattr(desktop_proactivity, "llm_stub_enabled", lambda: False)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setattr(desktop_proactivity, "get_openai_api_key", lambda: "dev-provider-key")
    monkeypatch.setattr(desktop_proactivity, "record_fallback", lambda **values: fallbacks.append(values))
    monkeypatch.setattr(
        desktop_proactivity,
        "record_direct_exception_surface",
        lambda **values: direct_surfaces.append(values),
    )
    monkeypatch.setattr(desktop_proactivity, "_consume_quota", allow)
    monkeypatch.setattr(desktop_proactivity, "_release_quota", release)
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_client", lambda: DirectClient())
    monkeypatch.setattr(desktop_proactivity, "get_llm_gateway_semaphore", lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, "uuid4", lambda: "request-id-invalid-422")

    response = Response()
    with pytest.raises(desktop_proactivity.HTTPException) as invalid:
        await desktop_proactivity.proactive_completion(request(), response, uid="user-1")

    assert invalid.value.status_code == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    assert invalid.value.detail == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_DETAIL
    assert invalid.value.headers == {
        "X-Omi-Request-ID": "request-id-invalid-422",
        "X-Proactive-Quota-Limit": "150",
        "X-Proactive-Quota-Remaining": "149",
        "X-Proactive-Quota-Reset": "86400",
    }
    assert released == [("user-1", desktop_proactivity.ProactiveOperation.EXTRACTION)]
    assert fallbacks == []
    assert direct_surfaces == []


@pytest.mark.asyncio
async def test_provider_configuration_failure_releases_reserved_quota(monkeypatch):
    released = []

    async def allow(*_):
        return _test_quota_state()

    async def release(uid, operation, *_args):
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
        return _test_quota_state()

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
        return _test_quota_state()

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
    assert fallbacks[0] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "direct_openai",
        "to_mode": "direct_openai_retry",
        "reason": "capability_mismatch",
        "outcome": "recovered",
        "log": None,
    }
    assert fallbacks[1] | {"log": None} == {
        "component": "llm_gateway",
        "from_mode": "gateway",
        "to_mode": "direct_openai",
        "reason": "config_incomplete",
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
        return _test_quota_state()

    async def release(uid, operation, *_args):
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
        return _test_quota_state()

    async def release(uid, operation, *_args):
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


def test_proactive_gateway_request_marks_desktop_platform(monkeypatch):
    """Desktop proactivity is desktop-only traffic; the ledger must say so."""
    monkeypatch.setenv("OMI_LLM_GATEWAY_URL", "http://gateway.test")
    captured = {}

    def fake_headers(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(desktop_proactivity, "llm_gateway_headers", fake_headers)
    monkeypatch.setattr(desktop_proactivity, "_gateway_payload", lambda _request: {})

    completion = request()
    desktop_proactivity._proactive_provider_request(completion, "user-1", "request-1")

    assert captured["platform"] == "desktop"
    assert captured["feature"] == f"desktop_{completion.operation.value}"


def _capture_proactivity_journeys(monkeypatch):
    terminal = []
    monkeypatch.setattr(journeys, 'record_client_journey_accepted', lambda *_: None)
    monkeypatch.setattr(
        journeys,
        'record_client_journey_terminal',
        lambda journey, client_kind, outcome, _elapsed, *, issue_class=None: terminal.append(
            (journey, client_kind, outcome, issue_class)
        ),
    )
    return terminal


@pytest.mark.asyncio
async def test_desktop_proactivity_journey_records_validated_result_success(monkeypatch):
    terminal = _capture_proactivity_journeys(monkeypatch)
    monkeypatch.setattr(desktop_proactivity, 'llm_stub_enabled', lambda: True)

    result = await desktop_proactivity.proactive_completion(
        request(),
        Response(),
        uid='user-1',
        x_app_platform='windows',
    )

    assert result.response['choices'][0]['message']['content'] == '{"summary":""}'
    assert terminal == [('desktop_proactivity', 'desktop_windows', 'success', None)]


@pytest.mark.asyncio
async def test_desktop_proactivity_journey_records_quota_cap_as_degraded(monkeypatch):
    terminal = _capture_proactivity_journeys(monkeypatch)
    monkeypatch.setattr(desktop_proactivity, 'llm_stub_enabled', lambda: False)

    async def capped(*_):
        raise desktop_proactivity.HTTPException(status_code=429, detail='Proactive request limit exceeded')

    monkeypatch.setattr(desktop_proactivity, '_consume_quota', capped)
    with pytest.raises(desktop_proactivity.HTTPException) as error:
        await desktop_proactivity.proactive_completion(
            request(),
            Response(),
            uid='user-1',
            x_app_platform='macos',
        )

    assert error.value.status_code == 429
    assert terminal == [('desktop_proactivity', 'desktop_macos', 'degraded', 'quota_capped')]


@pytest.mark.asyncio
async def test_desktop_proactivity_journey_rejects_post_200_invalid_structured_output(monkeypatch):
    terminal = _capture_proactivity_journeys(monkeypatch)

    class GatewayClient:
        async def post(self, url, *, headers, json):
            return httpx.Response(
                200,
                request=httpx.Request('POST', url),
                json={
                    'model': 'gpt-5.6-luna',
                    'choices': [{'finish_reason': 'stop', 'message': {'content': '{"summary":3}'}}],
                },
            )

    async def allow(*_):
        return _test_quota_state()

    async def release(*_):
        return None

    monkeypatch.setattr(desktop_proactivity, 'llm_stub_enabled', lambda: False)
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway')
    monkeypatch.setattr(desktop_proactivity, '_consume_quota', allow)
    monkeypatch.setattr(desktop_proactivity, '_release_quota', release)
    monkeypatch.setattr(desktop_proactivity, 'get_llm_gateway_client', lambda: GatewayClient())
    monkeypatch.setattr(desktop_proactivity, 'get_llm_gateway_semaphore', lambda: _ImmediateSemaphore())
    monkeypatch.setattr(desktop_proactivity, 'llm_gateway_headers', lambda **_: {})

    with pytest.raises(desktop_proactivity.HTTPException) as invalid:
        await desktop_proactivity.proactive_completion(
            request(),
            Response(),
            uid='user-1',
            user_agent='CFNetwork/1498.700.2 Darwin/23.6.0',
        )

    assert invalid.value.status_code == desktop_proactivity._INVALID_STRUCTURED_OUTPUT_STATUS
    assert terminal == [('desktop_proactivity', 'desktop_macos', 'failure', 'invalid_response')]


@pytest.mark.asyncio
async def test_legacy_clients_are_not_gated_by_jit_rollout(monkeypatch):
    """The released completion lane must serve deployed clients with no JIT cohort state.

    Regression guard for the gate that returned 403 ``jit_rollout_not_enabled``
    here: it silently killed context-bucket extraction for the whole shipped
    desktop fleet. JIT admission is enforced on the JIT reservation routes, not
    on this pre-existing lane; this test runs the full unobserved path with no
    rollout stub of any kind and expects provider work to proceed.
    """

    provider_calls = []

    async def quota(uid, operation):
        return desktop_proactivity.ProactiveQuotaState(limit=10, remaining=9, reset_seconds=60, reservation_token='tok')

    async def provider(provider_request, *, uid, operation, reservation_token, max_completion_tokens=None):
        provider_calls.append(operation)
        return {
            "choices": [{"message": {"content": "{\"insights\": []}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    monkeypatch.setattr(desktop_proactivity, '_consume_quota', quota)
    monkeypatch.setattr(
        desktop_proactivity,
        '_proactive_provider_request',
        lambda req, uid, request_id: desktop_proactivity._ProviderRequest(
            url='https://gateway.test/v1/chat/completions',
            headers={},
            payload={'max_completion_tokens': 800},
            fallback_class='none',
        ),
    )
    monkeypatch.setattr(desktop_proactivity, '_post_provider_completion', provider)
    monkeypatch.setattr(desktop_proactivity, '_validate_gateway_output', lambda *_a, **_k: None)
    monkeypatch.setattr(desktop_proactivity, 'llm_stub_enabled', lambda: False)
    assert not hasattr(desktop_proactivity, 'resolve_jit_rollout')

    envelope = await desktop_proactivity._proactive_completion_unobserved(request(), Response(), uid='user-1')

    assert provider_calls, 'provider must be reached without any JIT rollout consultation'
    assert envelope.operation.value == 'proactive_extraction'
