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
import threading
import time
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
# Above this length, decode keyframes only, so a ten-minute clip stays inside the timeout.
KEYFRAME_SAMPLING_SECONDS = 120
# The keyframe pass gets this long; if it runs out (every frame is a keyframe), the
# remaining budget goes to per-target seeks, which are cheap for exactly those clips.
KEYFRAME_PASS_SECONDS = 25
SEEK_PASS_SECONDS = 30
_MAX_KEPT_LINES = 256
_MAX_LINE_BYTES = 64 * 1024
DECODE_TIMEOUT_SECONDS = 60
# Mean absolute luma difference (0-255) below which another frame adds nothing new.
MIN_FRAME_CHANGE = 6.0
# A client frame is a downscaled still; anything larger is refused before decoding.
MAX_CLIENT_FRAME_PIXELS = 2048 * 2048
# Last sample sits this far before the end so a real frame exists there (a 10 fps clip's
# last frame is 0.1 s before its duration).
END_MARGIN_SECONDS = 0.1
_VIDEO_FORMATS = 'mov,matroska,webm,avi'
_DURATION = re.compile(rb'Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)')
_VIDEO_STREAM = re.compile(rb'Stream #\d+:\d+[^\n]*: Video: ')
_PROBE_LINE = re.compile(rb'Duration: |Stream #')
_PTS_TIME = re.compile(rb'Parsed_showinfo[^\n]*? pts_time:\s*(-?[0-9.]+)')


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


def _run_keeping(command: list[str], keep: re.Pattern, timeout: float, check: bool = True) -> list[bytes]:
    """Run FFmpeg, draining stderr line by line and keeping only lines that match ``keep``.

    Memory stays bounded however much a hostile or metadata-heavy file makes FFmpeg print:
    non-matching lines are discarded as read and at most _MAX_KEPT_LINES are retained.
    Raises subprocess.TimeoutExpired / CalledProcessError like subprocess.run.
    """
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    expired = threading.Event()

    def expire() -> None:
        expired.set()
        process.kill()

    timer = threading.Timer(timeout, expire)
    timer.start()
    kept: list[bytes] = []
    try:
        assert process.stderr is not None
        stderr = process.stderr
        for line in iter(lambda: stderr.readline(_MAX_LINE_BYTES), b''):
            if len(kept) < _MAX_KEPT_LINES and keep.search(line):
                kept.append(line)
        code = process.wait()
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
            process.wait()
    if expired.is_set():
        raise subprocess.TimeoutExpired(command, timeout)
    if check and code != 0:
        raise subprocess.CalledProcessError(code, command)
    return kept


def _probe(executable: str, source: Path) -> tuple[float, bool]:
    """Container duration and whether a picture stream exists (FFmpeg banner, no output)."""
    lines = _run_keeping(
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
        _PROBE_LINE,
        timeout=10,
        check=False,  # no output file: FFmpeg exits 1 after printing the stream summary
    )
    banner = b''.join(lines)
    match = _DURATION.search(banner)
    duration = 0.0
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return duration, bool(_VIDEO_STREAM.search(banner))


