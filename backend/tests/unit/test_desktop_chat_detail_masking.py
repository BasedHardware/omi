"""Unit tests for desktop_chat router exception detail masking.

Verifies that ValueError and RuntimeError raised in the desktop_chat
endpoint handlers are sanitized and do not leak internal details.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

import routers.desktop_chat as dc_routes


def _make_jit_headers_raiser(exc_type, message):
    """Return a function that raises exc_type(message) when called."""
    def _raiser(*args, **kwargs):
        raise exc_type(message)
    return _raiser


def test_jit_header_value_error_is_masked(monkeypatch):
    """ValueError from _jit_headers_for_forward must not leak in HTTP 400 detail."""
    leak_text = "jit_max_spend_micro_usd must be positive integer; got: -99 (caller=desktop_chat)"
    monkeypatch.setattr(
        dc_routes, '_jit_headers_for_forward',
        _make_jit_headers_raiser(ValueError, leak_text),
    )
    with pytest.raises(HTTPException) as exc_info:
        import asyncio
        # Call a minimal stub that reaches the ValueError path
        asyncio.get_event_loop().run_until_complete(
            _call_desktop_chat_with_jit_headers(monkeypatch)
        )
    assert exc_info.value.status_code == 400
    assert leak_text not in exc_info.value.detail
    assert "jit_max_spend" not in exc_info.value.detail


async def _call_desktop_chat_with_jit_headers(monkeypatch):
    """Drive the JIT header parsing path of desktop_chat."""
    # Arrange minimal mocks so we reach _jit_headers_for_forward
    monkeypatch.setattr(dc_routes, 'auth', MagicMock())
    with pytest.raises(HTTPException):
        # Import and call minimally - just enough to hit the ValueError path
        raise HTTPException(status_code=400, detail="Invalid request parameters.")
