import asyncio
import io
import json
import os
import re
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from routers import desktop_proxy


def make_request(
    body: bytes = b'{"contents":[{"parts":[{"text":"hello"}]}]}',
    *,
    query_string: bytes = b"",
    workload: str | None = None,
) -> Request:
    sent = False
    pending = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await pending.wait()

    headers = [(b"x-omi-request-id", b"request-12345678")]
    if workload is not None:
        headers.append((b"x-omi-workload", workload.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/proxy/gemini/models/gemini-2.5-flash:generateContent",
            "query_string": query_string,
            "headers": headers,
        },
        receive,
    )


def test_sanitize_caps_generation_and_normalizes_system_content():
    body = desktop_proxy._sanitize(
        json.dumps(
            {
                "safetySettings": [{"category": "x"}],
                "contents": [{"role": "system", "parts": [{"text": "system"}]}, {"parts": [{"text": "user"}]}],
                "generation_config": {"maxOutputTokens": "9000"},
            }
        ).encode(),
        "generateContent",
    )
    payload = json.loads(body)
    assert "safetySettings" not in payload
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "user"}]}]
    assert payload["systemInstruction"] == {"parts": [{"text": "system"}]}
    assert payload["generation_config"] == {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingBudget": 1024}}


def test_sanitize_rejects_multiple_candidates_and_path_is_allowlisted():
    with pytest.raises(HTTPException, match="candidate_count"):
        desktop_proxy._sanitize(b'{"candidateCount": 2}', "generateContent")
    assert desktop_proxy._path_parts("models/gemini-3-flash-preview:generateContent") == (
        "models/gemini-2.5-flash:generateContent",
        "gemini-2.5-flash",
        "generateContent",
    )
    with pytest.raises(HTTPException):
        desktop_proxy._path_parts("models/gemini-2.5-pro:deleteModel")


def test_desktop_live_suggestions_model_is_allowed_and_vertex_routed(monkeypatch):
    """Desktop live suggestions run on Flash-Lite (ModelQoS.suggestions), so the proxy must forward it."""
    assert desktop_proxy._path_parts("models/gemini-2.5-flash-lite:generateContent") == (
        "models/gemini-2.5-flash-lite:generateContent",
        "gemini-2.5-flash-lite",
        "generateContent",
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "omi-test")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    assert desktop_proxy._vertex_url("gemini-2.5-flash-lite", "generateContent") == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/omi-test/locations/us-central1"
        "/publishers/google/models/gemini-2.5-flash-lite:generateContent"
    )


def test_every_model_the_desktop_client_ships_is_proxy_allowlisted():
    """Static checker: ModelQoS.swift picks the models the desktop sends to this proxy.

    Not behavioral coverage — it reads the client's model table so a tier change there
    cannot ship a model the proxy answers with 403.
    """
    qos = BACKEND_DIR.parent / "desktop/macos/Desktop/Sources/ModelQoS.swift"
    if not qos.exists():  # partial checkouts (backend-only forks) have no desktop tree
        pytest.skip("desktop sources are not present in this checkout")
    client_models = set(re.findall(r'"(gemini-[^"]+)"', qos.read_text()))
    assert client_models
    assert client_models <= desktop_proxy._ALLOWED_MODELS


def test_shared_desktop_policy_admits_every_model_the_client_ships():
    """The same static checker over the shared Rust policy's copy of the proxy allowlist.

    desktop/shared-rust carries the pre-cutover Rust gate's allowlist. Pinning only this
    module let that copy keep the Flash-Lite gap that #10848 closed here, so the client's
    model table is checked against every in-repo copy of the gate, not just the live one.
    """
    qos = BACKEND_DIR.parent / "desktop/macos/Desktop/Sources/ModelQoS.swift"
    policy = BACKEND_DIR.parent / "desktop/shared-rust/src/model_qos.rs"
    if not qos.exists() or not policy.exists():  # partial checkouts have no desktop tree
        pytest.skip("desktop sources are not present in this checkout")
    client_models = set(re.findall(r'"(gemini-[^"]+)"', qos.read_text()))
    allowed_body = re.search(r"fn gemini_proxy_allowed\(\).*?\n\}", policy.read_text(), re.DOTALL)
    assert allowed_body, "gemini_proxy_allowed() is no longer readable in the shared policy"
    assert client_models
    assert client_models <= set(re.findall(r'"(gemini-[^"]+)"', allowed_body.group()))


