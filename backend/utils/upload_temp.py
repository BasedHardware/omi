"""Collision-free, self-cleaning temp paths for client-uploaded files.

Upload handlers used to write `_temp/<dir>/<client filename>` verbatim, which
let a client both traverse out of the directory (`../../etc/x`) and overwrite a
concurrent request's file. Prefixing a UUID fixes both, but makes every upload
a *new* file — so the path has to be removed once the request is done, or a
long-lived instance fills its disk.

`temp_upload_path()` is the one place that decides how an uploaded file is
named and when it disappears; upload routes must go through it.
"""

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
import logging

logger = logging.getLogger(__name__)

# Most filesystems (ext4, APFS, XFS) cap a single path component at 255 bytes.
# The UUID prefix plus separator costs 33 of them.
_MAX_COMPONENT_BYTES = 255
_PREFIX_BYTES = 33


def safe_upload_filename(filename: Optional[str]) -> str:
    """Return a single, safe path component for a client-supplied filename.

    Strips any directory part (path traversal) and bounds the result so the
    prefixed name still fits in one filesystem component, keeping the
    extension so downstream format sniffing still works.
    """
    suffix = Path(filename).name if filename else ''
    if not suffix or suffix in ('.', '..'):
        return 'upload'

    budget = _MAX_COMPONENT_BYTES - _PREFIX_BYTES
    if len(suffix.encode('utf-8')) <= budget:
        return suffix

    extension = Path(suffix).suffix
    if len(extension.encode('utf-8')) > budget:
        extension = ''
    stem = suffix[: len(suffix) - len(extension)] if extension else suffix
    stem_budget = budget - len(extension.encode('utf-8'))
    encoded_stem = stem.encode('utf-8')[:stem_budget]
    # A multibyte character may have been cut in half by the byte slice.
    stem = encoded_stem.decode('utf-8', 'ignore')
    return f'{stem}{extension}' or 'upload'


@contextmanager
def temp_upload_path(directory: str, filename: Optional[str]) -> Iterator[str]:
    """Yield a unique path under `directory` for an uploaded file, creating the
    directory and removing the file again on every exit path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f'{uuid.uuid4().hex}_{safe_upload_filename(filename)}')
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            # The path embeds the UID (speech uploads) and the raw client-supplied
            # filename; logging it would leak PII/control characters into logs.
            logger.warning('Could not remove temp upload file: %s', type(e).__name__)
