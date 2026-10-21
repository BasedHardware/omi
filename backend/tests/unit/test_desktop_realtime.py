import json

from fastapi import HTTPException
import httpx
import pytest

from routers import desktop_realtime


class _Client:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, *_args, **_kwargs):
        return self.response


@pytest.mark.asyncio
async def test_openai_mint_returns_ephemeral_token_and_persists_no_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    monkeypatch.setattr(
        desktop_realtime.httpx,
        "AsyncClient",
        lambda **_: _Client(httpx.Response(200, json={"value": "ek_secret", "expires_at": 123})),
    )
    persisted = {}

    async def persist(*args):
        persisted["args"] = args

    monkeypatch.setattr(desktop_realtime, "_persist_session", persist)

    async def run(_executor, function, *_args, **_kwargs):
        assert function is desktop_realtime.enforce_desktop_chat_quota
        return False

    monkeypatch.setattr(desktop_realtime, "run_blocking", run)

    response = await desktop_realtime.mint_session(desktop_realtime.MintRequest(provider="openai"), "user-1")

    assert response.status_code == 200
    assert json.loads(response.body) == {"provider": "openai", "token": "ek_secret", "expires_at": "123"}
    assert persisted["args"] == ("user-1", "ek_secret", "openai", "gpt-realtime-2", "123")


@pytest.mark.asyncio
async def test_mint_classifies_provider_quota_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "platform-key")
    monkeypatch.setattr(
        desktop_realtime.httpx,
        "AsyncClient",
        lambda **_: _Client(
            httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exhausted"}})
        ),
    )

    async def run(_executor, function, *_args, **_kwargs):
        assert function is desktop_realtime.enforce_desktop_chat_quota
        return False

    monkeypatch.setattr(desktop_realtime, "run_blocking", run)

    response = await desktop_realtime.mint_session(desktop_realtime.MintRequest(provider="gemini"), "user-1")

    assert response.status_code == 429
    assert json.loads(response.body) == {
        "error": "Quota exhausted",
        "reason": "provider_quota_exceeded",
        "backend_route": "/v2/realtime/session",
        "retryable": True,
        "provider": "gemini",
        "code": "RESOURCE_EXHAUSTED",
        "upstream_status_code": 429,
    }


@pytest.mark.asyncio
async def test_usage_clamps_negative_tokens_and_records_realtime_breakdown(monkeypatch):
    calls = []

    async def run(_executor, function, *args, **_kwargs):
        if function is desktop_realtime.enforce_desktop_chat_quota:
            return False
        calls.append((function, args))

    monkeypatch.setattr(desktop_realtime, "run_blocking", run)
    report = desktop_realtime.UsageReport(
        provider="openai",
        input_text_tokens=-1,
        input_audio_tokens=10,
        input_cached_tokens=-2,
        output_text_tokens=5,
        output_audio_tokens=-3,
    )

    response = await desktop_realtime.report_usage(report, "user-1")

    assert response.status_code == 204
    _, args = calls[0]
    assert args[0] == "user-1"
    assert args[2:] == (10, 5, 0, 15, 0.00044)


def test_usage_cost_uses_the_server_issued_gemini_model(monkeypatch):
    models = []

    def cost(provider, model, turn):
        models.append((provider, model))
        return 0.25

    monkeypatch.setattr(desktop_realtime, 'client_reported_cost_usd', cost)
    report = desktop_realtime.UsageReport(provider='gemini', model='gemini-2.5-flash-native-audio-preview-12-2025')

    assert desktop_realtime._usage_cost(report) == 0.25
    assert models == [('gemini', 'models/gemini-3.1-flash-live-preview')]


def test_realtime_writer_marks_full_provider_cost_complete(monkeypatch):
    recorded = {}
    monkeypatch.setattr(
        desktop_realtime.llm_usage_db,
        'record_llm_usage_bucket',
        lambda *args, **kwargs: recorded.update(args=args, kwargs=kwargs),
    )
    monkeypatch.setattr(desktop_realtime, 'get_customer_firestore_client', lambda: object())

    desktop_realtime._record_usage(
        'user-1',
        desktop_realtime.UsageReport(provider='openai'),
        input_tokens=10,
        output_tokens=5,
        cached_tokens=2,
        total_tokens=17,
        cost=0.25,
    )

    assert recorded['args'][0] == 'user-1'
    assert recorded['kwargs']['cost_status'] == 'complete'
    assert recorded['kwargs']['quota_questions'] == 1
    assert recorded['kwargs']['cost_usd'] == 0.25


@pytest.mark.asyncio
async def test_usage_with_no_positive_tokens_skips_firestore(monkeypatch):
    async def fail(_executor, function, *_args, **_kwargs):
        if function is desktop_realtime.enforce_desktop_chat_quota:
            return False
        raise AssertionError("usage write should not run")

    monkeypatch.setattr(desktop_realtime, "run_blocking", fail)

    response = await desktop_realtime.report_usage(
        desktop_realtime.UsageReport(provider="gemini", input_text_tokens=-1), "user-1"
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_mint_blocks_quota_before_provider_token_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")

    async def run(_executor, function, *_args, **_kwargs):
        assert function is desktop_realtime.enforce_desktop_chat_quota
        raise HTTPException(status_code=402, detail={"error": "quota_exceeded"})

    async def fail(*_args, **_kwargs):
        raise AssertionError("provider token should not be requested")

    monkeypatch.setattr(desktop_realtime, "run_blocking", run)
    monkeypatch.setattr(desktop_realtime, "_post_json", fail)

    with pytest.raises(HTTPException) as error:
        await desktop_realtime.mint_session(desktop_realtime.MintRequest(provider="openai"), "user-1")

    assert error.value.status_code == 402


@pytest.mark.asyncio
async def test_usage_blocks_quota_before_recording(monkeypatch):
    async def run(_executor, function, *_args, **_kwargs):
        assert function is desktop_realtime.enforce_desktop_chat_quota
        raise HTTPException(status_code=402, detail={"error": "quota_exceeded"})

    monkeypatch.setattr(desktop_realtime, "run_blocking", run)

    with pytest.raises(HTTPException) as error:
        await desktop_realtime.report_usage(
            desktop_realtime.UsageReport(provider="openai", input_text_tokens=1), "user-1"
        )

    assert error.value.status_code == 402
