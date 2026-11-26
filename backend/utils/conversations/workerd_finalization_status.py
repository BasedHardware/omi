"""Read the PostgreSQL-owned status of a bound ordinary-sync job."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import BoundedSemaphore
from urllib.parse import urlsplit

import httpx

from utils.sync.worker_client import identity_token

STATUS_TIMEOUT_SECONDS = 1.5
_LOOKUP_LIMIT = 4
_LOOKUP_SLOTS = BoundedSemaphore(_LOOKUP_LIMIT)
_LOOKUPS = ThreadPoolExecutor(max_workers=_LOOKUP_LIMIT, thread_name_prefix='workerd-status')


class StatusUnavailable(RuntimeError):
    """The Go job's current status could not be read."""


def read_status(uid: str, conversation_id: str, job_id: str, revision: int) -> dict | None:
    # A total deadline covers OIDC minting as well as the HTTP exchange.
    # Keep slow lookups charged until they actually finish, with no waiting queue.
    if not _LOOKUP_SLOTS.acquire(blocking=False):
        raise StatusUnavailable()
    try:
        future = _LOOKUPS.submit(_fetch_status, uid, conversation_id, job_id, revision)
    except Exception as error:
        _LOOKUP_SLOTS.release()
        raise StatusUnavailable() from error
    future.add_done_callback(lambda _: _LOOKUP_SLOTS.release())
    try:
        return future.result(timeout=STATUS_TIMEOUT_SECONDS)
    except TimeoutError as error:
        raise StatusUnavailable() from error


def _fetch_status(uid: str, conversation_id: str, job_id: str, revision: int) -> dict | None:
    origin = os.getenv('SYNC_EPISODE_INTAKE_ORIGIN', '').rstrip('/')
    audience = os.getenv('WORKER_EPISODE_INTAKE_AUDIENCE', '')
    try:
        url = urlsplit(origin)
        if (
            url.scheme != 'https'
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
            or not audience
        ):
            raise ValueError('workerd endpoint unavailable')
        response = httpx.post(
            f'{origin}/internal/finalization/status',
            json={'owner': uid, 'conversation': conversation_id, 'job': job_id, 'revision': revision},
            headers={'Authorization': f'Bearer {identity_token(audience)}'},
            follow_redirects=False,
            timeout=STATUS_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError('invalid workerd status')
        status, attempts = result.get('status'), result.get('attempt_count')
        if (
            status not in ('queued', 'leased', 'blocked_byok', 'dead_letter', 'completed')
            or type(attempts) is not int
            or attempts < 0
            or result.get('terminal_outcome') not in ('unknown', 'failure', 'success', 'stale')
        ):
            raise ValueError('invalid workerd status')
        return result
    except Exception as error:
        # Don't expose internal service URLs, tokens or response bodies to clients.
        raise StatusUnavailable() from error
