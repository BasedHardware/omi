"""Tests for the SSRF guard in utils.http_client: assert_public_http_url,
pin_to_resolved_ip, and safe_request_target.

Covers the post-disclosure hardening of app-developer-configured webhook /
setup_completed_url targets (app_integrations.py, routers/oauth.py):

- assert_public_http_url rejects loopback/private/link-local/reserved hosts
  and non-http(s) schemes, accepts ordinary public http/https targets, and
  inspects EVERY address a hostname resolves to (not just the first) so a
  multi-address DNS answer can't sneak an unsafe address past the check.
- pin_to_resolved_ip / safe_request_target close the DNS-rebinding gap: the
  validated IP is what the caller must actually connect to, with the
  original hostname preserved for the Host header and TLS SNI/cert check.

DNS is always mocked (via utils.http_client.socket.getaddrinfo) so these
tests are deterministic and make no real network calls.
"""

import asyncio
import socket

import httpx
import pytest

from utils.http_client import (
    UnsafeWebhookURLError,
    assert_public_http_url,
    get_pinned_http_url_once,
    pin_to_resolved_ip,
    safe_request_target,
)

# Real, unambiguously-public resolvers. NOT the TEST-NET documentation ranges
# (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) -- Python's ipaddress module
# actually flags those as `is_private`, so they'd be rejected and give a
# false sense of "testing the public case".
PUBLIC_IP_A = '8.8.8.8'
PUBLIC_IP_B = '1.1.1.1'


