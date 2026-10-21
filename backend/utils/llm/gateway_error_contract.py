"""Privacy-safe gateway failure details consumed at backend composition boundaries."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum

from fastapi import HTTPException

BYOK_RATE_LIMIT_FAILURE_CLASS = 'byok_rate_limit'
BYOK_QUOTA_FAILURE_CLASS = 'byok_quota'
GATEWAY_CREDENTIAL_FAILURE_CODE = 'credential_failure'
BYOK_RATE_LIMIT_ERROR_DETAIL = {
    'code': BYOK_RATE_LIMIT_FAILURE_CLASS,
    'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
}
BYOK_QUOTA_ERROR_DETAIL = {
    'code': BYOK_QUOTA_FAILURE_CLASS,
    'message': 'The configured provider account is out of credit or quota. Please top up the '
    'provider account or review its limits.',
}
# Anthropic's stable wording for an exhausted prepaid balance; direct-lane BYOK
# raises it as a plain 400, so the provider's own text is the only classifier.
_ANTHROPIC_CREDIT_EXHAUSTED_MARKER = 'credit balance is too low'
# OpenRouter's stable spellings for a credit balance that cannot cover the
# request; direct-lane BYOK raises it as a plain 402, once in the message and
# once as the ``limit_source`` metadata value. Either identifies the account state.
_OPENROUTER_CREDIT_EXHAUSTED_MARKERS = ('requires more credits', 'openrouter_credits')
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


def _bounded_error_text(error: BaseException) -> str:
    """Message text used only for class matching, never for logging or responses."""
    parts = [
        _string_value(getattr(error, 'message', None)) or '',
        str(error),
    ]
    body = getattr(error, 'body', None)
    if isinstance(body, Mapping):
        provider_error = body.get('error', body)
        if isinstance(provider_error, Mapping):
            parts.append(_string_value(provider_error.get('message')) or '')
    return '\n'.join(part for part in parts if part)


def is_byok_quota_error(error: BaseException) -> bool:
    """Return whether ``error`` reports the caller's own BYOK provider account
    being out of credit or quota.

    The gateway answers that account state with its ``byok_quota`` credential
    failure class (HTTP 429, in ``_THROTTLED_FAILURE_CLASSES``), while direct
    Anthropic BYOK raises the SDK's ``BadRequestError`` for an exhausted
    prepaid balance and direct OpenRouter BYOK answers 402 when the account's
    credits cannot cover the request. All are account state only the user can
    fix; every other request shape keeps the generic response.
    """
    if (
        _string_value(getattr(error, 'code', None)) == GATEWAY_CREDENTIAL_FAILURE_CODE
        and _string_value(getattr(error, 'failure_class', None)) == BYOK_QUOTA_FAILURE_CLASS
    ):
        return True

    status_code = getattr(error, 'status_code', None)
    if status_code == 429:
        body = getattr(error, 'body', None)
        if not isinstance(body, Mapping):
            return False
        gateway_error = body.get('error', body)
        if not isinstance(gateway_error, Mapping):
            return False
        return (
            _string_value(gateway_error.get('code')) == GATEWAY_CREDENTIAL_FAILURE_CODE
            and _string_value(gateway_error.get('failure_class')) == BYOK_QUOTA_FAILURE_CLASS
        )
    if status_code == 402:
        text = _bounded_error_text(error)
        return any(marker in text for marker in _OPENROUTER_CREDIT_EXHAUSTED_MARKERS)
    if status_code != 400:
        return False
    return _ANTHROPIC_CREDIT_EXHAUSTED_MARKER in _bounded_error_text(error)


def conversation_processing_http_exception(error: BaseException) -> HTTPException:
    """Map a processing failure to the existing safe HTTP contract.

    The caller is the authoritative conversation composition boundary. Logging
    the BYOK cases by their bounded class avoids leaking provider error bodies,
    while every other exception retains the existing generic response and a
    privacy-safe log entry.
    """
    if is_byok_rate_limit_gateway_error(error):
        logger.warning('Conversation processing halted because the configured BYOK provider is rate limited')
        return HTTPException(status_code=429, detail=BYOK_RATE_LIMIT_ERROR_DETAIL)
    if is_byok_quota_error(error):
        logger.warning(
            'Conversation processing halted because the configured BYOK provider account is out of credit or quota'
        )
        return HTTPException(status_code=429, detail=BYOK_QUOTA_ERROR_DETAIL)
    logger.error('Conversation processing failed: %s', type(error).__name__)
    return HTTPException(status_code=500, detail=GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL)
