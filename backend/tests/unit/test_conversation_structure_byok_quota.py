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

The notes lane serves BYOK users on their own Anthropic key (#21415 kept that lane working).
When that account's prepaid balance runs out, every conversation-processing call fails before
generation (~0.5s, words=13086/16573 in the notes receipts) and retries can never succeed:
users re-uploaded and re-polled for an hour against the same 500. The gateway already classifies
this account state as ``byok_quota`` and answers 429 (``_THROTTLED_FAILURE_CLASSES`` — answering
401/500 would make a fixable account state look like a server bug), and the composition boundary
already carries that contract for ``byok_rate_limit`` (#11112). This module extends the same
boundary to quota: the user gets an actionable typed response, and the provider's error body
still never reaches logs or clients.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7XUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import anthropic  # noqa: E402

from utils.llm.gateway_error_contract import (  # noqa: E402
    BYOK_QUOTA_ERROR_DETAIL,
    BYOK_RATE_LIMIT_ERROR_DETAIL,
    GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
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


def _anthropic_error(body: dict, status_code: int = 400) -> anthropic.BadRequestError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request, headers={"request-id": "req_unit"}, json=body)
    return anthropic.BadRequestError(f"Error code: {status_code} - {body}", response=response, body=body)


class _GatewayStyleError(Exception):
    """Raised gateway credential failure carrying its typed failure class."""

    def __init__(self, code: str, failure_class: str, status_code: int, body: dict | None = None):
        super().__init__("gateway credential failure")
        self.code = code
        self.failure_class = failure_class
        self.status_code = status_code
        self.body = body


def test_direct_anthropic_credit_exhaustion_maps_to_typed_429():
    error = _anthropic_error(_ANTHROPIC_CREDIT_BODY)

    assert is_byok_quota_error(error)

    mapped = conversation_processing_http_exception(error)

    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == 429
    assert mapped.detail == BYOK_QUOTA_ERROR_DETAIL
    assert mapped.detail["code"] == "byok_quota"
    # The provider's error body must not leak into the response contract.
    assert "credit balance" not in str(mapped.detail["message"])


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


def test_other_provider_bad_requests_keep_the_generic_500():
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
