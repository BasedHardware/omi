"""Empty framed WALs have no audio payload; byte size alone never proves silence."""

import os
import logging
import re
from typing import BinaryIO, Iterable

from fastapi import UploadFile

from utils.sync.upload_names import canonical_sync_upload_filenames
from utils.sync.capture_clock import SyncCaptureTimeRejected


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
    # This unconditional legacy normalization is part of content identity,
    # including with SYNC_COLLISION_SUFFIX_ENABLED off. Released apps put a
    # same-second collision sequence after the capture
    # time; every later read (admission, lanes, staging, workers) sees the
    # canonical name with the timestamp last. The capture time is unchanged.
    renamed = 0
    for file, name in zip(nonempty, canonical_sync_upload_filenames([f.filename or '' for f in nonempty])):
        if name != (file.filename or ''):
            file.filename = name
            renamed += 1
    if renamed:
        logging.getLogger(__name__).info('sync_upload_name_canonicalized uid=%s count=%s', uid, renamed)
    if any(re.search(r'_u[0-9]+\.bin$', file.filename or '') for file in nonempty):
        # The legacy parser refused every unresolved tail (including aliases
        # that the whole-request collision guard cannot safely rename). Do
        # not let the direct-reader extension mint a new HTTP ledger identity
        # that an old revision cannot reproduce during a roll or rollback.
        raise SyncCaptureTimeRejected()
    return nonempty


def nonempty_manifest_claims(
    claims: list[dict[str, str]] | None, filenames: Iterable[str]
) -> list[dict[str, str]] | None:
    # Verify the full signed request before dropping no-audio members: omission
    # must not demote legitimate remaining capture to the legacy lane.
    if claims is None:
        return None
    names = {os.path.basename(name) for name in filenames}
    kept, renamed = [], False
    for claim in claims:
        if claim['name'] not in names:
            # The signature covers the sent name; staging uses the canonical one.
            [canonical] = canonical_sync_upload_filenames([claim['name']])
            if canonical not in names:
                continue
            claim, renamed = {**claim, 'name': canonical}, True
        kept.append(claim)
    # manifest_claims_match_paths compares against the staged names in sorted order.
    return sorted(kept, key=lambda item: (item['name'], item['sha256'])) if renamed else kept
