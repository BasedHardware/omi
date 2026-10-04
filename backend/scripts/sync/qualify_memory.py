#!/usr/bin/env python3
"""Offline sync tail stress; executes unchanged decode/VAD functions from source.

No cloud clients or model inference. The fake VAD marks the complete synthetic
recording as speech. Files on macOS are disk-backed: RSS + their logical bytes
is the conservative tmpfs charge estimate, not a Linux cgroup measurement.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import struct
import threading
import time
from types import SimpleNamespace
from typing import Any, Optional
import wave

import resource
import numpy as np
from pydub import AudioSegment

BACKEND = Path(__file__).resolve().parents[2]
MIB = 1024**2


def load_functions(relative: str, names: set[str], namespace: dict) -> None:
    tree = ast.parse((BACKEND / relative).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == names
    for node in functions:
        node.decorator_list = []
    exec(compile(ast.Module(body=functions, type_ignores=[]), relative, 'exec'), namespace)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument(
        '--file-mib', type=int, default=200, help='per-file encoded MiB; bounded mode uses total batch budget'
    )
    parser.add_argument('--batch-files', type=int, default=1)
    parser.add_argument('--bounded', action='store_true')
    parser.add_argument('--pcm8', action='store_true')
    parser.add_argument('--concurrency', type=int, default=3)
    parser.add_argument('--retained-attempts', type=int, default=1)
    parser.add_argument('--tmpfs-stop-mib', type=int, default=4096)
    args = parser.parse_args()
    if min(args.file_mib, args.batch_files, args.concurrency) <= 0 or args.retained_attempts < 0:
        parser.error('sizes/counts must be positive, retained attempts nonnegative')
    args.root.mkdir(parents=True, exist_ok=False)
    owned = args.output.parent / 'owned-pids.txt'
    with owned.open('a') as file:
        file.write(f'{os.getpid()}\n')
    peaks = {'rss_bytes': 0, 'tmpfs_bytes': 0, 'rss_plus_tmpfs_bytes': 0}
    stop = threading.Event()
    samples = 0
    failure = None
    logger = logging.getLogger('synthetic-sync')
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    namespace = dict(
        os=os,
        wave=wave,
        struct=struct,
        Optional=Optional,
        Any=Any,
        logger=logger,
        io=io,
        sanitize=lambda value: value,
        threading=threading,
        raise_sync_storage_pressure=lambda error: None,
        np=np,
        List=list,
        Dict=dict,
        VAD_SAMPLE_RATE=16000,
        MAX_SYNC_FRAME_BYTES=65536,
        AudioSegment=AudioSegment,
        contextlib=contextlib,
        MAX_VAD_SEGMENT_SECONDS=300,
        _bounded_exception_type=lambda error: type(error).__name__,
        get_timestamp_from_path=lambda path: int(Path(path).stem.split('_')[-1]),
    )
    load_functions('utils/sync/playback.py', {'pcm_to_wav'}, namespace)
    namespace['sync_playback'] = SimpleNamespace(pcm_to_wav=namespace['pcm_to_wav'])
    load_functions('utils/sync/files.py', {'decode_pcm_file_to_wav', 'get_wav_duration'}, namespace)
    load_functions('utils/sync/pipeline.py', {'_merge_and_cap_vad_segments', 'retrieve_vad_segments'}, namespace)
    load_functions('utils/stt/vad.py', {'_run_file_vad'}, namespace)
    namespace['_segments_from_16khz_samples'] = lambda samples, **kwargs: [{'start': 0, 'end': len(samples) / 16000}]
    namespace['vad_is_empty'] = lambda path, **kwargs: namespace['_run_file_vad'](path)

    def measure() -> None:
        nonlocal samples
        while not stop.is_set():
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if os.uname().sysname != 'Darwin':
                rss *= 1024
            # Directory walk captures actual intermediates, including writes in flight.
            files = 0
            for directory, _, names in os.walk(args.root):
                for name in names:
                    try:
                        files += (Path(directory) / name).stat().st_size
                    except FileNotFoundError:
                        pass
            peaks['rss_bytes'] = max(peaks['rss_bytes'], rss)
            peaks['tmpfs_bytes'] = max(peaks['tmpfs_bytes'], files)
            peaks['rss_plus_tmpfs_bytes'] = max(peaks['rss_plus_tmpfs_bytes'], rss + files)
            samples += 1
            stop.wait(0.005)

    def write_raw(path: Path) -> None:
        # Exactly the multipart per-part ceiling; frames stay under 65536 bytes.
        remaining = args.file_mib * MIB // args.batch_files if args.bounded else args.file_mib * MIB
        if args.pcm8:
            # 32 MiB of PCM8 at 16 kHz is exactly 64 MiB after VAD conversion:
            # longest accepted audio duration, independent of framing overhead.
            remaining //= 2
        with path.open('wb') as file:
            while remaining >= (1 if args.pcm8 else 6):
                size = min(65536, remaining) if args.pcm8 else min(65536, remaining - 4) & ~1
                frame = struct.pack('<I', size) + b'\0' * size
                file.write(frame)
                remaining -= size if args.pcm8 else len(frame)

    def write_retained(path: Path) -> None:
        # Prior cancelled attempt retains decoded audio and all-speech segments.
        # file_mib is the total batch audio budget in bounded mode.
        with wave.open(str(path), 'wb') as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(16000)
            for _ in range(args.file_mib * 16):
                file.writeframes(b'\0' * 65536)

    barrier = threading.Barrier(args.concurrency)

    def run_request(index: int) -> None:
        directory = args.root / f'job-{index}'
        directory.mkdir()
        paths = []
        for file_index in range(args.batch_files):
            codec = 'pcm8' if args.pcm8 else 'pcm16'
            path = directory / f'audio_phonemic_{codec}_16000_1_fs160_{1710000000 + file_index}.bin'
            write_raw(path)
            paths.append(path)
        if args.bounded:
            namespace['validate_backfill_paths']([str(path) for path in paths])
        barrier.wait()
        wavs = []
        for path in paths:
            wav = path.with_suffix('.wav')
            assert namespace['decode_pcm_file_to_wav'](str(path), str(wav), sample_width=1 if args.pcm8 else 2)
            path.unlink()  # decode_files_to_wav cleans each original after decode.
            wavs.append(wav)
        segmented = set()
        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(lambda wav: namespace['retrieve_vad_segments'](str(wav), segmented), wavs))
        # Phase barriers mirror production: keep original WAVs until all VAD workers finish.
        for wav in wavs:
            wav.unlink()
        # Simulate provider failure and another attempt with the same job paths.
        for path in paths:
            write_raw(path)
        for path in paths:
            wav = path.with_suffix('.wav')
            assert namespace['decode_pcm_file_to_wav'](str(path), str(wav), sample_width=1 if args.pcm8 else 2)
            path.unlink()
        # Retry writes segments to the same names; no artificial per-attempt growth.
        for path in paths:
            namespace['retrieve_vad_segments'](str(path.with_suffix('.wav')), segmented)

    if args.bounded:
        import sys

        sys.path.insert(0, str(BACKEND))
        from utils.sync.input_limits import validate_backfill_paths

        namespace['validate_backfill_paths'] = validate_backfill_paths
    monitor = threading.Thread(target=measure, daemon=True)
    monitor.start()
    started = time.monotonic()
    try:
        for index in range(args.concurrency * args.retained_attempts):
            directory = args.root / f'cancelled-{index}'
            directory.mkdir()
            write_retained(directory / 'original.wav')
            write_retained(directory / 'segments.wav')
        # Bound the experiment itself; crossing 4 GiB already falsifies 4-GiB safety.
        planned_raw = args.concurrency * args.file_mib * MIB * (1 if args.bounded else args.batch_files)
        retained = sum(path.stat().st_size for path in args.root.rglob('*.wav'))
        if retained + planned_raw > args.tmpfs_stop_mib * MIB:
            failure = 'batch rejected by experiment safety budget before allocating; accepted runtime has no such guard'
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                list(pool.map(run_request, range(args.concurrency)))
    finally:
        time.sleep(0.05)
        stop.set()
        monitor.join()
        result = {
            'source_functions': ['decode_pcm_file_to_wav', 'pcm_to_wav', '_run_file_vad', 'retrieve_vad_segments'],
            'parameters': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            'platform': os.uname().sysname,
            'rss_method': 'getrusage process high-water RSS; sum is conservative sampled upper envelope',
            'duration_seconds': time.monotonic() - started,
            'samples': samples,
            'peaks': peaks,
            'failure': failure,
            'under_4gib_without_runtime_baseline': peaks['rss_plus_tmpfs_bytes'] < 4 * 1024**3 and failure is None,
        }
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        shutil.rmtree(args.root)  # Only this freshly created synthetic directory.


if __name__ == '__main__':
    main()
