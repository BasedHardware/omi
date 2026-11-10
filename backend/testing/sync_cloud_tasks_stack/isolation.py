"""Process-wide no-egress guard shared by every gauntlet child process.

Install before any backend import can construct a provider or cloud client:
non-loopback DNS and socket connections raise, and Google ADC discovery is
replaced with anonymous credentials for the loopback Firestore emulator.
"""

from __future__ import annotations

import os
import socket
from typing import Any

import google.auth
from google.auth import credentials as google_auth_credentials

LOOPBACK_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost', '0.0.0.0'})
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_SOCKET_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def _network_host(address: Any) -> str | None:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None


def _assert_loopback(address: Any) -> None:
    host = _network_host(address)
    if host is None or host in LOOPBACK_HOSTS:
        return
    raise RuntimeError(f'Sync stack blocked outbound network connection to {host!r}')


def _guarded_connect(sock: socket.socket, address: Any) -> Any:
    _assert_loopback(address)
    return _ORIGINAL_SOCKET_CONNECT(sock, address)


def _guarded_connect_ex(sock: socket.socket, address: Any) -> int:
    _assert_loopback(address)
    return _ORIGINAL_SOCKET_CONNECT_EX(sock, address)


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    _assert_loopback(address)
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if host is not None and str(host) not in LOOPBACK_HOSTS:
        raise RuntimeError(f'Sync stack blocked outbound DNS lookup for {host!r}')
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def _anonymous_google_credentials(
    *_args: Any, **_kwargs: Any
) -> tuple[google_auth_credentials.AnonymousCredentials, str]:
    project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('FIREBASE_PROJECT_ID') or 'demo-omi-sync-stack'
    return google_auth_credentials.AnonymousCredentials(), project


def install_no_egress_guard() -> None:
    """Idempotently block non-loopback traffic and ADC/metadata discovery."""
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.create_connection = _guarded_create_connection
    socket.getaddrinfo = _guarded_getaddrinfo
    # Firestore emulator traffic must never trigger ADC or metadata discovery.
    google.auth.default = _anonymous_google_credentials
