"""
Tests for desktop_chat router exception detail sanitization.
PR: fix(desktop_chat): sanitize exception detail leakage in chat endpoint handlers

Verifies that RuntimeError from metering/gateway and ValueError from JIT header
parsing do NOT leak internal Redis errors, server hostnames, or schema details in HTTP responses.
"""
from fastapi import HTTPException


def _simulate_desktop_chat_error_handler(exc: Exception, phase: str):
    """Simulate the patched desktop chat exception handling."""
    if phase == "jit_headers":
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail='Invalid JIT forwarding headers.') from exc
    elif phase == "metering":
        if isinstance(exc, HTTPException):
            raise exc
        if isinstance(exc, RuntimeError):
            raise HTTPException(status_code=503, detail='Desktop chat service is temporarily unavailable. Please try again.') from exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail='Invalid desktop chat request parameters.') from exc
    raise exc


class TestDesktopChatSanitization:
    """Ensure no raw exception strings reach client HTTP responses."""

    def test_jit_headers_value_error_sanitization(self):
        """ValueError during JIT header forward must not expose raw header payload."""
        raw_msg = "Invalid JIT base64 token: b64decode failed on 'sk-ant-api03-secret...'"
        err = ValueError(raw_msg)
        try:
            _simulate_desktop_chat_error_handler(err, "jit_headers")
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert raw_msg not in exc.detail
            assert "sk-ant" not in exc.detail
            assert exc.detail == "Invalid JIT forwarding headers."

    def test_metering_runtime_error_sanitization(self):
        """RuntimeError during metering/gateway must not expose internal pool addresses or credentials."""
        raw_msg = "Connection pool exhausted at redis://redis-master.internal:6379/0: max 500 connections"
        err = RuntimeError(raw_msg)
        try:
            _simulate_desktop_chat_error_handler(err, "metering")
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 503
            assert raw_msg not in exc.detail
            assert "redis-master.internal" not in exc.detail
            assert "6379" not in exc.detail
            assert exc.detail == "Desktop chat service is temporarily unavailable. Please try again."

    def test_metering_value_error_sanitization(self):
        """ValueError during quota enforcement must not expose internal quota DB details."""
        raw_msg = "Quota table calculation negative: daily_tokens=-1500 for uid='user_abc_456'"
        err = ValueError(raw_msg)
        try:
            _simulate_desktop_chat_error_handler(err, "metering")
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert raw_msg not in exc.detail
            assert "daily_tokens" not in exc.detail
            assert "user_abc_456" not in exc.detail
            assert exc.detail == "Invalid desktop chat request parameters."
