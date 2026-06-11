import asyncio
import logging
from typing import Optional

from utils.byok import get_byok_key, get_byok_uid
from utils.executors import storage_executor, submit_with_context
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_QUOTA_ERROR_NAMES = frozenset({'RateLimitError'})


def get_llm_error_source(provider: Optional[str]) -> str:
    """Return platform/byok for the current request and provider."""
    if provider and get_byok_key(provider):
        return 'byok'
    return 'platform'


def classify_byok_llm_error(error: Exception) -> Optional[str]:
    """Classify user-actionable BYOK failures for structured logging."""
    status_code = _get_status_code(error)
    error_name = type(error).__name__
    error_text = sanitize(str(error)).lower()

    if status_code == 401 or error_name == 'AuthenticationError':
        return 'invalid'
    if status_code == 403 or error_name == 'PermissionDeniedError':
        return 'permission'
    if status_code == 429 or error_name in _QUOTA_ERROR_NAMES:
        if 'insufficient_quota' in error_text or 'quota' in error_text:
            return 'quota'
    return None


def handle_llm_error(
    error: Exception,
    provider: Optional[str],
    feature: Optional[str] = None,
    model: Optional[str] = None,
    operation: str = 'chat',
) -> None:
    """Log LLM failures with source context."""
    source = get_llm_error_source(provider)
    reason = classify_byok_llm_error(error) if source == 'byok' else None
    uid = get_byok_uid()
    status_code = _get_status_code(error)

    logger.error(
        'LLM error source=%s provider=%s feature=%s model=%s operation=%s uid=%s status_code=%s reason=%s '
        'error_type=%s error=%s',
        source,
        provider or 'unknown',
        feature or 'unknown',
        model or 'unknown',
        operation,
        uid or 'unknown',
        status_code or 'unknown',
        reason or 'unknown',
        type(error).__name__,
        sanitize(str(error)),
    )


async def handle_llm_error_async(
    error: Exception,
    provider: Optional[str],
    feature: Optional[str] = None,
    model: Optional[str] = None,
    operation: str = 'chat',
) -> None:
    """Run LLM error handling off the event loop while preserving BYOK context."""
    future = submit_with_context(storage_executor, handle_llm_error, error, provider, feature, model, operation)
    try:
        await asyncio.wrap_future(future)
    except Exception as e:
        logger.error('Async LLM error handler failed provider=%s feature=%s: %s', provider, feature, e)


def _get_status_code(error: Exception) -> Optional[int]:
    status_code = getattr(error, 'status_code', None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(error, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int):
        return response_status
    return None
