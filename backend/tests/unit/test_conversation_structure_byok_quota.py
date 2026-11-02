"""A spent BYOK provider account must answer as a typed 429, not the generic 500.

Live prod signature (backend image /app, 2026-10-15, api.omi.me):

    File "/app/utils/conversations/process_conversation.py", line 632, in _get_structured
      raise conversation_processing_http_exception(e) from e
    fastapi.exceptions.HTTPException: 500: Error processing conversation, please try again later
    [chained from]
      File "/app/utils/llm/conversation_processing.py", line 466, in model_turn
      response = await call_model.ainvoke(messages)
    File "/opt/venv/.../anthropic/_base_client.py", line 1941, in request
      raise self._make_status_error_from_response(response) from None
    anthropic.BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type':
      'invalid_request_error', 'message': 'Your credit balance is too low to access the
      Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}}

Recurring live signature (backend image /app, 2026-10-19, api.omi.me, group frame
``process_conversation.py:633``):

    File "/app/utils/conversations/process_conversation.py", line 633, in _get_structured
      raise conversation_processing_http_exception(e) from e
    fastapi.exceptions.HTTPException: 500: Error processing conversation, please try again later
    [chained from]
      File "/app/utils/conversations/process_conversation.py", line 610, in _get_structured
      structured = llm_input_dedupe.notes(
    File "/app/utils/llm/conversation_processing.py", line 466, in model_turn
      response = await call_model.ainvoke(messages)
    File "/opt/venv/.../openai/_base_client.py", line 1716, in request
      raise self._make_status_error_from_response(err.response) from None
    openai.APIStatusError: Error code: 402 - {'error': {'message': 'This request requires
      more credits, or fewer max_tokens. You requested up to 65535 tokens, but can only
      afford 65032. To increase, visit https://openrouter.ai/settings/credits and upgrade
      to a paid account', 'code': 402, 'metadata': {'limit_source': 'openrouter_credits', ...}}}

The notes lane serves BYOK users on their own Anthropic key (#21415 kept that lane working),
and BYOK users whose only key is OpenRouter's are routed to openrouter.ai directly
(``_get_or_create_openrouter_llm``). When that account's credits cannot cover the request,
every conversation-processing call fails before generation and retries can never succeed:
users re-polled against the same 500 for hours. The gateway already classifies this account
state as ``byok_quota`` and answers 429 (``_THROTTLED_FAILURE_CLASSES`` — answering
401/500 would make a fixable account state look like a server bug), and the composition
boundary already carries that contract for ``byok_rate_limit`` (#11112) and direct
Anthropic credit exhaustion (#21779). This module extends the same boundary to the direct
OpenRouter spelling: the user gets an actionable typed response, and the provider's error
body still never reaches logs or clients.

Since 2026-10-24 the classifier also covers Anthropic's usage-limit 400 spelling
("You have reached your specified API usage limits" — the residual 500s in the
03:51–04:21Z window), OpenAI's 429 ``insufficient_quota``, OpenRouter's 429
``limit_source`` rate limits, and rejected keys (``byok_invalid_key``). Direct
provider errors only classify when the request ran on the user's own validated
key; the same error on Omi's server-paid key stays a loud server fault. The
boundary logs one structured WARNING (``byok=true failure_class=...``) so
severity>=ERROR stops counting user account state.
"""

import logging
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7XUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import anthropic  # noqa: E402
import openai  # noqa: E402

from utils.byok import set_byok_uid, set_validated_byok_keys  # noqa: E402
from utils.llm.gateway_error_contract import (  # noqa: E402
    BYOK_INVALID_KEY_ERROR_DETAIL,
    BYOK_QUOTA_ERROR_DETAIL,
    BYOK_RATE_LIMIT_ERROR_DETAIL,
    GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
    byok_failure_class_of,
    conversation_processing_http_exception,
    is_byok_quota_error,
)

_ANTHROPIC_CREDIT_BODY = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "Your credit balance is too low to access the Anthropic API. "
        "Please go to Plans & Billing to upgrade or purchase credits.",
    },
}

