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
        out = redact_session_string(f"prefix-{TEST_SESSION_STRING}-suffix")
        assert TEST_SESSION_STRING not in out
        assert "session=<redacted>" in out
        assert "prefix-" in out
        assert "-suffix" in out

    def test_strips_session_with_trailing_padding(self):
        """Regression: the regex used to leave trailing `==` padding
        intact because `\b` doesn't match non-word characters like
        `=`. Telethon session strings end in 0-2 `=` chars, so a
        boundary bug here leaks the last 1-2 chars of the session."""
        # Build a session that ENDS with == padding.
        sess = TEST_SESSION_STRING + "=="
        out = redact_session_string(f"Connect failed for {sess}")
        assert sess not in out
        # Specifically: the trailing "==" must NOT remain in the
        # redacted output. If the regex's trailing boundary was
        # wrong, "session=<redacted>==" or "session=<redacted>=" would
        # appear here.
        assert not out.endswith("=="), f"trailing '==' leaked: {out!r}"
        assert not out.endswith("="), f"trailing '=' leaked: {out!r}"

    def test_does_not_match_short_alphanumeric_run(self):
        """A run of <200 alphanumeric characters is too short to be
        a Telethon session (sessions are 200+ chars). The redactor
        must NOT touch short runs — that would create false
        positives on common log strings like UUIDs, hex hashes, or
        short tokens.
        """
        # 50 chars of base64-alphabet — too short to be a session.
        short = "A" * 50
        out = redact_session_string(f"Connecting to {short}")
        assert short in out

    def test_does_not_match_run_with_non_base64_separators(self):
        """A 200+ char run of NON-base64-alphabet characters
        (e.g., spaces, hyphens, dots) cannot be a base64 session.
        The redactor's character class excludes these, so they
        break the run. Documented as: the redactor is base64-only.
        """
        # 300 chars including spaces — the spaces break the run,
        # so the redactor shouldn't match anything here.
        long_text = "A" * 100 + " " + "B" * 100 + " " + "C" * 100
        out = redact_session_string(long_text)
        # No redaction marker in the output (no 200+ base64 run).
        assert "session=<redacted>" not in out
        # The original text survives unchanged.
        assert long_text in out

    def test_matches_even_when_surrounded_by_base64(self):
        """Document the redactor's actual behavior: a 200+ char
        base64 run is redacted whether or not it's bordered by
        non-base64 characters. The 1s in `1A...A1` are valid
        base64 (digits are part of the alphabet), so the redactor
        matches the entire 202-char run. This is by design — the
        alternative (only redacting when bordered by non-base64)
        would miss the realistic case of a session embedded in a
        long URL or query string.
        """
        middle = "A" * 200
        text = f"1{middle}1"  # 202 chars of valid base64
        out = redact_session_string(text)
        assert "session=<redacted>" in out
        # The session marker is at position 0 — the leading "1"
        # is part of the matched run.
        assert out == "session=<redacted>", f"unexpected output: {out!r}"

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

    def test_safe_log_message_does_not_crash_on_mismatched_template(self):
        """safe_log_message must NOT raise TypeError when the
        template and args are mismatched. Standard Python logging
        catches this deep in the handler's emit() stack, but our
        eager interpolation would raise at the call site. Catch
        the formatting error and return a safe fallback that
        contains NO args (which may be the very thing the
        redactor couldn't handle).
        """
        # Template wants %s but no args passed.
        out = safe_log_message("Failed: %s")
        assert "log format error" in out
        assert "Failed" not in out or "[" in out  # template was either redacted out or wrapped in [...]
        # No original arg should leak into the fallback. The
        # fallback only contains the redacted template, the error
        # type, and the error message.
        assert "session=" not in out  # no <redacted> marker

    def test_safe_log_message_redacts_mismatched_template_args(self):
        """When a template/args mismatch happens, the args that
        WOULD have leaked via the standard logging handler should
        be redacted from the fallback message.
        """
        # Template expects %d but gets a string with the session.
        out = safe_log_message("Code: %d", TEST_SESSION_STRING)
        # The fallback should mention a format error AND not contain
        # the session string.
        assert "log format error" in out
        assert TEST_SESSION_STRING not in out


class _SessionStringException(Exception):
    """A Telethon-like exception whose str() includes the session.

    Used by TestRedactingFormatterTraceback to drive a real
    `logger.exception(...)` call (which captures exc_info) and
    assert the formatted traceback is redacted.
    """

    def __init__(self, session):
        super().__init__(f"AuthKeyError: invalid key for session {session}")
        self.session = session


class TestRedactingFormatterTraceback:
    """The redacting Formatter must also redact traceback / exception
    text (not just the message). Telethon exceptions whose str()
    includes the session string would otherwise leak through
    logger.exception() calls.
    """

    def test_traceback_does_not_leak_session(self):
        """logger.exception() captures exc_info. The traceback
        formatter should redact the session string in the formatted
        exception text."""
        from redact import install_formatter_on_handlers

        logger = logging.getLogger("omi-telegram-user-account.traceback-test")
        captured: list[str] = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(self.format(record))

        h = _CaptureHandler()
        logger.addHandler(h)
        install_formatter_on_handlers()  # wrap the new handler
        try:
            try:
                raise _SessionStringException(TEST_SESSION_STRING)
            except _SessionStringException:
                logger.exception("Connect failed")
        finally:
            logger.removeHandler(h)

        assert captured, "no log records captured"
        for msg in captured:
            assert TEST_SESSION_STRING not in msg, f"session string leaked into formatted traceback: {msg!r}"


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
            assert TEST_SESSION_STRING not in msg, f"logging.Formatter failed to redact: {msg!r}"
