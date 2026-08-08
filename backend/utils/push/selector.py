"""Push backend selection — the ADR-0011 feature flag.

Read at call time (not cached) so a redeploy or a per-test env override takes effect
without reloading the module. Idiom mirrors ``AUTH_BACKEND`` / ``STORAGE_BACKEND``.
"""

import logging
import os

from utils.observability.fallback import record_fallback
from utils.push.base import FCM, VALID_BACKENDS

logger = logging.getLogger(__name__)


def resolve_push_backend() -> str:
    """Return the active push backend from ``PUSH_NOTIFICATION_BACKEND`` (default ``fcm``).

    An unset/blank value selects FCM (upstream default). An unrecognized value is logged
    and coerced to FCM rather than raising, so a typo never takes push delivery down.
    """
    # Strip first, then fall back: an unset OR whitespace-only value defaults cleanly to FCM without
    # logging a spurious "invalid" error. Only a non-blank unrecognized value is an actual typo.
    value = (os.getenv('PUSH_NOTIFICATION_BACKEND') or '').strip().lower() or FCM
    if value not in VALID_BACKENDS:
        # A typo degrades push delivery to the FCM default — record it as a fallback so the drift is
        # visible in omi_fallback_total (record_fallback also emits the warning log; never raises).
        record_fallback(
            component='push',
            from_mode=value,
            to_mode=FCM,
            reason='config_invalid',
            outcome='degraded',
            log=logger,
        )
        return FCM
    return value
