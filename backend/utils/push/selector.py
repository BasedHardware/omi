"""Push backend selection — the ADR-0011 feature flag.

Read at call time (not cached) so a redeploy or a per-test env override takes effect
without reloading the module. Idiom mirrors ``AUTH_BACKEND`` / ``STORAGE_BACKEND``.
"""

import logging
import os

from utils.observability.fallback import record_fallback
from utils.push.base import DISABLED, FCM, UNIFIEDPUSH, VALID_BACKENDS

logger = logging.getLogger(__name__)


def _unifiedpush_is_usable() -> bool:
    """Whether the UnifiedPush transport can actually deliver.

    ``UNIFIEDPUSH_INTERNAL_BASE_URL`` is REQUIRED by ``utils/push/unifiedpush.py::_target_url``, which
    refuses to POST to the stored endpoint verbatim because it is user-registered (SSRF). That refusal is
    right; the problem was that nothing above it knew. Blank counts as missing, matching ``_target_url``.
    """
    return bool((os.getenv('UNIFIEDPUSH_INTERNAL_BASE_URL') or '').strip())


def resolve_push_backend() -> str:
    """Return the active push backend from ``PUSH_NOTIFICATION_BACKEND`` (default ``fcm``).

    An unset/blank value selects FCM (upstream default). An unrecognized value is logged
    and coerced to FCM rather than raising, so a typo never takes push delivery down.

    A RECOGNISED transport that cannot work is a different situation and gets a different answer:
    ``unifiedpush`` without its base URL resolves to ``disabled`` (first-class in ADR-0011) instead of
    reporting a transport that loses 100% of notifications. Measured before this existed: the selector
    answered ``unifiedpush``, readiness passed, and every send failed with one ERROR log per endpoint and
    NOTHING on ``omi_fallback_total`` (BACKLOG L18).

    Not ``fcm``: the operator declared an on-prem transport, so falling back to Google's would be the
    vendor-fallback class this project keeps closing — and on an on-prem stack it would fail anyway,
    later and less clearly.
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
    if value == UNIFIEDPUSH and not _unifiedpush_is_usable():
        record_fallback(
            component='push',
            from_mode=UNIFIEDPUSH,
            to_mode=DISABLED,
            reason='config_incomplete',
            outcome='degraded',
            log=logger,
        )
        return DISABLED
    return value


def validate_push_configuration() -> None:
    """Say at BOOT that push cannot be delivered, instead of once per endpoint per notification.

    Same shape as ``utils/subscription.py::validate_stripe_price_ids``: log loudly, name the
    consequence, and do NOT refuse to boot. Push is the single admitted cloud exception (ADR-0011), not
    the critical path — an API that stops serving because a notification transport is misconfigured
    would trade a partial loss for a total one. Never raises: it runs at import time in ``main.py``.
    """
    try:
        declared = (os.getenv('PUSH_NOTIFICATION_BACKEND') or '').strip().lower()
        if declared == UNIFIEDPUSH and not _unifiedpush_is_usable():
            logger.error(
                'STARTUP: PUSH_NOTIFICATION_BACKEND=unifiedpush but UNIFIEDPUSH_INTERNAL_BASE_URL is not '
                'set — no push notification will be delivered (the transport refuses to POST to a '
                'user-registered endpoint verbatim). Set the internal push-server base URL, or declare '
                'PUSH_NOTIFICATION_BACKEND=disabled to make the choice explicit.'
            )
    except Exception:  # pragma: no cover - a startup log must never break startup
        pass
