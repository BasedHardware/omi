"""Tests verifying web_tools URL validation, HTML parsing, SSRF guard, and schema.org extraction.

Ensures that empty or None URLs are rejected gracefully without raising AttributeError,
HTML void tags (<meta>, <link>) do not break body text extraction, HTML entities are unescaped,
JSON-LD @graph structures are unpacked, and SSRF/HTTP errors are handled safely.
"""

from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _web_tools_module():
    """Load web_tools with temporary stub dependencies."""
    langchain_tools = ModuleType("langchain_core.tools")
    langchain_tools.tool = _tool_decorator

    model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
    log_sanitizer = load_module_fresh("utils.log_sanitizer", str(BACKEND_DIR / "utils" / "log_sanitizer.py"))

    http_client = ModuleType("utils.http_client")
    http_client.get_web_fetch_client = MagicMock()

    stubs = {
        "langchain_core": ModuleType("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "utils.http_client": http_client,
        "utils.model_text": model_text,
        "utils.log_sanitizer": log_sanitizer,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools.web_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "web_tools.py"),
        )
        globals()["wt"] = module
        yield
        globals().pop("wt", None)


@pytest.mark.asyncio
async def test_empty_and_none_url_rejection():
    res1 = await wt.fetch_url_tool.func("")
    assert res1 == "Error: URL cannot be empty."

    res2 = await wt.fetch_url_tool.func("   ")
    assert res2 == "Error: URL cannot be empty."

    res3 = await wt.fetch_url_tool.func(None)
    assert res3 == "Error: URL cannot be empty."


@pytest.mark.asyncio
async def test_invalid_scheme_rejection():
    res1 = await wt.fetch_url_tool.func("ftp://example.com")
    assert res1 == "Error: URL must start with http:// or https://"

    res2 = await wt.fetch_url_tool.func("file:///etc/passwd")
    assert res2 == "Error: URL must start with http:// or https://"

    res3 = await wt.fetch_url_tool.func("javascript:alert(1)")
    assert res3 == "Error: URL must start with http:// or https://"


def test_private_ip_detection():
    assert wt._is_private_ip("127.0.0.1") is True
    assert wt._is_private_ip("10.0.0.1") is True
    assert wt._is_private_ip("172.16.0.1") is True
    assert wt._is_private_ip("192.168.1.1") is True
    assert wt._is_private_ip("169.254.169.254") is True
    assert wt._is_private_ip("8.8.8.8") is False
    assert wt._is_private_ip("1.1.1.1") is False
    assert wt._is_private_ip("invalid") is True


def test_html_meta_and_entity_unescaping():
    html_sample = (
        "<html><head>"
        "<title>Tom &amp; Jerry &quot;Show&quot;</title>"
        '<meta name="description" content="Catch the cat &amp; mouse &#39;fun&#39;!">'
        "</head><body><p>Episode 1 text.</p></body></html>"
    )
    extracted = wt._html_to_text(html_sample)
    assert 'Tom & Jerry "Show"' in extracted
    assert "Catch the cat & mouse 'fun'!" in extracted
    assert "Episode 1 text." in extracted


def test_html_parser_void_tag_depth_safety():
    html_doc = (
        "<html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="stylesheet" href="style.css">'
        "</head><body>"
        "<h1>Main Title</h1>"
        "<p>First paragraph content.</p>"
        "</body></html>"
    )
    extracted = wt._html_to_text(html_doc)
    assert "Main Title" in extracted
    assert "First paragraph content." in extracted


def test_json_ld_graph_unpacking():
    graph_json_ld = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context": "https://schema.org", "@graph": ['
        '  {"@type": "NewsArticle", "headline": "Major AI Breakthrough &amp; Update", "author": {"name": "Alice &amp; Bob"}},'
        '  {"@type": "WebSite", "name": "Tech Daily"}'
        "]}"
        "</script>"
        "</head><body><p>Article body content.</p></body></html>"
    )
    extracted = wt._html_to_text(graph_json_ld)
    assert "Headline: Major AI Breakthrough & Update" in extracted
    assert "Author: Alice & Bob" in extracted
    assert "Title: Tech Daily" in extracted
    assert "Article body content." in extracted


@pytest.mark.asyncio
async def test_successful_fetch_url():
    with patch.object(wt, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (
            200,
            "text/html",
            "<html><head><title>Omi Platform</title></head><body><p>AI Wearable</p></body></html>",
        )
        res = await wt.fetch_url_tool.func("https://omi.me")
        assert "Content from https://omi.me:" in res
        assert "Omi Platform" in res
        assert "AI Wearable" in res
        assert wt.UNTRUSTED_LEGEND in res


@pytest.mark.asyncio
async def test_ssrf_blocked_exception():
    with patch.object(wt, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = ValueError("URL resolves to a private or reserved address")
        res = await wt.fetch_url_tool.func("http://169.254.169.254/latest/meta-data/")
        assert "Error: URL resolves to a private or reserved address" in res


@pytest.mark.asyncio
async def test_http_non_200_status():
    with patch.object(wt, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (404, "text/html", "")
        res = await wt.fetch_url_tool.func("https://example.com/not-found")
        assert res == "Error: Could not fetch page (HTTP 404)"


@pytest.mark.asyncio
async def test_unsupported_content_type():
    with patch.object(wt, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (200, "application/pdf", "%PDF-1.4")
        res = await wt.fetch_url_tool.func("https://example.com/document.pdf")
        assert "Unsupported content type 'application/pdf'" in res


@pytest.mark.asyncio
async def test_empty_page_content():
    with patch.object(wt, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (200, "text/html", "")
        res = await wt.fetch_url_tool.func("https://example.com/empty")
        assert res == "Error: Page appears to be empty or too large to read."


def test_html_document_without_head_tag():
    html_no_head = "<html><body><h1>Direct Body Header</h1><p>Body paragraph without head tag.</p></body></html>"
    extracted = wt._html_to_text(html_no_head)
    assert "Direct Body Header" in extracted
    assert "Body paragraph without head tag." in extracted


def test_html_unclosed_head_resets_on_body():
    # A <head> missing its closing </head> tag should have its skip depth reset
    # upon encountering <body>, ensuring body text is not silently dropped.
    html_unclosed_head = "<html><head><title>Page Title</title><body><h1>Visible Main Content</h1><p>Body paragraph.</p></body></html>"
    extracted = wt._html_to_text(html_unclosed_head)
    assert "Page Title" in extracted
    assert "Visible Main Content" in extracted
    assert "Body paragraph." in extracted


def test_html_unclosed_script_preceding_body():
    # Confirms that a genuinely unclosed <script> before <body> is not masked:
    # because HTMLParser treats everything until </script> as script CDATA,
    # script contents are not leaked or extracted as body text.
    html_unclosed_pre_body = (
        "<html><head><script>var analytics = 1; <body>"
        "<h1>Visible Main Content</h1>"
        "<p>This text should be rendered properly.</p>"
        "</body></html>"
    )
    extracted = wt._html_to_text(html_unclosed_pre_body)
    assert "var analytics" not in extracted


def test_html_unclosed_script_inside_body_does_not_mask_skip():
    # Conversely, an unclosed script inside <body> keeps _skip_depth > 0,
    # properly skipping script content and not leaking into extracted body text.
    html_unclosed_in_body = (
        "<html><body>"
        "<h1>First Heading</h1>"
        "<script>console.log('malformed script without close'); <p>Text inside unclosed script</p>"
        "</body></html>"
    )
    extracted = wt._html_to_text(html_unclosed_in_body)
    assert "First Heading" in extracted
    assert "Text inside unclosed script" not in extracted
