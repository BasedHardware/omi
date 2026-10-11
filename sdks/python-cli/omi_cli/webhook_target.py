"""The rules Omi's delivery client applies to a webhook URL.

Mirrors ``backend/utils/http_client.py``. The delivery client refuses a URL
that is not http(s), that does not resolve, or that resolves to any
non-public address, and it never follows a redirect. None of this is visible
from the outside: a webhook on a private address is rejected before any
request leaves the backend, so the endpoint simply never receives an event.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Union
from urllib.parse import urlsplit

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
Resolver = Callable[[str], Sequence[str]]

READ_TIMEOUT_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 2.0

# Carrier-grade NAT, which is also where Tailscale hands out addresses.
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


@dataclass(frozen=True)
class TargetReport:
    """Whether Omi's delivery client would accept this URL at all."""

    ok: bool
    summary: str
    detail: Optional[str] = None


def is_public_address(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NETWORK:
        return False
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def resolve_addresses(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def inspect_target(url: str, resolver: Optional[Resolver] = None) -> TargetReport:
    resolve = resolver or resolve_addresses
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return TargetReport(
            False,
            f"Omi refuses the scheme {parts.scheme or '(none)'}",
            "Only http and https are delivered.",
        )
    host = parts.hostname
    if not host:
        return TargetReport(False, "The URL has no hostname")

    try:
        resolved = resolve(host)
    except socket.gaierror as exc:
        return TargetReport(False, f"Omi cannot resolve {host}", str(exc))

    addresses: list[IPAddress] = []
    for candidate in resolved:
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            # The backend parses every answer the same way and rejects the URL
            # when one of them raises, so an unreadable address is a failure
            # here too rather than an answer to skip.
            return TargetReport(False, f"{host} resolves to an address Omi cannot read: {candidate}")
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        return TargetReport(False, f"Omi cannot resolve {host}", "No addresses returned.")

    private = [str(ip) for ip in addresses if not is_public_address(ip)]
    if private:
        return TargetReport(
            False,
            f"{host} resolves to a non-public address: {', '.join(private)}",
            "Omi rejects the delivery before sending anything, so this endpoint never receives an event in "
            "production. Deploy it or expose it through a tunnel.",
        )

    detail = None if parts.scheme == "https" else "Omi delivers over http too, but the payload is unencrypted."
    return TargetReport(True, f"{host} resolves to {', '.join(str(ip) for ip in addresses)}", detail)
