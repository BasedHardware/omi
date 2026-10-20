"""Video as stills: one sandboxed FFmpeg decode, then images the vision lane already reads.

A clip is never sent to a model as video. One FFmpeg pass samples a bounded set of
candidate frames (at most ``MAX_CANDIDATES``, at most ``MAX_CANDIDATE_FPS``). From those:

- the overview: up to ``MAX_SHEET_FRAMES`` frames chosen for visual change, tiled into one
  numbered contact sheet, so a clip costs about one image regardless of its length;
- the filmstrip: every candidate in one grid, kept so a later question about a time window
  can be answered with denser frames without keeping the original video.

The audio track stays on the existing voice-note transcription path.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

MAX_SHEET_FRAMES = 6
MAX_CANDIDATES = 48
MAX_CANDIDATE_FPS = 4.0
CELL_EDGE = 384
STRIP_COLUMNS = 8
# Keyframe-only decode above this length keeps a ten-minute clip inside the timeout.
KEYFRAME_ONLY_SECONDS = 120
DECODE_TIMEOUT_SECONDS = 60
# Mean absolute luma difference (0-255) below which another frame adds nothing new.
MIN_FRAME_CHANGE = 6.0
_VIDEO_FORMATS = 'mov,matroska,webm,avi'
_DURATION = re.compile(rb'Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)')
_VIDEO_STREAM = re.compile(rb'Stream #\d+:\d+[^\n]*: Video: ')


class VideoFramesError(ValueError):
    """The clip has no decodable picture; the caller falls back to its audio alone."""


@dataclass(frozen=True)
class Filmstrip:
    jpeg: bytes
    times: tuple[float, ...]
    columns: int
    cell_width: int
    cell_height: int


@dataclass(frozen=True)
class VideoDigest:
    duration: float
    sheet: bytes
    sheet_times: tuple[float, ...]
    strip: Filmstrip


def clock(seconds: float, tenths: bool = False) -> str:
    """m:ss, or m:ss.s for a short clip where frames are fractions of a second apart."""
    if tenths:
        tenth = max(0, int(round(seconds * 10)))
        return f'{tenth // 600}:{(tenth % 600) // 10:02d}.{tenth % 10}'
    whole = max(0, int(round(seconds)))
    return f'{whole // 60}:{whole % 60:02d}'


def _decoder() -> str:
    from utils.messaging.adapters.decoder import get_media_decoder

    return get_media_decoder()


def _probe(executable: str, source: Path) -> tuple[float, bool]:
    """Container duration and whether a picture stream exists (FFmpeg banner, no output)."""
    result = subprocess.run(
        [
            executable,
            '-nostdin',
            '-hide_banner',
            '-protocol_whitelist',
            'file',
            '-format_whitelist',
            _VIDEO_FORMATS,
            '-i',
            str(source),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    banner = result.stderr[:65536]
    match = _DURATION.search(banner)
    duration = 0.0
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return duration, bool(_VIDEO_STREAM.search(banner))


def _candidates(executable: str, source: Path, duration: float, directory: Path) -> tuple[list[Image.Image], float]:
    span = duration if duration > 0 else 10.0
    rate = min(MAX_CANDIDATE_FPS, MAX_CANDIDATES / max(span, 0.25))
    command = [
        executable,
        '-nostdin',
        '-v',
        'error',
        '-threads',
        '1',
        '-filter_threads',
        '1',
        '-protocol_whitelist',
        'file',
        '-format_whitelist',
        _VIDEO_FORMATS,
    ]
    if span > KEYFRAME_ONLY_SECONDS:
        command += ['-skip_frame', 'nokey']
    command += [
        '-i',
        str(source),
        '-map',
        '0:v:0',
        '-an',
        '-sn',
        '-vf',
        f'fps={rate:.6f},scale={CELL_EDGE}:{CELL_EDGE}:force_original_aspect_ratio=decrease:flags=bilinear',
        '-frames:v',
        str(MAX_CANDIDATES),
        '-q:v',
        '5',
        '-f',
        'image2',
        '-y',
        str(directory / 'c%03d.jpg'),
    ]
    subprocess.run(
        command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=DECODE_TIMEOUT_SECONDS
    )
    frames = []
    for path in sorted(directory.glob('c*.jpg'))[:MAX_CANDIDATES]:
        with Image.open(path) as image:
            frames.append(image.convert('RGB'))
    return frames, rate


def _signature(image: Image.Image) -> bytes:
    return image.convert('L').resize((16, 16), Image.Resampling.BILINEAR).tobytes()


def _distance(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def select_keyframes(frames: Sequence[Image.Image], limit: int = MAX_SHEET_FRAMES) -> list[int]:
    """First and last frame, then the frames most unlike those already chosen.

    Farthest-point selection on a 16x16 luma signature. A near-static clip (a talking
    head, a video note) stops at three frames instead of six copies of one picture.
    """
    count = len(frames)
    if count <= 2 or limit <= 2:
        return list(range(min(count, max(limit, 1))))
    signatures = [_signature(frame) for frame in frames]
    chosen = [0, count - 1]
    nearest = [min(_distance(s, signatures[0]), _distance(s, signatures[-1])) for s in signatures]
    while len(chosen) < min(limit, count):
        index = max(
            (i for i in range(count) if i not in chosen),
            # Ties go to the frame farthest in time from the chosen ones, so a static clip spreads out.
            key=lambda i: (nearest[i], min(abs(i - c) for c in chosen)),
        )
        if nearest[index] < MIN_FRAME_CHANGE and len(chosen) >= 3:
            break
        chosen.append(index)
        nearest = [min(nearest[i], _distance(signatures[i], signatures[index])) for i in range(count)]
    return sorted(chosen)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without scalable default font
        return ImageFont.load_default()


def contact_sheet(frames: Sequence[Image.Image], times: Sequence[float]) -> bytes:
    """Tile frames into one numbered JPEG; each cell is labelled with its number and time."""
    if not frames:
        raise VideoFramesError('no frames')
    count = len(frames)
    columns = 1 if count == 1 else 2 if count in (2, 4) else 3
    rows = math.ceil(count / columns)
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    gap = 4
    sheet = Image.new('RGB', (columns * width + (columns - 1) * gap, rows * height + (rows - 1) * gap), (16, 16, 16))
    draw = ImageDraw.Draw(sheet)
    font = _font(max(14, max(width, height) // 18))
    tenths = max(times, default=0) < 60
    for index, (frame, at) in enumerate(zip(frames, times)):
        left = (index % columns) * (width + gap) + (width - frame.width) // 2
        top = (index // columns) * (height + gap) + (height - frame.height) // 2
        sheet.paste(frame, (left, top))
        label = f'{index + 1}  {clock(at, tenths)}'
        box = draw.textbbox((0, 0), label, font=font)
        draw.rectangle((left, top, left + box[2] + 10, top + box[3] + 8), fill=(0, 0, 0))
        draw.text((left + 5, top + 4), label, fill=(255, 255, 255), font=font)
    output = BytesIO()
    sheet.save(output, 'JPEG', quality=82)
    return output.getvalue()


def filmstrip(frames: Sequence[Image.Image], times: Sequence[float]) -> Filmstrip:
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    columns = min(STRIP_COLUMNS, len(frames))
    rows = math.ceil(len(frames) / columns)
    strip = Image.new('RGB', (columns * width, rows * height), (0, 0, 0))
    for index, frame in enumerate(frames):
        strip.paste(frame, ((index % columns) * width, (index // columns) * height))
    output = BytesIO()
    strip.save(output, 'JPEG', quality=78)
    return Filmstrip(output.getvalue(), tuple(round(t, 2) for t in times), columns, width, height)


def window_sheet(
    strip_jpeg: bytes,
    times: Sequence[float],
    columns: int,
    cell_width: int,
    cell_height: int,
    start: float,
    end: float,
    limit: int = MAX_SHEET_FRAMES,
) -> tuple[bytes, tuple[float, ...]]:
    """A contact sheet of up to ``limit`` filmstrip frames, evenly spaced inside [start, end]."""
    if not times or columns <= 0:
        raise VideoFramesError('empty filmstrip')
    if end < start:
        start, end = end, start
    inside = [i for i, t in enumerate(times) if start - 1e-6 <= t <= end + 1e-6]
    if not inside:
        middle = (start + end) / 2
        inside = [min(range(len(times)), key=lambda i: abs(times[i] - middle))]
    if len(inside) > limit:
        step = (len(inside) - 1) / (limit - 1)
        inside = sorted({inside[round(k * step)] for k in range(limit)})
    with Image.open(BytesIO(strip_jpeg)) as image:
        strip = image.convert('RGB')
    frames = []
    for index in inside:
        left, top = (index % columns) * cell_width, (index // columns) * cell_height
        if top + cell_height > strip.height or left + cell_width > strip.width:
            raise VideoFramesError('filmstrip layout mismatch')
        frames.append(strip.crop((left, top, left + cell_width, top + cell_height)))
    chosen = tuple(times[i] for i in inside)
    return contact_sheet(frames, chosen), chosen


def digest_video(data: bytes, duration_hint: float = 0, executable: Optional[str] = None) -> VideoDigest:
    """Decode an untrusted clip to an overview sheet and filmstrip, or raise VideoFramesError.

    File-only protocols and a demuxer allowlist keep a hostile container from fetching
    remote resources; the decode is single-threaded and time-bounded.
    """
    executable = executable or _decoder()
    try:
        with tempfile.TemporaryDirectory(prefix='omi-video-') as name:
            directory = Path(name)
            source = directory / 'input'
            source.write_bytes(data)
            duration, has_picture = _probe(executable, source)
            if not has_picture:
                raise VideoFramesError('no video stream')
            if duration <= 0:
                duration = float(duration_hint or 0)
            frames, rate = _candidates(executable, source, duration, directory)
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoFramesError('decode failed') from error
    if not frames:
        raise VideoFramesError('no frames')
    times = [i / rate for i in range(len(frames))]
    if duration > 0:
        times = [min(t, duration) for t in times]
    else:
        duration = times[-1]
    picked = select_keyframes(frames)
    sheet_times = tuple(round(times[i], 2) for i in picked)
    return VideoDigest(
        duration=round(duration, 2),
        sheet=contact_sheet([frames[i] for i in picked], sheet_times),
        sheet_times=sheet_times,
        strip=filmstrip(frames, times),
    )


def digest_frames(images: Sequence[bytes], times: Sequence[float], duration: float) -> VideoDigest:
    """The same digest from frames a client already sampled (no video upload).

    Untrusted images are decoded with Pillow's size guard, downscaled to the candidate edge,
    and capped at ``MAX_CANDIDATES``; times are clamped to the clip and must ascend.
    """
    if not images or len(images) != len(times):
        raise VideoFramesError('frames and times differ')
    if len(images) > MAX_CANDIDATES:
        raise VideoFramesError('too many frames')
    span = max(0.0, float(duration))
    clean_times = [min(max(0.0, float(t)), span) if span else max(0.0, float(t)) for t in times]
    if any(not math.isfinite(t) for t in clean_times) or clean_times != sorted(clean_times):
        raise VideoFramesError('frame times must ascend')
    frames = []
    for blob in images:
        try:
            with Image.open(BytesIO(blob)) as image:
                if image.format not in ('JPEG', 'PNG'):
                    raise VideoFramesError('frames must be JPEG or PNG')
                frame = image.convert('RGB')
        except (OSError, Image.DecompressionBombError) as error:
            raise VideoFramesError('unreadable frame') from error
        frame.thumbnail((CELL_EDGE, CELL_EDGE))
        frames.append(frame)
    # The filmstrip grid needs one cell size; pad mixed sizes onto a common canvas.
    width, height = max(f.width for f in frames), max(f.height for f in frames)
    frames = [_pad(f, width, height) for f in frames]
    picked = select_keyframes(frames)
    sheet_times = tuple(round(clean_times[i], 2) for i in picked)
    return VideoDigest(
        duration=round(span or clean_times[-1], 2),
        sheet=contact_sheet([frames[i] for i in picked], sheet_times),
        sheet_times=sheet_times,
        strip=filmstrip(frames, clean_times),
    )


def _pad(frame: Image.Image, width: int, height: int) -> Image.Image:
    if frame.size == (width, height):
        return frame
    canvas = Image.new('RGB', (width, height), (0, 0, 0))
    canvas.paste(frame, ((width - frame.width) // 2, (height - frame.height) // 2))
    return canvas


def describe(duration: float, sheet_times: Sequence[float], transcript: str = '', tool_hint: bool = True) -> str:
    """The note the chat model sees for a video: length, frame times, and what was said."""
    seconds = max(1, round(duration))
    stamps = ', '.join(clock(t, duration < 60) for t in sheet_times)
    frames = f'{len(sheet_times)} frame' + ('' if len(sheet_times) == 1 else 's')
    speech = f'Audio transcript: {transcript.strip()}' if transcript.strip() else 'No speech in the audio.'
    hint = (
        'Use search_files_tool to look at it; pass start_seconds/end_seconds for a closer look at a moment. '
        if tool_hint
        else ''
    )
    return f'[Video, {seconds} s: {frames} ({stamps}) are attached as one numbered image. {hint}{speech}]'
