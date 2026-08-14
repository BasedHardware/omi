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
) -> Request:
    sent = False
    pending = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await pending.wait()

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/proxy/gemini/models/gemini-2.5-flash:generateContent",
            "query_string": query_string,
            "headers": [(b"x-omi-request-id", b"request-12345678")],
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
    monkeypatch.setattr(desktop_proxy, "is_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


@pytest.mark.asyncio
async def test_server_gemini_meter_downgrades_pro_after_the_soft_limit(monkeypatch):
    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return True, 31, 86_400
            return True, 1, 60
        return 31, 86_400

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.delenv("OMI_MODEL_TIER", raising=False)

    assert (
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )
        == "models/gemini-2.5-flash:generateContent"
    )


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
    chunk = b'data: {"ok":true}\n\n'

    class UpstreamResponse:
        status_code = 200

        async def aiter_bytes(self):
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

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:streamGenerateContent", True, "user")

    assert response.status_code == 200
    assert streams_opened == 0
    chunks = [chunk async for chunk in response.body_iterator]
    assert chunks == [chunk]
    assert streams_opened == 1
    assert streams_closed == 1
