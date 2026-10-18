"""Low-level network guard for hermetic test runs."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import ipaddress
import os
import socket
from typing import Iterator


class BlockedNetworkError(RuntimeError):
    """Raised when a hermetic test tries to reach a non-local endpoint."""


# Captured at import time, before any guard can patch it: hostname checks
# inside the Redis guard must consult the real resolver. ``block_outbound_
# network`` refuses DNS for non-local names and the Redis guard runs beneath
# it, so calling ``socket.getaddrinfo`` dynamically there would classify an
# alias like ``redis.local`` as "unresolvable" instead of resolving it.
# ``backend/tests/conftest.py`` imports this module while loading conftests,
# before ``pytest_sessionstart`` installs the outbound guard, so the capture
# is pristine. Tests patch this attribute to fake resolution.
_UNGUARDED_GETADDRINFO = socket.getaddrinfo


def is_local_address(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode('idna')
    if not isinstance(host, str):
        return False

    normalized = host.strip().strip('[]').lower()
    if normalized in {'', 'localhost'}:
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback


def _host_from_address(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    return None


def _is_unix_socket(sock: socket.socket) -> bool:
    af_unix = getattr(socket, 'AF_UNIX', None)
    return af_unix is not None and sock.family == af_unix


@contextmanager
def block_outbound_network() -> Iterator[None]:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex

    def guarded_connect(sock: socket.socket, address: object):
        if not _is_unix_socket(sock) and not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object):
        if not _is_unix_socket(sock) and not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args, **kwargs):
        if not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host: object, *args, **kwargs):
        if not is_local_address(host):
            raise BlockedNetworkError(f'Blocked DNS resolution for {host!r}')
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host: object):
        if not is_local_address(host):
            raise BlockedNetworkError(f'Blocked DNS resolution for {host!r}')
        return original_gethostbyname(host)

    def guarded_gethostbyname_ex(host: object):
        if not is_local_address(host):
            raise BlockedNetworkError(f'Blocked DNS resolution for {host!r}')
        return original_gethostbyname_ex(host)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo
        socket.gethostbyname = original_gethostbyname
        socket.gethostbyname_ex = original_gethostbyname_ex


def _configured_redis_port() -> int:
    port_env = os.getenv('REDIS_DB_PORT')
    return int(port_env) if port_env is not None else 6379


def _fake_redis_endpoint_allowed() -> bool:
    return os.getenv('OMI_HERMETIC_ALLOW_FAKE_REDIS', '').lower() not in {'', '0', 'false', 'no', 'off'}


def _sockaddr_is_loopback(sockaddr: tuple) -> bool:
    address = sockaddr[0] if sockaddr else None
    if isinstance(address, bytes):
        address = address.decode('idna')
    if not isinstance(address, str):
        return False
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _redis_endpoint_host_is_local(host: object, port: int) -> bool:
    """True when ``host`` is loopback, is ``localhost``, or resolves to loopback.

    Literal addresses and the ``localhost`` name need no DNS. Any other
    hostname is resolved through the unguarded resolver, so a name such as a
    hosts-file ``redis.local`` pointing at 127.0.0.1 is refused exactly like
    the literal address no matter which of ``connect``/``connect_ex``/
    ``create_connection`` carried it, while a host that resolves off loopback
    keeps flowing to the chained guards. Resolution failures count as "not
    blocked": the original connect then surfaces its own natural error
    instead of the guard inventing one.
    """
    if isinstance(host, bytes):
        try:
            host = host.decode('idna')
        except UnicodeError:
            return False
    if not isinstance(host, str):
        return False
    if is_local_address(host):
        return True
    hostname = host.strip().strip('[]')
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return False  # A literal non-loopback address needs no resolution.
    try:
        resolved = _UNGUARDED_GETADDRINFO(hostname, port, 0, socket.SOCK_STREAM)
    except (OSError, RuntimeError, UnicodeError):
        return False
    return any(_sockaddr_is_loopback(result[4]) for result in resolved)


def _is_blocked_redis_endpoint(address: object, resolution_cache: dict | None = None) -> bool:
    """True for the ``database.redis_db`` endpoint when it is or resolves locally.

    ``_redis_connection_kwargs`` falls back to redis-py's ``localhost`` default
    when ``REDIS_DB_HOST`` is unset, so the endpoint a unit test would reach is
    the configured port on the configured host: a loopback literal, the
    ``localhost`` name, or any hostname that resolves to a loopback address.
    Tests that deliberately host their own fake Redis listener (real socket
    I/O against a stub peer) set ``OMI_HERMETIC_ALLOW_FAKE_REDIS`` to keep
    that endpoint reachable.
    """
    if _fake_redis_endpoint_allowed():
        return False
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host, port = address[0], address[1]
    if port != _configured_redis_port():
        return False
    cache_key = (host, port)
    if resolution_cache is not None and cache_key in resolution_cache:
        return resolution_cache[cache_key]
    blocked = _redis_endpoint_host_is_local(host, port)
    if resolution_cache is not None:
        resolution_cache[cache_key] = blocked
    return blocked


def _refuse_redis(address: object) -> None:
    raise ConnectionRefusedError(
        errno.ECONNREFUSED,
        'hermetic unit tests cannot reach the local Redis rate limiter',
    )


_REDIS_REFUSED_ERRNO = errno.ECONNREFUSED


@contextmanager
def block_local_redis() -> Iterator[None]:
    """Make the configured Redis endpoint unreachable, loopback included.

    ``block_outbound_network`` deliberately allows loopback, so on a machine
    that runs Redis locally the "hermetic" unit tree silently talks to it:
    rate-limited routes consume real ``rl:*`` quota for fixed test uids that
    persists for the policy window across runs, processes, and sibling lanes,
    which surfaces as shifting 429s that CI can never reproduce (CI has no
    Redis, so the limiter fails open there).

    The block raises ``ConnectionRefusedError`` — an ``OSError`` with
    ``ECONNREFUSED``, byte-for-byte what a closed port yields — so redis-py
    maps it to ``redis.ConnectionError`` and every fail-open path behaves
    exactly as it already does on CI. The refused endpoint is the configured
    port on the configured host after resolution, so a ``REDIS_DB_HOST`` alias
    (or any hostname) that resolves to loopback cannot sidestep the literal
    address check. A test that hosts its own fake Redis listener and needs
    the socket I/O to happen can set ``OMI_HERMETIC_ALLOW_FAKE_REDIS`` for
    its own duration.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    # Hostname classification resolves DNS; cache per endpoint so repeated
    # connects (redis-py retries) pay for resolution at most once.
    resolution_cache: dict = {}

    def redis_guarded_connect(sock: socket.socket, address: object):
        if not _is_unix_socket(sock) and _is_blocked_redis_endpoint(address, resolution_cache):
            _refuse_redis(address)
        return original_connect(sock, address)

    def redis_guarded_connect_ex(sock: socket.socket, address: object):
        # ``connect_ex`` reports failures as the errno instead of raising;
        # keep that contract so probing callers see a genuine refusal.
        if not _is_unix_socket(sock) and _is_blocked_redis_endpoint(address, resolution_cache):
            return _REDIS_REFUSED_ERRNO
        return original_connect_ex(sock, address)

    def redis_guarded_create_connection(address: object, *args, **kwargs):
        if _is_blocked_redis_endpoint(address, resolution_cache):
            _refuse_redis(address)
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = redis_guarded_connect
    socket.socket.connect_ex = redis_guarded_connect_ex
    socket.create_connection = redis_guarded_create_connection
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