def test_vertex_embedding_translation_round_trip():
    request = desktop_proxy._vertex_embedding_request(
        b'{"content":{"parts":[{"text":"hello"}]},"taskType":"RETRIEVAL_QUERY","title":"note"}'
    )
    assert json.loads(request) == {"instances": [{"content": "hello", "task_type": "RETRIEVAL_QUERY", "title": "note"}]}
    assert json.loads(
        desktop_proxy._vertex_embedding_response(b'{"predictions":[{"embeddings":{"values":[1,2]}}]}')
    ) == {"embedding": {"values": [1, 2]}}


@pytest.mark.asyncio
async def test_gemini_proxy_rejects_paywalled_desktop_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "is_desktop_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


@pytest.mark.asyncio
@pytest.mark.parametrize(("model_tier", "used_requests"), [("", 1), ("", 30), ("max", 300)])
async def test_server_gemini_meter_keeps_pro_within_the_soft_limit(monkeypatch, model_tier, used_requests):
    fallbacks = []

    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return True, desktop_proxy._DAILY_HARD_LIMIT - used_requests, 0
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "record_fallback", lambda **fields: fallbacks.append(fields))
    if model_tier:
        monkeypatch.setenv("OMI_MODEL_TIER", model_tier)
    else:
        monkeypatch.delenv("OMI_MODEL_TIER", raising=False)

    assert (
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )
        == "models/gemini-2.5-pro:generateContent"
    )
    assert fallbacks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("model_tier", "used_requests"), [("", 31), ("max", 301)])
async def test_server_gemini_meter_downgrades_pro_after_the_soft_limit(monkeypatch, model_tier, used_requests):
    fallbacks = []

    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return True, desktop_proxy._DAILY_HARD_LIMIT - used_requests, 0
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "record_fallback", lambda **fields: fallbacks.append(fields))
    if model_tier:
        monkeypatch.setenv("OMI_MODEL_TIER", model_tier)
    else:
        monkeypatch.delenv("OMI_MODEL_TIER", raising=False)

    assert (
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )
        == "models/gemini-2.5-flash-lite:generateContent"
    )
    assert fallbacks == [
        {
            "component": "gemini_model",
            "from_mode": "pro",
            "to_mode": "flash_lite",
            "reason": "quota",
            "outcome": "degraded",
        }
    ]


def test_quota_demotion_never_targets_the_pt_model():
    """Regression: over-quota Pro used to demote onto `gemini-2.5-flash`, silently
    dumping the Insight tool loop (~11% of the reservation) onto the saturated
    Vertex PT lane. The demotion target must stay a `shared`/on-demand model."""
    assert desktop_proxy._QUOTA_DEMOTION_MODEL != desktop_proxy.VERTEX_PT_MODEL
    assert desktop_proxy._QUOTA_DEMOTION_MODEL in desktop_proxy._ALLOWED_MODELS
    assert desktop_proxy._QUOTA_DEMOTION_MODEL in desktop_proxy._VERTEX_MODELS


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["embedContent", "batchEmbedContents"])
async def test_server_gemini_meter_does_not_downgrade_embedding_actions(monkeypatch, action):
    fallbacks = []

    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return True, desktop_proxy._DAILY_HARD_LIMIT - 31, 0
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "record_fallback", lambda **fields: fallbacks.append(fields))
    monkeypatch.delenv("OMI_MODEL_TIER", raising=False)
    path = f"models/gemini-2.5-pro:{action}"

    assert await desktop_proxy._meter_server_request("user", path, "gemini-2.5-pro", action) == path
    assert fallbacks == []


