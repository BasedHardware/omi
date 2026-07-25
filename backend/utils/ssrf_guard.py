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
        return any(ip in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return True  # unparseable -> treat as blocked


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
