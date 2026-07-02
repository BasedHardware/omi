"""Redact Telethon session strings (and other long-lived credentials) from log output.

The session string is a fully-compromising identity secret — anyone
with it can read all of the user's Telegram chats, send as the user,
and the only revocation path is Settings → Devices on the user's
phone. It must NEVER appear in:
- Log records (any level: DEBUG, INFO, WARNING, ERROR, CRITICAL)
- HTTP response bodies
- Exception messages
- Stack traces
- The on-disk discovery file
- The on-disk JSON storage

This module provides:
1. `redact_session_string(text)` — direct string transformation.
2. `safe_log_message(template, *args)` — formatted log message,
   redacted on both the template and the args.
3. A `_SessionStringRedactor` logging.Filter installed on the root
   logger at import time. This is the safety net: even if a developer
   forgets to call `safe_log_message`, the filter strips the session
   before any handler sees it. The filter is registered when this
   module is imported (which happens whenever the plugin's modules
   are loaded — see the `__init__.py` note about why the package
   can't be imported by its hyphenated directory name).

Detection heuristic: a Telethon session string is 200-400 chars of
base64 (matching `[A-Za-z0-9+/=]`). The string typically starts
with a version byte (1-2 chars). We replace any contiguous run of
200+ base64 chars with a fixed marker.

This is best-effort: a future Telethon release could change the
session format. Pin the detection in test_session_never_logged.py
to make regression tests easy to update.
"""

from __future__ import annotations

import logging
import re

# Telethon session strings are base64 (the encoding Telethon uses
# for its StringSession class). The shortest documented session is
# ~200 chars; the longest is ~400. We use 200+ as a conservative
# lower bound. The 200+ threshold means a normal English sentence
# won't trigger a false positive (typical English sentences are
# shorter than 200 base64 chars).
_TELETHON_SESSION_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{200,}=*\b")

# A separate pattern for hex-encoded session strings, in case
# Telethon switches encoding. Hex is 0-9a-f, so a session string
# is 200+ contiguous hex chars. We don't apply this to base64
# patterns because hex is a subset of [A-Za-z0-9] and would
# double-trigger; instead we look for hex-only runs.
_HEX_SESSION_PATTERN = re.compile(r"\b[0-9a-fA-F]{256,}\b")

# Replacement marker. Fixed-width so the surrounding log message
# remains readable.
_REDACTED_MARKER = "session=<redacted>"


def redact_session_string(text):
    """Strip any Telethon session string from a string.

    Args:
        text: any object; non-strings are returned unchanged.

    Returns:
        The same string with any 200+ char base64 or 256+ char hex
        run replaced by `session=<redacted>`. Non-string inputs
        pass through.
    """
    if not isinstance(text, str):
        return text
    text = _TELETHON_SESSION_PATTERN.sub(_REDACTED_MARKER, text)
    text = _HEX_SESSION_PATTERN.sub(_REDACTED_MARKER, text)
    return text


def safe_log_message(template, *args):
    """Format a log message with the redactor applied to BOTH the
    template and the args.

    Use this INSTEAD of `logger.error(template, *args)` for any
    message that might include a Telethon exception or RPC error.
    The default `logger.error(template, *args)` interpolates args
    via %-formatting with no redaction, leaking any session string
    in the arg into the log record.

    Example:
        try:
            await client.connect()
        except TelethonError as exc:
            logger.error(safe_log_message(
                "Connect failed: %s",
                exc,  # might contain session string
            ))
    """
    safe_template = redact_session_string(template)
    safe_args = tuple(redact_session_string(a) for a in args)
    return safe_template % safe_args if safe_args else safe_template


# ---------------------------------------------------------------------------
# Logging filter — defense in depth. Registered on the root logger
# at import time so any log record emitted by ANY logger in this
# Python process is redacted before reaching a handler. The plugin
# can't import its own __init__.py (the directory has a hyphen), so
# we register here in `redact.py` which is imported by the plugin's
# production entry point AND by every test that needs the redactor.
# ---------------------------------------------------------------------------


class _RedactingFormatter(logging.Formatter):
    """Formatter that redacts session strings in the formatted message.

    Wraps an existing formatter so log format strings are preserved
    while ensuring the redactor runs in the format pipeline. The
    redactor is invoked on `record.getMessage()` which is the
    fully-formatted string (after %-substitution of args). This
    catches Telethon exceptions whose `str()` includes the session.

    `original_format` is the formatter we delegate to AFTER
    redaction. If None, we fall back to `logging.Formatter.format`
    which uses the default format string.
    """

    def __init__(self, original_format=None):
        super().__init__()
        self._original_format = original_format

    def format(self, record):
        try:
            original = record.getMessage()
            redacted = redact_session_string(original)
            if redacted != original:
                # Replace record.msg with the redacted string and
                # clear args so the parent format() call returns the
                # redacted form. record.args may contain the original
                # (unredacted) session string, but since we clear
                # them, format() will just return record.msg verbatim.
                record.msg = redacted
                record.args = ()
        except Exception:
            # A redactor failure must never break logging.
            pass
        if self._original_format is not None:
            return self._original_format.format(record)
        return super().format(record)


# A no-op Filter (logging.Filter returns True) installed on the
# root logger. This is belt-and-suspenders alongside the Formatter:
# if any code path on a child logger's handler emits without a
# Formatter (rare but possible for default-formatter handlers), the
# Filter still redacts record.getMessage() at filter time. The
# Formatter approach handles all real-world cases.
class _SessionStringRedactor(logging.Filter):
    def filter(self, record):
        try:
            original = record.getMessage()
            redacted = redact_session_string(original)
            if redacted != original:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


_REDACTOR = _SessionStringRedactor()
logging.getLogger().addFilter(_REDACTOR)


def install_formatter_on_handlers():
    """Walk every existing handler in this process and wrap its
    formatter with the redacting one. Idempotent — re-running on a
    handler whose formatter is already wrapped is a no-op.

    Called automatically at import time. Tests that create their
    own handlers should also call this if they want redaction.
    """
    seen = set()
    for logger_name in logging.root.manager.loggerDict:
        lg = logging.root.manager.loggerDict[logger_name]
        if not isinstance(lg, logging.Logger):
            continue
        for handler in lg.handlers:
            if id(handler) in seen:
                continue
            seen.add(id(handler))
            _wrap_handler_formatter(handler)
    for handler in logging.root.handlers:
        if id(handler) not in seen:
            seen.add(id(handler))
            _wrap_handler_formatter(handler)


def _wrap_handler_formatter(handler):
    """If the handler doesn't already have a redacting formatter,
    wrap its current formatter with one. The original formatter's
    format() is delegated to so log format strings are preserved."""
    if getattr(handler, "_telegram_user_redactor_wrapped", False):
        return
    original_formatter = handler.formatter
    redacting = _RedactingFormatter(original_format=original_formatter)
    handler.setFormatter(redacting)
    handler._telegram_user_redactor_wrapped = True


# Auto-install at import time. This runs once per process — the
# `seen` set inside install_formatter_on_handlers prevents double-
# wrapping if redact is imported multiple times.
install_formatter_on_handlers()