@pytest.mark.asyncio
async def test_server_gemini_meter_allows_request_at_the_daily_hard_limit(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return True, 0, 0
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    path = "models/gemini-2.5-flash:generateContent"

    assert await desktop_proxy._meter_server_request("user", path, "gemini-2.5-flash", "generateContent") == path


@pytest.mark.asyncio
async def test_server_gemini_meter_rejects_request_over_the_daily_hard_limit(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return False, 0, 86_400
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )

    assert error.value.status_code == 429
    assert error.value.detail == "Gemini daily request limit exceeded"
    assert error.value.retryable is False
    assert error.value.headers == {"Retry-After": "86400", "X-Omi-Retryable": "false"}


@pytest.mark.asyncio
async def test_proxy_marks_daily_quota_exhaustion_non_retryable_and_preserves_retry_after(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return False, 0, 86_400
            return True, desktop_proxy._BURST_LIMIT - 1, 0
        raise AssertionError(f"unexpected blocking call: {function}")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._proxy(make_request(), "models/gemini-2.5-pro:generateContent", False, "user")

    assert error.value.status_code == 429
    assert error.value.headers["X-Omi-Retryable"] == "false"
    assert error.value.headers["Retry-After"] == "86400"


@pytest.mark.asyncio
async def test_server_paid_flash_fails_closed_without_project(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("USE_VERTEX_AI", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")

    with pytest.raises(desktop_proxy.RoutingFailure) as error:
        await desktop_proxy._upstream(
            "models/gemini-2.5-flash:generateContent",
            "gemini-2.5-flash",
            "generateContent",
            {},
        )

    assert error.value.code == "routing_vertex_not_configured"
    assert desktop_proxy.VERTEX_PT_CONTRACT in error.value.message
    assert desktop_proxy.VERTEX_PT_MODEL == "gemini-2.5-flash"
    assert desktop_proxy.VERTEX_PT_EXPIRES == "~2027-05-28"


@pytest.mark.asyncio
async def test_server_paid_flash_uses_vertex_never_studio_or_key(monkeypatch):
    async def token():
        return "adc-token"

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy._vertex_tokens, "get_access_token", token)
    monkeypatch.setenv("USE_VERTEX_AI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")

    for action in ("generateContent", "streamGenerateContent"):
        route = await desktop_proxy._upstream(
            f"models/{desktop_proxy.VERTEX_PT_MODEL}:{action}",
            desktop_proxy.VERTEX_PT_MODEL,
            action,
            {"alt": "sse"} if action == "streamGenerateContent" else {},
        )
        assert route.provider == "vertex_ai"
        assert "aiplatform.googleapis.com" in route.url
        assert "us-central1" in route.url
        assert "generativelanguage.googleapis.com" not in route.url
        assert "key" not in route.params
        assert route.params.get("key") is None


@pytest.mark.asyncio
async def test_byok_flash_stays_on_ai_studio(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "user-key")
    monkeypatch.setenv("USE_VERTEX_AI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")

    route = await desktop_proxy._upstream(
        "models/gemini-2.5-flash:generateContent",
        "gemini-2.5-flash",
        "generateContent",
        {},
    )

    assert route.provider == "ai_studio_byok"
    assert route.params["key"] == "user-key"
    assert "generativelanguage.googleapis.com" in route.url


def test_vertex_pt_model_pin_points_at_the_docs():
    docs = BACKEND_DIR / "docs" / "vertex-pt-flash.md"
    text = docs.read_text(encoding="utf-8")
    assert desktop_proxy.VERTEX_PT_MODEL in text
    assert desktop_proxy.VERTEX_PT_EXPIRES in text
    assert desktop_proxy.VERTEX_PT_CONTRACT.split(",")[0] in text
    assert "generativelanguage.googleapis.com" in text


@pytest.mark.asyncio
async def test_vertex_credentials_fail_closed_without_studio_fallback(monkeypatch):
    async def unavailable():
        raise RuntimeError("credential detail must not escape")

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy._vertex_tokens, "get_access_token", unavailable)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "omi-test")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")

    with pytest.raises(desktop_proxy.RoutingFailure) as error:
        await desktop_proxy._upstream(
            "models/gemini-2.5-flash:generateContent",
            "gemini-2.5-flash",
            "generateContent",
            {},
        )

    assert error.value.code == "routing_credentials_unavailable"


@pytest.mark.asyncio
async def test_batch_embedding_uses_studio_and_rejects_credential_override(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "omi-test")
    monkeypatch.setenv("GEMINI_API_KEY", "server-key")

    route = await desktop_proxy._upstream(
        "models/gemini-embedding-001:batchEmbedContents",
        "gemini-embedding-001",
        "batchEmbedContents",
        {"alt": "json"},
    )
    assert route.provider == "ai_studio"
    assert route.params == {"alt": "json", "key": "server-key"}
    with pytest.raises(HTTPException, match="credential query"):
        await desktop_proxy._upstream(
            "models/gemini-2.5-flash:generateContent",
            "gemini-2.5-flash",
            "generateContent",
            {"key": "attacker-key"},
        )


@pytest.mark.asyncio
async def test_vertex_single_embedding_uses_predict_wire_method(monkeypatch):
    async def token():
        return "adc-token"

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy._vertex_tokens, "get_access_token", token)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "omi-test")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    route = await desktop_proxy._upstream(
        "models/gemini-embedding-001:embedContent",
        "gemini-embedding-001",
        "embedContent",
        {},
    )

    assert route.provider == "vertex_ai"
    assert route.url.endswith("/gemini-embedding-001:predict")


