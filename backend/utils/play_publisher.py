"""Google Play Android Publisher v3 over REST with Application Default Credentials.

Kept free of the entitlement stack so account deletion can cancel Play subscriptions without
importing it. ``cancel_for_account_deletion`` stops every future Google charge for a deleted uid
and raises when Google cannot confirm it, so the deletion task stays retryable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Protocol

import database.play_subscriptions as play_db
from config import play_billing as config

logger = logging.getLogger(__name__)

_PUBLISHER_API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications'

# Purchases that can still charge the user; anything else needs no cancel.
_CHARGEABLE_STATES = frozenset(
    {
        'SUBSCRIPTION_STATE_ACTIVE',
        'SUBSCRIPTION_STATE_IN_GRACE_PERIOD',
        'SUBSCRIPTION_STATE_ON_HOLD',
        'SUBSCRIPTION_STATE_PAUSED',
        'SUBSCRIPTION_STATE_PENDING',
    }
)


class PurchaseNotFound(Exception):
    """Google says the token does not exist for this package."""


class PublisherHTTPError(Exception):
    """A Publisher API failure carrying only the HTTP status: request URLs hold the purchase token."""

    def __init__(self, status_code: int, operation: str):
        super().__init__(f'Google Play {operation} failed with HTTP {status_code}')
        self.status_code = status_code


class PlayCancelPending(RuntimeError):
    """Google could not confirm a deletion cancel yet. Retryable: the deletion wipe backs off and tries again."""

    def __init__(self, status_code: Optional[int], token_hash: str):
        status = status_code if status_code is not None else 'unavailable'
        super().__init__(f'Google Play cancel not confirmed (status {status}) for purchase {token_hash[:12]}')
        self.status_code = status_code


def _raise_for_status(response, operation: str) -> None:
    if response.status_code >= 400:
        raise PublisherHTTPError(response.status_code, operation)


class PublisherClient(Protocol):
    def get_subscription(self, package_name: str, token: str) -> dict: ...

    def acknowledge(self, package_name: str, product_id: str, token: str) -> None: ...

    def cancel(self, package_name: str, token: str) -> None: ...


class GooglePublisher:
    """Android Publisher v3 REST over google-auth (built lazily on first use)."""

    def __init__(self):
        from urllib.parse import quote

        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        # Application Default Credentials: the runtime service account. No key file.
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/androidpublisher'])
        self._session = AuthorizedSession(credentials)
        self._quote = lambda value: quote(value, safe='')

    def _base(self, package_name: str) -> str:
        return f'{_PUBLISHER_API}/{self._quote(package_name)}/purchases'

    def get_subscription(self, package_name: str, token: str) -> dict:
        response = self._session.get(
            f'{self._base(package_name)}/subscriptionsv2/tokens/{self._quote(token)}', timeout=15
        )
        if response.status_code in (400, 404, 410):
            raise PurchaseNotFound()
        _raise_for_status(response, 'read')
        return response.json()

    def acknowledge(self, package_name: str, product_id: str, token: str) -> None:
        url = f'{self._base(package_name)}/subscriptions/{self._quote(product_id)}/tokens/{self._quote(token)}:acknowledge'
        response = self._session.post(url, json={}, timeout=15)
        _raise_for_status(response, 'acknowledge')

    def cancel(self, package_name: str, token: str) -> None:
        """subscriptionsv2.cancel: stops the next payment; the developer type cannot be restored by the user."""
        url = f'{self._base(package_name)}/subscriptionsv2/tokens/{self._quote(token)}:cancel'
        body = {'cancellationContext': {'cancellationType': 'DEVELOPER_REQUESTED_STOP_PAYMENTS'}}
        response = self._session.post(url, json=body, timeout=15)
        if response.status_code in (404, 410):
            raise PurchaseNotFound()
        _raise_for_status(response, 'cancel')


_default: Optional[PublisherClient] = None


def default_publisher() -> PublisherClient:
    global _default
    if _default is None:
        _default = GooglePublisher()
    return _default


def _google_view(publisher: PublisherClient, token: str) -> tuple[bool, bool]:
    """Google's current view: (can still be charged, user-cancelled with paid time left). Not found is neither.

    A purchase the developer already cancelled cannot be restored by the user, so it needs no second cancel.
    """
    try:
        resource = publisher.get_subscription(config.package_name(), token)
    except PurchaseNotFound:
        return False, False
    state = str(resource.get('subscriptionState') or '')
    if state in _CHARGEABLE_STATES:
        return True, False
    developer_cancelled = 'developerInitiatedCancellation' in (resource.get('canceledStateContext') or {})
    return False, state == 'SUBSCRIPTION_STATE_CANCELED' and not developer_cancelled and _expires_in_future(resource)


def _expires_in_future(resource: dict) -> bool:
    items = resource.get('lineItems') or []
    expiry = (items[0] or {}).get('expiryTime') if items and isinstance(items[0], dict) else None
    try:
        return datetime.fromisoformat(str(expiry).replace('Z', '+00:00')) > datetime.now(timezone.utc)
    except ValueError:
        return False


def _status_code(error: BaseException) -> Optional[int]:
    return getattr(error, 'status_code', None)


def cancel_for_account_deletion(uid: str, publisher: Optional[PublisherClient] = None) -> int:
    """Stop every future Google charge for ``uid``. Returns how many purchases needed a cancel.

    Covers every purchase document bound to ``uid`` (the set the wipe purges) plus the user's pointers.
    Google is re-read every time, never a stored flag: a purchase cancelled by an earlier deletion and
    resubscribed after a restore is chargeable again. An ended, expired, developer-cancelled or unknown
    purchase is already done. A failed cancel is re-read once and accepted when it can no longer be
    charged. Anything else raises ``PlayCancelPending``, which the deletion wipe retries with backoff;
    the error carries the HTTP status and a token hash only, never the token. A user-cancelled purchase
    with paid time left is cancelled too (best effort), so it cannot be restored in Google Play once the
    account is gone. Each settled purchase is stamped with the confirmation time the purge checks.
    The publisher (Google credentials) is built only when the user has a Play purchase.
    """
    fields = play_db.get_user_fields(uid)
    pointers = [key for key in (fields.get(play_db.USER_POINTER_FIELD), fields.get(play_db.PENDING_FIELD)) if key]
    cancelled = 0
    pending: Optional[PlayCancelPending] = None
    for key in dict.fromkeys(pointers + play_db.purchase_keys_for_uid(uid)):
        record = play_db.get_purchase(key) or {}
        if record.get('uid') != uid:
            continue
        token = record.get('purchase_token')
        if token:
            publisher = publisher or default_publisher()
            try:
                cancelled += _cancel_one(publisher, key, token)
            except PlayCancelPending as error:
                # One purchase Google cannot confirm never holds back the cancel of the others.
                pending = pending or error
                continue
        play_db.update_purchase(
            key, {'auto_renewing': False, play_db.DELETION_CONFIRMED_FIELD: datetime.now(timezone.utc)}
        )
    if pending is not None:
        raise pending
    return cancelled


def _cancel_one(publisher: PublisherClient, key: str, token: str) -> int:
    """Cancel one purchase when Google can still charge or restore it; raises ``PlayCancelPending`` if unconfirmed."""
    try:
        chargeable, restorable = _google_view(publisher, token)
    except Exception as error:
        raise PlayCancelPending(_status_code(error), key) from None
    if not (chargeable or restorable):
        return 0
    try:
        publisher.cancel(config.package_name(), token)
        return 1
    except PurchaseNotFound:
        return 0
    except Exception as error:
        if restorable:
            # No charge is due: the user already cancelled. Best effort only.
            logger.warning(
                'play_billing deletion cancel of a cancelled purchase failed: status=%s', _status_code(error)
            )
            return 0
        try:
            chargeable = _google_view(publisher, token)[0]
        except Exception:
            chargeable = True
        if chargeable:
            logger.warning('play_billing deletion cancel failed: status=%s', _status_code(error))
            raise PlayCancelPending(_status_code(error), key) from None
        return 0


def purge_account_records(uid: str, confirmed_since: datetime, publisher: Optional[PublisherClient] = None) -> int:
    """Account wipe: drop the user's Play purchase records and account-map entries (uid + token).

    Refuses while any purchase lacks a cancel confirmed at or after ``confirmed_since``. Right before the
    delete, Google is read once more per purchase: one that can charge again (``_CHARGEABLE_STATES``:
    ACTIVE, IN_GRACE_PERIOD, ON_HOLD, PAUSED, PENDING), for example resubscribed in Google Play, raises
    ``PlayCancelPending`` and is kept, so the retried wipe cancels it again. A user-cancelled purchase with
    paid time left cannot charge: the cancel step already tried the developer cancel (best effort), and the
    purge proceeds whatever Google answered, so erasure never waits for the paid time to run out.
    """
    for key in play_db.purchase_keys_for_uid(uid):
        token = (play_db.get_purchase(key) or {}).get('purchase_token')
        if not token:
            continue
        publisher = publisher or default_publisher()
        try:
            chargeable, restorable = _google_view(publisher, token)
        except Exception as error:
            raise PlayCancelPending(_status_code(error), key) from None
        if chargeable:
            logger.warning('play_billing purchase chargeable again before purge; wipe retries: purchase=%s', key[:12])
            raise PlayCancelPending(None, key)
        if restorable:
            logger.warning('play_billing purge of a user-cancelled purchase with paid time left: purchase=%s', key[:12])
    return play_db.purge_account_records(uid, confirmed_since)
