"""Yield the shared GPU between bounded backfill quanta, preserving file time.

The original file remains available for whole-file speaker clustering in v2.
No archived audio is changed. Only one temporary quantum exists per request.
"""

import asyncio
import functools
import os
import tempfile
from concurrent.futures import Executor
from typing import Any, Dict

import soundfile as sf

MAX_BACKFILL_SECONDS = 120


def _write_quantum(source: str, target: str, start: int, frames: int) -> None:
    with sf.SoundFile(source) as audio:
        audio.seek(start)
        samples = audio.read(frames, dtype='float32', always_2d=True)
        # Float WAV avoids introducing quantization into decoded source samples.
        sf.write(target, samples, audio.samplerate, format='WAV', subtype='FLOAT')


async def submit_audio(
    engine: Any,
    path: str,
    executor: Executor,
    *,
    packing: bool,
    lane: str = 'backfill',
    owns_file: bool = False,
    queue_deadline: float | None = None,
) -> Dict[str, Any]:
    if not packing or lane == 'live':
        return await engine.submit(path, timestamps=True, owns_file=owns_file, lane=lane, queue_deadline=queue_deadline)
    loop = asyncio.get_running_loop()
    delegated = False
    try:
        info = await loop.run_in_executor(executor, sf.info, path)
        if info.duration <= MAX_BACKFILL_SECONDS:
            delegated = True
            return await engine.submit(path, timestamps=True, lane=lane, owns_file=owns_file)
        quantum = MAX_BACKFILL_SECONDS * info.samplerate
        merged: Dict[str, Any] = {'text': '', 'timestamp': {}}
        text = []
        for start in range(0, info.frames, quantum):
            fd, chunk = tempfile.mkstemp(prefix='parakeet-quantum-', suffix='.wav', dir=os.path.dirname(path) or '.')
            os.close(fd)
            submitted = False
            try:
                write = loop.run_in_executor(executor, functools.partial(_write_quantum, path, chunk, start, quantum))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    # The file writer must finish before unlinking its output.
                    await write
                    raise
                # BatchEngine retains ownership until a running GPU batch finishes,
                # including when the HTTP caller cancels during inference.
                submitted = True
                result = await engine.submit(chunk, timestamps=True, lane=lane, owns_file=True)
                text.append(result.get('text', ''))
                offset = start / info.samplerate
                for key, entries in result.get('timestamp', {}).items():
                    for entry in entries:
                        shifted = dict(entry)
                        for field in ('start', 'end'):
                            if field in shifted:
                                shifted[field] = float(shifted[field]) + offset
                        merged['timestamp'].setdefault(key, []).append(shifted)
            finally:
                if not submitted:
                    os.unlink(chunk)
        merged['text'] = ' '.join(t for t in text if t)
        return merged
    finally:
        if owns_file and not delegated:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
