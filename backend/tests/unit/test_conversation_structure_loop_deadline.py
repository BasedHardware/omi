"""A whole-call notes deadline must answer as a typed 504, not the generic 500.

Live prod signature (backend revision backend-01929-dl9, commit ecd1f40, api.omi.me,
2026-10-18 18:03-20:19 UTC, POST /v1/conversations/from-segments):

    File "/app/utils/conversations/process_conversation.py", line 653, in _get_structured
      structured = llm_input_dedupe.notes(
    File "/app/utils/llm/conversation_processing.py", line 474, in _get_shaped_conversation_notes
      result = asyncio.run(invoke())
    File "/app/utils/llm/shaped_agent.py", line 217, in run_loop
      async with asyncio.timeout(budget.deadline_seconds):
    File "/usr/local/lib/python3.11/asyncio/timeouts.py", line 115, in __aexit__
      raise TimeoutError from exc_val
    [mapped by]
    File "/app/utils/conversations/process_conversation.py", line 674, in _get_structured
      raise conversation_processing_http_exception(e) from e
    fastapi.exceptions.HTTPException: 500: Error processing conversation, please try again later
    [logged as] ERROR:utils.llm.gateway_error_contract:Conversation processing failed: TimeoutError

The shaped notes mount budgets the whole model call at the 60s foreground deadline
(``notes_mount`` -> ``run_loop``). When the provider lane runs past it,
``asyncio.timeout`` raises the builtin ``TimeoutError``; with ``turns=1`` there is no
partial turn to degrade to, and the composition boundary answered the generic 500.
Nine uids hit this in one evening, and one client retried the same from-segments
request every 2 minutes for over two hours (120 occurrences), each holding a Cloud
Run instance for 61-72s — a retryable timeout indistinguishable from a server bug.

An expired deadline is transient upstream latency, not a bug: the boundary answers
504 with a typed, privacy-safe detail (the desktop gateways already use 504 for
provider timeouts), so SDKs and clients can back off and retry instead of treating
the conversation pipeline as broken. BYOK account states keep their typed 429s, and
every other exception keeps the generic response.
"""

import asyncio
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7XUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from utils.llm.gateway_error_contract import (  # noqa: E402
    BYOK_RATE_LIMIT_ERROR_DETAIL,
    GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
    PROVIDER_TIMEOUT_ERROR_DETAIL,
    conversation_processing_http_exception,
)


class _GatewayStyleError(Exception):
    """Raised gateway credential failure carrying its typed failure class."""

    def __init__(self, code: str, failure_class: str, status_code: int, body: dict | None = None):
        super().__init__("gateway credential failure")
        self.code = code
        self.failure_class = failure_class
        self.status_code = status_code
        self.body = body


def _deadline_timeout() -> TimeoutError:
    async def expire():
        async with asyncio.timeout(0.01):
            await asyncio.sleep(1)

    with pytest.raises(TimeoutError) as exc_info:
        asyncio.run(expire())
    return exc_info.value


def test_notes_loop_deadline_maps_to_typed_504():
    # asyncio.timeout raises the builtin TimeoutError, exactly as the prod frame shows.
    mapped = conversation_processing_http_exception(_deadline_timeout())

    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == 504
    assert mapped.detail == PROVIDER_TIMEOUT_ERROR_DETAIL
    assert mapped.detail["code"] == "provider_timeout"
    # No provider body, transcript excerpt or deadline value reaches the contract.
    assert "anthropic" not in str(mapped.detail["message"]).lower()


def test_plain_timeout_error_maps_to_typed_504():
    mapped = conversation_processing_http_exception(TimeoutError("timed out"))

    assert mapped.status_code == 504
    assert mapped.detail == PROVIDER_TIMEOUT_ERROR_DETAIL


def test_byok_rate_limit_still_maps_to_its_typed_429():
    error = _GatewayStyleError(
        code="credential_failure",
        failure_class="byok_rate_limit",
        status_code=429,
        body={"error": {"code": "credential_failure", "failure_class": "byok_rate_limit"}},
    )

    mapped = conversation_processing_http_exception(error)

    assert mapped.status_code == 429
    assert mapped.detail == BYOK_RATE_LIMIT_ERROR_DETAIL


def test_unrelated_exceptions_keep_the_generic_500():
    for error in (ValueError("notes"), KeyError("timeout in a field name")):
        mapped = conversation_processing_http_exception(error)
        assert mapped.status_code == 500
        assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