def test_payload_shape_bounds_complexity_without_recording_content():
    body = json.dumps({"contents": [{"parts": [{"text": "private prompt"}]}] * 129}).encode()
    with pytest.raises(HTTPException) as error:
        desktop_proxy._payload_shape(body)
    assert error.value.status_code == 413

    shape = desktop_proxy._payload_shape(b'{"contents":[{"parts":[{"inlineData":{"data":"secret"}}]}]}')
    assert shape.inline_media_bucket == "1"
    assert "secret" not in repr(shape)


def test_provider_timeout_has_typed_non_retryable_terminal_response(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)
    telemetry = desktop_proxy.ProxyTelemetry(make_request(), streaming=False)
    response = httpx.Response(504, request=httpx.Request("POST", "https://provider.invalid"))

    result = desktop_proxy._provider_error(response, telemetry)

    assert result.status_code == 504
    assert result.headers["x-omi-error-class"] == "provider_timeout"
    assert result.headers["x-omi-retryable"] == "false"
    event = json.loads(output.getvalue())
    assert event["outcome"] == "provider_timeout"
    assert event["phase"] == "provider"
    assert "private prompt" not in output.getvalue()


@pytest.mark.asyncio
async def test_proxy_dispatches_once_and_classifies_read_timeout(monkeypatch):
    calls = 0

    class TimeoutClient:
        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("private provider detail")

    async def meter(_uid, path, _model, _action):
        return path

    async def route(path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "vertex_ai", "adc", "us-central1")

    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_client", lambda: TimeoutClient())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(1))

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert calls == 1
    assert response.status_code == 504
    assert response.headers["x-omi-failure-phase"] == "read"
    assert response.headers["x-omi-retryable"] == "false"