def _addrinfo(*ips: str) -> list[tuple]:
    """Build a fake socket.getaddrinfo() return value for the given IPv4 literals."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


def _mock_resolve(monkeypatch, *ips: str):
    monkeypatch.setattr('utils.http_client.socket.getaddrinfo', lambda host, port: _addrinfo(*ips))


def _mock_resolve_failure(monkeypatch):
    def _raise(host, port):
        raise socket.gaierror('Name or service not known')

    monkeypatch.setattr('utils.http_client.socket.getaddrinfo', _raise)


# ---------------------------------------------------------------------------
# Scheme / hostname validation (no DNS involved)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('scheme_url', ['ftp://example.com/x', 'file:///etc/passwd', 'gopher://example.com'])
def test_rejects_non_http_schemes(scheme_url):
    with pytest.raises(UnsafeWebhookURLError, match='Unsupported URL scheme'):
        assert_public_http_url(scheme_url)


def test_rejects_url_with_no_hostname():
    with pytest.raises(UnsafeWebhookURLError, match='no hostname'):
        assert_public_http_url('http:///just-a-path')


@pytest.mark.parametrize(
    'credential_url',
    [
        'https://user@example.com/private',
        'https://user:password@example.com/private',
        'https://user%40tenant@example.com/private',
    ],
)
def test_rejects_credential_bearing_urls_before_dns(monkeypatch, credential_url):
    monkeypatch.setattr(
        'utils.http_client.socket.getaddrinfo',
        lambda *_args: (_ for _ in ()).throw(AssertionError('credential URLs must not resolve')),
    )
    with pytest.raises(UnsafeWebhookURLError, match='must not contain credentials'):
        assert_public_http_url(credential_url)


@pytest.mark.parametrize(
    'malformed_url',
    [
        'https://example.com:not-a-port/path',
        'https://example.com:70000/path',
        'https://[2001:db8::1/path',
        'https://2001:db8::1]/path',
    ],
)
def test_malformed_port_or_ipv6_is_an_unsafe_url_error(monkeypatch, malformed_url):
    monkeypatch.setattr(
        'utils.http_client.socket.getaddrinfo',
        lambda *_args: (_ for _ in ()).throw(AssertionError('malformed URLs must not resolve')),
    )
    with pytest.raises(UnsafeWebhookURLError, match='Malformed URL authority'):
        assert_public_http_url(malformed_url)


def test_rejects_when_dns_resolution_fails(monkeypatch):
    _mock_resolve_failure(monkeypatch)
    with pytest.raises(UnsafeWebhookURLError, match='Could not resolve host'):
        assert_public_http_url('https://nonexistent.example.invalid/webhook')


def test_rejects_when_getaddrinfo_returns_no_addresses(monkeypatch):
    monkeypatch.setattr('utils.http_client.socket.getaddrinfo', lambda host, port: [])
    with pytest.raises(UnsafeWebhookURLError, match='no addresses returned'):
        assert_public_http_url('https://example.com/webhook')


# ---------------------------------------------------------------------------
# Rejects loopback / private / link-local / reserved
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'unsafe_ip,label',
    [
        ('127.0.0.1', 'loopback'),
        ('10.1.2.3', 'RFC1918 private (10/8)'),
        ('172.16.0.5', 'RFC1918 private (172.16/12)'),
        ('192.168.1.1', 'RFC1918 private (192.168/16)'),
        ('169.254.169.254', 'link-local / cloud metadata'),
        # 100.64.0.0/10 is RFC 6598 carrier-grade NAT shared address space.
        # Python's ipaddress flags NEITHER is_private NOR is_reserved for it,
        # so an explicit guard is required -- without it this address was
        # wrongly accepted as "public".
        ('100.64.0.1', 'CGNAT/RFC6598 (100.64/10) -- not flagged by ipaddress'),
        ('100.127.255.254', 'CGNAT/RFC6598 upper boundary'),
        ('224.0.0.1', 'multicast'),
        ('240.0.0.1', 'reserved'),
        ('0.0.0.0', 'unspecified'),
    ],
)
def test_rejects_non_public_addresses(monkeypatch, unsafe_ip, label):
    _mock_resolve(monkeypatch, unsafe_ip)
    with pytest.raises(UnsafeWebhookURLError, match='non-public address'):
        assert_public_http_url('https://webhook.example.com/callback')


# ---------------------------------------------------------------------------
# Accepts ordinary public targets
# ---------------------------------------------------------------------------


def test_accepts_ordinary_public_https_url(monkeypatch):
    _mock_resolve(monkeypatch, PUBLIC_IP_A)
    resolved = assert_public_http_url('https://webhook.example.com/callback?x=1')
    assert resolved == PUBLIC_IP_A


def test_accepts_ordinary_public_http_url(monkeypatch):
    _mock_resolve(monkeypatch, PUBLIC_IP_A)
    resolved = assert_public_http_url('http://webhook.example.com/callback')
    assert resolved == PUBLIC_IP_A


def test_accepts_addresses_just_outside_the_cgnat_range(monkeypatch):
    # 100.64.0.0/10 spans 100.64.0.0 - 100.127.255.255. Addresses immediately
    # below and above are globally routable and must remain accepted -- this
    # pins the boundary so the CGNAT guard can't accidentally widen.
    _mock_resolve(monkeypatch, '100.63.255.255')
    assert assert_public_http_url('https://edge-low.example.com/hook') == '100.63.255.255'
    _mock_resolve(monkeypatch, '100.128.0.0')
    assert assert_public_http_url('https://edge-high.example.com/hook') == '100.128.0.0'


# ---------------------------------------------------------------------------
# Multi-address DNS results
# ---------------------------------------------------------------------------


def test_multi_address_all_public_returns_first(monkeypatch):
    _mock_resolve(monkeypatch, PUBLIC_IP_A, PUBLIC_IP_B)
    resolved = assert_public_http_url('https://round-robin.example.com/hook')
    assert resolved == PUBLIC_IP_A


def test_multi_address_rejects_if_any_address_is_unsafe(monkeypatch):
    # First address looks fine; second is the cloud metadata address. A check
    # that only looked at the first result would miss this.
    _mock_resolve(monkeypatch, PUBLIC_IP_A, '169.254.169.254')
    with pytest.raises(UnsafeWebhookURLError, match='non-public address'):
        assert_public_http_url('https://sneaky.example.com/hook')


def test_multi_address_rejects_if_first_address_is_unsafe(monkeypatch):
    # Same idea, opposite order -- the loop must not stop at the first safe
    # hit either; it has to check every returned address.
    _mock_resolve(monkeypatch, '169.254.169.254', PUBLIC_IP_A)
    with pytest.raises(UnsafeWebhookURLError, match='non-public address'):
        assert_public_http_url('https://sneaky.example.com/hook')


# ---------------------------------------------------------------------------
# pin_to_resolved_ip: URL rewriting for the DNS-rebinding fix
# ---------------------------------------------------------------------------


def test_pin_ipv4_preserves_path_and_query():
    pinned_url, extra = pin_to_resolved_ip('https://example.com/webhook?uid=abc', '203.0.113.5')
    assert pinned_url == 'https://203.0.113.5/webhook?uid=abc'
    assert extra == {'headers': {'Host': 'example.com'}, 'extensions': {'sni_hostname': 'example.com'}}


def test_pin_ipv6_brackets_host_and_preserves_port():
    pinned_url, extra = pin_to_resolved_ip('http://example.com:8080/x', '2001:db8::1')
    assert pinned_url == 'http://[2001:db8::1]:8080/x'
    assert extra['headers']['Host'] == 'example.com:8080'
    assert extra['extensions']['sni_hostname'] == 'example.com'


def test_pin_host_header_omits_default_port_and_brackets_ipv6_origin():
    _, default_extra = pin_to_resolved_ip('https://example.com:443/x', PUBLIC_IP_A)
    assert default_extra['headers']['Host'] == 'example.com'

    pinned_url, ipv6_extra = pin_to_resolved_ip('https://[2606:4700:4700::1111]:8443/x', PUBLIC_IP_A)
    assert pinned_url == f'https://{PUBLIC_IP_A}:8443/x'
    assert ipv6_extra['headers']['Host'] == '[2606:4700:4700::1111]:8443'
    assert ipv6_extra['extensions']['sni_hostname'] == '2606:4700:4700::1111'


# ---------------------------------------------------------------------------
# safe_request_target: validate + pin in one call (what production code uses)
# ---------------------------------------------------------------------------


def test_safe_request_target_pins_to_the_validated_address(monkeypatch):
    _mock_resolve(monkeypatch, PUBLIC_IP_A)
    pinned_url, extra = safe_request_target('https://webhook.example.com/callback?uid=1')
    assert pinned_url == f'https://{PUBLIC_IP_A}/callback?uid=1'
    assert extra['headers']['Host'] == 'webhook.example.com'
    assert extra['extensions']['sni_hostname'] == 'webhook.example.com'


def test_safe_request_target_raises_for_unsafe_target_without_pinning(monkeypatch):
    _mock_resolve(monkeypatch, '10.0.0.5')
    with pytest.raises(UnsafeWebhookURLError):
        safe_request_target('https://internal.example.com/callback')


def test_same_ip_different_hosts_use_distinct_one_shot_clients(monkeypatch):
    clients = []

    class _Client:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.calls = []
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return object()

    monkeypatch.setattr('utils.http_client.httpx.AsyncClient', _Client)
    first_url, first_pin = pin_to_resolved_ip('https://alpha.example.test/setup', PUBLIC_IP_A)
    second_url, second_pin = pin_to_resolved_ip('https://beta.example.test/setup', PUBLIC_IP_A)

    async def exercise():
        timeout = httpx.Timeout(10.0, connect=2.0)
        await get_pinned_http_url_once(first_url, first_pin, timeout=timeout)
        await get_pinned_http_url_once(second_url, second_pin, timeout=timeout)

    asyncio.run(exercise())

    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert clients[0].init_kwargs['limits'].max_keepalive_connections == 0
    assert clients[1].init_kwargs['limits'].max_keepalive_connections == 0
    assert clients[0].calls[0][1]['headers']['Host'] == 'alpha.example.test'
    assert clients[0].calls[0][1]['extensions']['sni_hostname'] == 'alpha.example.test'
    assert clients[1].calls[0][1]['headers']['Host'] == 'beta.example.test'
    assert clients[1].calls[0][1]['extensions']['sni_hostname'] == 'beta.example.test'
    assert all(client.calls[0][1]['follow_redirects'] is False for client in clients)