# Anthropic's usage-limit spelling from the 2026-10-24 03:51-04:21Z prod window:
# also a plain 400, also only fixable by the user.
_ANTHROPIC_USAGE_LIMIT_BODY = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "You have reached your specified API usage limits. Please visit "
        "https://console.anthropic.com/settings/limits to learn more.",
    },
}

_OPENROUTER_CREDIT_BODY = {
    "error": {
        "message": "This request requires more credits, or fewer max_tokens. You requested up to 65535 "
        "tokens, but can only afford 65032. To increase, visit https://openrouter.ai/settings/credits "
        "and upgrade to a paid account",
        "code": 402,
        "metadata": {"limit_source": "openrouter_credits", "provider_name": None},
    }
}

_OPENAI_INSUFFICIENT_QUOTA_BODY = {
    "error": {
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "type": "insufficient_quota",
        "code": "insufficient_quota",
    }
}


def _anthropic_error(body: dict, status_code: int = 400) -> anthropic.BadRequestError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request, headers={"request-id": "req_unit"}, json=body)
    return anthropic.BadRequestError(f"Error code: {status_code} - {body}", response=response, body=body)


def _openai_error(body: dict, status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status_code, request=request, headers={"x-request-id": "req_unit"}, json=body)
    return openai.APIStatusError(f"Error code: {status_code} - {body}", response=response, body=body)


def _openrouter_error(body: dict, status_code: int = 402) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code, request=request, headers={"x-openrouter-request-id": "req_unit"}, json=body)
    return openai.APIStatusError(f"Error code: {status_code} - {body}", response=response, body=body)


class _GatewayStyleError(Exception):
    """Raised gateway credential failure carrying its typed failure class."""

    def __init__(self, code: str, failure_class: str, status_code: int, body: dict | None = None):
        super().__init__("gateway credential failure")
        self.code = code
        self.failure_class = failure_class
        self.status_code = status_code
        self.body = body


@pytest.fixture
def byok_anthropic_key():
    set_validated_byok_keys({"anthropic": "sk-ant-byok-unit"}, "uid_byok_unit")
    yield
    set_validated_byok_keys({}, "uid_byok_unit")
    set_byok_uid(None)


@pytest.fixture
def byok_openrouter_key():
    set_validated_byok_keys({"openrouter": "sk-or-byok-unit"}, "uid_byok_unit")
    yield
    set_validated_byok_keys({}, "uid_byok_unit")
    set_byok_uid(None)


@pytest.fixture
def byok_openai_key():
    set_validated_byok_keys({"openai": "sk-byok-unit"}, "uid_byok_unit")
    yield
    set_validated_byok_keys({}, "uid_byok_unit")
    set_byok_uid(None)


def test_direct_anthropic_credit_exhaustion_maps_to_typed_429(byok_anthropic_key):
    error = _anthropic_error(_ANTHROPIC_CREDIT_BODY)

    assert is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == 429
    assert mapped.detail == BYOK_QUOTA_ERROR_DETAIL
    assert mapped.detail["code"] == "byok_quota"
    # The provider's error body must not leak into the response contract.
    assert "credit balance" not in str(mapped.detail["message"])


def test_direct_anthropic_usage_limit_maps_to_typed_429(byok_anthropic_key):
    # The residual "500 path" from the 2026-10-24 prod window: same account
    # state as the credit spelling, different provider wording.
    error = _anthropic_error(_ANTHROPIC_USAGE_LIMIT_BODY)

    assert is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_QUOTA_ERROR_DETAIL


def test_sdk_wrapped_gateway_quota_envelope_maps_to_typed_429():
    # The gateway answers byok_quota as 429 with its OpenAI-compatible envelope.
    error = _GatewayStyleError(
        code="credential_failure",
        failure_class="byok_quota",
        status_code=429,
        body={"error": {"code": "credential_failure", "failure_class": "byok_quota"}},
    )

    assert is_byok_quota_error(error)
    assert conversation_processing_http_exception(error).detail == BYOK_QUOTA_ERROR_DETAIL


