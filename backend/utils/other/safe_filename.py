"""Sanitize a client-supplied filename before it is joined into a filesystem path.

The multipart parser hands us ``UploadFile.filename`` exactly as the client sent
it, so it may contain ``../`` segments, an absolute path, backslashes or a NUL
byte. Any route that concatenates it into a path the server then writes to --
``file_path = f"_temp/{uid}/{file.filename}"`` -- lets the client pick the write
location, which is an arbitrary file write (CWE-22) with attacker-controlled
bytes. Overwriting a file the process can write (``.env``, a config, a module on
``sys.path``) escalates straight out of the upload feature.

This is one shared implementation so a new upload route cannot silently
reintroduce the traversal. Callers already using it:

* ``routers/chat.py``   -- ``/v1/files`` and ``/v2/files`` (after #6804)
* ``routers/stt.py``    -- forwards the name to the parakeet service
* ``routers/apps.py``   -- app logo upload on create / clone / update
* ``routers/speech_profile.py`` -- onboarding audio sample
"""

import os
import re

# Anything outside this set becomes '_'. This is what makes the result safe on
# POSIX *and* Windows: os.path.basename only strips '/' on POSIX, so a name like
# '..\..\etc\x' would otherwise survive as one opaque segment -- substituting the
# backslashes here leaves nothing that can re-enter the path.
_SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._-]')

# Keep names short so a crafted name cannot blow past the filesystem's own
# NAME_MAX (255 bytes) once a prefix is added.
_MAX_FILENAME_LEN = 64
_MAX_EXTENSION_LEN = 8


def safe_filename(filename, default: str = 'upload', max_len: int = _MAX_FILENAME_LEN) -> str:
    """Reduce a client-supplied filename to a single safe path component.

    Strips directory components (including Windows separators), drops leading
    dots so no ``..`` or hidden-file name survives, replaces every character
    outside ``[A-Za-z0-9._-]``, and truncates while keeping a short extension so
    decoders that sniff by suffix still work.

    Args:
        filename: the raw client value, may be ``None`` or empty.
        default: returned when nothing usable remains (e.g. ``'..'``, ``'/'``).
        max_len: maximum length of the returned name.

    Returns:
        A name that is safe to ``os.path.join`` onto a trusted directory and
        which can never escape it.
    """
    base = os.path.basename((filename or '').replace('\\', '/'))
    base = _SAFE_FILENAME_RE.sub('_', base).lstrip('.')

    if len(base) > max_len:
        stem, dot, ext = base.rpartition('.')
        if dot and 0 < len(ext) <= _MAX_EXTENSION_LEN:
            base = stem[: max_len - len(ext) - 1] + '.' + ext
        else:
            base = base[:max_len]

    return base or default
