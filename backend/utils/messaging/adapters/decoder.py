"""Locked FFmpeg wheel first, with an observable system fallback and startup probe."""

import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
UNAVAILABLE = 'Messaging audio decoder unavailable: sync locked backend dependencies or install FFmpeg.'


class MediaDecoderUnavailable(RuntimeError):
    """Installation failure, distinct from unreadable user audio."""


def _probe(executable: str) -> None:
    subprocess.run(
        [executable, '-version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
    )


def _wheel_decoder() -> tuple[str, bool]:
    import imageio_ffmpeg

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    bundled = Path(executable).resolve().parent == Path(imageio_ffmpeg.__file__).resolve().parent / 'binaries'
    return executable, bundled


def _fallback() -> None:
    record_fallback(
        component='other',
        from_mode='bundled_ffmpeg',
        to_mode='system_ffmpeg',
        reason='other',
        outcome='recovered',
        log=logger,
    )


@lru_cache(maxsize=1)
def get_media_decoder() -> str:
    """Validate once at channel startup; never download a binary at runtime."""
    try:
        executable, bundled = _wheel_decoder()
        _probe(executable)
    except (ImportError, RuntimeError, OSError, subprocess.SubprocessError):
        executable = shutil.which('ffmpeg')
        if executable:
            try:
                _probe(executable)
            except (OSError, subprocess.SubprocessError):
                executable = None
        if not executable:
            logger.error(UNAVAILABLE)
            raise MediaDecoderUnavailable(UNAVAILABLE) from None
        bundled = False
    if not bundled:
        _fallback()
    return executable