def _base_command(executable: str) -> list[str]:
    return [
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


_SCALE = f'scale={CELL_EDGE}:{CELL_EDGE}:force_original_aspect_ratio=decrease:flags=bilinear'


def _load(paths: Sequence[Path]) -> list[Image.Image]:
    frames = []
    for path in paths:
        with Image.open(path) as image:
            frames.append(image.convert('RGB'))
    return frames


def _candidates(
    executable: str, source: Path, duration: float, directory: Path
) -> tuple[list[Image.Image], list[float]]:
    """Up to MAX_CANDIDATES frames from 0 to just before the end, each with its real time.

    One pass; the select filter decides which frames are scaled, logged and written, so the
    output is bounded however the clip is encoded, and showinfo reports each written
    frame's own presentation time.

    - Up to KEYFRAME_SAMPLING_SECONDS: every frame is decoded and the first frame at or
      after each of ``count`` evenly spaced targets (0 … duration - 0.05) is taken.
    - Longer: only keyframes are decoded (fast for a ten-minute clip), taking a keyframe
      once ``step`` seconds have passed since the last one taken; the tail can fall short
      of the end by up to one step plus one keyframe interval.
    """
    span = duration if duration > 0 else 10.0
    count = candidate_count(span) if duration <= KEYFRAME_SAMPLING_SECONDS else MAX_CANDIDATES
    step = max(span - END_MARGIN_SECONDS, 0.0) / max(count - 1, 1)
    command = _base_command(executable)
    command[command.index('-v') + 1] = 'info'  # showinfo reports at info level
    command.append('-hide_banner')
    if duration > KEYFRAME_SAMPLING_SECONDS:
        command += ['-skip_frame', 'nokey']
        chooser = f'isnan(prev_selected_t)+gte(t-prev_selected_t\\,{step:.3f})'
    else:
        chooser = f'gte(t\\,selected_n*{step:.4f})'
    command += [
        '-i',
        str(source),
        '-map',
        '0:v:0',
        '-an',
        '-sn',
        '-vf',
        f'select={chooser},{_SCALE},showinfo',
        '-fps_mode',
        'passthrough',
        '-frames:v',
        str(count),
        '-q:v',
        '5',
        '-f',
        'image2',
        '-y',
        str(directory / 'c%03d.jpg'),
    ]
    budget = KEYFRAME_PASS_SECONDS if duration > KEYFRAME_SAMPLING_SECONDS else DECODE_TIMEOUT_SECONDS
    try:
        lines = _run_keeping(command, _PTS_TIME, timeout=budget)
    except subprocess.TimeoutExpired:
        if duration <= KEYFRAME_SAMPLING_SECONDS:
            raise
        # Every frame is a keyframe (an all-intra screen recording): seek to each target
        # instead, which decodes one frame per target for exactly this kind of clip.
        for path in directory.glob('c*.jpg'):
            path.unlink(missing_ok=True)
        return _seek_candidates(executable, source, duration, directory)
    stamps = [max(0.0, float(m.group(1))) for m in map(_PTS_TIME.search, lines) if m]
    paths = sorted(directory.glob('c*.jpg'))[:count]
    if len(stamps) != len(paths):  # showinfo and the muxer see the same frames in order
        raise VideoFramesError('frame times unavailable')
    if duration > 0:
        stamps = [min(t, duration) for t in stamps]
    return _load(paths), stamps


def _seek_candidates(
    executable: str, source: Path, duration: float, directory: Path
) -> tuple[list[Image.Image], list[float]]:
    """One accurate seek per target, inside a shared budget; for clips where every frame is a keyframe."""
    step = (duration - END_MARGIN_SECONDS) / (MAX_CANDIDATES - 1)
    deadline = time.monotonic() + SEEK_PASS_SECONDS
    paths: list[Path] = []
    times: list[float] = []
    for index in range(MAX_CANDIDATES):
        at = index * step
        output = directory / f's{index:03d}.jpg'
        decoded = _seek_one(executable, source, at, output, deadline)
        if decoded is None and index == MAX_CANDIDATES - 1 and times and at - 1.0 > times[-1]:
            # A low-frame-rate clip can end before the last target: take its final second.
            decoded = _seek_one(executable, source, at - 1.0, output, deadline)
        if decoded is not None and (not times or decoded > times[-1]):
            paths.append(output)
            times.append(decoded)
    return _load(paths), times


def _seek_one(executable: str, source: Path, at: float, output: Path, deadline: float) -> Optional[float]:
    """Write the first frame at or after ``at`` seconds to ``output`` and return its real time.

    ``-copyts`` keeps the source timestamps through the seek, so showinfo reports the decoded
    frame's own time (a 2 fps clip asked for 2.76 s answers with its 3.0 s frame).
    None when nothing decoded there in time.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    command = _base_command(executable)
    command[command.index('-v') + 1] = 'info'  # showinfo reports at info level
    command += [
        '-hide_banner',
        '-copyts',
        '-ss',
        f'{at:.3f}',
        '-i',
        str(source),
        '-map',
        '0:v:0',
        '-an',
        '-sn',
        '-vf',
        f'{_SCALE},showinfo',
        '-frames:v',
        '1',
        '-q:v',
        '5',
        '-y',
        str(output),
    ]
    try:
        lines = _run_keeping(command, _PTS_TIME, timeout=min(remaining, 5))
    except subprocess.SubprocessError:
        return None  # one undecodable spot; the rest still describe the clip
    match = _PTS_TIME.search(lines[0]) if lines else None
    if not match or not output.exists():
        return None
    return max(0.0, float(match.group(1)))


def candidate_count(duration: float) -> int:
    """Frames from 0 to just before the end, at most 4 per second, at most MAX_CANDIDATES."""
    if not math.isfinite(duration) or duration <= END_MARGIN_SECONDS:
        return 1
    return min(MAX_CANDIDATES, int((duration - END_MARGIN_SECONDS) * MAX_CANDIDATE_FPS) + 1)


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
            frames, times = _candidates(executable, source, duration, directory)
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoFramesError('decode failed') from error
    if not frames:
        raise VideoFramesError('no frames')
    if duration <= 0:
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
                # Header only so far: refuse a frame that declares a huge canvas before decoding it.
                if image.format not in ('JPEG', 'PNG'):
                    raise VideoFramesError('frames must be JPEG or PNG')
                if image.width * image.height > MAX_CLIENT_FRAME_PIXELS:
                    raise VideoFramesError('frame too large')
                if image.format == 'JPEG':
                    image.draft('RGB', (CELL_EDGE, CELL_EDGE))  # decode at reduced scale
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
