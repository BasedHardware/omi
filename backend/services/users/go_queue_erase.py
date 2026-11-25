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
    """Use the rollout value rendered into every deletion runtime at deploy time."""
    return os.getenv('GO_QUEUE_ERASE_REQUIRED', '').strip().lower() == 'true'


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


# Pin the physical writer and the exact queue catalog objects. The provisioned
# fingerprint comes from the intended workerd queue, never the recovery DSN.
RECOVERY_QUEUE_ID_SQL = """
SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.concat_ws(':',
    control.system_identifier, db.oid, settings.oid, erasure.oid,
    pg_catalog.inet_server_addr(), pg_catalog.inet_server_port()
), 'UTF8')), 'hex') AS queue_id
FROM pg_catalog.pg_control_system() AS control
JOIN pg_catalog.pg_database AS db ON db.datname = pg_catalog.current_database()
JOIN pg_catalog.pg_namespace AS ns ON ns.nspname = %s
JOIN pg_catalog.pg_class AS settings ON settings.relnamespace = ns.oid AND settings.relname = 'queue_settings'
JOIN pg_catalog.pg_class AS erasure ON erasure.relnamespace = ns.oid AND erasure.relname = 'queue_erasure'
WHERE pg_catalog.inet_server_addr() IS NOT NULL AND NOT pg_catalog.pg_is_in_recovery()
"""


async def _recover_erase(dsn: str, schema: str, uid: str, expires: datetime, expected_queue_id: str) -> str:
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
                options='-c search_path=pg_catalog -c statement_timeout=6000 -c lock_timeout=4000',
            )

        async def commit_erase() -> str:
            await connection.set_isolation_level(psycopg.IsolationLevel.READ_COMMITTED)
            result = await connection.execute(
                sql.SQL(
                    'WITH identity AS (' + RECOVERY_QUEUE_ID_SQL + ') '
                    'SELECT queue_id, CASE WHEN queue_id = %s '
                    'THEN {}.queue_erase_tenant(%s) IS NOT NULL ELSE FALSE END FROM identity'
                ).format(sql.Identifier(schema)),
                (schema, expected_queue_id, uid),
            )
            proof = await result.fetchone()
            if proof != (expected_queue_id, True):
                raise EraseRejected('Go queue erase recovery target does not match the intended queue')
            if loop.time() >= deadline or datetime.now(timezone.utc) >= expires:
                raise TimeoutError
            await connection.commit()
            return expected_queue_id

        operation = asyncio.create_task(commit_erase())
        try:
            done, _ = await asyncio.wait({operation}, timeout=max(0, deadline - loop.time()))
            if not done or loop.time() >= deadline:
                raise TimeoutError
            return operation.result()
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


def _erase_at_postgres(uid: str, expires: datetime) -> str | None:
    dsn = os.getenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', '')
    expected_queue_id = os.getenv('GO_QUEUE_ERASE_RECOVERY_QUEUE_ID', '')
    if not dsn or not expected_queue_id:
        return None
    if not receipt.valid_recovery_queue_id(expected_queue_id):
        raise EraseRejected('invalid Go queue erase recovery queue fingerprint')
    schema = os.getenv('GO_QUEUE_ERASE_RECOVERY_SCHEMA', '')
    if not schema:
        raise EraseRejected('Go queue erase recovery schema missing')
    from psycopg import ProgrammingError
    from psycopg.conninfo import conninfo_to_dict

    try:
        params = conninfo_to_dict(dsn)
        host, hostaddr = params.get('host'), params.get('hostaddr')
        if not isinstance(host, str) or not host or ',' in host or '/' in host:
            raise ValueError('missing verification host')
        if not isinstance(hostaddr, str):
            raise ValueError('missing numeric address')
        ip_address(hostaddr)
    except (ProgrammingError, ValueError):
        raise EraseRejected('Go queue erase recovery requires a TLS host and numeric hostaddr') from None
    return asyncio.run(_recover_erase(dsn, schema, uid, expires, expected_queue_id))


def require_committed_erase(
    uid: str, job_id: str, token: str, owns_claim: Callable[[], datetime], remote_inflight: Callable[[bool], None]
) -> None:
    claim = receipt.claim_fingerprint(token)
    marker = receipt.record(uid, job_id, claim, 'arm', expires=owns_claim())
    try:
        if marker.get(receipt.RECEIPT_AT) is None:
            remote_inflight(True)
            path = 'workerd'
            queue_id = None
            try:
                _erase_at_worker(uid, job_id, claim)
            except EraseUnavailable:
                owns_claim()
                current = receipt.record(uid, job_id, claim, 'verify')
                expires = current.get(receipt.CLAIM_EXPIRES_AT)
                if not isinstance(expires, datetime):
                    raise
                queue_id = _erase_at_postgres(uid, expires)
                if queue_id is None:
                    raise
                path = 'postgres'
            owns_claim()
            if queue_id is None:
                receipt.record(uid, job_id, claim, 'receipt', path)
            else:
                receipt.record(uid, job_id, claim, 'receipt', path, queue_id=queue_id)
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
