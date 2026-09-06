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
from utils.managed_compute import Decision
from utils.observability import journeys
from config.plan_catalog import PlanType


def make_request(
    body: bytes = b'{"contents":[{"parts":[{"text":"hello"}]}]}',
    *,
    query_string: bytes = b"",
    workload: str | None = None,
    platform: str | None = None,
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
    if platform is not None:
        headers.append((b"x-app-platform", platform.encode()))
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
    async def run_blocking(_, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "is_desktop_trial_paywalled", lambda uid, platform, **kwargs: True)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


def _decision(*, allowed: bool, reason: str, plan: PlanType | None = PlanType.basic) -> Decision:
    return Decision(
        allowed=allowed,
        reason=reason,
        feature=desktop_proxy._PLAN_GATED_PROXY_FEATURE,
        funding_owner="omi",
        plan=plan,
        plan_resolved=plan is not None,
    )


async def _passthrough_run_blocking(_, function, *args, **kwargs):
    return function(*args, **kwargs)


@pytest.mark.asyncio
async def test_gemini_proxy_rejects_basic_generate_with_structured_402(monkeypatch):
    """Route-level S14 gate: basic + generateContent never reaches the provider.

    red-proof: drop the gemini_proxy await _enforce_managed_plan_gate call and
    this test still passes if it only drove _proxy.
    """
    provider_calls = []

    async def should_not_proxy(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("provider must not run for a plan-gated basic user")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(
        desktop_proxy,
        "authorize_managed_compute",
        lambda *_args, **_kwargs: _decision(allowed=False, reason="basic_not_entitled"),
    )
    monkeypatch.setattr(desktop_proxy, "_proxy", should_not_proxy)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy.gemini_proxy(
            make_request(),
            "models/gemini-2.5-flash:generateContent",
            "basic-uid",
        )

    assert error.value.status_code == 402
    assert error.value.detail == {
        "error": "plan_gated",
        "plan_type": "basic",
        "reason": "basic_not_entitled",
    }
    assert provider_calls == []


@pytest.mark.asyncio
async def test_gemini_stream_proxy_rejects_basic_stream_generate(monkeypatch):
    provider_calls = []

    async def should_not_proxy(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("stream provider must not run for a plan-gated basic user")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(
        desktop_proxy,
        "authorize_managed_compute",
        lambda *_args, **_kwargs: _decision(allowed=False, reason="basic_not_entitled"),
    )
    monkeypatch.setattr(desktop_proxy, "_proxy", should_not_proxy)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy.gemini_stream_proxy(
            make_request(),
            "models/gemini-2.5-flash:streamGenerateContent",
            "basic-uid",
        )

    assert error.value.status_code == 402
    assert error.value.detail["error"] == "plan_gated"
    assert provider_calls == []


@pytest.mark.asyncio
async def test_gemini_proxy_allows_paid_generate_to_reach_the_provider(monkeypatch):
    from fastapi.responses import Response

    seen = []

    async def fake_proxy(request, path, streaming, uid):
        seen.append((path, streaming, uid))
        return Response(b'{"ok":true}', media_type="application/json")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(
        desktop_proxy,
        "authorize_managed_compute",
        lambda *_args, **_kwargs: _decision(allowed=True, reason="plan_paid", plan=PlanType.plus),
    )
    monkeypatch.setattr(desktop_proxy, "_proxy", fake_proxy)

    response = await desktop_proxy.gemini_proxy(
        make_request(),
        "models/gemini-2.5-flash:generateContent",
        "plus-uid",
    )

    assert response.status_code == 200
    assert seen == [("models/gemini-2.5-flash:generateContent", False, "plus-uid")]


@pytest.mark.asyncio
async def test_gemini_proxy_allows_basic_byok_generate(monkeypatch):
    from fastapi.responses import Response

    funding = []

    def authorize(uid, feature, funding_owner, **_kwargs):
        funding.append((uid, feature, funding_owner))
        return Decision(
            allowed=True,
            reason="byok",
            feature=feature,
            funding_owner=funding_owner,
            plan=PlanType.basic,
            plan_resolved=True,
        )

    async def fake_proxy(*_args, **_kwargs):
        return Response(b'{"ok":true}', media_type="application/json")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda provider: "gk" if provider == "gemini" else None)
    monkeypatch.setattr(desktop_proxy, "authorize_managed_compute", authorize)
    monkeypatch.setattr(desktop_proxy, "_proxy", fake_proxy)

    response = await desktop_proxy.gemini_proxy(
        make_request(),
        "models/gemini-2.5-flash:generateContent",
        "byok-basic",
    )

    assert response.status_code == 200
    assert funding == [("byok-basic", "screen_frame_judge", "byok")]


@pytest.mark.asyncio
async def test_gemini_proxy_does_not_plan_gate_embed_content(monkeypatch):
    from fastapi.responses import Response

    auth_calls = []

    def authorize(*_args, **_kwargs):
        auth_calls.append(True)
        return _decision(allowed=False, reason="basic_not_entitled")

    async def fake_proxy(*_args, **_kwargs):
        return Response(b'{"embedding":{"values":[1]}}', media_type="application/json")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(desktop_proxy, "authorize_managed_compute", authorize)
    monkeypatch.setattr(desktop_proxy, "_proxy", fake_proxy)

    response = await desktop_proxy.gemini_proxy(
        make_request(),
        "models/gemini-embedding-001:embedContent",
        "basic-uid",
    )

    assert response.status_code == 200
    assert auth_calls == [], "embedContent is TBD-4 / S24 and must not inherit the generate gate"


@pytest.mark.asyncio
async def test_gemini_proxy_fails_closed_when_authorization_is_unavailable(monkeypatch):
    provider_calls = []

    async def should_not_proxy(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("unavailable authorization must not fall through to the provider")

    monkeypatch.setattr(desktop_proxy, "run_blocking", _passthrough_run_blocking)
    monkeypatch.setattr(
        desktop_proxy,
        "authorize_managed_compute",
        lambda *_args, **_kwargs: _decision(allowed=False, reason="authorization_unavailable", plan=None),
    )
    monkeypatch.setattr(desktop_proxy, "_proxy", should_not_proxy)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy.gemini_proxy(
            make_request(),
            "models/gemini-2.5-flash:generateContent",
            "basic-uid",
        )

    assert error.value.status_code == 503
    assert provider_calls == []


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


@pytest.mark.parametrize("upstream_status", [502, 503])
def test_provider_availability_fault_authorizes_client_replay(monkeypatch, upstream_status):
    """An upstream 502/503 delivered nothing, so the caller may re-issue it.

    Both desktop clients read this decision off the wire: macOS gates
    `shouldAutoRetry` on `X-Omi-Retryable`, and the Windows Gemini and rewind
    embedding clients retry only on a 429 or a 503 status. Reporting a
    non-retryable 502 revoked replay on both at once.
    """
    output = io.StringIO()
    monkeypatch.setattr(desktop_proxy.sys, "stdout", output)
    telemetry = desktop_proxy.ProxyTelemetry(make_request(), streaming=False)
    response = httpx.Response(upstream_status, request=httpx.Request("POST", "https://provider.invalid"))

    result = desktop_proxy._provider_error(response, telemetry)

    assert result.status_code == 503
    assert result.headers["x-omi-error-class"] == "provider_unavailable"
    assert result.headers["x-omi-retryable"] == "true"
    assert result.headers["retry-after"] == str(desktop_proxy._PROVIDER_UNAVAILABLE_RETRY_AFTER_SECONDS)
    event = json.loads(output.getvalue())
    assert event["outcome"] == "provider_unavailable"
    assert event["upstream_status"] == upstream_status
    assert event["retryable"] is True


def test_provider_internal_error_stays_terminal(monkeypatch):
    """500 is not an availability signal — it can be a verdict on the request,
    so it keeps the terminal 502 rather than inviting a replay of the same body."""
    monkeypatch.setattr(desktop_proxy.sys, "stdout", io.StringIO())
    telemetry = desktop_proxy.ProxyTelemetry(make_request(), streaming=False)
    response = httpx.Response(500, request=httpx.Request("POST", "https://provider.invalid"))

    result = desktop_proxy._provider_error(response, telemetry)

    assert result.status_code == 502
    assert result.headers["x-omi-retryable"] == "false"


@pytest.mark.asyncio
async def test_proxy_reports_upstream_unavailable_as_retryable(monkeypatch):
    """The whole non-stream route, from dispatch to the headers the client sees."""

    class UnavailableClient:
        async def post(self, *args, **kwargs):
            return httpx.Response(
                503,
                json={"error": {"code": 503, "message": "The service is currently unavailable."}},
                request=httpx.Request("POST", "https://provider.invalid"),
            )

    async def meter(_uid, path, _model, _action):
        return path

    async def route(path, _model, _action, _query, **_kwargs):
        return desktop_proxy.UpstreamRoute("https://provider.invalid", {}, {}, "ai_studio", "server_key", "global")

    monkeypatch.setattr(desktop_proxy.sys, "stdout", io.StringIO())
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_client", lambda: UnavailableClient())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(1))

    response = await desktop_proxy._proxy(
        make_request(), "models/gemini-embedding-001:batchEmbedContents", False, "user"
    )

    assert response.status_code == 503
    assert response.headers["x-omi-retryable"] == "true"
    assert response.headers["x-omi-error-class"] == "provider_unavailable"
    assert "currently unavailable" not in response.body.decode()


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


@pytest.fixture(autouse=True)
def _reset_pt_promotion_state():
    """Observed capacity and learned reachability are module state; never leak
    them between tests. Reachability is a per-model table now, so clearing one
    target field is no longer enough."""
    desktop_proxy._pt_target_ready = False
    desktop_proxy._pt_target_probed_at = None
    desktop_proxy._model_unavailable_at.clear()
    yield
    desktop_proxy._pt_target_ready = False
    desktop_proxy._pt_target_probed_at = None
    desktop_proxy._model_unavailable_at.clear()


def _retarget(path: str) -> str:
    return desktop_proxy._retarget_path(*desktop_proxy._path_parts(path))


def test_pro_is_remapped_to_the_migration_target(monkeypatch):
    """gemini-2.5-pro is $10.00/1M out; the target is $1.50."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert _retarget("models/gemini-2.5-pro:generateContent") == "models/gemini-3.1-flash-lite:generateContent"


def test_client_pinned_flash_lite_is_never_promoted(monkeypatch):
    """gemini-3.1-flash-lite costs 3.75x more per output token than
    gemini-2.5-flash-lite, so promoting the client-pinned low-value lanes
    (macOS ModelQoS.lightweight, Windows memory/goals/insight) would be a large
    cost regression, not a saving."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert _retarget("models/gemini-2.5-flash-lite:generateContent") == ("models/gemini-2.5-flash-lite:generateContent")


def test_byok_models_are_never_remapped(monkeypatch):
    """BYOK users pay for the model they asked for."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "user-key")
    assert _retarget("models/gemini-2.5-pro:generateContent") == "models/gemini-2.5-pro:generateContent"


def test_flash_stays_on_the_current_reservation_until_target_capacity_exists(monkeypatch):
    """Moving dedicated traffic early pays for an idle reservation AND on-demand."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert _retarget("models/gemini-2.5-flash:generateContent") == "models/gemini-2.5-flash:generateContent"


def test_flash_is_remapped_once_the_target_reservation_is_observed(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    desktop_proxy._record_pt_target_observation(True)
    assert _retarget("models/gemini-2.5-flash:generateContent") == "models/gemini-3.1-flash-lite:generateContent"


def test_operator_override_pins_the_reservation_back(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    desktop_proxy._record_pt_target_observation(True)
    monkeypatch.setenv(desktop_proxy._PT_MODEL_OVERRIDE_ENV, "gemini-2.5-flash")
    assert _retarget("models/gemini-2.5-flash:generateContent") == "models/gemini-2.5-flash:generateContent"


def test_overflow_never_targets_the_live_reservation(monkeypatch):
    """FC-degraded-fallback-consumes-protected-budget across the migration."""
    monkeypatch.delenv(desktop_proxy._OVERFLOW_MODEL_OVERRIDE_ENV, raising=False)
    ladder = desktop_proxy.ptr.resolve_overflow_ladder
    assert ladder(pt_model="gemini-2.5-flash")[0] == "gemini-3.1-flash-lite"
    assert ladder(pt_model="gemini-3.1-flash-lite")[0] == "gemini-2.5-flash-lite"
    for pt in ("gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"):
        assert pt not in ladder(pt_model=pt)


def test_overflow_plan_is_empty_for_traffic_that_cannot_exhaust_the_reservation(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert desktop_proxy._overflow_plan("gemini-2.5-flash-lite") == []


def test_overflow_plan_probes_the_target_before_paying_on_demand(monkeypatch):
    monkeypatch.delenv(desktop_proxy._OVERFLOW_MODEL_OVERRIDE_ENV, raising=False)
    plan = desktop_proxy._overflow_plan("gemini-2.5-flash")
    assert plan == [
        ("gemini-3.1-flash-lite", "dedicated"),
        ("gemini-3.1-flash-lite", "shared"),
        ("gemini-2.5-flash-lite", "shared"),
    ]


def test_overflow_skips_a_rung_traffic_has_proved_unreachable(monkeypatch):
    """Keeping an unreachable rung in the plan would spend a round trip to 404
    on every overflow request."""
    monkeypatch.delenv(desktop_proxy._OVERFLOW_MODEL_OVERRIDE_ENV, raising=False)
    desktop_proxy._record_model_unavailable(desktop_proxy.VERTEX_PT_TARGET_MODEL)
    assert desktop_proxy._overflow_plan("gemini-2.5-flash") == [("gemini-2.5-flash-lite", "shared")]


def test_pro_falls_back_when_the_target_is_unreachable(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    desktop_proxy._record_model_unavailable(desktop_proxy.VERTEX_PT_TARGET_MODEL)
    assert _retarget("models/gemini-2.5-pro:generateContent") == (
        f"models/{desktop_proxy._QUOTA_DEMOTION_MODEL}:generateContent"
    )


def test_an_unavailable_target_cannot_be_considered_a_live_reservation():
    """A model that cannot be reached cannot be holding prepaid capacity."""
    desktop_proxy._record_pt_target_observation(True)
    assert desktop_proxy._pt_target_is_ready() is True
    desktop_proxy._record_model_unavailable(desktop_proxy.VERTEX_PT_TARGET_MODEL)
    assert desktop_proxy._pt_target_is_ready() is False


def test_model_unavailability_is_distinguished_from_capacity_conditions():
    not_enabled = "Publisher model `projects/p/locations/l/publishers/google/models/m` was not found"
    assert desktop_proxy.ptr.is_model_unavailable(404, not_enabled)
    assert not desktop_proxy.ptr.is_model_unavailable(404, "The requested resource was not found")
    assert not desktop_proxy.ptr.is_model_unavailable(429, "Exceeded the Provisioned Throughput.")
    assert not desktop_proxy._overflow_triggered(404, not_enabled)


def test_overflow_can_be_disabled_for_an_emergency(monkeypatch):
    monkeypatch.setenv(desktop_proxy._OVERFLOW_ENABLED_ENV, "false")
    assert desktop_proxy._overflow_plan("gemini-2.5-flash") == []


def test_thinking_budget_is_sent_to_every_model_family():
    """Measured 2026-08-18: gemini-3.1-flash-lite honors thinkingBudget
    (0 -> thoughts 0, 1024 -> thoughts 278) and 2.5 models reject
    thinkingLevel with HTTP 400. One body is therefore valid on both families,
    so a fallback that crosses families rewrites nothing."""
    body = desktop_proxy._sanitize(b'{"contents":[]}', "generateContent")
    assert json.loads(body)["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": desktop_proxy._DEFAULT_THINKING_BUDGET
    }


@pytest.mark.asyncio
async def test_dedicated_capacity_is_requested_only_for_the_reservation(monkeypatch):
    async def token():
        return "token"

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy._vertex_tokens, "get_access_token", token)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    reserved = await desktop_proxy._upstream(
        "models/gemini-2.5-flash:generateContent", "gemini-2.5-flash", "generateContent", {}
    )
    on_demand = await desktop_proxy._upstream(
        "models/gemini-3.1-flash-lite:generateContent", "gemini-3.1-flash-lite", "generateContent", {}
    )

    header = desktop_proxy.ptr.REQUEST_TYPE_HEADER
    assert reserved.headers[header] == "dedicated"
    assert on_demand.headers[header] == "shared"


def _pt_exhausted_response(url: str) -> httpx.Response:
    return httpx.Response(
        429,
        request=httpx.Request("POST", url),
        json={"error": {"code": 429, "message": "Too many requests. Exceeded the Provisioned Throughput."}},
    )


def _ok_response(url: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}},
    )


class _ScriptedClient:
    """Replies per attempt so an overflow ladder can be asserted in order."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls: list[tuple[str, str, bytes]] = []

    async def post(self, url, *, params, content, headers):
        header = desktop_proxy.ptr.REQUEST_TYPE_HEADER
        self.calls.append((url, headers.get(header, ""), content))
        return self._replies[len(self.calls) - 1](url)


def _install_proxy_doubles(monkeypatch, client):
    routed: list[tuple[str, str]] = []

    async def route(path, model, action, query, *, request_type=None):
        routed.append((model, request_type or ""))
        return desktop_proxy.UpstreamRoute(
            f"https://provider.invalid/{model}",
            {desktop_proxy.ptr.REQUEST_TYPE_HEADER: request_type or "dedicated"},
            {},
            "vertex_ai",
            "adc",
            "us-central1",
        )

    async def meter(_uid, path, _model, _action):
        return path

    async def passthrough(_request, awaitable):
        # The disconnect watcher polls a test Request whose receive() never
        # returns, which would hold every attempt open for the full 75s
        # provider deadline. Its real behaviour is covered by
        # test_disconnect_cancels_in_flight_provider_call.
        return await awaitable

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "_cancel_on_disconnect", passthrough)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_client", lambda: client)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: asyncio.Semaphore(1))
    return routed


@pytest.mark.asyncio
async def test_saturated_reservation_probes_the_target_then_pays_on_demand(monkeypatch):
    """A full reservation must not silently spill onto pay-as-you-go flash.

    Attempt 1 is the reservation. Attempt 2 asks the migration target for
    dedicated capacity and is refused. Attempt 3 buys the same work on-demand
    at gemini-3.1-flash-lite rates ($1.50/1M out) instead of gemini-2.5-flash
    spillover ($2.50/1M out).
    """
    client = _ScriptedClient([_pt_exhausted_response, _pt_exhausted_response, _ok_response])
    routed = _install_proxy_doubles(monkeypatch, client)

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert response.status_code == 200
    assert routed == [
        ("gemini-2.5-flash", ""),
        ("gemini-3.1-flash-lite", "dedicated"),
        ("gemini-3.1-flash-lite", "shared"),
    ]
    assert desktop_proxy._pt_target_is_ready() is False


@pytest.mark.asyncio
async def test_a_successful_dedicated_probe_promotes_the_reservation(monkeypatch):
    """This is the whole migration mechanism: no deploy, no flag, no date."""
    client = _ScriptedClient([_pt_exhausted_response, _ok_response])
    routed = _install_proxy_doubles(monkeypatch, client)

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert response.status_code == 200
    assert routed == [("gemini-2.5-flash", ""), ("gemini-3.1-flash-lite", "dedicated")]
    assert desktop_proxy._pt_target_is_ready() is True
    # And from now on flash requests are served by the new reservation.
    assert _retarget("models/gemini-2.5-flash:generateContent") == "models/gemini-3.1-flash-lite:generateContent"


@pytest.mark.asyncio
async def test_generic_rate_limiting_is_not_converted_into_extra_spend(monkeypatch):
    """A per-project 429 is backpressure. Treating it as overflow would buy
    on-demand capacity to work around a limit that is not about capacity."""

    def throttled(url):
        return httpx.Response(
            429,
            request=httpx.Request("POST", url),
            json={"error": {"code": 429, "message": "Quota exceeded for requests per minute"}},
        )

    client = _ScriptedClient([throttled])
    routed = _install_proxy_doubles(monkeypatch, client)

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert response.status_code == 429
    assert routed == [("gemini-2.5-flash", "")]


@pytest.mark.asyncio
async def test_overflow_keeps_the_bounded_generation_config(monkeypatch):
    """Overflow crosses model families, and the caps that bound paid output
    must survive the crossing. thinkingBudget is honored by both families
    (measured 2026-08-18), so the body is forwarded rather than rewritten."""
    client = _ScriptedClient([_pt_exhausted_response, _pt_exhausted_response, _ok_response])
    _install_proxy_doubles(monkeypatch, client)

    await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    reserved = json.loads(client.calls[0][2])["generationConfig"]
    overflowed = json.loads(client.calls[-1][2])["generationConfig"]
    assert reserved["thinkingConfig"] == {"thinkingBudget": desktop_proxy._DEFAULT_THINKING_BUDGET}
    assert overflowed["thinkingConfig"] == {"thinkingBudget": desktop_proxy._DEFAULT_THINKING_BUDGET}
    assert overflowed["maxOutputTokens"] == desktop_proxy._SERVER_PAID_MAX_OUTPUT_TOKENS


@pytest.mark.asyncio
async def test_streaming_overflow_falls_back_and_leaks_no_provider_slot(monkeypatch):
    """The streaming ladder must close every refused attempt and release its
    slot, or a saturated reservation would drain the concurrency pool."""
    opened: list[str] = []
    closed = 0

    class Refused:
        status_code = 429

        def __init__(self):
            self.text = "Too many requests. Exceeded the Provisioned Throughput."

        async def aread(self):
            return self.text.encode()

        async def aiter_bytes(self):
            yield b""

    class Served:
        status_code = 200
        text = ""

        async def aread(self):
            return b""

        async def aiter_bytes(self):
            yield b'data: {"usageMetadata":{"totalTokenCount":3}}\r\n\r\n'

    class StreamContext:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, *_args):
            nonlocal closed
            closed += 1

    class Client:
        def stream(self, _method, url, **_kwargs):
            opened.append(url)
            return StreamContext(Refused() if len(opened) < 3 else Served())

    async def route(path, model, action, query, *, request_type=None):
        return desktop_proxy.UpstreamRoute(
            f"https://provider.invalid/{model}",
            {desktop_proxy.ptr.REQUEST_TYPE_HEADER: request_type or "dedicated"},
            {},
            "vertex_ai",
            "adc",
            "us-central1",
        )

    async def passthrough(_request, awaitable):
        return await awaitable

    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "_cancel_on_disconnect", passthrough)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_stream_client", lambda: Client())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: semaphore)

    telemetry = desktop_proxy.ProxyTelemetry(make_request(), streaming=True)
    primary = await route("p", "gemini-2.5-flash", "streamGenerateContent", {})
    body = b'{"generationConfig":{"thinkingConfig":{"thinkingBudget":1024}}}'
    emitted = [
        chunk
        async for chunk in desktop_proxy._stream_provider(
            make_request(),
            primary,
            body,
            telemetry,
            model="gemini-2.5-flash",
            action="streamGenerateContent",
            query={},
        )
    ]

    assert b"usageMetadata" in b"".join(emitted)
    assert [url.rsplit("/", 1)[-1] for url in opened] == [
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite",
    ]
    assert closed == 3
    assert semaphore.locked() is False


def test_migration_contract_is_documented():
    """Same rule as the existing pin test: the reservation's behaviour is only
    safe to change if the note operators read changes with it."""
    text = (BACKEND_DIR / "docs" / "vertex-pt-flash.md").read_text(encoding="utf-8")
    assert desktop_proxy.VERTEX_PT_TARGET_MODEL in text
    assert desktop_proxy._PT_MODEL_OVERRIDE_ENV in text
    assert desktop_proxy._OVERFLOW_MODEL_OVERRIDE_ENV in text
    assert desktop_proxy._OVERFLOW_ENABLED_ENV in text
    assert desktop_proxy.ptr.REQUEST_TYPE_HEADER in text
    # The generalized fallback table and the endpoint split are operator-facing
    # behaviour: an operator reading only this note must be able to predict
    # which model and which endpoint a degraded request lands on.
    assert "MODEL_FALLBACKS" in text
    assert desktop_proxy.ptr.MULTI_REGION_HOST in text
    assert f"locations/{desktop_proxy.ptr.MULTI_REGION_LOCATION}" in text
    assert desktop_proxy._MULTI_REGION_LOCATION_ENV in text
    for model, chain in desktop_proxy.ptr.MODEL_FALLBACKS.items():
        assert model in text, f"{model} has a declared fallback chain but is undocumented"
        for rung in chain:
            assert rung in text


def test_a_new_instance_probes_immediately_regardless_of_uptime(monkeypatch):
    """time.monotonic() has an arbitrary origin: on a freshly started container
    it can be smaller than the probe TTL. Seeding the last-probe time with 0.0
    would suppress the first probe for the first 10 minutes of every new
    instance's life, which is most of a Cloud Run instance's life."""
    monkeypatch.setattr(desktop_proxy.time, "monotonic", lambda: 1.0)
    desktop_proxy._pt_target_probed_at = None
    assert desktop_proxy._pt_probe_due() is True

    desktop_proxy._record_pt_target_observation(False)
    assert desktop_proxy._pt_probe_due() is False


def _model_not_found_response(url: str) -> httpx.Response:
    model = url.rsplit("/", 1)[-1]
    return httpx.Response(
        404,
        request=httpx.Request("POST", url),
        json={
            "error": {
                "code": 404,
                "message": (
                    f"Publisher model `projects/based-hardware/locations/us-central1"
                    f"/publishers/google/models/{model}` was not found or your project "
                    f"does not have access to it."
                ),
            }
        },
    )


@pytest.mark.asyncio
async def test_pro_recovers_when_the_target_model_is_not_enabled(monkeypatch):
    """Observed in production 2026-08-18: every gemini-3.x model was listed in
    the global publisher catalog and 404 on the project-scoped endpoint. A Pro
    request remapped onto it must still be served, not fail."""
    client = _ScriptedClient([_model_not_found_response, _ok_response])
    routed = _install_proxy_doubles(monkeypatch, client)

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-pro:generateContent", False, "user")

    assert response.status_code == 200
    assert routed == [
        ("gemini-3.1-flash-lite", ""),
        ("gemini-2.5-flash-lite", "shared"),
    ]


@pytest.mark.asyncio
async def test_one_404_stops_the_whole_fleet_retrying_a_dead_model(monkeypatch):
    """The latch is what keeps a project-wide access gap from costing a wasted
    round trip on every single request."""
    client = _ScriptedClient([_model_not_found_response, _ok_response, _ok_response])
    routed = _install_proxy_doubles(monkeypatch, client)

    await desktop_proxy._proxy(make_request(), "models/gemini-2.5-pro:generateContent", False, "user")
    assert desktop_proxy._model_believed_available(desktop_proxy.VERTEX_PT_TARGET_MODEL) is False

    await desktop_proxy._proxy(make_request(), "models/gemini-2.5-pro:generateContent", False, "user")
    # Second request goes straight to a model the project can call.
    assert routed[-1] == ("gemini-2.5-flash-lite", "")


@pytest.mark.asyncio
async def test_access_granted_later_promotes_without_a_deploy(monkeypatch):
    """Availability is re-checked on the same TTL as capacity, so enabling
    gemini-3.x for the project recovers the routing on its own."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    clock = {"now": 1_000.0}
    monkeypatch.setattr(desktop_proxy.time, "monotonic", lambda: clock["now"])

    desktop_proxy._record_model_unavailable(desktop_proxy.VERTEX_PT_TARGET_MODEL)
    assert _retarget("models/gemini-2.5-pro:generateContent") != ("models/gemini-3.1-flash-lite:generateContent")

    clock["now"] += desktop_proxy._PT_PROBE_TTL_SECONDS + 1
    assert _retarget("models/gemini-2.5-pro:generateContent") == ("models/gemini-3.1-flash-lite:generateContent")


# --- Endpoint selection ----------------------------------------------------


def test_gemini_3_x_is_routed_to_the_us_multi_region_endpoint(monkeypatch):
    """The production defect behind #11826.

    Measured 2026-08-18 with credentials that can invoke inference:
    gemini-3.1-flash-lite answers 200 on locations/us and 404s on us-central1,
    us-east5, us-west1, europe-west4 and asia-northeast1. The proxy built a
    regional URL for every model, so no 3.x request could ever succeed. It was
    never a project access gap.
    """
    monkeypatch.delenv(desktop_proxy._MULTI_REGION_LOCATION_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    assert desktop_proxy._vertex_url("gemini-3.1-flash-lite", "generateContent") == (
        "https://aiplatform.googleapis.com/v1/projects/based-hardware/locations/us"
        "/publishers/google/models/gemini-3.1-flash-lite:generateContent"
    )


def test_the_multi_region_residency_pin_is_us_and_is_operator_flippable(monkeypatch):
    """`global` may serve a request from anywhere in the world; `us` keeps
    inference in the US multi-region, matching where every other server-paid
    Gemini call in this service already runs. Users' conversations and
    transcripts go through this path, so widening residency must be a
    deliberate operator flip, never a side effect of a routing change."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.delenv(desktop_proxy._MULTI_REGION_LOCATION_ENV, raising=False)
    assert "/locations/us/" in str(desktop_proxy._vertex_url("gemini-3.1-flash-lite", "generateContent"))

    monkeypatch.setenv(desktop_proxy._MULTI_REGION_LOCATION_ENV, "global")
    assert "/locations/global/" in str(desktop_proxy._vertex_url("gemini-3.1-flash-lite", "generateContent"))


def test_the_reservation_model_is_never_routed_off_its_region(monkeypatch):
    """FC-degraded-fallback-consumes-protected-budget / the 2026-08-04 incident.

    gemini-2.5-flash ALSO answers 200 on locations/us and locations/global
    (trafficType=ON_DEMAND), so "route whatever answers multi-region to
    multi-region" is a tempting simplification. It would bypass the 5 GSU
    us-central1 Provisioned Throughput order and bill on-demand while the
    reservation kept charging ~$290/day — paying twice for the same tokens,
    which is precisely the 2026-08-04 double-pay regression recorded in
    docs/vertex-pt-flash.md. The endpoint rule is by model family, never by
    what happens to answer.
    """
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.setenv(desktop_proxy._MULTI_REGION_LOCATION_ENV, "global")
    url = desktop_proxy._vertex_url("gemini-2.5-flash", "generateContent")
    assert url == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/based-hardware/locations/us-central1"
        "/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert "locations/global" not in url
    assert "locations/us/" not in url
    assert "//aiplatform.googleapis.com" not in url


@pytest.mark.asyncio
async def test_a_fallback_across_families_also_crosses_endpoints(monkeypatch):
    """The reservation and the model that absorbs its overflow do not share a
    location, so location must be resolved per model, not once per process."""

    async def token():
        return "token"

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy._vertex_tokens, "get_access_token", token)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    reserved = await desktop_proxy._upstream(
        "models/gemini-2.5-flash:generateContent", "gemini-2.5-flash", "generateContent", {}
    )
    overflow = await desktop_proxy._upstream(
        "models/gemini-3.1-flash-lite:generateContent", "gemini-3.1-flash-lite", "generateContent", {}
    )
    assert reserved.region == "us-central1"
    assert overflow.region == "us"
    # Multi-region labels must survive the telemetry sanitizer, not log as none.
    assert desktop_proxy._safe_region(overflow.region) == "us"


# --- Generalized fallback chains -------------------------------------------


def test_every_routable_model_declares_a_fallback_chain():
    """A model the proxy can route to but that has no declared chain would have
    no defined behaviour when it stops answering."""
    text_models = {m for m in desktop_proxy._ALLOWED_MODELS}
    assert text_models <= set(desktop_proxy.ptr.MODEL_FALLBACKS)


def test_reachability_is_learned_per_model_not_globally(monkeypatch):
    """One dead model must not take the rest of the ladder down with it."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    desktop_proxy._record_model_unavailable("gemini-3.1-flash-lite")
    assert desktop_proxy._model_believed_available("gemini-3.1-flash-lite") is False
    assert desktop_proxy._model_believed_available("gemini-2.5-flash-lite") is True
    assert desktop_proxy._model_believed_available("gemini-2.5-flash") is True


def test_a_new_instance_believes_every_model_reachable_regardless_of_uptime(monkeypatch):
    """Same arbitrary-origin trap as the probe timestamp: time.monotonic() on a
    fresh container can be smaller than the TTL, so an observation seeded with
    0.0 would mark every model dead for the first 10 minutes of the instance's
    life. Absence of a key, not a zero, means 'never observed'."""
    monkeypatch.setattr(desktop_proxy.time, "monotonic", lambda: 1.0)
    desktop_proxy._model_unavailable_at.clear()
    for model in desktop_proxy.ptr.MODEL_FALLBACKS:
        assert desktop_proxy._model_believed_available(model) is True


def test_a_success_clears_a_stale_unreachable_latch(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    desktop_proxy._record_model_unavailable("gemini-3.1-flash-lite")
    assert desktop_proxy._model_believed_available("gemini-3.1-flash-lite") is False
    desktop_proxy._record_model_available("gemini-3.1-flash-lite")
    assert desktop_proxy._model_believed_available("gemini-3.1-flash-lite") is True


def test_byok_traffic_never_teaches_the_reachability_table(monkeypatch):
    """BYOK goes to AI Studio on the user's own key, so its answers say nothing
    about what this project can reach on Vertex. One user's key must not be
    able to latch a model dead for the whole fleet."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "user-key")
    desktop_proxy._record_model_unavailable("gemini-3.1-flash-lite")
    assert desktop_proxy._model_unavailable_at == {}
    assert desktop_proxy._recovery_plan("gemini-3.1-flash-lite", 404, "publisher model was not found") == []


@pytest.mark.parametrize("pt_model", ["gemini-2.5-flash", "gemini-3.1-flash-lite"])
def test_no_recovery_plan_ever_routes_onto_the_reservation(monkeypatch, pt_model):
    """FC-degraded-fallback-consumes-protected-budget, through the proxy rather
    than the policy module, at both PT states."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.delenv(desktop_proxy._OVERFLOW_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(desktop_proxy._PT_MODEL_OVERRIDE_ENV, pt_model)
    not_found = "Publisher model was not found or your project does not have access to it."
    exhausted = "Too many requests. Exceeded the provisioned throughput."
    for model in sorted(desktop_proxy.ptr.MODEL_FALLBACKS):
        desktop_proxy._model_unavailable_at.clear()
        for status, message in ((404, not_found), (429, exhausted)):
            plan = desktop_proxy._recovery_plan(model, status, message)
            assert pt_model not in [rung for rung, _ in plan], (model, status, plan)


def test_a_dead_model_is_never_offered_its_own_name_as_a_fallback(monkeypatch):
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    plan = desktop_proxy._recovery_plan("gemini-3.1-flash-lite", 404, "publisher model was not found")
    assert "gemini-3.1-flash-lite" not in [rung for rung, _ in plan]


def test_a_terminal_model_has_no_recovery_plan(monkeypatch):
    """gemini-2.5-flash-lite is the floor of the ladder. Inventing a fallback
    for it would promote the client-pinned lanes onto a costlier model."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert desktop_proxy._recovery_plan("gemini-2.5-flash-lite", 404, "publisher model was not found") == []


@pytest.mark.asyncio
async def test_a_404_on_any_model_falls_back_and_latches_it(monkeypatch):
    """Generalized from the migration target to every routable model: the
    second request must not repeat the round trip that already failed."""
    client = _ScriptedClient([_model_not_found_response, _ok_response, _ok_response])
    routed = _install_proxy_doubles(monkeypatch, client)
    desktop_proxy._record_pt_target_observation(True)  # 3.1-flash-lite now holds PT

    response = await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")

    assert response.status_code == 200
    # Flash is served by the promoted reservation, 404s, and steps to the floor.
    assert routed == [("gemini-3.1-flash-lite", ""), ("gemini-2.5-flash-lite", "shared")]
    assert desktop_proxy._model_believed_available("gemini-3.1-flash-lite") is False

    # The second request never re-attempts the latched model: a model that
    # cannot be reached cannot be holding prepaid capacity, so the reservation
    # demotes back to gemini-2.5-flash and serves flash traffic directly.
    await desktop_proxy._proxy(make_request(), "models/gemini-2.5-flash:generateContent", False, "user")
    assert routed[-1] == ("gemini-2.5-flash", "")
    assert "gemini-3.1-flash-lite" not in [model for model, _ in routed[2:]]


@pytest.mark.asyncio
async def test_streaming_unreachable_model_falls_back_and_leaks_no_provider_slot(monkeypatch):
    """The 404 ladder gets the same lifecycle guarantee as the overflow ladder:
    every refused attempt is closed and its provider slot released."""
    opened: list[str] = []
    closed = 0

    class NotFound:
        status_code = 404
        text = "Publisher model `.../models/gemini-3.1-flash-lite` was not found or your project does not have access."

        async def aread(self):
            return self.text.encode()

        async def aiter_bytes(self):
            yield b""

    class Served:
        status_code = 200
        text = ""

        async def aread(self):
            return b""

        async def aiter_bytes(self):
            yield b'data: {"usageMetadata":{"totalTokenCount":3}}\r\n\r\n'

    class StreamContext:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, *_args):
            nonlocal closed
            closed += 1

    class Client:
        def stream(self, _method, url, **_kwargs):
            opened.append(url)
            return StreamContext(NotFound() if len(opened) < 2 else Served())

    async def route(path, model, action, query, *, request_type=None):
        return desktop_proxy.UpstreamRoute(
            f"https://provider.invalid/{model}",
            {desktop_proxy.ptr.REQUEST_TYPE_HEADER: request_type or "shared"},
            {},
            "vertex_ai",
            "adc",
            "us-central1",
        )

    async def passthrough(_request, awaitable):
        return await awaitable

    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_upstream", route)
    monkeypatch.setattr(desktop_proxy, "_cancel_on_disconnect", passthrough)
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_stream_client", lambda: Client())
    monkeypatch.setattr(desktop_proxy, "get_desktop_gemini_semaphore", lambda: semaphore)

    telemetry = desktop_proxy.ProxyTelemetry(make_request(), streaming=True)
    primary = await route("p", "gemini-3.1-flash-lite", "streamGenerateContent", {})
    emitted = [
        chunk
        async for chunk in desktop_proxy._stream_provider(
            make_request(),
            primary,
            b'{"generationConfig":{"thinkingConfig":{"thinkingBudget":1024}}}',
            telemetry,
            model="gemini-3.1-flash-lite",
            action="streamGenerateContent",
            query={},
        )
    ]

    assert b"usageMetadata" in b"".join(emitted)
    assert [url.rsplit("/", 1)[-1] for url in opened] == ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
    assert closed == 2
    assert semaphore.locked() is False
    assert desktop_proxy._model_believed_available("gemini-3.1-flash-lite") is False


@pytest.mark.parametrize("target_reachable", [True, False])
@pytest.mark.parametrize("reservation_promoted", [True, False])
def test_server_paid_traffic_never_dispatches_gemini_2_5_pro(monkeypatch, target_reachable, reservation_promoted):
    """gemini-2.5-pro is $10.00/1M out — 6.7x gemini-3.1-flash-lite and 25x
    gemini-2.5-flash-lite. No combination of reservation state and learned
    reachability may leave a server-paid request actually being served by it.

    MODEL_FALLBACKS still lists a chain for it because a client may still
    *request* it (it stays proxy-allowlisted, and BYOK users pay for it
    themselves), but no server-paid request reaches dispatch as Pro.
    """
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    if reservation_promoted:
        desktop_proxy._record_pt_target_observation(True)
    if not target_reachable:
        desktop_proxy._record_model_unavailable(desktop_proxy.VERTEX_PT_TARGET_MODEL)

    served = _retarget("models/gemini-2.5-pro:generateContent")

    assert "gemini-2.5-pro" not in served
    expected = (
        f"models/{desktop_proxy.VERTEX_PT_TARGET_MODEL}:generateContent"
        if target_reachable
        else f"models/{desktop_proxy._QUOTA_DEMOTION_MODEL}:generateContent"
    )
    assert served == expected


def test_byok_pro_is_still_honoured_because_the_user_pays_for_it(monkeypatch):
    """The guarantee above is about company-paid spend, not about banning the
    model: a BYOK user asking for Pro gets Pro on their own key."""
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: "user-key")
    assert _retarget("models/gemini-2.5-pro:generateContent") == ("models/gemini-2.5-pro:generateContent")


def _capture_proxy_journeys(monkeypatch):
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
async def test_desktop_proxy_proactivity_journey_requires_content_and_terminal_marker(monkeypatch):
    terminal = _capture_proxy_journeys(monkeypatch)

    async def source():
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"suggestion"}]}}]}\n\n'
        yield b'data: {"candidates":[{"content":{"parts":[{"text":""}]},"finishReason":"STOP"}]}\n\n'

    async def unobserved(*_args, **_kwargs):
        return desktop_proxy.StreamingResponse(source(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_unobserved', unobserved)
    response = await desktop_proxy._proxy(
        make_request(workload='maintenance', platform='macos'),
        'models/gemini-2.5-flash-lite:streamGenerateContent',
        True,
        'user-1',
    )
    assert [chunk async for chunk in response.body_iterator]
    assert terminal == [('desktop_proactivity', 'desktop_macos', 'success', None)]


@pytest.mark.asyncio
async def test_desktop_proxy_proactivity_journey_catches_post_200_error_event(monkeypatch):
    terminal = _capture_proxy_journeys(monkeypatch)

    async def source():
        yield b'data: {"error":"provider_timeout","phase":"body"}\n\n'

    async def unobserved(*_args, **_kwargs):
        return desktop_proxy.StreamingResponse(source(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_unobserved', unobserved)
    response = await desktop_proxy._proxy(
        make_request(workload='maintenance', platform='windows'),
        'models/gemini-2.5-flash-lite:streamGenerateContent',
        True,
        'user-1',
    )
    assert [chunk async for chunk in response.body_iterator]
    assert terminal == [('desktop_proactivity', 'desktop_windows', 'failure', 'provider_error')]


@pytest.mark.asyncio
async def test_desktop_proxy_proactivity_journey_marks_redis_cap_degraded(monkeypatch):
    terminal = _capture_proxy_journeys(monkeypatch)

    async def capped(*_args, **_kwargs):
        raise desktop_proxy._GeminiRateLimitExceeded('daily cap', retryable=False, retry_after=60)

    monkeypatch.setattr(desktop_proxy, '_proxy_unobserved', capped)
    with pytest.raises(desktop_proxy.HTTPException) as error:
        await desktop_proxy._proxy(
            make_request(workload='maintenance', platform='linux'),
            'models/gemini-2.5-flash-lite:generateContent',
            False,
            'user-1',
        )

    assert error.value.status_code == 429
    assert terminal == [('desktop_proactivity', 'desktop_linux', 'degraded', 'quota_capped')]


# --- Company-paid gateway hop (desktop stays the BFF) ----------------------


def _gateway_feature_mode(monkeypatch):
    monkeypatch.setenv("OMI_LLM_GATEWAY_FEATURE_MODE", "gateway")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)


def _install_gateway_doubles(monkeypatch, *, byok: str | None = None):
    """Metering on, direct provider plumbing instrumented to fail loudly."""
    from utils.llm import desktop_gemini_gateway as dgg

    monkeypatch.setattr(dgg, 'get_byok_key', lambda _provider: byok)

    async def meter(_uid, path, _model, _action):
        return path

    async def passthrough(_request, awaitable):
        return await awaitable

    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.setattr(desktop_proxy, "_meter_server_request", meter)
    monkeypatch.setattr(desktop_proxy, "_cancel_on_disconnect", passthrough)
    monkeypatch.setattr(
        desktop_proxy,
        "get_desktop_gemini_client",
        lambda: pytest.fail("company-paid gateway mode must not dispatch direct provider traffic"),
    )
    return dgg


@pytest.mark.asyncio
async def test_company_paid_generate_content_hops_the_gateway_never_vertex_direct(monkeypatch):
    _gateway_feature_mode(monkeypatch)
    _install_gateway_doubles(monkeypatch)
    monkeypatch.delenv("OMI_LLM_GATEWAY_URL", raising=False)

    captured: dict = {}

    class FakeResult:
        gemini_payload = {"candidates": [{"content": {"parts": [{"text": "gateway answer"}]}}]}

    async def fake_chat(body, *, model, action, uid):
        captured.update(body=json.loads(body), model=model, action=action, uid=uid)
        return FakeResult()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(desktop_proxy.desktop_gemini_gateway, "gateway_desktop_chat", fake_chat)
        response = await desktop_proxy._proxy(
            make_request(), "models/gemini-2.5-flash:generateContent", False, "user-1"
        )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["candidates"][0]["content"]["parts"][0]["text"] == "gateway answer"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["uid"] == "user-1"
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_company_paid_embed_content_hops_the_gateway_embeddings_surface(monkeypatch):
    _gateway_feature_mode(monkeypatch)
    _install_gateway_doubles(monkeypatch)

    captured: dict = {}

    class FakeEmbedding:
        values = [0.1, 0.2]

    async def fake_embed(body, *, uid):
        captured.update(body=json.loads(body), uid=uid)
        return FakeEmbedding()

    body = json.dumps({"content": {"parts": [{"text": "screen"}]}, "taskType": "RETRIEVAL_DOCUMENT"}).encode()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(desktop_proxy.desktop_gemini_gateway, "gateway_desktop_embed_content", fake_embed)
        response = await desktop_proxy._proxy(
            make_request(body), "models/gemini-embedding-001:embedContent", False, "user-1"
        )

    assert response.status_code == 200
    assert json.loads(response.body) == {"embedding": {"values": [0.1, 0.2]}}
    assert captured["body"]["taskType"] == "RETRIEVAL_DOCUMENT"


@pytest.mark.asyncio
async def test_byok_stays_direct_ai_studio_even_in_gateway_feature_mode(monkeypatch):
    _gateway_feature_mode(monkeypatch)
    client = _ScriptedClient([_ok_response])
    _install_proxy_doubles(monkeypatch, client)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda provider: "user-key" if provider == "gemini" else None)
    monkeypatch.setattr(
        desktop_proxy.desktop_gemini_gateway,
        "get_byok_key",
        lambda provider: "user-key" if provider == "gemini" else None,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            desktop_proxy.desktop_gemini_gateway,
            "gateway_desktop_chat",
            lambda *a, **k: pytest.fail("BYOK gemini must keep the thin direct AI Studio path"),
        )
        response = await desktop_proxy._proxy(
            make_request(), "models/gemini-2.5-flash:generateContent", False, "user-1"
        )

    assert response.status_code == 200
    assert "aiplatform.googleapis.com" not in str(client.calls[0][0])


@pytest.mark.asyncio
async def test_gateway_error_maps_to_the_retryable_proxy_envelope(monkeypatch):
    from utils.llm.desktop_gemini_gateway import DesktopGeminiGatewayError

    _gateway_feature_mode(monkeypatch)
    _install_gateway_doubles(monkeypatch)

    async def failing_chat(body, *, model, action, uid):
        raise DesktopGeminiGatewayError(
            status_code=503, code="provider_unavailable", message="Gemini gateway is temporarily unavailable"
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(desktop_proxy.desktop_gemini_gateway, "gateway_desktop_chat", failing_chat)
        response = await desktop_proxy._proxy(
            make_request(), "models/gemini-2.5-flash:generateContent", False, "user-1"
        )

    assert response.status_code == 503
    assert response.headers["x-omi-retryable"] == "true"
    assert response.headers["x-omi-provider"] == "llm_gateway"


def test_feature_mode_off_keeps_the_direct_vertex_path(monkeypatch):
    monkeypatch.delenv("OMI_LLM_GATEWAY_FEATURE_MODE", raising=False)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert desktop_proxy._company_paid_via_gateway("gemini-2.5-flash", "generateContent") is False
    assert desktop_proxy._company_paid_via_gateway("gemini-embedding-001", "embedContent") is False


def test_gateway_hop_gates_by_action_and_model(monkeypatch):
    _gateway_feature_mode(monkeypatch)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    assert desktop_proxy._company_paid_via_gateway("gemini-2.5-flash", "generateContent") is True
    assert desktop_proxy._company_paid_via_gateway("gemini-2.5-flash", "streamGenerateContent") is True
    assert desktop_proxy._company_paid_via_gateway("gemini-embedding-001", "embedContent") is True
    # batch embeddings stay on AI Studio: Vertex's batch wire shape differs.
    assert desktop_proxy._company_paid_via_gateway("gemini-embedding-001", "batchEmbedContents") is False
    assert desktop_proxy._company_paid_via_gateway("gemini-2.5-pro", "generateContent") is True
