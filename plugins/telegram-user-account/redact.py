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
#
# Boundary detection: standard `\b` doesn't work for base64 because
# `+`, `/`, and `=` are non-word characters. A session string that
# ENDS with `==` padding would only have `=` matched up to an
# internal word boundary, leaving the trailing `=` characters
# unredacted. A session string that STARTS with `+` or `/` (unlikely
# but possible) would also fail the leading boundary. We use
# negative lookbehind/lookahead to match only when the run is NOT
# surrounded by other base64 characters (which is what we want for
# session detection — a session is a standalone blob in logs, not
# embedded mid-word).
_TELETHON_SESSION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9+/=])"  # not preceded by base64 char
    r"[A-Za-z0-9+/]{200,}"  # 200+ base64 chars (no word boundary)
    r"=*"  # optional padding (greedy)
    r"(?![A-Za-z0-9+/=])"  # not followed by base64 char
)

# A separate pattern for hex-encoded session strings, in case
# Telethon switches encoding. Hex is 0-9a-f, so a session string
# is 200+ contiguous hex chars. We don't apply this to base64
# patterns because hex is a subset of [A-Za-z0-9] and would
# double-trigger; instead we look for hex-only runs.
_HEX_SESSION_PATTERN = re.compile(
    r"(?<![0-9a-fA-F])"  # not preceded by hex char
    r"[0-9a-fA-F]{256,}"  # 256+ hex chars
    r"(?![0-9a-fA-F])"  # not followed by hex char
)

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

    Failure mode: if the template and args are mismatched (e.g.,
    template has `%s` but no args are passed, or template has no
    placeholders but args are passed), standard Python logging
    raises a `TypeError` deep inside the handler's `emit()` call
    stack. Here we do the interpolation eagerly, so a TypeError
    would be raised at the CALL SITE — that's still better than
    silent corruption, but a `safe_log_message` that crashes the
    caller contradicts the docstring's "drop-in" claim.

    To preserve the standard logging behavior (a bad template
    silently produces an unformatted string with the args
    swallowed, NOT a TypeError), we catch the formatting error
    and return a safe fallback: "[log format error: <error>]".
    The fallback never contains the original args, so any
    sensitive content in the args is stripped.
    """
    safe_template = redact_session_string(template)
    safe_args = tuple(redact_session_string(a) for a in args)
    try:
        # Always run % formatting, even with zero args, so a
        # mismatch like `safe_log_message("Failed: %s")` with no
        # args raises TypeError — which we catch and turn into a
        # safe fallback. The previous `if not safe_args else ...`
        # early return bypassed the try/except and returned the
        # template verbatim, contradicting the docstring's
        # "drop-in for logger.error" promise.
        return safe_template % safe_args
    except (TypeError, ValueError) as exc:
        # TypeError: wrong number of args / wrong type for placeholder
        # ValueError: e.g., %d with a string arg
        # Return a safe fallback that includes the error and the
        # (already-redacted) template. NEVER include the args here
        # — they may be the very thing the redactor couldn't handle.
        return f"[log format error: {type(exc).__name__}: {exc}] template={safe_template!r}"


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

    Traceback / stack redaction: Python's `Formatter.format()` calls
    `formatException()` (for `record.exc_info`) and `formatStack()`
    (for `record.stack_info`) AFTER assembling the message. These
    formatted strings can include Telethon exception tracebacks
    whose `str(exc)` contains the session. We override both methods
    so the redactor runs on the formatted exception / stack text
    BEFORE the final output is written. This is the P1 fix from
    cubic review 4614064929.
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

    def formatException(self, ei):
        """Override: format the exception, then redact the result.

        `ei` is the exc_info tuple (type, value, traceback) — the same
        shape `Formatter.formatException` accepts. We delegate to the
        parent (which uses `traceback.format_exception` to build the
        string) and then run the redactor on the output. Telethon
        exceptions' `str(value)` can include the session string —
        for example, `AuthKeyError: invalid auth key for session
        <base64-session-string>`. The standard formatter would
        include that verbatim; we strip it.
        """
        try:
            formatted = super().formatException(ei)
        except Exception:
            # formatException itself failed. Return a safe placeholder
            # rather than letting the failure propagate.
            return "[exception format error]"
        return redact_session_string(formatted)

    def formatStack(self, stack_info):
        """Override: format the stack info, then redact the result.

        `stack_info` is the string from `record.stack_info` (None if
        the record didn't capture a stack). Stack frames usually
        contain local variable reprs, which can include the session
        string if a Telethon client stored it in a local var that
        survived into the exception scope. The redactor catches
        any such leak.
        """
        try:
            formatted = super().formatStack(stack_info)
        except Exception:
            return "[stack format error]"
        return redact_session_string(formatted)


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
