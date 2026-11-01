"""Privacy-safe gateway failure details consumed at backend composition boundaries."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum
from typing import NamedTuple

from fastapi import HTTPException

from utils.byok import get_byok_key, has_validated_byok_keys

BYOK_RATE_LIMIT_FAILURE_CLASS = 'byok_rate_limit'
BYOK_QUOTA_FAILURE_CLASS = 'byok_quota'
BYOK_INVALID_KEY_FAILURE_CLASS = 'byok_invalid_key'
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
BYOK_INVALID_KEY_ERROR_DETAIL = {
    'code': BYOK_INVALID_KEY_FAILURE_CLASS,
    'message': 'The configured provider account rejected the API key. Please update the provider '
    'key in settings to restore processing.',
}
# Anthropic's stable wordings for account state only the user can fix; direct-lane
# BYOK raises them as a plain 400, so the provider's own text is the only classifier.
_ANTHROPIC_QUOTA_EXHAUSTED_MARKERS = (
    'credit balance is too low',
    'reached your specified api usage limits',
)
# OpenRouter's stable spellings for a credit balance that cannot cover the
# request; direct-lane BYOK raises it as a plain 402, once in the message and
# once as the ``limit_source`` metadata value. Either identifies the account state.
_OPENROUTER_CREDIT_EXHAUSTED_MARKERS = ('requires more credits', 'openrouter_credits')
# OpenAI's stable spellings for a spent server-paid-account quota on the user's
# own key; the SDK raises them as a 429 although retrying can never succeed.
_OPENAI_QUOTA_EXHAUSTED_MARKERS = ('insufficient_quota', 'you exceeded your current quota')
# Stable provider wordings for a rejected key. A bare 401 without one of these
# markers is not classified: it may be an unmapped request shape.
_INVALID_KEY_MARKERS = (
    'invalid api key',
    'invalid_api_key',
    'incorrect api key',
    'invalid x-api-key',
    'api key not valid',
    'no auth credentials found',
)
# OpenRouter's machine-readable rate-limit metadata values (``limit_source``);
# ``openrouter_credits`` is quota (never retried into success), the rest are the
# account's own rate limits.
_OPENROUTER_RATE_LIMIT_SOURCES = frozenset({'requester_rates', 'free-tier_rates', 'provider_rates'})
GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL = 'Error processing conversation, please try again later'

logger = logging.getLogger(__name__)


class ByokProviderFailure(NamedTuple):
    """A provider failure raised on the user's own key, safe to name in logs."""

    failure_class: str
    provider: str


def is_byok_rate_limit_gateway_error(error: BaseException) -> bool:
    """Return whether ``error`` is the gateway's typed BYOK rate-limit failure.

    Gateway code may be raised directly in in-process tests, while production
    callers receive either the gateway's OpenAI-compatible error envelope or
    its unwrapped ``error`` member through the SDK. Require both the credential
    error code and the explicit failure class so generic provider 429s and other
    BYOK credential failures remain distinct.
    """
    failure = classify_byok_provider_failure(error)
    return failure is not None and failure.failure_class == BYOK_RATE_LIMIT_FAILURE_CLASS


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


def _lowered_error_text(error: BaseException) -> str:
    return _bounded_error_text(error).lower()


def _byok_key_in_use(provider: str) -> bool:
    """Whether the current request carries the user's validated key for *provider*.

    Only validated keys reach provider clients (the middleware and the pusher
    finalization boundary install them), so this is the authoritative
    "the failing request ran on the user's own key" signal. Without it, the
    same provider error raised on Omi's server-paid key must stay a loud
    server fault.
    """
    return has_validated_byok_keys() and bool(get_byok_key(provider))


def _openrouter_limit_source(error: BaseException) -> str | None:
    body = getattr(error, 'body', None)
    if not isinstance(body, Mapping):
        return None
    provider_error = body.get('error', body)
    if not isinstance(provider_error, Mapping):
        return None
    metadata = provider_error.get('metadata')
    if not isinstance(metadata, Mapping):
        return None
    source = _string_value(metadata.get('limit_source'))
    return source


