"""
Tools for fetching content from specific URLs.
"""

import re
import logging
from html.parser import HTMLParser
from langchain_core.tools import tool
from utils.http_client import get_webhook_client
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_SKIP_TAGS = {'script', 'style', 'noscript', 'head', 'meta', 'link', 'svg', 'iframe', 'nav', 'footer'}
_MAX_CONTENT_CHARS = 8000


_BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br', 'tr', 'blockquote', 'section', 'article'}


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
    logger.info(f"fetch_url_tool called - url: {url}")

    if not url.startswith(('http://', 'https://')):
        return "Error: URL must start with http:// or https://"

    try:
        client = get_webhook_client()
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Omi-AI-Bot/1.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = await client.get(url, headers=headers, timeout=15.0, follow_redirects=True)

        if response.status_code != 200:
            logger.warning(f"fetch_url_tool - HTTP {response.status_code} for {url}")
            return f"Error: Could not fetch page (HTTP {response.status_code})"

        content_type = response.headers.get('content-type', '')
        if 'text/html' in content_type or 'text/plain' in content_type or not content_type:
            text = _html_to_text(response.text)
        else:
            return f"Error: Unsupported content type '{content_type}'. Only HTML and plain text pages can be read."

        if not text:
            return "Error: Page appears to be empty or has no readable text content."

        if len(text) > _MAX_CONTENT_CHARS:
            text = text[:_MAX_CONTENT_CHARS] + f'\n\n[Content truncated — {len(text)} total characters]'

        logger.info(f"fetch_url_tool - fetched {len(text)} chars from {url}")
        return f"Content from {url}:\n\n{text}"

    except Exception as e:
        logger.error(f"fetch_url_tool - error fetching {url}: {sanitize(str(e))}")
        return f"Error: Failed to fetch the URL. {sanitize(str(e))}"
