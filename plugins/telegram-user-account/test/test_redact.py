"""Tests for the session-string redactor.

The redactor has two surfaces:
1. `redact_session_string(text)` — direct string transformation.
   Used by callers that build log messages manually.
2. `safe_log_message(template, *args)` — formatted log message.
   Used as a drop-in replacement for `logger.error(template, *args)`
   when the args might contain a Telethon exception.
3. A logging.Filter on the plugin's logger hierarchy — automatic
   defense in depth: even if a developer forgets to call
   safe_log_message, the filter strips the session before any
   handler sees it.

These tests pin all three.
"""

from __future__ import annotations

import logging

import pytest

from redact import (
    redact_session_string,
    safe_log_message,
)
from test.test_session_never_logged import (
    TEST_SESSION_STRING,
)


class TestRedactSessionString:
    def test_strips_telethon_session(self):
        """The canonical case: a log message that includes a
        Telethon session string verbatim gets the session replaced
        with `session=<redacted>`."""
        out = redact_session_string(f"Connect failed for {TEST_SESSION_STRING}")
        assert TEST_SESSION_STRING not in out
        assert "session=<redacted>" in out

    def test_does_not_touch_short_strings(self):
        """A 50-char base64-looking string is NOT a session
        (sessions are 200+ chars). The redactor should not
        touch short strings — false positives would be noisy."""
        short = "abcdefghij" * 5  # 50 chars
        out = redact_session_string(f"Connecting to {short}")
        assert short in out

    def test_strips_session_at_start(self):
        out = redact_session_string(f"{TEST_SESSION_STRING}: AuthError")
        assert TEST_SESSION_STRING not in out
        assert "session=<redacted>" in out

    def test_strips_session_in_middle(self):
        out = redact_session_string(
            f"prefix-{TEST_SESSION_STRING}-suffix"
        )
        assert TEST_SESSION_STRING not in out
        assert "session=<redacted>" in out
        assert "prefix-" in out
        assert "-suffix" in out

    def test_non_string_input_passes_through(self):
        """Non-strings are returned unchanged (the function is
        used with `record.msg` and `record.args` from logging,
        both of which can be non-strings)."""
        assert redact_session_string(None) is None
        assert redact_session_string(42) == 42
        assert redact_session_string([1, 2, 3]) == [1, 2, 3]
        assert redact_session_string({"key": "val"}) == {"key": "val"}


class TestSafeLogMessage:
    def test_formats_template_with_args(self):
        """safe_log_message is a drop-in for %-formatted log calls."""
        out = safe_log_message("Failed: %s", "timeout")
        assert out == "Failed: timeout"

    def test_redacts_session_in_args(self):
        out = safe_log_message(
            "Connect failed: %s",
            f"AuthError for {TEST_SESSION_STRING}",
        )
        assert TEST_SESSION_STRING not in out
        assert "session=<redacted>" in out

    def test_redacts_session_in_template(self):
        out = safe_log_message(
            f"Connect failed for {TEST_SESSION_STRING}",
        )
        assert TEST_SESSION_STRING not in out

    def test_handles_no_args(self):
        out = safe_log_message("Just a message")
        assert out == "Just a message"


class TestLoggingFilter:
    """The redactor as a logging.Filter is the safety net."""

    def test_filter_redacts_session_in_message(self):
        """A log record whose formatted message includes the
        session string has the message replaced with the
        redacted form. This is the safety net for developers
        who forget to call safe_log_message()."""
        # `redact` is imported at the top of this file, which
        # triggered the side-effect of installing the redacting
        # Formatter on every existing handler in the process.
        # We call install_formatter_on_handlers() here too in case
        # the test runs handlers that were created after redact's
        # import.
        from redact import install_formatter_on_handlers

        logger = logging.getLogger("omi-telegram-user-account.filter-test")
        captured: list[str] = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                # Use the formatter's output (self.format), not
                # record.getMessage() — the redactor runs in the
                # formatter pipeline, so self.format(record) is
                # what an actual log destination (file, stderr)
                # would see.
                captured.append(self.format(record))

        h = _CaptureHandler()
        logger.addHandler(h)
        # Wrap the handler's formatter AFTER it's added to the
        # logger, so the redactor's install_formatter_on_handlers
        # can see it.
        install_formatter_on_handlers()
        try:
            logger.error(
                "Bad session: %s",
                TEST_SESSION_STRING,
            )
        finally:
            logger.removeHandler(h)

        assert captured, "no log records captured"
        for msg in captured:
            assert TEST_SESSION_STRING not in msg, (
                f"logging.Formatter failed to redact: {msg!r}"
            )
