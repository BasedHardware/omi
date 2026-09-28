import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from testing.import_isolation import load_module_fresh

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_fetch_url_tool_sanitizes_unexpected_exception() -> None:
    os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

    web_tools = load_module_fresh(
        "utils.retrieval.tools.web_tools",
        str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "web_tools.py"),
    )

    leak_token = "INTERNAL_POSTGRES_DB_SECRET_KEY_98765"
    with patch.object(web_tools, "_fetch_page", side_effect=RuntimeError(f"Connection failed: {leak_token}")):
        result = asyncio.run(web_tools.fetch_url_tool.ainvoke({"url": "https://example.com/test"}))

    assert result == "Error: Failed to fetch the URL. Please try again later."
    assert leak_token not in result


def test_fetch_url_tool_preserves_expected_validation_errors() -> None:
    os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

    web_tools = load_module_fresh(
        "utils.retrieval.tools.web_tools",
        str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "web_tools.py"),
    )

    # Invalid scheme
    res_scheme = asyncio.run(web_tools.fetch_url_tool.ainvoke({"url": "ftp://example.com"}))
    assert res_scheme == "Error: URL must start with http:// or https://"

    # Private network SSRF rejection
    with patch.object(
        web_tools, "_fetch_page", side_effect=ValueError("URL resolves to a private or reserved address")
    ):
        res_ssrf = asyncio.run(web_tools.fetch_url_tool.ainvoke({"url": "https://192.168.1.1"}))
        assert res_ssrf == "Error: URL resolves to a private or reserved address"
