"""Call the tenant erase barrier from the authenticated Python deletion executor."""

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import os
from functools import partial
from urllib.parse import urlsplit

import httpx

from database import go_queue_erase as receipt

logger = logging.getLogger(__name__)


class EraseUnavailable(RuntimeError):
    """The service could not confirm a committed erase."""


class EraseRejected(RuntimeError):
    """Integrity or authorization error. Never use database recovery."""


def go_queue_erase_required() -> bool:
    mode = os.getenv('GO_QUEUE_ERASE_REQUIRED', 'false').strip().lower()
    if mode not in {'true', 'false'}:
        raise ValueError('invalid GO_QUEUE_ERASE_REQUIRED')
    return mode == 'true'


def _oidc_token(audience: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    # Bound metadata and identity requests independently of workerd.
    return fetch_id_token(partial(Request(), timeout=2), audience)


def _erase_at_worker(uid: str, job_id: str, claim: str) -> None:
    endpoint = os.getenv('GO_QUEUE_ERASE_URL', '')
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != '/internal/v1/tenant-erase'
    ):
        raise EraseRejected('invalid Go queue erase URL')
    audience = os.getenv('GO_QUEUE_ERASE_AUDIENCE', '')
    if not audience:
        raise EraseRejected('missing Go queue erase audience')
    try:
        token = _oidc_token(audience)
    except Exception:
        raise EraseRejected('Go queue erase workload identity unavailable') from None
    try:
        response = httpx.post(
            endpoint,
            headers={'Authorization': f'Bearer {token}'},
            json={'tenant': uid, 'wipe_job_id': job_id, 'claim': claim},
            timeout=httpx.Timeout(8, connect=2),
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.RequestError:
        raise EraseUnavailable('Go queue erase request unavailable') from None
    if response.status_code in (408, 429, 500, 502, 503, 504):
        raise EraseUnavailable('Go queue erase service unavailable')
    if response.status_code != 200:
        raise EraseRejected('Go queue erase request rejected')
    try:
        data = response.json()
    except ValueError:
        raise EraseRejected('invalid Go queue erase receipt') from None
    if data != {'wipe_job_id': job_id, 'claim': claim}:
        raise EraseRejected('mismatched Go queue erase receipt')


def _erase_at_postgres(uid: str) -> bool:
    if os.getenv('GO_QUEUE_ERASE_RECOVERY_ENABLED', 'false').strip().lower() != 'true':
        return False
    dsn = os.getenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', '')
    if not dsn:
        raise EraseRejected('Go queue erase recovery credential missing')
    import psycopg

    try:
        with psycopg.connect(
            dsn,
            sslmode='verify-full',
            connect_timeout=3,
            options='-c statement_timeout=6000 -c lock_timeout=4000',
        ) as connection:
            connection.execute('SELECT public.queue_erase_tenant(%s)', (uid,))
    except psycopg.Error:
        raise EraseUnavailable('Go queue erase recovery unavailable') from None
    return True


def require_committed_erase(uid: str, job_id: str, token: str, owns_claim: Callable[[], None]) -> None:
    claim = receipt.claim_fingerprint(token)
    owns_claim()
    marker = receipt.record(uid, job_id, claim, 'arm')
    try:
        if marker.get(receipt.RECEIPT_AT) is None:
            path = 'workerd'
            try:
                _erase_at_worker(uid, job_id, claim)
            except EraseUnavailable:
                owns_claim()
                receipt.record(uid, job_id, claim, 'verify')
                if not _erase_at_postgres(uid):
                    raise
                path = 'postgres'
            owns_claim()
            receipt.record(uid, job_id, claim, 'receipt', path)
    except (EraseRejected, EraseUnavailable) as error:
        armed = marker.get(receipt.ARMED_AT)
        if isinstance(error, EraseRejected) or (
            isinstance(armed, datetime) and datetime.now(timezone.utc) - armed >= receipt.ERASE_DEADLINE
        ):
            logger.error(
                'go_queue_erase_page', extra={'reason': 'rejected' if isinstance(error, EraseRejected) else 'overdue'}
            )
        raise
    owns_claim()
    receipt.record(uid, job_id, claim, 'wipe')
