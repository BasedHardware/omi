"""Backfill admission and worker bounds, including compressed expansion.

Reject before admission rather than acknowledging only a prefix of a recording.
Workers apply the same contract to older staging; oversized legacy jobs remain
retryable with their cloud audio intact for an operator to restore capacity.
"""

from __future__ import annotations

import errno
import os
import re
import struct
from typing import BinaryIO, Iterable

from fastapi import HTTPException, UploadFile

MAX_BACKFILL_FILES = 20
MAX_BACKFILL_RAW_BYTES = 64 * 1024**2
MAX_BACKFILL_AUDIO_BYTES = 64 * 1024**2
MAX_BACKFILL_SECONDS = 3600
MAX_BACKFILL_FRAMES = 360000
MAX_FRAME_BYTES = 65536
OPUS_FRAME_SAMPLES = frozenset((40, 80, 160, 320, 640, 960, 1280, 1920))


class BackfillInputLimitExceeded(ValueError):
    """Not suitable for a 4-GiB worker; no raw payload in the error."""


class BackfillStoragePressure(RuntimeError):
    """Tmpfs saturation is retryable capacity pressure, never invalid audio."""


def raise_sync_storage_pressure(error: Exception) -> None:
    if isinstance(error, OSError) and error.errno in (errno.ENOSPC, errno.EDQUOT):
        raise BackfillStoragePressure('sync temporary storage full') from error


def sync_pcm_format(filename: str) -> tuple[int, int] | None:
    """Shared with the decoder, including legacy missing-rate fallback names."""
    if '_pcm16_' not in filename and '_pcm8_' not in filename:
        return None
    match = re.search(r'_pcm(?:8|16)_(\d+)_', filename)
    rate = int(match.group(1)) if match else (16000 if '_pcm16_' in filename else 8000)
    width = 1 if '_pcm8_' in filename else 2
    return rate, width


def _validate(streams: Iterable[tuple[str, BinaryIO]]) -> None:
    raw_bytes = audio_bytes = frames = 0
    seconds = 0.0
    count = 0
    for filename, stream in streams:
        count += 1
        if count > MAX_BACKFILL_FILES:
            raise BackfillInputLimitExceeded('backfill file count exceeded')
        pcm = sync_pcm_format(filename)
        if pcm:
            rate, width = pcm
            if not 8000 <= rate <= 48000:
                raise BackfillInputLimitExceeded('backfill sample rate unsupported')
        else:
            width, rate = 2, 16000
            match = re.search(r'_fs(\d+)', filename)
            frame_samples = int(match.group(1)) if match else 160
            if frame_samples not in OPUS_FRAME_SAMPLES:
                raise BackfillInputLimitExceeded('backfill Opus frame size unsupported')
        position = stream.tell()
        try:
            stream.seek(0, os.SEEK_END)
            raw_bytes += stream.tell()
            if raw_bytes > MAX_BACKFILL_RAW_BYTES:
                raise BackfillInputLimitExceeded('backfill encoded batch limit exceeded')
            stream.seek(0)
            while True:
                prefix = stream.read(4)
                if not prefix:
                    break
                if len(prefix) != 4:
                    break  # Preserve the decoder's existing usable-prefix semantics.
                length = struct.unpack('<I', prefix)[0]
                if not 0 < length <= MAX_FRAME_BYTES or (pcm and length % width):
                    break  # The decoder stops here; the full encoded size was checked.
                frames += 1
                # PCM WAV bytes and its 16-kHz/16-bit VAD working representation
                # are each covered. Opus output cannot exceed decoder frame_size.
                samples = length // width if pcm else frame_samples
                duration = samples / rate
                audio_bytes += max(length, (samples * 32000 + rate - 1) // rate) if pcm else samples * 2
                seconds += duration
                if (
                    raw_bytes > MAX_BACKFILL_RAW_BYTES
                    or audio_bytes > MAX_BACKFILL_AUDIO_BYTES
                    or seconds > MAX_BACKFILL_SECONDS
                    or frames > MAX_BACKFILL_FRAMES
                ):
                    raise BackfillInputLimitExceeded('backfill batch resource limit exceeded')
                if len(stream.read(length)) != length:
                    break
        finally:
            stream.seek(position)
    if count == 0:
        raise BackfillInputLimitExceeded('backfill batch empty')


def validate_backfill_uploads(files: list[UploadFile]) -> None:
    """413 before local staging, content claims, 202, or client custody release."""
    try:
        if len(files) > MAX_BACKFILL_FILES:
            raise BackfillInputLimitExceeded('backfill file count exceeded')
        _validate((file.filename or '', file.file) for file in files)
    except BackfillInputLimitExceeded as error:
        raise HTTPException(
            status_code=413,
            detail='Historical sync batch exceeds safe processing limits; retain audio and upload smaller batches',
        ) from error


def validate_backfill_paths(paths: list[str]) -> None:
    """Recheck staged input on every attempt; bounded reads, no PCM allocation."""
    if len(paths) > MAX_BACKFILL_FILES or sum(os.path.getsize(path) for path in paths) > MAX_BACKFILL_RAW_BYTES:
        raise BackfillInputLimitExceeded('backfill staged batch resource limit exceeded')

    def streams():
        for path in paths:
            with open(path, 'rb') as file:
                yield os.path.basename(path), file

    _validate(streams())
