"""Low-level network guard for hermetic test runs."""

from __future__ import annotations

from contextlib import contextmanager
import ipaddress
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
