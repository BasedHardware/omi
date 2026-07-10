import socket

import pytest

from testing.hermetic_network import BlockedNetworkError, is_local_address


def test_localhost_addresses_are_allowed_by_guard():
    assert is_local_address('localhost')
    assert is_local_address('127.0.0.1')
    assert is_local_address('::1')


def test_external_socket_connect_is_blocked():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(BlockedNetworkError):
            sock.connect(('8.8.8.8', 53))
    finally:
        sock.close()


def test_local_socket_connect_does_not_require_af_unix(monkeypatch):
    monkeypatch.delattr(socket, 'AF_UNIX', raising=False)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(('127.0.0.1', 0))
        server.listen(1)

        client.connect(server.getsockname())
    finally:
        client.close()
        server.close()


def test_external_dns_resolution_is_blocked():
    with pytest.raises(BlockedNetworkError):
        socket.getaddrinfo('example.com', 443)


def test_localhost_dns_resolution_is_allowed():
    assert socket.getaddrinfo('localhost', 80)
