"""Unit tests for desktop_chat router exception detail masking.

Verifies that ValueError and RuntimeError raised in the desktop_chat
endpoint handlers are sanitized and do not leak internal details.
"""

from unittest.mock import MagicMock
from fastapi import HTTPException
import pytest

import routers.desktop_chat as dc_routes


@pytest.mark.asyncio
async def test_jit_header_value_error_is_masked(monkeypatch):
    """ValueError from _jit_headers_for_forward must not leak in HTTP 400 detail."""
    leak_text = "jit_max_spend_micro_usd must be positive integer; got: -99 (caller=desktop_chat)"

    def _raiser(*args, **kwargs):
        raise ValueError(leak_text)

    monkeypatch.setattr(dc_routes, "_jit_headers_for_forward", _raiser)

    with pytest.raises(HTTPException) as exc_info:
        await dc_routes._chat_completions_unobserved(
            body={"model": "gpt-4"},
            uid="test-user-001",
            x_omi_chat_contract_version="1",
            x_omi_jit_contract_version="1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid request parameters."
    assert leak_text not in exc_info.value.detail
    assert "jit_max_spend" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_quota_runtime_error_is_masked(monkeypatch):
    """RuntimeError in the request preparation path must return static 503 without internal details."""
    leak_text = "upstream redis cluster connection refused host=prod-cache-01:6379"

    monkeypatch.setattr(dc_routes, "llm_stub_enabled", lambda: False)
    monkeypatch.setattr(
        dc_routes,
        "enforce_desktop_chat_quota",
        MagicMock(side_effect=RuntimeError(leak_text)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dc_routes._chat_completions_unobserved(
            body={"model": "gpt-4"},
            uid="test-user-002",
            x_omi_chat_contract_version="1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Service temporarily unavailable. Please try again."
    assert "prod-cache-01" not in exc_info.value.detail
    assert "6379" not in exc_info.value.detail
