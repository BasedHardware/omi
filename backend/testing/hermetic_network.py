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


@contextmanager
def block_outbound_network() -> Iterator[None]:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def guarded_connect(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX and not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX and not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args, **kwargs):
        if not is_local_address(_host_from_address(address)):
            raise BlockedNetworkError(f'Blocked outbound network connection to {address!r}')
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
