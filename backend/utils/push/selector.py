"""Push backend selection — the ADR-0011 feature flag.

Read at call time (not cached) so a redeploy or a per-test env override takes effect
without reloading the module. Idiom mirrors ``AUTH_BACKEND`` / ``STORAGE_BACKEND``.
"""

import logging
import os

from utils.push.base import FCM, VALID_BACKENDS

logger = logging.getLogger(__name__)


def resolve_push_backend() -> str:
    """Return the active push backend from ``PUSH_NOTIFICATION_BACKEND`` (default ``fcm``).

    An unset/blank value selects FCM (upstream default). An unrecognized value is logged
    and coerced to FCM rather than raising, so a typo never takes push delivery down.
    """
    value = (os.getenv('PUSH_NOTIFICATION_BACKEND') or FCM).strip().lower()
    if value not in VALID_BACKENDS:
        logger.error("Invalid PUSH_NOTIFICATION_BACKEND=%r; falling back to '%s'", value, FCM)
        return FCM
    return value
