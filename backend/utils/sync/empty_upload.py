"""Empty framed WALs have no audio payload; byte size alone never proves silence."""

import os
from typing import BinaryIO


def empty_framed_clip(stream: BinaryIO) -> bool:
    # The wire contract needs a four-byte length AND at least one payload byte.
    # Never use a KB/duration threshold: a tiny compressed frame may be speech.
    position = stream.tell()
    try:
        stream.seek(0, os.SEEK_END)
        return stream.tell() <= 4
    finally:
        stream.seek(position)


def nonempty_sync_uploads(files):
    return [file for file in files if not empty_framed_clip(file.file)]
