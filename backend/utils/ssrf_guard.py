"""Shared SSRF guard: reject URLs that resolve to private/reserved IP ranges.

Originally lived only in utils/retrieval/tools/web_tools.py (guarding the LLM agent's
fetch_url_tool). Extracted here so any server-side outbound fetch of a user-supplied URL
(agent tool calls, developer webhook delivery, OAuth setup_completed_url callbacks, ...)
can reuse the same check instead of re-implementing it inconsistently.
"""

import asyncio
import ipaddress

# RFC-1918, loopback, link-local (incl. cloud metadata), carrier-grade NAT, IPv6 private
PRIVATE_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('100.64.0.0/10'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fe80::/10'),
    ipaddress.ip_network('fc00::/7'),
]


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> treat as blocked

    # Unwrap IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1, which ipaddress parses as
    # the IPv6 address ::ffff:7f00:1) to the IPv4 address they represent before
    # classifying. Without this, a mapped loopback/private address is a valid IPv6
    # literal that matches none of PRIVATE_NETWORKS' IPv4 entries and isn't covered by
    # the IPv6 entries either - a real bypass for the private-IP check below.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if any(ip in net for net in PRIVATE_NETWORKS):
        return True

    # Backstop via Python's own classification, which covers ranges PRIVATE_NETWORKS
    # doesn't explicitly enumerate (multicast, IANA "reserved", unspecified 0.0.0.0/::).
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


async def hostname_is_public(hostname: str) -> bool:
    """Resolve hostname and return True only if every IP is a public address."""
    try:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(hostname, None)
        if not results:
            return False
        return not any(is_private_ip(r[4][0]) for r in results)
    except Exception:
        return False