def classify_byok_provider_failure(error: BaseException) -> ByokProviderFailure | None:
    """Classify a provider failure raised on the user's own (BYOK) key.

    The gateway answers BYOK account states with its ``credential_failure``
    classes (``byok_quota``/``byok_rate_limit`` as throttled 429s, ``byok_auth``
    as 401); those carry the BYOK verdict themselves. Direct-lane providers
    raise plain SDK errors, so those are only classified when the marker
    identifies the account state (credit/quota/usage-limit or a rejected key)
    AND the current request runs on the user's validated key for that provider.
    Everything else — including the same provider error on Omi's server-paid
    key — returns None and keeps the generic server-fault response and logging.
    """
    code = _string_value(getattr(error, 'code', None))
    failure_class = _string_value(getattr(error, 'failure_class', None))
    if code == GATEWAY_CREDENTIAL_FAILURE_CODE and failure_class:
        if failure_class == BYOK_RATE_LIMIT_FAILURE_CLASS:
            return ByokProviderFailure(BYOK_RATE_LIMIT_FAILURE_CLASS, 'gateway')
        if failure_class == BYOK_QUOTA_FAILURE_CLASS:
            return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'gateway')
        # The gateway's byok_auth is the same user-actionable state under its
        # own registry name; surface it under the backend's invalid-key class.
        if failure_class == 'byok_auth':
            return ByokProviderFailure(BYOK_INVALID_KEY_FAILURE_CLASS, 'gateway')

    status_code = getattr(error, 'status_code', None)
    body = getattr(error, 'body', None)
    gateway_error = body.get('error', body) if isinstance(body, Mapping) else None
    if status_code == 429 and isinstance(gateway_error, Mapping):
        if (
            _string_value(gateway_error.get('code')) == GATEWAY_CREDENTIAL_FAILURE_CODE
            and _string_value(gateway_error.get('failure_class')) == BYOK_RATE_LIMIT_FAILURE_CLASS
        ):
            return ByokProviderFailure(BYOK_RATE_LIMIT_FAILURE_CLASS, 'gateway')
        if (
            _string_value(gateway_error.get('code')) == GATEWAY_CREDENTIAL_FAILURE_CODE
            and _string_value(gateway_error.get('failure_class')) == BYOK_QUOTA_FAILURE_CLASS
        ):
            return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'gateway')
        if (
            _string_value(gateway_error.get('code')) == GATEWAY_CREDENTIAL_FAILURE_CODE
            and _string_value(gateway_error.get('failure_class')) == 'byok_auth'
        ):
            return ByokProviderFailure(BYOK_INVALID_KEY_FAILURE_CLASS, 'gateway')

    error_module = type(error).__module__
    is_anthropic_sdk = error_module.startswith('anthropic')
    is_openai_sdk = error_module.startswith('openai')

    if is_anthropic_sdk:
        if status_code == 400 and _byok_key_in_use('anthropic'):
            text = _lowered_error_text(error)
            if any(marker in text for marker in _ANTHROPIC_QUOTA_EXHAUSTED_MARKERS):
                return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'anthropic')
        if status_code in (401, 403) and _byok_key_in_use('anthropic'):
            if any(marker in _lowered_error_text(error) for marker in _INVALID_KEY_MARKERS) or type(error).__name__ in (
                'AuthenticationError',
                'PermissionDeniedError',
            ):
                return ByokProviderFailure(BYOK_INVALID_KEY_FAILURE_CLASS, 'anthropic')
        return None

    if is_openai_sdk:
        if status_code == 402 and _byok_key_in_use('openrouter'):
            if any(marker in _lowered_error_text(error) for marker in _OPENROUTER_CREDIT_EXHAUSTED_MARKERS):
                return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'openrouter')
            return None
        if status_code == 429:
            text = _lowered_error_text(error)
            if _byok_key_in_use('openai') and any(marker in text for marker in _OPENAI_QUOTA_EXHAUSTED_MARKERS):
                return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'openai')
            if _byok_key_in_use('openrouter'):
                limit_source = _openrouter_limit_source(error)
                if limit_source == 'openrouter_credits':
                    return ByokProviderFailure(BYOK_QUOTA_FAILURE_CLASS, 'openrouter')
                if limit_source in _OPENROUTER_RATE_LIMIT_SOURCES:
                    return ByokProviderFailure(BYOK_RATE_LIMIT_FAILURE_CLASS, 'openrouter')
            return None
        if status_code == 401:
            text = _lowered_error_text(error)
            for provider in ('openai', 'openrouter'):
                if _byok_key_in_use(provider) and (
                    any(marker in text for marker in _INVALID_KEY_MARKERS)
                    or type(error).__name__ == 'AuthenticationError'
                ):
                    return ByokProviderFailure(BYOK_INVALID_KEY_FAILURE_CLASS, provider)
        return None

    return None


