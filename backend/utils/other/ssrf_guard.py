"""SSRF guard for external URL fetches.

Applied to any code path that fetches a URL supplied by a user, app
developer, or third-party integration (webhook_url, setup_completed_url,
oauth redirect, etc.). Without this, attackers can pivot from an app
creator role into the backend VPC: cloud metadata services, Redis on
localhost, internal admin endpoints, etc.

Design:
- Allowlist schemes (https by default; http allowed only in dev).
- Block credentials in URL (user:pass@host).
- Resolve DNS once, reject any address that is private / loopback /
  link-local / reserved / multicast.
- Size cap on response body.
- Short, explicit timeouts.

NOTE: DNS rebinding (public IP on first resolve, private on reconnect)
is not fully mitigated — for strict prod hardening, use an httpx
transport that pins to the resolved IP. Good enough for an OWASP A10
baseline; track a follow-up if the threat model requires more.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, Optional
from urllib.parse import urlparse

import httpx

_ALLOW_HTTP = os.getenv('SSRF_ALLOW_HTTP', '').lower() == 'true'
_DEFAULT_TIMEOUT = float(os.getenv('SSRF_TIMEOUT_SECONDS', '8'))
_MAX_RESPONSE_BYTES = int(os.getenv('SSRF_MAX_RESPONSE_BYTES', str(1 << 20)))  # 1 MiB


class SSRFError(ValueError):
    """Raised when a URL fails SSRF policy."""


def _allowed_schemes() -> set[str]:
    schemes = {'https'}
    if _ALLOW_HTTP:
        schemes.add('http')
    return schemes


def _reject_ip(ip: ipaddress._BaseAddress) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise SSRFError(f"resolved to restricted address: {ip}")


def validate_url(url: str, allowed_hosts: Optional[Iterable[str]] = None) -> str:
    """Validate URL against SSRF policy. Returns the (possibly normalized) URL.

    Raises SSRFError on any policy violation.
    """
    if not url or not isinstance(url, str):
        raise SSRFError("empty or non-string URL")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _allowed_schemes():
        raise SSRFError(f"scheme not allowed: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise SSRFError("URLs with credentials are not allowed")

    host = (parsed.hostname or '').lower()
    if not host:
        raise SSRFError("missing host")

    if allowed_hosts is not None:
        allowed = {h.lower() for h in allowed_hosts}
        if host not in allowed:
            raise SSRFError(f"host not in allowlist: {host}")

    # Resolve and validate every returned address.
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {host}: {e}")

    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        # IPv6 addresses may include a scope id after '%'
        if '%' in ip_str:
            ip_str = ip_str.split('%', 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFError(f"unparseable address: {ip_str}")
        _reject_ip(ip)

    return url


async def safe_get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    allowed_hosts: Optional[Iterable[str]] = None,
    max_bytes: int = _MAX_RESPONSE_BYTES,
) -> httpx.Response:
    """Perform an SSRF-safe GET and return the httpx.Response (caller .json())."""
    validate_url(url, allowed_hosts=allowed_hosts)
    resp = await client.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        follow_redirects=False,  # redirects are a classic SSRF bypass; force explicit
    )
    # Truncate large bodies defensively
    if resp.content is not None and len(resp.content) > max_bytes:
        raise SSRFError(f"response exceeds {max_bytes} bytes")
    return resp


async def safe_post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    allowed_hosts: Optional[Iterable[str]] = None,
    max_bytes: int = _MAX_RESPONSE_BYTES,
) -> httpx.Response:
    """SSRF-safe POST used for user- or app-supplied webhook URLs.

    Same validation contract as safe_get_json, but for POST. Used by the
    user webhook handlers (memory_created, day_summary, realtime_transcript,
    audio_bytes) and the app integration webhooks — any of which could
    otherwise be pointed at internal infra by a malicious URL.
    """
    validate_url(url, allowed_hosts=allowed_hosts)
    resp = await client.post(
        url,
        json=json,
        params=params,
        headers=headers,
        timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        follow_redirects=False,
    )
    if resp.content is not None and len(resp.content) > max_bytes:
        raise SSRFError(f"response exceeds {max_bytes} bytes")
    return resp
