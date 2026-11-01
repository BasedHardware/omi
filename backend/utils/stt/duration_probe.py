"""Single-request PyAV worker; no account, provider, or ledger access."""

import ctypes
import errno
import math
import sys
from typing import BinaryIO

import av
import av.logging as av_logging
from av.error import FFmpegError
from fastapi import HTTPException


def audio_seconds(audio_file: BinaryIO) -> int:
    """Probe the uploaded media, rather than billing transcript timestamp gaps.

    PyAV is the existing FFmpeg binding used by voice-duration accounting.
    The existing seekable upload spool supports containers whose metadata is
    at the end, without an external ffprobe binary or a resident body copy
    while waiting for a provider slot. The child installs a null log callback
    before opening media; exception details never enter the response.
    """
    try:
        seconds = 0.0
        with av.open(audio_file, mode='r') as audio:
            if not audio.streams.audio:
                raise ValueError('missing audio stream')
            stream = audio.streams.audio[0]
            if audio.duration is not None:
                seconds = float(audio.duration) / 1_000_000
            elif stream.duration is not None and stream.time_base is not None:
                seconds = float(stream.duration * stream.time_base)
            else:
                raise ValueError('missing duration')
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('invalid duration')
        return math.ceil(seconds)
    except FFmpegError as error:
        if error.errno == errno.ETIMEDOUT:
            raise HTTPException(status_code=503, detail='Audio duration probe timed out — try again shortly') from None
        raise HTTPException(status_code=400, detail='Cannot determine audio duration') from None
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='Cannot determine audio duration') from None


def main() -> None:
    try:
        # Resolve the libav used by this PyAV extension, rather than guessing a
        # system library name. Only this disposable probe process is affected.
        library = ctypes.CDLL(av_logging.__file__)
        callback = library.av_log_set_callback
        callback.argtypes = [ctypes.c_void_p]
        callback.restype = None
        callback(None)
        print(audio_seconds(sys.stdin.buffer))
    except HTTPException as error:
        raise SystemExit(2 if error.status_code == 400 else 3) from None
    except Exception:
        raise SystemExit(3) from None


if __name__ == '__main__':
    main()