def test_raised_gateway_quota_class_maps_to_typed_429():
    error = _GatewayStyleError(code="credential_failure", failure_class="byok_quota", status_code=400)

    assert is_byok_quota_error(error)
    assert conversation_processing_http_exception(error).status_code == 429


def test_direct_openrouter_credit_exhaustion_maps_to_typed_429(byok_openrouter_key):
    error = _openrouter_error(_OPENROUTER_CREDIT_BODY)

    assert is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == 429
    assert mapped.detail == BYOK_QUOTA_ERROR_DETAIL
    assert mapped.detail["code"] == "byok_quota"
    # The provider's error body must not leak into the response contract.
    assert "credits" not in str(mapped.detail["message"])


def test_openrouter_credit_metadata_alone_classifies(byok_openrouter_key):
    # The limit_source metadata is the machine-readable spelling of the same
    # account state; it must classify even if the message wording changes.
    error = _openrouter_error(
        {"error": {"message": "Request rejected", "code": 402, "metadata": {"limit_source": "openrouter_credits"}}}
    )

    assert is_byok_quota_error(error)
    assert conversation_processing_http_exception(error).status_code == 429


def test_openai_insufficient_quota_maps_to_typed_429(byok_openai_key):
    # The SDK raises the spent-account state as a 429 even though retrying
    # can never succeed; it must still answer the typed quota contract.
    error = _openai_error(_OPENAI_INSUFFICIENT_QUOTA_BODY, 429)

    assert is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_QUOTA_ERROR_DETAIL


def test_openrouter_rate_limit_metadata_maps_to_typed_429(byok_openrouter_key):
    error = _openrouter_error(
        {"error": {"message": "Rate limit exceeded", "code": 429, "metadata": {"limit_source": "requester_rates"}}},
        status_code=429,
    )

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_RATE_LIMIT_ERROR_DETAIL


def test_gateway_byok_auth_maps_to_typed_invalid_key():
    # The gateway answers a rejected BYOK key as credential_failure/byok_auth
    # (401). The conversation boundary keeps the throttled typed answer so a
    # stale key is never mistaken for a server fault or an Omi session expiry.
    error = _GatewayStyleError(
        code="credential_failure",
        failure_class="byok_auth",
        status_code=401,
        body={"error": {"code": "credential_failure", "failure_class": "byok_auth"}},
    )

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_INVALID_KEY_ERROR_DETAIL
    assert mapped.detail["code"] == "byok_invalid_key"


def test_direct_anthropic_invalid_key_maps_to_typed_invalid_key(byok_anthropic_key):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    response = httpx.Response(401, request=request, json=body)
    error = anthropic.AuthenticationError(f"Error code: 401 - {body}", response=response, body=body)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_INVALID_KEY_ERROR_DETAIL


