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


METADATA_ENDPOINT = ('169.254.169.254', 80)
METADATA_NAME_ENDPOINT = ('metadata.google.internal', 80)  # google-auth connects by hostname
METADATA_NAMES = frozenset({'metadata.google.internal', '169.254.169.254'})
POSTGRES_PORT = 5432


def _cloudsql_iam_host() -> str | None:
    """PG host of the staging conformance job, or None unless ``OMI_TEST_POSTGRES_IAM=host,db,user`` is set.

    This env var is the explicit knob (like ``OMI_HERMETIC_ALLOW_FAKE_REDIS``): an unset or malformed value
    adds no allowance. The IAM connector needs exactly two things, the GCE metadata server for its token and
    the private-IP Cloud SQL instance.
    """
    parts = [part.strip() for part in os.getenv('OMI_TEST_POSTGRES_IAM', '').split(',')]
    return parts[0] if len(parts) == 3 and all(parts) else None


def _allowed_endpoint(address: object) -> bool:
    host = _cloudsql_iam_host()
    if host is None or not isinstance(address, tuple) or len(address) < 2:
        return False
    return (address[0], address[1]) in {METADATA_ENDPOINT, METADATA_NAME_ENDPOINT, (host, POSTGRES_PORT)}


def _allowed_dns(name: object) -> bool:
    host = _cloudsql_iam_host()
    return host is not None and isinstance(name, str) and name in (METADATA_NAMES | {host})


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
        if (
            not _is_unix_socket(sock)
            and not is_local_address(_host_from_address(address))
            and not _allowed_endpoint(address)
        ):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object):
        if (
            not _is_unix_socket(sock)
            and not is_local_address(_host_from_address(address))
            and not _allowed_endpoint(address)
        ):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args, **kwargs):
        if not is_local_address(_host_from_address(address)) and not _allowed_endpoint(address):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host: object, *args, **kwargs):
        if not is_local_address(host) and not _allowed_dns(host):
            raise BlockedNetworkError(f'Blocked DNS resolution for {host!r}')
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host: object):
        if not is_local_address(host) and not _allowed_dns(host):
            raise BlockedNetworkError(f'Blocked DNS resolution for {host!r}')
        return original_gethostbyname(host)

    def guarded_gethostbyname_ex(host: object):
        if not is_local_address(host) and not _allowed_dns(host):
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


# Read with plain file I/O (never the resolver) so the Redis guard can
# classify hosts-file names offline; tests monkeypatch this attribute to
# point at a fixture hosts file.
_HOSTS_FILE_PATH = '/etc/hosts'

_HOSTS_LOOPBACK_NAMES_KEY = 'hosts_loopback_names'


def _read_hosts_file_loopback_names(path: str) -> frozenset[str]:
    """Names the hosts file maps to a loopback address, or an empty set.

    Plain file I/O only — the hermetic Redis guard must answer offline, so
    no resolver and no subprocess. An unreadable or malformed file simply
    contributes no names; those endpoints then flow to the outbound guard.
    """
    loopback_names: set[str] = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as hosts_file:
            for raw_line in hosts_file:
                fields = raw_line.split('#', 1)[0].split()
                if not fields:
                    continue
                try:
                    address = ipaddress.ip_address(fields[0])
                except ValueError:
                    continue
                if not address.is_loopback:
                    continue
                for name in fields[1:]:
                    normalized = name.rstrip('.').lower()
                    if normalized:
                        loopback_names.add(normalized)
    except OSError:
        pass
    return frozenset(loopback_names)


def _hosts_file_loopback_names(classification_cache: dict | None) -> frozenset[str]:
    if classification_cache is None:
        return _read_hosts_file_loopback_names(_HOSTS_FILE_PATH)
    names = classification_cache.get(_HOSTS_LOOPBACK_NAMES_KEY)
    if names is None:
        names = _read_hosts_file_loopback_names(_HOSTS_FILE_PATH)
        classification_cache[_HOSTS_LOOPBACK_NAMES_KEY] = names
    return names


def _redis_endpoint_host_is_local(host: object, classification_cache: dict | None = None) -> bool:
    """True when ``host`` is provably machine-local without any DNS lookup.

    Local means a literal loopback IP (v4 or v6), a ``localhost`` name in
    any case — including the ``localhost.`` and ``*.localhost`` forms — or
    a name the hosts file maps to a loopback address. Anything else is not
    classified here: the guard must never resolve DNS itself, or a unit
    session configured with a remote ``REDIS_DB_HOST`` would turn the
    guard into a real DNS client from inside the hermetic boundary. The
    chained outbound guard already blocks non-local endpoints, so a
    non-local hostname simply flows through untouched.
    """
    if isinstance(host, bytes):
        try:
            host = host.decode('idna')
        except UnicodeError:
            return False
    if not isinstance(host, str):
        return False
    hostname = host.strip().strip('[]').lower().rstrip('.')
    if hostname == '':
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return address.is_loopback
    if hostname == 'localhost' or hostname.endswith('.localhost'):
        return True
    return hostname in _hosts_file_loopback_names(classification_cache)


def _is_blocked_redis_endpoint(address: object, classification_cache: dict | None = None) -> bool:
    """True for the ``database.redis_db`` endpoint when its host is machine-local.

    ``_redis_connection_kwargs`` falls back to redis-py's ``localhost`` default
    when ``REDIS_DB_HOST`` is unset, so the endpoint a unit test would reach is
    the configured port on the configured host. The host is classified with a
    strictly offline check — loopback literal, ``localhost`` name form, or a
    hosts-file mapping to loopback — because this guard must never emit DNS
    queries itself; any other hostname is left to the outbound guard, which
    already blocks non-local network. Tests that deliberately host their own
    fake Redis listener (real socket I/O against a stub peer) set
    ``OMI_HERMETIC_ALLOW_FAKE_REDIS`` to keep that endpoint reachable.
    """
    if _fake_redis_endpoint_allowed():
        return False
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host, port = address[0], address[1]
    if port != _configured_redis_port():
        return False
    cache_key = (host, port)
    if classification_cache is not None and cache_key in classification_cache:
        return classification_cache[cache_key]
    blocked = _redis_endpoint_host_is_local(host, classification_cache)
    if classification_cache is not None:
        classification_cache[cache_key] = blocked
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
    port on the configured host, classified strictly offline (loopback
    literal, ``localhost`` name form, or hosts-file mapping to loopback): the
    guard never resolves DNS, so a remote-looking ``REDIS_DB_HOST`` is simply
    not classified here and the chained outbound guard blocks it. A test
    that hosts its own fake Redis listener and needs the socket I/O to
    happen can set ``OMI_HERMETIC_ALLOW_FAKE_REDIS`` for its own duration.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    # Offline classification reads the hosts file at most once and caches
    # per-endpoint verdicts, so repeated connects (redis-py retries)
    # recheck nothing.
    classification_cache: dict = {}

    def redis_guarded_connect(sock: socket.socket, address: object):
        if not _is_unix_socket(sock) and _is_blocked_redis_endpoint(address, classification_cache):
            _refuse_redis(address)
        return original_connect(sock, address)

    def redis_guarded_connect_ex(sock: socket.socket, address: object):
        # ``connect_ex`` reports failures as the errno instead of raising;
        # keep that contract so probing callers see a genuine refusal.
        if not _is_unix_socket(sock) and _is_blocked_redis_endpoint(address, classification_cache):
            return _REDIS_REFUSED_ERRNO
        return original_connect_ex(sock, address)

    def redis_guarded_create_connection(address: object, *args, **kwargs):
        if _is_blocked_redis_endpoint(address, classification_cache):
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
