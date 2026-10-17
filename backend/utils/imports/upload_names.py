"""Safe reduction of user-supplied upload filenames.

Upload endpoints stage files under ``_temp/``. A raw multipart filename is
attacker-controlled: ``../../tmp/x.zip``, ``/etc/x.zip`` and ``C:\\..\\x.zip``
all carry path segments that would escape the staging directory if joined
directly. Reducing to the basename after normalizing ``\\`` separators makes
the name a pure suffix hint — the job id remains the unique prefix.
"""

from __future__ import annotations

import os


def safe_upload_basename(filename: str | None) -> str | None:
    """Return *filename* reduced to a safe basename, or ``None`` when unusable.

    ``None``/empty input, a name that reduces to ``.``/``..``, and any name
    still containing a separator or NUL are rejected. Extension policy (.zip,
    .srt, ...) is the caller's concern — this only guarantees the result is a
    single path segment.
    """
    if not filename:
        return None
    name = os.path.basename(filename.replace('\\', '/'))
    if not name or name in ('.', '..') or '\x00' in name or '/' in name or '\\' in name:
        return None
    return name
