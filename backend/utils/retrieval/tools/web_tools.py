"""
Tools for fetching content from specific URLs.
"""

import asyncio
import ipaddress
import re
import logging
from html.parser import HTMLParser
from urllib.parse import urlparse

from langchain_core.tools import tool

from utils.http_client import get_web_fetch_client
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_SKIP_TAGS = {'script', 'style', 'noscript', 'head', 'meta', 'link', 'svg', 'iframe', 'nav', 'footer'}
_BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br', 'tr', 'blockquote', 'section', 'article'}
_MAX_CONTENT_CHARS = 8000
_MAX_BODY_BYTES = 512 * 1024  # cap before HTML parsing
_MAX_REDIRECTS = 5

# RFC-1918, loopback, link-local (incl. cloud metadata), carrier-grade NAT, IPv6 private
_PRIVATE_NETWORKS = [
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

_PARSEABLE_TYPES = ('text/html', 'text/plain', 'application/xhtml+xml', 'application/xml')


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return True  # unparseable → treat as blocked


async def _hostname_is_public(hostname: str) -> bool:
    """Resolve hostname and return True only if every IP is a public address."""
    try:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(hostname, None)
        if not results:
            return False
        return not any(_is_private_ip(r[4][0]) for r in results)
    except Exception:
        return False


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS and self._skip_depth == 0 and self.chunks:
            self.chunks.append('\n')

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.chunks.append(text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = ' '.join(parser.chunks)
    text = re.sub(r' \n ', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def _fetch_page(url: str, headers: dict) -> tuple[int, str, str]:
    """
    Fetch *url* with SSRF guard, manual redirect following, and a body-size cap.
    Returns (status_code, content_type, body_text).
    Raises ValueError on SSRF/redirect violations.
    """
    client = get_web_fetch_client()

    for _ in range(_MAX_REDIRECTS + 1):
        if not url.startswith(('http://', 'https://')):
            raise ValueError('Redirect target must use http:// or https://')

        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        if not hostname:
            raise ValueError('Invalid URL: no hostname')

        if not await _hostname_is_public(hostname):
            raise ValueError('URL resolves to a private or reserved address')

        redirect_url = None
        status = 0
        content_type = ''
        body_text = ''

        async with client.stream('GET', url, headers=headers, follow_redirects=False) as response:
            status = response.status_code
            content_type = response.headers.get('content-type', '')

            if status in (301, 302, 303, 307, 308):
                location = response.headers.get('location', '')
                redirect_url = location
            else:
                cl_header = response.headers.get('content-length')
                if cl_header and int(cl_header) > _MAX_BODY_BYTES:
                    return status, content_type, ''

                chunks = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    total += len(chunk)
                    chunks.append(chunk)
                    if total >= _MAX_BODY_BYTES:
                        break

                body_text = b''.join(chunks).decode('utf-8', errors='replace')

        if redirect_url is not None:
            url = redirect_url
            continue

        return status, content_type, body_text

    raise ValueError('Too many redirects')


@tool
async def fetch_url_tool(url: str) -> str:
    """
    Fetch and read the content of a specific web page URL.

    Use this tool when:
    - The user shares a direct URL and asks you to read, summarize, or analyze it
    - The user says "check this link", "what does this page say", "summarize this article" with a URL
    - You need to read the actual content at a specific web address

    DO NOT use this tool for general web searches — use web_search instead.

    Args:
        url: The full URL to fetch (must start with http:// or https://)

    Returns:
        The readable text content of the page (up to 8000 characters)
    """
    logger.info(f"fetch_url_tool called - url: {sanitize(url)}")

    if not url.startswith(('http://', 'https://')):
        return 'Error: URL must start with http:// or https://'

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Omi-AI-Bot/1.0)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    try:
        status, content_type, body = await _fetch_page(url, headers)
    except ValueError as e:
        logger.warning(f"fetch_url_tool blocked - {sanitize(str(e))}")
        return f'Error: {sanitize(str(e))}'
    except Exception as e:
        logger.error(f"fetch_url_tool - error fetching {sanitize(url)}: {sanitize(str(e))}")
        return f'Error: Failed to fetch the URL. {sanitize(str(e))}'

    if status != 200:
        logger.warning(f"fetch_url_tool - HTTP {status} for {sanitize(url)}")
        return f'Error: Could not fetch page (HTTP {status})'

    if not any(t in content_type for t in _PARSEABLE_TYPES) and content_type:
        return f"Error: Unsupported content type '{content_type}'. Only HTML and plain text pages can be read."

    if not body:
        return 'Error: Page appears to be empty or too large to read.'

    text = _html_to_text(body)
    if not text:
        return 'Error: Page has no readable text content.'

    if len(text) > _MAX_CONTENT_CHARS:
        text = text[:_MAX_CONTENT_CHARS] + f'\n\n[Content truncated — {len(text)} total characters]'

    logger.info(f"fetch_url_tool - fetched {len(text)} chars from {sanitize(url)}")
    return f'Content from {url}:\n\n{text}'
