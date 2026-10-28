"""Empty framed WALs have no audio payload; byte size alone never proves silence."""

import os
import logging
from typing import BinaryIO, Iterable

from fastapi import UploadFile


def empty_framed_clip(stream: BinaryIO) -> bool:
    # The wire contract needs a four-byte length AND at least one payload byte.
    # Never use a KB/duration threshold: a tiny compressed frame may be speech.
    position = stream.tell()
    try:
        stream.seek(0, os.SEEK_END)
        return stream.tell() <= 4
    finally:
        stream.seek(position)


class EmptySyncUpload(Exception):
    """No audio payload to admit; the route returns an empty success receipt."""


def prepare_sync_uploads(files: list[UploadFile], uid: str) -> list[UploadFile]:
    nonempty = [file for file in files if not empty_framed_clip(file.file)]
    if len(nonempty) != len(files):
        logging.getLogger(__name__).info(
            'sync_empty_clip uid=%s count=%s reason=empty_clip', uid, len(files) - len(nonempty)
        )
    if not nonempty:
        raise EmptySyncUpload()
    return nonempty


def nonempty_manifest_claims(
    claims: list[dict[str, str]] | None, filenames: Iterable[str]
) -> list[dict[str, str]] | None:
    # Verify the full signed request before dropping no-audio members: omission
    # must not demote legitimate remaining capture to the legacy lane.
    names = {os.path.basename(name) for name in filenames}
    return None if claims is None else [claim for claim in claims if claim['name'] in names]
