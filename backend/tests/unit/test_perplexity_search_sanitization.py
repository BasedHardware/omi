import asyncio
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def test_perplexity_gateway_search_sanitizes_unexpected_exception() -> None:
    fake_client = AsyncMock()
    fake_client.post.side_effect = RuntimeError("INTERNAL_DATABASE_CREDENTIALS_LEAK")

    stubs = {
        "utils.http_client": _module(
            "utils.http_client",
            get_webhook_client=lambda: fake_client,
        ),
        "utils.llm.gateway_client": _module(
            "utils.llm.gateway_client",
            feature_auto_lane_id=lambda _x: "web_search",
            get_llm_gateway_base_url=lambda: "http://fake-gateway",
            llm_gateway_headers=lambda: {},
        ),
        "utils.log_sanitizer": _module(
            "utils.log_sanitizer",
            sanitize=lambda x: str(x),
        ),
    }

    with stub_modules(stubs):
        perplexity_tools = load_module_fresh(
            "utils.retrieval.tools.perplexity_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "perplexity_tools.py"),
        )
        result = asyncio.run(perplexity_tools._perplexity_gateway_search("test query"))

    assert result == "Error: An unexpected error occurred while searching. Please try again later."
    assert "INTERNAL_DATABASE_CREDENTIALS_LEAK" not in result
