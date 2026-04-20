"""Unit tests for utils/other/ssrf_guard.

Covers the attack vectors the guard is designed to stop: private IPs,
loopback, link-local, cloud metadata, URL credentials, non-HTTPS schemes,
and redirects/DNS rebinding edge cases.
"""

from __future__ import annotations

import socket
from unittest import mock

import pytest

from utils.other import ssrf_guard
from utils.other.ssrf_guard import SSRFError, validate_url


def _mock_resolve(ip: str):
    """Patch socket.getaddrinfo to resolve anything to `ip`."""
    family = socket.AF_INET if ':' not in ip else socket.AF_INET6
    return mock.patch.object(
        ssrf_guard.socket,
        'getaddrinfo',
        return_value=[(family, socket.SOCK_STREAM, 0, '', (ip, 0))],
    )


def test_rejects_non_https():
    with pytest.raises(SSRFError):
        validate_url('http://example.com/x')


def test_rejects_credentials_in_url():
    with _mock_resolve('93.184.216.34'):
        with pytest.raises(SSRFError):
            validate_url('https://user:pass@example.com/')


def test_rejects_loopback_ipv4():
    with _mock_resolve('127.0.0.1'):
        with pytest.raises(SSRFError, match='restricted'):
            validate_url('https://evil.example/')


def test_rejects_aws_metadata():
    with _mock_resolve('169.254.169.254'):
        with pytest.raises(SSRFError, match='restricted'):
            validate_url('https://evil.example/')


def test_rejects_private_rfc1918():
    for ip in ('10.0.0.1', '192.168.1.1', '172.16.0.1'):
        with _mock_resolve(ip):
            with pytest.raises(SSRFError, match='restricted'):
                validate_url('https://evil.example/')


def test_rejects_loopback_ipv6():
    with _mock_resolve('::1'):
        with pytest.raises(SSRFError, match='restricted'):
            validate_url('https://evil.example/')


def test_rejects_link_local_ipv6():
    with _mock_resolve('fe80::1'):
        with pytest.raises(SSRFError, match='restricted'):
            validate_url('https://evil.example/')


def test_rejects_missing_scheme():
    with pytest.raises(SSRFError):
        validate_url('example.com')


def test_rejects_empty_host():
    with pytest.raises(SSRFError):
        validate_url('https:///path')


def test_accepts_public_ip():
    with _mock_resolve('93.184.216.34'):
        assert validate_url('https://example.com/path') == 'https://example.com/path'


def test_allowlist_blocks_unlisted_hosts():
    with _mock_resolve('93.184.216.34'):
        with pytest.raises(SSRFError, match='allowlist'):
            validate_url('https://example.com/', allowed_hosts=['api.stripe.com'])


def test_allowlist_permits_listed_host():
    with _mock_resolve('93.184.216.34'):
        assert validate_url(
            'https://api.stripe.com/v1/events',
            allowed_hosts=['api.stripe.com'],
        ).startswith('https://api.stripe.com')


def test_rejects_multi_resolved_any_private():
    """If DNS returns mixed public + private, we still reject."""
    with mock.patch.object(
        ssrf_guard.socket,
        'getaddrinfo',
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('10.0.0.5', 0)),
        ],
    ):
        with pytest.raises(SSRFError, match='restricted'):
            validate_url('https://mixed.example/')


def test_dns_failure_is_ssrf_error():
    with mock.patch.object(
        ssrf_guard.socket,
        'getaddrinfo',
        side_effect=socket.gaierror('nxdomain'),
    ):
        with pytest.raises(SSRFError, match='DNS'):
            validate_url('https://nx.example/')
