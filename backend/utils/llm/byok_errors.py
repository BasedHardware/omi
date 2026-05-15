import logging
from typing import Optional

from firebase_admin import messaging

try:
    import database.notifications as notification_db
except ImportError:
    notification_db = None

try:
    from database.redis_db import try_acquire_byok_llm_error_notification_lock
except ImportError:

    def try_acquire_byok_llm_error_notification_lock(
        uid: str, provider: str, reason: str, ttl: int = 60 * 60 * 24
    ) -> bool:
        logger.error('BYOK LLM notification lock unavailable uid=%s provider=%s reason=%s', uid, provider, reason)
        return False


from utils.byok import get_byok_key, get_byok_uid
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_PERMANENT_FAILURE_CODES = frozenset({'UNREGISTERED', 'INVALID_REGISTRATION_TOKEN', 'NOT_FOUND'})
_QUOTA_ERROR_NAMES = frozenset({'RateLimitError'})


def get_llm_error_source(provider: Optional[str]) -> str:
    """Return platform/byok for the current request and provider."""
    if provider and get_byok_key(provider):
        return 'byok'
    return 'platform'


def classify_byok_llm_error(error: Exception) -> Optional[str]:
    """Classify user-actionable BYOK failures for logging and notification."""
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
    """Log LLM failures with source context and notify users about broken BYOK keys."""
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

    if source == 'byok' and uid and provider and reason:
        _send_byok_llm_error_notification(uid, provider, reason)


def _get_status_code(error: Exception) -> Optional[int]:
    status_code = getattr(error, 'status_code', None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(error, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int):
        return response_status
    return None


def _send_byok_llm_error_notification(uid: str, provider: str, reason: str) -> None:
    if notification_db is None:
        logger.error('BYOK LLM notification database unavailable uid=%s provider=%s reason=%s', uid, provider, reason)
        return

    provider_name = provider.capitalize()
    if reason == 'quota':
        body = f'Your {provider_name} BYOK key appears to be out of quota. Update it to restore AI features.'
    elif reason == 'permission':
        body = f'Your {provider_name} BYOK key was denied access. Check its project and permissions in Omi settings.'
    else:
        body = f'Your {provider_name} BYOK key was rejected. Update it in Omi settings to restore AI features.'

    try:
        tokens = notification_db.get_all_tokens(uid)
    except Exception as e:
        logger.error(
            'BYOK LLM notification token lookup failed uid=%s provider=%s reason=%s: %s', uid, provider, reason, e
        )
        return

    if not tokens:
        logger.info('No tokens found for BYOK LLM notification uid=%s provider=%s reason=%s', uid, provider, reason)
        return

    try:
        acquired = try_acquire_byok_llm_error_notification_lock(uid, provider, reason)
    except Exception as e:
        logger.error('BYOK LLM notification lock failed uid=%s provider=%s reason=%s: %s', uid, provider, reason, e)
        return

    if not acquired:
        logger.info('BYOK LLM notification already sent recently uid=%s provider=%s reason=%s', uid, provider, reason)
        return

    notification = messaging.Notification(title='omi', body=body)
    data = {'type': 'byok_llm_error', 'provider': provider, 'reason': reason}
    messages = [messaging.Message(token=token, notification=notification, data=data) for token in tokens]

    try:
        response = messaging.send_each(messages)
    except Exception as e:
        logger.error('BYOK LLM notification send failed uid=%s provider=%s reason=%s: %s', uid, provider, reason, e)
        return

    invalid_tokens = []
    success_count = 0
    for idx, result in enumerate(response.responses):
        if result.success:
            success_count += 1
        elif result.exception:
            error_code = getattr(result.exception, 'code', None)
            if error_code in _PERMANENT_FAILURE_CODES:
                invalid_tokens.append(tokens[idx])
            else:
                logger.error('BYOK LLM notification FCM send failed uid=%s error=%s', uid, result.exception)

    if invalid_tokens:
        try:
            notification_db.remove_bulk_tokens(invalid_tokens)
        except Exception as e:
            logger.error('BYOK LLM notification invalid token cleanup failed uid=%s: %s', uid, e)

    logger.info(
        'BYOK LLM notification sent uid=%s provider=%s reason=%s success=%s total=%s',
        uid,
        provider,
        reason,
        success_count,
        len(tokens),
    )