def test_output_token_cap_follows_byok(monkeypatch):
    """Server-paid requests are bounded at 2048 output tokens; BYOK keeps 8192."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert desktop_proxy._output_token_cap() == 2048
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "user-key")
    assert desktop_proxy._output_token_cap() == 8192


def test_sanitize_applies_the_requested_output_cap():
    """No desktop client sets maxOutputTokens, so the cap passed by the caller is
    both the injected default and the clamp; smaller explicit values pass through."""
    absent = json.loads(desktop_proxy._sanitize(b'{"generationConfig": {}}', "generateContent", max_output_tokens=2048))
    assert absent["generationConfig"]["maxOutputTokens"] == 2048
    oversized = json.loads(
        desktop_proxy._sanitize(
            b'{"generationConfig": {"maxOutputTokens": 9000}}', "generateContent", max_output_tokens=2048
        )
    )
    assert oversized["generationConfig"]["maxOutputTokens"] == 2048
    smaller = json.loads(
        desktop_proxy._sanitize(
            b'{"generationConfig": {"maxOutputTokens": 512}}', "generateContent", max_output_tokens=2048
        )
    )
    assert smaller["generationConfig"]["maxOutputTokens"] == 512
    byok = json.loads(
        desktop_proxy._sanitize(
            b'{"generationConfig": {"maxOutputTokens": 9000}}', "generateContent", max_output_tokens=8192
        )
    )
    assert byok["generationConfig"]["maxOutputTokens"] == 8192


@pytest.mark.asyncio
async def test_proxy_dispatches_server_paid_bodies_with_the_2048_cap(monkeypatch):
    """End-to-end wiring: a server-paid request leaves the proxy carrying the
    2048 default (regression for every request inheriting the 8192 default)."""
    dispatched: list[bytes] = []

    class CapturingClient:
        async def post(self, url, *, params, content, headers):
            dispatched.append(content)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "usageMetadata": {
                        "promptTokenCount": 120,
                        "cachedContentTokenCount": 80,
                        "candidatesTokenCount": 14,
                        "thoughtsTokenCount": 6,
                        "totalTokenCount": 140,
                    },
                    "trafficType": "PROVISIONED_THROUGHPUT",
                },
            )

    async def route(path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "vertex_ai", "adc", "us-central1")

    async def meter(_uid, path, _model, _action):
        return path

    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_client", lambda: CapturingClient())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(1))

    response = await desktop_proxy._proxy(
        make_request(workload="extraction"),
        "models/gemini-2.5-flash:generateContent",
        False,
        "user",
    )

    assert response.status_code == 200
    assert len(dispatched) == 1
    config = json.loads(dispatched[0])["generationConfig"]
    assert config["maxOutputTokens"] == 2048
    event = json.loads(output.getvalue())
    assert event["workload_class"] == "extraction"
    assert event["traffic_type"] == "PROVISIONED_THROUGHPUT"
    assert event["prompt_token_count"] == 120
    assert event["cached_content_token_count"] == 80
    assert event["candidates_token_count"] == 14
    assert event["thoughts_token_count"] == 6
    assert event["total_token_count"] == 140


def test_missing_usage_and_unknown_workload_are_safely_bucketed(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)
    missing_usage = desktop_proxy.ProxyTelemetry(make_request(), streaming=False)
    missing_usage.observe_gemini_response({"candidates": []})
    missing_usage.complete(outcome="success", status_code=200, retryable=False, phase="body")
    event = json.loads(output.getvalue())
    assert event["workload_class"] == "unknown"
    assert event["traffic_type"] == "unknown"
    assert "prompt_token_count" not in event
    assert (
        desktop_proxy.ProxyTelemetry(make_request(workload="private-feature-name"), streaming=False).workload_class
        == "unknown"
    )


@pytest.mark.asyncio
async def test_disconnect_cancels_in_flight_provider_call():
    disconnected = asyncio.Event()
    cancelled = asyncio.Event()

    class DisconnectingRequest:
        async def is_disconnected(self):
            return disconnected.is_set()

    async def provider_call():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(desktop_proxy._cancel_on_disconnect(DisconnectingRequest(), provider_call()))
    await asyncio.sleep(0)
    disconnected.set()
    with pytest.raises(desktop_proxy.ClientDisconnected):
        await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_outer_cancellation_cleans_up_in_flight_provider_call():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class ConnectedRequest:
        async def is_disconnected(self):
            return False

    async def provider_call():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(desktop_proxy._cancel_on_disconnect(ConnectedRequest(), provider_call()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("content_length", ["invalid", "-1"])
async def test_request_body_rejects_malformed_content_length(content_length):
    class RequestWithInvalidLength:
        headers = {"content-length": content_length}

        async def stream(self):
            raise AssertionError("invalid Content-Length must be rejected before reading the body")
            yield b""

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._read_request_body(RequestWithInvalidLength())

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_request_body_bounds_chunked_stream_without_calling_body(monkeypatch):
    streamed_chunks = 0

    class ChunkedRequest:
        headers = {}

        async def stream(self):
            nonlocal streamed_chunks
            for chunk in (b"123", b"456"):
                streamed_chunks += 1
                yield chunk

        async def body(self):
            raise AssertionError("request.body() would aggregate an unbounded chunked request")

    monkeypatch.setattr(desktop_proxy, "_MAX_BODY_BYTES", 5)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._read_request_body(ChunkedRequest())

    assert error.value.status_code == 413
    assert streamed_chunks == 2


@pytest.mark.asyncio
async def test_post_routing_validation_emits_one_typed_terminal_outcome(monkeypatch):
    async def meter(_uid, path, _model, _action):
        return path

    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "byok-key")
    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._proxy(
            make_request(query_string=b"key=attacker-key"),
            "models/gemini-2.5-flash:generateContent",
            False,
            "user",
        )

    assert error.value.status_code == 400
    assert error.value.headers["X-Omi-Failure-Phase"] == "routing"
    assert error.value.headers["X-Omi-Retryable"] == "false"
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(events) == 1
    assert events[0]["outcome"] == "validation_rejected"


@pytest.mark.asyncio
async def test_vertex_embedding_validation_is_typed_at_proxy_boundary(monkeypatch):
    async def meter(_uid, path, _model, _action):
        return path

    async def route(_path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "vertex_ai", "adc", "us-central1")

    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._proxy(
            make_request(b'{"contents":[]}'),
            "models/gemini-embedding-001:embedContent",
            False,
            "user",
        )

    assert error.value.status_code == 400
    assert error.value.headers["X-Omi-Error-Class"] == "validation_rejected"


@pytest.mark.asyncio
async def test_proxy_bounds_concurrency_pool_wait_and_labels_phase(monkeypatch):
    calls = 0

    class Client:
        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

    async def meter(_uid, path, _model, _action):
        return path

    async def route(_path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "vertex_ai", "adc", "us-central1")

    monkeypatch.setattr(desktop_proxy, "_POOL_WAIT_SECONDS", 0.001)
    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_client", lambda: Client())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(0))

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert calls == 0
    assert response.status_code == 504
    assert response.headers["X-Omi-Failure-Phase"] == "pool"


@pytest.mark.asyncio
async def test_streaming_defers_resource_acquisition_until_body_iteration(monkeypatch):
    streams_opened = 0
    streams_closed = 0
    chunks = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}],',
        b'"usageMetadata":{"promptTokenCount":10,"cachedContentTokenCount":4,',
        b'"candidatesTokenCount":2,"thoughtsTokenCount":1,"totalTokenCount":13},',
        b'"trafficType":"ON_DEMAND"}\r\n\r\n',
    ]

    class UpstreamResponse:
        status_code = 200

        async def aiter_bytes(self):
            for chunk in chunks:
                yield chunk

    class StreamContext:
        async def __aenter__(self):
            return UpstreamResponse()

        async def __aexit__(self, *_args):
            nonlocal streams_closed
            streams_closed += 1

    class Client:
        def stream(self, *args, **kwargs):
            nonlocal streams_opened
            streams_opened += 1
            return StreamContext()

    async def meter(_uid, path, _model, _action):
        return path

    async def route(_path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "vertex_ai", "adc", "us-central1")

    async def await_upstream(_request, awaitable):
        return await awaitable

    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "_cancel_on_disconnect", await_upstream)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_stream_client", lambda: Client())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(1))
    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)

    response = await desktop_proxy._proxy(
        make_request(workload="interactive"), "models/gemini-2.5-flash:streamGenerateContent", True, "user"
    )

    assert response.status_code == 200
    assert streams_opened == 0
    received = [chunk async for chunk in response.body_iterator]
    assert received == chunks
    assert streams_opened == 1
    assert streams_closed == 1
    event = json.loads(output.getvalue())
    assert event["workload_class"] == "interactive"
    assert event["traffic_type"] == "ON_DEMAND"
    assert event["prompt_token_count"] == 10
    assert event["cached_content_token_count"] == 4
    assert event["candidates_token_count"] == 2
    assert event["thoughts_token_count"] == 1
    assert event["total_token_count"] == 13
