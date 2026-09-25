"""POST /v1/conversations/{id}/test-prompt reports an upstream provider failure as one.

Live prod signature (backend image 79a585b, api.omi.me, 2026-08-19):

    File "/app/routers/conversations.py", line 1459, in test_prompt
      summary = generate_summary_with_prompt(...)
    File "/app/utils/llm/conversation_processing.py", line 1509, in generate_summary_with_prompt
      response = get_llm('daily_summary', cache_key='omi-daily-summary').invoke(full_prompt)
    openai.APITimeoutError: Request timed out.

One user retried the same conversation three times; every attempt died at the 15s gateway
first-byte deadline (15.19s / 15.45s / 15.34s of request latency) and returned HTTP 500. Two
things were wrong: a foreground request inherited a deadline sized for background feature calls,
and the resulting transport failure escaped unclassified, so a slow provider was indistinguishable
from a bug in this route.

Both halves are covered here: the classification at the provider call, and the status code the
client actually receives, driven over HTTP against the real router.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routers.conversations as conv  # noqa: E402
import utils.llm.conversation_processing as processing  # noqa: E402
from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS  # noqa: E402
from utils.other import endpoints as endpoints_module  # noqa: E402

CONVERSATION_ID = "277d188e-9563-4fd1-bf1b-8a6bbcbe4b94"
_REQUEST = httpx.Request("POST", "https://gateway.invalid/v1/chat/completions")


def _upstream_5xx():
    return openai.InternalServerError(
        "upstream exploded",
        response=httpx.Response(status_code=503, request=_REQUEST),
        body=None,
    )


# --- classification at the provider call -------------------------------------------------


@pytest.fixture
def failing_llm(monkeypatch):
    """Replace the provider client, leaving the real generate_summary_with_prompt in place."""

    llm = MagicMock()
    get_llm = MagicMock(return_value=llm)
    monkeypatch.setattr(processing, "get_llm", get_llm)
    return SimpleNamespace(llm=llm, get_llm=get_llm)


def test_summary_asks_for_a_foreground_deadline(failing_llm):
    """The 15s gateway first-byte deadline is what timed these requests out; ask for more."""
    failing_llm.llm.invoke.return_value = SimpleNamespace(content="a summary")

    assert processing.generate_summary_with_prompt("transcript", "summarize") == "a summary"

    request_timeout = failing_llm.get_llm.call_args.kwargs["request_timeout"]
    assert request_timeout == processing.SUMMARY_WITH_PROMPT_TIMEOUT_SECONDS
    assert request_timeout > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_provider_timeout_becomes_a_typed_summary_failure(failing_llm):
    failing_llm.llm.invoke.side_effect = openai.APITimeoutError(request=_REQUEST)

    with pytest.raises(processing.SummaryProviderError) as raised:
        processing.generate_summary_with_prompt("transcript", "summarize")

    assert raised.value.timed_out is True


def test_provider_5xx_becomes_a_typed_summary_failure(failing_llm):
    failing_llm.llm.invoke.side_effect = _upstream_5xx()

    with pytest.raises(processing.SummaryProviderError) as raised:
        processing.generate_summary_with_prompt("transcript", "summarize")

    assert raised.value.timed_out is False


def test_non_provider_error_is_not_reclassified(failing_llm):
    """A bug in this code path must keep its own exception instead of posing as an outage."""
    failing_llm.llm.invoke.side_effect = ValueError("not a provider failure")

    with pytest.raises(ValueError):
        processing.generate_summary_with_prompt("transcript", "summarize")


# --- what the client receives ------------------------------------------------------------


def _conversation(text: str = "hello there"):
    segments = [SimpleNamespace(text=text)] if text else []
    return SimpleNamespace(transcript_segments=segments, language="en")


@pytest.fixture
def client(monkeypatch):
    # Rate limiting is a Redis round trip that this route's error handling has nothing to do with.
    monkeypatch.setattr(endpoints_module, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(conv, "_get_valid_conversation_by_id", lambda uid, conversation_id: {"id": conversation_id})
    monkeypatch.setattr(conv, "deserialize_conversation", lambda data: _conversation())

    app = FastAPI()
    app.include_router(conv.router)
    app.dependency_overrides[conv.auth.get_current_user_uid] = lambda: "test-uid"
    return TestClient(app, raise_server_exceptions=False)


def _post(client, prompt="summarize this"):
    return client.post(f"/v1/conversations/{CONVERSATION_ID}/test-prompt", json={"prompt": prompt})


def _raise(exc):
    def _raiser(*args, **kwargs):
        raise exc

    return _raiser


def test_timed_out_provider_answers_504(client, monkeypatch):
    monkeypatch.setattr(
        conv,
        "generate_summary_with_prompt",
        _raise(conv.SummaryProviderError("provider timed out", timed_out=True)),
    )

    response = _post(client)

    assert response.status_code == 504
    assert response.json()["detail"] == "summary_provider_timeout"


def test_unavailable_provider_answers_502(client, monkeypatch):
    monkeypatch.setattr(
        conv,
        "generate_summary_with_prompt",
        _raise(conv.SummaryProviderError("provider 5xx", timed_out=False)),
    )

    response = _post(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "summary_provider_unavailable"


def test_provider_timeout_answers_504_through_both_layers(client, monkeypatch):
    """The prod signature end to end: only the provider client is replaced, nothing in between.

    Against unmodified source this is the failure that shipped — HTTP 500.
    """
    llm = MagicMock()
    llm.invoke.side_effect = openai.APITimeoutError(request=_REQUEST)
    monkeypatch.setattr(processing, "get_llm", MagicMock(return_value=llm))

    response = _post(client)

    assert response.status_code == 504
    assert response.json()["detail"] == "summary_provider_timeout"


def test_unexpected_error_still_surfaces_as_500(client, monkeypatch):
    monkeypatch.setattr(conv, "generate_summary_with_prompt", _raise(ValueError("route bug")))

    response = _post(client)

    assert response.status_code == 500


def test_successful_summary_is_returned(client, monkeypatch):
    monkeypatch.setattr(conv, "generate_summary_with_prompt", lambda *args, **kwargs: "a summary")

    response = _post(client)

    assert response.status_code == 200
    assert response.json()["summary"] == "a summary"


def test_conversation_without_text_still_rejected_as_bad_request(client, monkeypatch):
    monkeypatch.setattr(conv, "deserialize_conversation", lambda data: _conversation(text=""))

    response = _post(client)

    assert response.status_code == 400
