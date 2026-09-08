"""Privacy-safe gateway failure details consumed at backend composition boundaries."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum

from fastapi import HTTPException

BYOK_RATE_LIMIT_FAILURE_CLASS = 'byok_rate_limit'
GATEWAY_CREDENTIAL_FAILURE_CODE = 'credential_failure'
BYOK_RATE_LIMIT_ERROR_DETAIL = {
    'code': BYOK_RATE_LIMIT_FAILURE_CLASS,
    'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
}
GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL = 'Error processing conversation, please try again later'

logger = logging.getLogger(__name__)


def is_byok_rate_limit_gateway_error(error: BaseException) -> bool:
    """Return whether ``error`` is the gateway's typed BYOK rate-limit failure.

    Gateway code may be raised directly in in-process tests, while production
    callers receive either the gateway's OpenAI-compatible error envelope or
    its unwrapped ``error`` member through the SDK. Require both the credential
    error code and the explicit failure class so generic provider 429s and other
    BYOK credential failures remain distinct.
    """
    if (
        _string_value(getattr(error, 'code', None)) == GATEWAY_CREDENTIAL_FAILURE_CODE
        and _string_value(getattr(error, 'failure_class', None)) == BYOK_RATE_LIMIT_FAILURE_CLASS
    ):
        return True

    if getattr(error, 'status_code', None) != 429:
        return False

    body = getattr(error, 'body', None)
    if not isinstance(body, Mapping):
        return False
    gateway_error = body.get('error', body)
    if not isinstance(gateway_error, Mapping):
        return False
    return (
        _string_value(gateway_error.get('code')) == GATEWAY_CREDENTIAL_FAILURE_CODE
        and _string_value(gateway_error.get('failure_class')) == BYOK_RATE_LIMIT_FAILURE_CLASS
    )


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Enum) and isinstance(value.value, str):
        return value.value
    return None


def conversation_processing_http_exception(error: BaseException) -> HTTPException:
    """Map a processing failure to the existing safe HTTP contract.

    The caller is the authoritative conversation composition boundary. Logging
    the BYOK case by its bounded class avoids leaking provider error bodies,
    while every other exception retains the existing generic response and a
    privacy-safe log entry.
    """
    if is_byok_rate_limit_gateway_error(error):
        logger.warning('Conversation processing halted because the configured BYOK provider is rate limited')
        return HTTPException(status_code=429, detail=BYOK_RATE_LIMIT_ERROR_DETAIL)
    logger.error('Conversation processing failed: %s', type(error).__name__)
    return HTTPException(status_code=500, detail=GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL)
