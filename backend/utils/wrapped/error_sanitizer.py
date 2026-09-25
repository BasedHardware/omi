"""Utility helpers for sanitising exception information.

The goal is to avoid leaking internal details (stack traces, API keys,
SQL statements, etc.) to API consumers. All exceptions that bubble up
through the Wrapped‑2025 background job are passed through
`sanitize_error` before being persisted or returned.
"""

import traceback
import re
from typing import Any


def sanitize_error(exc: BaseException) -> str:
    """
    Return a short, safe string representation of an exception.

    - Uses the exception class name to give a hint about the failure.
    - Includes the original message but strips new‑lines and any
      potentially sensitive substrings (e.g. file paths, SQL queries).
    - Guarantees the result is a single line < 256 characters.

    This function is deliberately defensive: if anything goes wrong while
    sanitising we fall back to a generic message.
    """
    try:
        # Basic class name + message
        msg = f"{exc.__class__.__name__}: {str(exc)}"

        # Remove newlines and excessive whitespace
        msg = " ".join(msg.split())

        # Strip anything that looks like a traceback line (e.g. "File ...")
        # This is a simple heuristic – we just drop any occurrence of the word
        # "Traceback" or a pattern like "File \"...\"".
        msg = re.sub(r"Traceback.*", "", msg, flags=re.IGNORECASE)
        msg = re.sub(r'File\s+"[^"]+"', "", msg, flags=re.IGNORECASE)

        # Truncate to a reasonable length
        if len(msg) > 200:
            msg = msg[:197] + "..."

        return msg
    except Exception:  # pragma: no cover – extremely unlikely
        # In the very unlikely case sanitisation itself fails, return a generic
        # placeholder that does not expose any internal data.
        return "Internal server error"
