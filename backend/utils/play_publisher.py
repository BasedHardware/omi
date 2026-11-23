"""Google Play Android Publisher v3 over REST with Application Default Credentials.

Kept free of the entitlement stack so account deletion can cancel Play subscriptions without
importing it. ``cancel_for_account_deletion`` stops every future Google charge for a deleted uid
and raises when Google cannot confirm it, so the deletion task stays retryable.
"""

from __future__ import annotations

import logging
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


def _still_chargeable(publisher: PublisherClient, token: str) -> bool:
    """Google's current view: can this purchase still be charged? Not found counts as no."""
    try:
        resource = publisher.get_subscription(config.package_name(), token)
    except PurchaseNotFound:
        return False
    return str(resource.get('subscriptionState') or '') in _CHARGEABLE_STATES


def _status_code(error: BaseException) -> Optional[int]:
    return getattr(error, 'status_code', None)


def cancel_for_account_deletion(uid: str, publisher: Optional[PublisherClient] = None) -> int:
    """Stop every future Google charge for ``uid``. Returns how many purchases needed a cancel.

    Google is re-read first: an ended, expired, cancelled (no further charge) or unknown purchase is
    already done. A failed cancel is re-read once and accepted when it can no longer be charged.
    Anything else raises ``PlayCancelPending``, which the deletion wipe retries with backoff; the
    error carries the HTTP status and a token hash only, never the token.
    """
    publisher = publisher or default_publisher()
    fields = play_db.get_user_fields(uid)
    keys = [key for key in (fields.get(play_db.USER_POINTER_FIELD), fields.get(play_db.PENDING_FIELD)) if key]
    cancelled = 0
    for key in dict.fromkeys(keys):
        record = play_db.get_purchase(key) or {}
        token = record.get('purchase_token')
        if record.get('uid') != uid or not token or record.get('account_deletion_cancelled'):
            continue
        try:
            chargeable = _still_chargeable(publisher, token)
        except Exception as error:
            raise PlayCancelPending(_status_code(error), key) from None
        if chargeable:
            try:
                publisher.cancel(config.package_name(), token)
                cancelled += 1
            except PurchaseNotFound:
                pass
            except Exception as error:
                try:
                    chargeable = _still_chargeable(publisher, token)
                except Exception:
                    chargeable = True
                if chargeable:
                    logger.warning('play_billing deletion cancel failed: status=%s', _status_code(error))
                    raise PlayCancelPending(_status_code(error), key) from None
        play_db.update_purchase(key, {'auto_renewing': False, 'account_deletion_cancelled': True})
    return cancelled
