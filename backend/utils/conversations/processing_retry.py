"""Failure policy at the processing boundary; never classify by exception text."""

import anthropic
import httpx
import openai
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    GoogleAPICallError,
    ServiceUnavailable,
    TooManyRequests,
)

from config.conversation_processing_retry import DETERMINISTIC_PROCESSING_FAILURE, TRANSIENT_PROCESSING_FAILURE


def processing_failure_code(error: BaseException) -> str:
    """Unwrap composition errors before deciding whether another burst can help.

    A processing HTTP 500 with no provider cause is a failed processing seam,
    not evidence of a transient provider outage. SDK timeouts/connections and
    provider 429/5xx retain bounded recovery. The explicit cause is authoritative
    even when an SDK rollback error masks it via __context__. Every generic
    processing_failed wrapper must enter this classifier, including one with
    only __context__ (even suppressed context). Missing or cyclic chains are
    not proven transient: they use the deterministic bounded-then-terminal
    policy and cannot receive a delayed second budget.
    """
    seen = set()
    current = error
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (
                TimeoutError,
                ConnectionError,
                httpx.TimeoutException,
                httpx.NetworkError,
                anthropic.APIConnectionError,
                openai.APIConnectionError,
                Aborted,
                DeadlineExceeded,
                ServiceUnavailable,
                TooManyRequests,
            ),
        ):
            return TRANSIENT_PROCESSING_FAILURE
        if isinstance(current, (anthropic.APIStatusError, openai.APIStatusError, httpx.HTTPStatusError)):
            status = current.response.status_code
            if status == 429 or status >= 500:
                return TRANSIENT_PROCESSING_FAILURE
        if isinstance(current, GoogleAPICallError) and isinstance(current.code, int) and current.code >= 500:
            return TRANSIENT_PROCESSING_FAILURE
        cause = current.__cause__ or current.__context__
        if cause is not None and id(cause) not in seen:
            current = cause
            continue
        return DETERMINISTIC_PROCESSING_FAILURE
    return DETERMINISTIC_PROCESSING_FAILURE
