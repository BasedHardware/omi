"""Bounded speech Opus, decoded to ordinary PCM WAV for held recovery."""

import hashlib
from pathlib import Path
import subprocess
import wave

from utils.observability.held_content import record_capture

MAX_OBJECT_BYTES = 128 * 1024


def _ffmpeg(args: list[str], *, pcm: bytes | None = None, timeout: float = 20) -> bytes:
    try:
        result = subprocess.run(
            ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args],
            input=pcm,
            capture_output=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise RuntimeError('held audio codec failed') from error
    return result.stdout


def encode(path: str, pcm: bytes, rate: int, *, max_bytes: int = MAX_OBJECT_BYTES) -> None:
    args = [
        '-f',
        's16le',
        '-ar',
        str(rate),
        '-ac',
        '1',
        '-i',
        'pipe:0',
        '-c:a',
        'libopus',
        '-application',
        'voip',
        '-b:a',
        '16k',
    ]
    # FFmpeg resampling has an undefined clock for sub-millisecond input.
    # Pad to one packet; source_frames trims only that explicit tail on decode.
    pcm += b'\0' * max(0, (rate // 50) * 2 - len(pcm))
    _ffmpeg([*args, '-vbr', 'constrained', '-f', 'opus', path], pcm=pcm)
    # Constrained VBR saves silence without assuming a speech detector's recall.
    # A hard CBR fallback bounds unusual/noisy input, including container framing.
    if Path(path).stat().st_size > max_bytes:
        _ffmpeg([*args, '-vbr', 'off', '-f', 'opus', path], pcm=pcm)
    if Path(path).stat().st_size > max_bytes:
        raise ValueError('held Opus object exceeds minute bound')


def decode(source: str, destination: str, rate: int, frames: int) -> None:
    try:
        _ffmpeg(['-i', source, '-ac', '1', '-ar', str(rate), '-f', 'wav', destination])
        with wave.open(destination, 'rb') as audio:
            if frames <= 0 or frames > 60 * rate or audio.getnframes() < frames:
                record_capture('frame_mismatch')
                raise ValueError('held Opus source clock mismatch')
            params, pcm = audio.getparams(), audio.readframes(frames)
        with wave.open(destination, 'wb') as audio:
            audio.setparams(params)
            audio.writeframes(pcm)
    except BaseException:
        Path(destination).unlink(missing_ok=True)
        raise


def pcm_description(path: str) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    with wave.open(path, 'rb') as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError('held recovery requires mono PCM16')
        frames, rate = source.getnframes(), source.getframerate()
        while data := source.readframes(16384):
            digest.update(data)
    return frames, rate, digest.hexdigest()