def is_byok_quota_error(error: BaseException) -> bool:
    """Return whether ``error`` reports the caller's own BYOK provider account
    being out of credit or quota.

    The gateway answers that account state with its ``byok_quota`` credential
    failure class (HTTP 429, in ``_THROTTLED_FAILURE_CLASSES``), while direct
    Anthropic BYOK raises the SDK's ``BadRequestError`` for an exhausted
    prepaid balance or usage limit and direct OpenRouter/OpenAI BYOK answers
    402/429 when the account's credits cannot cover the request. All are
    account state only the user can fix on their own key; every other request
    shape keeps the generic response.
    """
    failure = classify_byok_provider_failure(error)
    return failure is not None and failure.failure_class == BYOK_QUOTA_FAILURE_CLASS


def byok_failure_class_of(error: BaseException) -> str | None:
    """Return the byok failure class an already-mapped exception carries.

    ``conversation_processing_http_exception`` answers byok failures as typed
    HTTPExceptions whose detail ``code`` is the failure class; wrappers
    (finalization, background tasks) re-raise them as their cause. This reads
    that verdict back without re-classifying, for severity decisions upstream.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, HTTPException):
            detail = current.detail
            if isinstance(detail, Mapping):
                code = _string_value(detail.get('code'))
                if code in (
                    BYOK_RATE_LIMIT_FAILURE_CLASS,
                    BYOK_QUOTA_FAILURE_CLASS,
                    BYOK_INVALID_KEY_FAILURE_CLASS,
                ):
                    return code
        current = current.__cause__ or current.__context__
    return None


def _log_byok_provider_failure(failure: ByokProviderFailure, route: str) -> None:
    """One structured WARNING line; never ERROR, never a traceback, no uid, no key material."""
    logger.warning(
        'byok provider failure is user account state, not a server fault: byok=true failure_class=%s '
        'provider=%s route=%s',
        failure.failure_class,
        failure.provider,
        route,
    )


def conversation_processing_http_exception(
    error: BaseException, *, route: str = 'conversation_processing'
) -> HTTPException:
    """Map a processing failure to the existing safe HTTP contract.

    The caller is the authoritative conversation composition boundary. A
    provider failure on the user's own key answers the typed detail (429 for
    quota/rate-limit/invalid-key account states) and logs one structured
    WARNING line, so severity>=ERROR keeps counting only Omi-side faults.
    Every other exception retains the existing generic response and a
    privacy-safe log entry.
    """
    failure = classify_byok_provider_failure(error)
    if failure is not None:
        _log_byok_provider_failure(failure, route)
        if failure.failure_class == BYOK_RATE_LIMIT_FAILURE_CLASS:
            return HTTPException(status_code=429, detail=BYOK_RATE_LIMIT_ERROR_DETAIL)
        if failure.failure_class == BYOK_INVALID_KEY_FAILURE_CLASS:
            return HTTPException(status_code=429, detail=BYOK_INVALID_KEY_ERROR_DETAIL)
        return HTTPException(status_code=429, detail=BYOK_QUOTA_ERROR_DETAIL)
    logger.error('Conversation processing failed: %s', type(error).__name__)
    return HTTPException(status_code=500, detail=GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL)
