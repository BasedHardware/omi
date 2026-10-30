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
    # ``::ffff:100.64.0.1`` and ``100.64.0.1`` name one destination, and
    # getaddrinfo returns either form depending on the host's resolver. Python's
    # own categories read through to the embedded address, but CGNAT is not one
    # of them, so classify the mapped address rather than the form it arrived in
    # — otherwise the rule below only sees half the addresses it is written for.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NETWORK:
        return False
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def _format_address(ip: IPAddress) -> str:
    # str() of an IPv4-mapped address depends on the Python release: newer ones
    # print ::ffff:100.64.0.1, older ones (3.12.10, the newest 3.12 with Windows
    # installers, is one) print ::ffff:6440:1. Spell the mapped form out so the
    # report names the address the same way on every Python.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        text = f"::ffff:{ip.ipv4_mapped}"
        return f"{text}%{ip.scope_id}" if ip.scope_id else text
    return str(ip)


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

    private = [_format_address(ip) for ip in addresses if not is_public_address(ip)]
    if private:
        return TargetReport(
            False,
            f"{host} resolves to a non-public address: {', '.join(private)}",
            "Omi rejects the delivery before sending anything, so this endpoint never receives an event in "
            "production. Deploy it or expose it through a tunnel.",
        )

    detail = None if parts.scheme == "https" else "Omi delivers over http too, but the payload is unencrypted."
    return TargetReport(True, f"{host} resolves to {', '.join(_format_address(ip) for ip in addresses)}", detail)
