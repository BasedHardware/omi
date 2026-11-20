"""Call the tenant erase barrier from the authenticated Python deletion executor."""

import asyncio
from collections.abc import Callable
import errno
import http.client
from ipaddress import ip_address
import json
import socket
import ssl
from datetime import datetime, timezone
import logging
import os
from functools import partial
from typing import NoReturn
from urllib.parse import urlsplit

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
    token = fetch_id_token(partial(Request(), timeout=2), audience)
    if not isinstance(token, str) or not token:
        raise EraseRejected('missing Go queue erase workload token')
    return token


# Only availability failures may select the separate recovery credential.
_NETWORK_AVAILABILITY_ERRORS = {
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.EHOSTDOWN,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETRESET,
    errno.ENETUNREACH,
    errno.EPIPE,
    errno.ETIMEDOUT,
}


def _raise_transport_error(error: OSError) -> NoReturn:
    if isinstance(error, TimeoutError) or error.errno in _NETWORK_AVAILABILITY_ERRORS:
        raise EraseUnavailable('Go queue erase network unavailable') from None
    raise EraseRejected('Go queue erase network operation rejected') from None


_RETRYABLE_WORKER_HTTP_STATUSES = frozenset({408, 429, 502, 503, 504})


class _EraseHTTPResponse(http.client.HTTPResponse):
    def begin(self) -> None:
        try:
            super().begin()
        except (OSError, http.client.HTTPException):
            # The stdlib uses a sentinel until it parses the final status line.
            if self.status in range(100, 1000) and self.status not in _RETRYABLE_WORKER_HTTP_STATUSES | {200}:
                raise EraseRejected('Go queue erase request rejected') from None
            if self.status in _RETRYABLE_WORKER_HTTP_STATUSES | {200}:
                raise EraseUnavailable('Go queue erase response headers were interrupted') from None
            raise


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
        raw = socket.create_connection((parsed.hostname, parsed.port or 443), timeout=2)
    except socket.gaierror as error:
        if error.errno != socket.EAI_AGAIN:
            raise EraseRejected('invalid Go queue erase host') from None
        raise EraseUnavailable('Go queue erase host temporarily unavailable') from None
    except OSError as error:
        _raise_transport_error(error)
    with raw:
        try:
            tls = ssl.create_default_context()
            tls.minimum_version = ssl.TLSVersion.TLSv1_2
        except OSError:
            raise EraseRejected('Go queue erase TLS context setup failed') from None
        try:
            secured = tls.wrap_socket(raw, server_hostname=parsed.hostname)
        except TimeoutError:
            raise EraseUnavailable('Go queue erase TLS handshake timed out') from None
        except OSError:
            raise EraseRejected('Go queue erase TLS handshake failed') from None
        with secured:
            secured.settimeout(5)
            connection = http.client.HTTPSConnection(parsed.hostname, parsed.port)
            connection.sock = secured
            connection.response_class = _EraseHTTPResponse
            try:
                connection.request(
                    'POST',
                    parsed.path,
                    body=json.dumps({'tenant': uid, 'wipe_job_id': job_id, 'claim': claim}),
                    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                )
                with connection.getresponse() as response:
                    status = response.status
                    body = response.read(2049) if status == 200 else b''
                    if status == 200 and len(body) <= 2048 and response.length:
                        raise http.client.IncompleteRead(body, response.length)
            except (http.client.IncompleteRead, http.client.RemoteDisconnected, ssl.SSLEOFError):
                raise EraseUnavailable('Go queue erase acknowledgement was interrupted') from None
            except ssl.SSLError:
                raise EraseRejected('Go queue erase TLS session failed') from None
            except OSError as error:
                _raise_transport_error(error)
            except http.client.HTTPException:
                raise EraseRejected('invalid Go queue erase HTTP response') from None
            finally:
                connection.close()
    if status in _RETRYABLE_WORKER_HTTP_STATUSES:
        raise EraseUnavailable('Go queue erase service unavailable')
    if status != 200 or len(body) > 2048:
        raise EraseRejected('Go queue erase request rejected')
    try:
        data = json.loads(body)
    except ValueError:
        raise EraseRejected('invalid Go queue erase receipt') from None
    if data != {'wipe_job_id': job_id, 'claim': claim}:
        raise EraseRejected('mismatched Go queue erase receipt')


async def _recover_erase(dsn: str, schema: str, uid: str, expires: datetime) -> None:
    import psycopg
    from psycopg import sql

    try:
        loop = asyncio.get_running_loop()
        started = loop.time()
        remaining = (expires - datetime.now(timezone.utc)).total_seconds()
        deadline = started + min(10, remaining)
        if loop.time() >= deadline:
            raise EraseUnavailable('Go queue erase recovery grant expired')
        async with asyncio.timeout_at(deadline):
            connection = await psycopg.AsyncConnection.connect(
                dsn,
                sslmode='verify-full',
                connect_timeout=3,
                options='-c statement_timeout=6000 -c lock_timeout=4000',
            )

        async def commit_erase() -> None:
            await connection.set_isolation_level(psycopg.IsolationLevel.READ_COMMITTED)
            await connection.execute(sql.SQL('SELECT {}.queue_erase_tenant(%s)').format(sql.Identifier(schema)), (uid,))
            if loop.time() >= deadline or datetime.now(timezone.utc) >= expires:
                raise TimeoutError
            await connection.commit()

        operation = asyncio.create_task(commit_erase())
        try:
            done, _ = await asyncio.wait({operation}, timeout=max(0, deadline - loop.time()))
            if not done or loop.time() >= deadline:
                raise TimeoutError
            operation.result()
        finally:
            # Close the wire before cancellation, so psycopg cannot wait on a stalled server.
            await connection.close()
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
    except psycopg.errors.InsufficientPrivilege:
        raise EraseRejected('Go queue erase recovery permission denied') from None
    except (psycopg.Error, TimeoutError):
        raise EraseUnavailable('Go queue erase recovery unavailable') from None


def _erase_at_postgres(uid: str, expires: datetime) -> bool:
    dsn = os.getenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', '')
    if not dsn:
        return False
    schema = os.getenv('GO_QUEUE_ERASE_RECOVERY_SCHEMA', '')
    if not schema:
        raise EraseRejected('Go queue erase recovery schema missing')
    from psycopg import ProgrammingError
    from psycopg.conninfo import conninfo_to_dict

    try:
        params = conninfo_to_dict(dsn)
        host = params.get('host', '')
        if not host or ',' in host or '/' in host:
            raise ValueError('missing verification host')
        ip_address(params.get('hostaddr', ''))
    except (ProgrammingError, ValueError):
        raise EraseRejected('Go queue erase recovery requires a TLS host and numeric hostaddr') from None
    asyncio.run(_recover_erase(dsn, schema, uid, expires))
    return True


def require_committed_erase(
    uid: str, job_id: str, token: str, owns_claim: Callable[[], datetime], remote_inflight: Callable[[bool], None]
) -> None:
    claim = receipt.claim_fingerprint(token)
    marker = receipt.record(uid, job_id, claim, 'arm', expires=owns_claim())
    try:
        if marker.get(receipt.RECEIPT_AT) is None:
            remote_inflight(True)
            path = 'workerd'
            try:
                _erase_at_worker(uid, job_id, claim)
            except EraseUnavailable:
                owns_claim()
                current = receipt.record(uid, job_id, claim, 'verify')
                expires = current.get(receipt.CLAIM_EXPIRES_AT)
                if not isinstance(expires, datetime) or not _erase_at_postgres(uid, expires):
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
    remote_inflight(False)
    receipt.record(uid, job_id, claim, 'wipe')