def test_server_paid_provider_failures_stay_loud_500(caplog):
    # The same provider error raised on Omi's own key (no validated BYOK key in
    # the request context) is a genuine server fault: generic 500, ERROR log.
    caplog.set_level(logging.WARNING, logger="utils.llm.gateway_error_contract")
    credit_error = _anthropic_error(_ANTHROPIC_CREDIT_BODY)
    openrouter_error = _openrouter_error(_OPENROUTER_CREDIT_BODY)

    for error in (credit_error, openrouter_error):
        assert not is_byok_quota_error(error)
        mapped = conversation_processing_http_exception(error)
        assert mapped.status_code == 500
        assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL

    assert [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not [
        record for record in caplog.records if record.levelno == logging.WARNING and "byok=true" in record.getMessage()
    ]


def test_other_402_responses_keep_the_generic_500(byok_openrouter_key):
    # A 402 without OpenRouter's credit markers is not an identified account
    # state, so it keeps the privacy-safe generic response.
    error = _openrouter_error({"error": {"message": "Payment required", "code": 402}})

    assert not is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 500
    assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL


def test_other_provider_bad_requests_keep_the_generic_500(byok_anthropic_key):
    # Any other 400 (here: an invalid request) is not account state the user can
    # fix by topping up, so it keeps the privacy-safe generic response.
    error = _anthropic_error(
        {"type": "error", "error": {"type": "invalid_request_error", "message": "max_tokens is required"}}
    )

    assert not is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 500
    assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL


def test_byok_rate_limit_contract_is_unchanged():
    error = _GatewayStyleError(
        code="credential_failure",
        failure_class="byok_rate_limit",
        status_code=429,
        body={"error": {"code": "credential_failure", "failure_class": "byok_rate_limit"}},
    )

    assert not is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_RATE_LIMIT_ERROR_DETAIL


def test_unrelated_exceptions_keep_the_generic_500():
    for error in (ValueError("credit balance is too low in some transcript text"), KeyError("notes")):
        assert not is_byok_quota_error(error)
        mapped = conversation_processing_http_exception(error)
        assert mapped.status_code == 500
        assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL


def test_byok_failure_logs_one_structured_warning_not_error(byok_anthropic_key, caplog):
    # The incident signature was severity=ERROR tracebacks; a user's spent
    # provider account must surface as exactly one structured WARNING line.
    caplog.set_level(logging.WARNING, logger="utils.llm.gateway_error_contract")
    error = _anthropic_error(_ANTHROPIC_CREDIT_BODY)

    conversation_processing_http_exception(error)

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING and "byok=true" in record.getMessage()
    ]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "failure_class=byok_quota" in message
    assert "provider=anthropic" in message
    assert "route=conversation_processing" in message
    # No traceback at WARNING, and nothing at ERROR for the byok failure.
    assert warnings[0].exc_info is None
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    # No provider error body and no key material in the line.
    assert "credit balance" not in message
    assert "sk-ant" not in message


def test_byok_failure_class_is_readable_off_wrapped_exceptions(byok_anthropic_key):
    # Wrappers (finalization, background funnels) re-raise the typed boundary
    # exception as their cause; the severity downgrades read the verdict back.
    typed = conversation_processing_http_exception(_anthropic_error(_ANTHROPIC_CREDIT_BODY))
    wrapped: BaseException | None = None
    try:
        try:
            raise typed
        except HTTPException as cause:
            raise RuntimeError("processing_failed") from cause
    except RuntimeError as error:
        wrapped = error
    assert wrapped is not None

    assert byok_failure_class_of(typed) == "byok_quota"
    assert byok_failure_class_of(wrapped) == "byok_quota"
    assert byok_failure_class_of(ValueError("unrelated")) is None


def test_background_task_funnel_downgrades_byok_failures(caplog):
    # The executor failure callback is what printed full ERROR tracebacks for
    # submitted processing work; a typed byok failure must not reach it.
    from concurrent.futures import Future

    from utils.executors import _log_background_failure

    caplog.set_level(logging.WARNING, logger="utils.executors")
    typed = HTTPException(status_code=429, detail=BYOK_QUOTA_ERROR_DETAIL)

    byok_future = Future()
    byok_future.set_exception(typed)
    _log_background_failure("process_byok_unit", byok_future)

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING and "byok=true" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "failure_class=byok_quota" in warnings[0].getMessage()
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert warnings[0].exc_info is None

    caplog.clear()
    server_future = Future()
    server_future.set_exception(ValueError("real failure"))
    _log_background_failure("process_server_unit", server_future)

    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is not None


def test_finalization_failure_metric_reason_separates_byok():
    from utils.observability.finalization import FinalizationFailureReason, classify_finalization_failure

    typed = HTTPException(status_code=429, detail=BYOK_QUOTA_ERROR_DETAIL)
    assert classify_finalization_failure(typed) is FinalizationFailureReason.byok_provider

    server_fault = _anthropic_error(_ANTHROPIC_CREDIT_BODY)
    assert classify_finalization_failure(server_fault) is FinalizationFailureReason.provider
    assert classify_finalization_failure(ValueError("bug")) is FinalizationFailureReason.processing
