"""Regolo-specific error taxonomy.

Maps Regolo HTTP responses to distinct internal categories so callers can
distinguish credential failures from quota exhaustion from temporary outages.
A generic 500 from the backend masks credential compromise and gives users no
useful signal — every category here exists because at least one upstream
caller needs to react differently.

These errors are raised by the EU Privacy Mode dispatcher and the chat router
when a Regolo call fails. The dispatcher decides whether the error is
fallback-eligible (ServiceError, RateLimitError after backoff) or terminal
(AuthError, ForbiddenError, ModelNotFoundError).
"""

from __future__ import annotations

from typing import Any, Optional


class RegoloError(Exception):
    """Base class for all Regolo-specific failures.

    Subclasses carry the original status code so logging can record it
    without re-deriving from response bodies (which may be sanitized).
    """

    status_code: Optional[int] = None
    fallback_eligible: bool = False

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class RegoloAuthError(RegoloError):
    """401 — invalid or revoked API key.

    Surface to the user as an auth-required signal so they re-enter the BYOK
    Regolo key. Never fall back: a key change is required to recover.
    """

    status_code = 401
    fallback_eligible = False


class RegoloForbiddenError(RegoloError):
    """403 — model not allowed on the current plan tier.

    Example: requesting `qwen3-vl-32b` on PAYG. UI must disable the feature
    that needs this model rather than retrying with a different prompt.
    """

    status_code = 403
    fallback_eligible = False


class RegoloModelNotFoundError(RegoloError):
    """404 — model id does not exist (typo or model retirement).

    Logs at WARNING level with the model name so the catalog drift is
    discoverable. Caller should surface a configuration error to the
    operator, not retry.
    """

    status_code = 404
    fallback_eligible = False


class RegoloRateLimitError(RegoloError):
    """429 — quota or per-tenant rate limit exceeded.

    Carries `retry_after_s` parsed from the `Retry-After` header so the
    caller can implement bounded exponential backoff instead of guessing.
    """

    status_code = 429
    fallback_eligible = True

    def __init__(self, message: str, retry_after_s: Optional[float] = None):
        super().__init__(message, status_code=429)
        self.retry_after_s = retry_after_s


class RegoloServiceError(RegoloError):
    """5xx — Regolo service outage or upstream failure.

    Fallback-eligible: after one retry, the EU Privacy Mode dispatcher may
    fall back to the primary provider with a visible banner. Repeated
    occurrences should fire a circuit breaker.
    """

    status_code = 500
    fallback_eligible = True


def classify_regolo_error(exc: BaseException) -> RegoloError:
    """Map an arbitrary upstream exception to the right RegoloError subclass.

    Inspects common attributes set by the OpenAI Python SDK / httpx
    (`status_code`, `response.status_code`, `code`) without raising on
    missing fields. Falls back to RegoloServiceError for anything we can't
    classify so a transient unknown error stays fallback-eligible.

    Never re-raises — always returns an instance the caller can `raise from`.
    """
    if isinstance(exc, RegoloError):
        return exc

    status = _extract_status_code(exc)
    detail = _safe_message(exc)

    if status == 401:
        return RegoloAuthError(detail or 'Regolo authentication failed', status_code=status)
    if status == 403:
        return RegoloForbiddenError(detail or 'Regolo model not allowed on plan', status_code=status)
    if status == 404:
        return RegoloModelNotFoundError(detail or 'Regolo model not found', status_code=status)
    if status == 429:
        retry_after = _extract_retry_after(exc)
        return RegoloRateLimitError(detail or 'Regolo rate limit exceeded', retry_after_s=retry_after)
    if status is not None and 500 <= status < 600:
        return RegoloServiceError(detail or f'Regolo service error ({status})', status_code=status)

    # Unknown — treat as transient so we get fallback behavior on first hit.
    return RegoloServiceError(detail or 'Regolo error (unclassified)', status_code=status)


def _extract_status_code(exc: BaseException) -> Optional[int]:
    for attr in ('status_code', 'http_status'):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, 'response', None)
    if response is not None:
        value = getattr(response, 'status_code', None)
        if isinstance(value, int):
            return value
    return None


def _extract_retry_after(exc: BaseException) -> Optional[float]:
    response = getattr(exc, 'response', None)
    if response is None:
        return None
    headers = getattr(response, 'headers', None)
    if headers is None:
        return None
    raw = headers.get('Retry-After') if hasattr(headers, 'get') else None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _safe_message(exc: BaseException) -> str:
    """Return a sanitized one-line summary of the exception.

    Keeps status code and error type — drops potentially sensitive payload
    bodies. The Regolo API may echo prompt content in error messages on some
    400-family errors; we don't want that reaching our logs.
    """
    cls = type(exc).__name__
    text = str(exc)
    # Truncate aggressively — error chains can include full request bodies.
    if len(text) > 200:
        text = text[:200] + '…'
    return f'{cls}: {text}' if text else cls
