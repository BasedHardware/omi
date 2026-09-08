"""Regression coverage for collection-time network blocking."""

import socket

from testing.hermetic_network import BlockedNetworkError

COLLECTION_TIME_DNS_ERROR = None

try:
    socket.getaddrinfo('example.com', 443)
except BlockedNetworkError as exc:
    COLLECTION_TIME_DNS_ERROR = exc


def test_collection_time_dns_resolution_is_blocked():
    assert isinstance(COLLECTION_TIME_DNS_ERROR, BlockedNetworkError)


def test_collection_time_guard_still_allows_localhost_dns():
    assert socket.getaddrinfo('localhost', 80)
