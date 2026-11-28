"""The local recorder for ``--stt record-local``: production's Parakeet batch model on this machine's CPU.

``nvidia/parakeet-tdt-0.6b-v3`` at the production revision (``ASR_REVISION`` in
``diarizer/batch_pipeline_startup.py``), fp32 on CPU, decoded by the product's own
``diarizer.batch_pipeline_models.pin_parakeet_decoding(model, cuda_graphs=False)`` and
``ParakeetWords.transcribe_batch`` (``greedy_batch``, word timestamps on, CUDA graphs off).

Windows (``--windows``): ``vad`` (default) transcribes production's local Silero VAD spans packed into windows of
at most 30 s (:func:`speech_windows`), the way the batch worker cuts speech before ASR; ``fixed`` cuts plain 30 s
windows the way ``ParakeetBatchAdapter`` does (``adapters.windowed_words``). Fixed windows that mix speech with
exact digital silence make the CPU model return no words for the whole window (measured 2026-11-26 on a two-voice
LibriSpeech mix: 38 of 102 words fixed, 102 of 102 with VAD spans). The recorder never adds noise to the audio.

Its cassettes are keyed ``parakeet_local`` / ``parakeet-tdt-0.6b-v3@<revision[:8]>/cpu-fp32`` (fixed windows;
VAD spans add ``/vad``, so a cassette recorded one way is never read as the other) with ``source: local`` and
cost zero, so a CPU fp32 result is never filed or read as a production GPU result. The cassette's
``source_detail`` records the windowing mode and the VAD model and parameters.
Parakeet gives no speaker labels and no language: words carry neither, and the scenario's diarization
then has one anonymous speaker.

What a local cassette is evidence for: everything downstream of the words (VAD windows, projection,
landing, Finish, planner, Home). Not transcription quality: on synthetic ``say`` speech the 2026-11-25
spike measured a word error rate of 2.3 % on 60 s and 7.2 % on 10 min in 30 s windows.

Optional extra, never in the default install: ``torch``, ``nemo_toolkit[asr]`` and the product import
chain are pinned in ``testing/pipeline_lab/requirements-local-stt.txt``. Nothing here imports them at
module import time. The model runs either in this interpreter (when it has the extra) or, normally, in a
separate venv named by ``$OMI_PIPELINE_LAB_LOCAL_STT_PYTHON``, which this module starts as a worker::

    python -m testing.pipeline_lab.cassette.local_parakeet --pcm FILE.pcm --out FILE.json [--window-seconds 30]

(cwd ``backend/``). The first run downloads the 2.51 GB checkpoint into ``$HF_HOME``; set
``HF_HUB_OFFLINE=1`` afterwards to run with no network at all.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Optional, Sequence

from testing.pipeline_lab.cassette.adapters import windowed_words
from testing.pipeline_lab.cassette.format import BYTES_PER_SECOND, Word
from testing.pipeline_lab.cassette.local import LocalRecorder, LocalRecorderNotInstalled, LocalWord

BACKEND = Path(__file__).resolve().parents[3]
STARTUP = BACKEND / 'diarizer' / 'batch_pipeline_startup.py'
REQUIREMENTS = Path(__file__).resolve().parents[1] / 'requirements-local-stt.txt'
MODEL_ID = 'nvidia/parakeet-tdt-0.6b-v3'
CHECKPOINT = 'parakeet-tdt-0.6b-v3.nemo'
PROVIDER = 'parakeet_local'
ADAPTER = 'parakeet_local'
PYTHON_ENV = 'OMI_PIPELINE_LAB_LOCAL_STT_PYTHON'
WINDOW_SECONDS = 30.0
WINDOW_MODES = ('vad', 'fixed')
DEFAULT_WINDOWS = 'vad'
VAD_JOIN_GAP = 0.3  # seconds: neighbouring speech spans closer than this share a window
VAD_PAD = 0.2  # seconds of context kept on each side of a speech span
VAD_MODEL = 'silero_vad.onnx (utils/stt/local_vad.py, threshold 0.5)'

INSTALL = (
    'the local Parakeet recorder needs the optional local-STT extra, in its own venv outside the repository '
    '(never the backend .venv): `uv venv -p python3.11 /Volumes/scratch/local-stt/venv && uv pip install '
    '-p /Volumes/scratch/local-stt/venv/bin/python -r backend/testing/pipeline_lab/requirements-local-stt.txt`, '
    f'then `export {PYTHON_ENV}=/Volumes/scratch/local-stt/venv/bin/python HF_HOME=/Volumes/scratch/local-stt/hf` '
    '(the first run downloads the 2.51 GB model; add HF_HUB_OFFLINE=1 after that)'
)


def asr_revision(startup: Path = STARTUP) -> str:
    """Production's pinned checkpoint revision, read from source (importing the module needs the GPU deps)."""
    match = re.search(r"^ASR_REVISION\s*=\s*'([0-9a-f]{40})'", startup.read_text(encoding='utf-8'), re.M)
    if not match:
        raise RuntimeError(f'ASR_REVISION not found in {startup.name}')
    return match.group(1)


def model_key(revision: str, windows: str = 'fixed') -> str:
    """The cassette model key. Fixed windows keep the original key (every cassette recorded before VAD spans
    existed used them); VAD spans add ``/vad``."""
    if windows not in WINDOW_MODES:
        raise ValueError(f'windows must be one of {WINDOW_MODES}')
    base = f'parakeet-tdt-0.6b-v3@{revision[:8]}/cpu-fp32'
    return base + '/vad' if windows == 'vad' else base


def windowing_detail(windows: str) -> dict[str, Any]:
    """What a cassette records about how its audio was cut (``Cassette.source_detail``)."""
    if windows == 'fixed':
        return {'windows': 'fixed', 'window_seconds': WINDOW_SECONDS}
    return {
        'windows': 'vad',
        'vad': {'model': VAD_MODEL, 'max_seconds': WINDOW_SECONDS, 'join_gap': VAD_JOIN_GAP, 'pad': VAD_PAD},
    }


def _has_extra() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ('torch', 'nemo'))


# ---- the model (only in an interpreter with the extra) ----------------------------------------------


class ParakeetCPU:
    """The checkpoint loaded once, decoded through the product's ``ParakeetWords``."""

    def __init__(self, revision: str, *, load: Optional[Callable[[str], Any]] = None):
        self.revision = revision
        self._load = load or _load_product_words
        self._words: Any = None

    def window(self, chunk: bytes, language: Optional[str]) -> tuple[list[Word], None]:
        import numpy as np

        if self._words is None:
            self._words = self._load(self.revision)
        samples = np.frombuffer(chunk, dtype='<i2').astype(np.float32) / 32768.0
        raw = self._words.transcribe_batch([samples])[0]
        return [Word(float(w['timestamp'][0]), float(w['timestamp'][1]), str(w['word'])) for w in raw], None


def _load_product_words(revision: str) -> Any:
    try:
        import nemo.collections.asr as nemo_asr
        import torch
        from huggingface_hub import hf_hub_download

        from diarizer.batch_pipeline_models import ParakeetWords, pin_parakeet_decoding
    except ImportError as error:
        raise LocalRecorderNotInstalled(f'{error}. {INSTALL}') from None
    checkpoint = hf_hub_download(MODEL_ID, CHECKPOINT, revision=revision)
    model = nemo_asr.models.ASRModel.restore_from(checkpoint, map_location='cpu').to(torch.float32).eval()
    pin_parakeet_decoding(model, cuda_graphs=False)
    return ParakeetWords(model, cuda_graphs=False)


def transcribe_pcm(
    pcm16: bytes, language: Optional[str], *, engine: Any, window_seconds: float = WINDOW_SECONDS
) -> list[Word]:
    return windowed_words(pcm16, language, window_seconds, engine.window)[0]


def transcribe_spans(pcm16: bytes, language: Optional[str], spans: list, *, engine: Any) -> list[Word]:
    """Each ``[start, end]`` window on its own, words shifted onto the recording clock."""
    words: list[Word] = []
    for start, end in spans:
        left, right = int(start * 16000) * 2, int(end * 16000) * 2
        found, _ = engine.window(pcm16[left:right], language)
        words.extend(Word(w.start + start, w.end + start, w.text) for w in found)
    return words


def speech_windows(
    pcm16: bytes,
    *,
    max_seconds: float = WINDOW_SECONDS,
    join_gap: float = VAD_JOIN_GAP,
    pad: float = VAD_PAD,
    segments: Optional[Callable[[bytes], list]] = None,
) -> list[list[float]]:
    """Production's local Silero VAD spans packed into windows of at most ``max_seconds``, the way the batch
    worker cuts speech before ASR. Fixed 30 s windows that mix speech with digital silence or abrupt level
    changes make the CPU model return no words for the whole window (measured 2026-11-26: 38 of 102 words on a
    two-voice LibriSpeech mix); VAD-packed windows return all of them."""
    if segments is None:
        from utils.stt.local_vad import offline_pcm_speech_segments as segments

    duration = len(pcm16) / 32000
    windows: list[list[float]] = []
    for span in segments(pcm16):
        start, end = max(0.0, span['start'] - pad), min(duration, span['end'] + pad)
        if windows:
            # Windows never overlap: a word in shared padding would be transcribed by both and recorded twice.
            start = max(start, windows[-1][1])
            if end <= start:
                continue
        if windows and start - windows[-1][1] <= join_gap and end - windows[-1][0] <= max_seconds:
            windows[-1][1] = end
            continue
        while end - start > max_seconds:
            windows.append([start, start + max_seconds])
            start += max_seconds
        windows.append([start, end])
    return [[round(a, 3), round(b, 3)] for a, b in windows if b > a]


# ---- recognizers ----------------------------------------------------------------------------------


def transcribe(
    pcm16: bytes,
    language: Optional[str],
    *,
    engine: Any,
    windows: str = DEFAULT_WINDOWS,
    spans: Optional[list] = None,
    vad: Optional[Callable[[bytes], list]] = None,
) -> list[Word]:
    """Words for ``pcm16`` the way ``windows`` says: VAD-packed spans (``spans`` when given, else
    :func:`speech_windows`) or fixed 30 s windows."""
    if windows not in WINDOW_MODES:
        raise ValueError(f'windows must be one of {WINDOW_MODES}')
    if windows == 'fixed':
        return transcribe_pcm(pcm16, language, engine=engine)
    if spans is None:
        spans = speech_windows(pcm16, segments=vad)
    return transcribe_spans(pcm16, language, spans, engine=engine)


class InProcess:
    def __init__(self, revision: str, windows: str = DEFAULT_WINDOWS):
        self.engine = ParakeetCPU(revision)
        self.windows = windows

    def __call__(self, pcm16: bytes, language: Optional[str]) -> list[Word]:
        return transcribe(pcm16, language, engine=self.engine, windows=self.windows)


def _private_work_root() -> Path:
    """Where the worker's PCM and words go: an owner-only directory under the scenario lab root, never the
    system temp directory (private audio and words stay inside the lab root, even if the process is killed)."""
    from testing.pipeline_lab.scenario.paths import private_lab_root
    from testing.pipeline_lab.store import ensure_private_dir

    return ensure_private_dir(private_lab_root() / 'tmp' / 'local-stt')


class Worker:
    """Runs the model in the extra's venv: PCM in a 0600 file under the private lab root, words back as JSON."""

    def __init__(
        self,
        python: str,
        revision: str,
        *,
        run: Callable[..., Any] = subprocess.run,
        work_root: Optional[Path] = None,
        windows: str = 'fixed',
        vad: Optional[Callable[[bytes], list]] = None,
    ):
        if windows not in WINDOW_MODES:
            raise ValueError(f'windows must be one of {WINDOW_MODES}')
        self.python, self.revision, self._run, self._work_root = python, revision, run, work_root
        self.windows, self._vad = windows, vad

    def __call__(self, pcm16: bytes, language: Optional[str], spans: Optional[list] = None) -> list[LocalWord]:
        from testing.pipeline_lab.store import ensure_private_dir

        if spans is None and self.windows == 'vad':
            # VAD runs here (the backend venv has the product's Silero model); the worker gets the spans.
            spans = speech_windows(pcm16, segments=self._vad)
        if spans is not None and not spans:
            return []  # no speech: nothing to transcribe

        base = ensure_private_dir(self._work_root) if self._work_root is not None else _private_work_root()
        with tempfile.TemporaryDirectory(prefix='plab-local-stt-', dir=base) as work:
            pcm_path, out_path = Path(work, 'audio.pcm'), Path(work, 'words.json')
            fd = os.open(pcm_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(pcm16)
            command = [self.python, '-m', 'testing.pipeline_lab.cassette.local_parakeet']
            command += ['--pcm', str(pcm_path), '--out', str(out_path), '--revision', self.revision]
            if language:
                command += ['--language', language]
            if spans is not None:
                spans_path = Path(work, 'spans.json')
                spans_path.write_text(json.dumps(spans))
                command += ['--spans', str(spans_path)]
            timeout = 600 + 4 * len(pcm16) / BYTES_PER_SECOND
            done = self._run(command, cwd=BACKEND, capture_output=True, text=True, timeout=timeout)
            if done.returncode != 0:
                tail = '\n'.join((done.stderr or '').strip().splitlines()[-12:])
                if 'LocalRecorderNotInstalled' in tail or 'ModuleNotFoundError' in tail:
                    raise LocalRecorderNotInstalled(f'{self.python}: {tail.splitlines()[-1]}. {INSTALL}')
                raise RuntimeError(f'local Parakeet worker exited {done.returncode}:\n{tail}')
            value = json.loads(out_path.read_text(encoding='utf-8'))
        if value.get('revision') != self.revision:
            raise RuntimeError('local Parakeet worker ran a different revision than the cassette key')
        return [LocalWord(w['start'], w['end'], w['text']) for w in value['words']]


def _not_installed(pcm16: bytes, language: Optional[str]) -> list[Word]:
    raise LocalRecorderNotInstalled(INSTALL)


def recorder(windows: str = DEFAULT_WINDOWS) -> LocalRecorder:
    """Parakeet on this machine: the worker venv when ``$OMI_PIPELINE_LAB_LOCAL_STT_PYTHON`` names one, else
    this interpreter when it has the extra, else a not-installed recorder that explains how to install.
    ``windows``: ``vad`` (default, VAD-packed speech spans) or ``fixed`` (30 s windows)."""
    revision = asr_revision()
    model = model_key(revision, windows)
    detail = windowing_detail(windows)
    python = os.environ.get(PYTHON_ENV, '').strip()
    if python:
        if not os.access(python, os.X_OK):
            return LocalRecorder(PROVIDER, model, _missing_python(python), installed=False, detail=detail)
        return LocalRecorder(PROVIDER, model, Worker(python, revision, windows=windows), detail=detail)
    if _has_extra():
        return LocalRecorder(PROVIDER, model, InProcess(revision, windows), detail=detail)
    return LocalRecorder(PROVIDER, model, _not_installed, installed=False, detail=detail)


def _missing_python(python: str) -> Callable[[bytes, Optional[str]], list[Word]]:
    def fail(pcm16: bytes, language: Optional[str]) -> list[Word]:
        raise LocalRecorderNotInstalled(f'{PYTHON_ENV}={python} is not an executable interpreter. {INSTALL}')

    return fail


# ---- worker entry ---------------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.cassette.local_parakeet')
    parser.add_argument('--pcm', required=True, help='16 kHz mono PCM16LE')
    parser.add_argument('--out', required=True)
    parser.add_argument('--revision', default=None)
    parser.add_argument('--language', default=None)
    parser.add_argument('--window-seconds', type=float, default=WINDOW_SECONDS)
    parser.add_argument('--spans', default=None, help='JSON [[start, end], ...] seconds: transcribe only these windows')
    parser.add_argument(
        '--windows', choices=WINDOW_MODES, default='fixed', help='without --spans: fixed 30 s windows or VAD spans'
    )
    args = parser.parse_args(argv)
    revision = asr_revision()
    if args.revision not in (None, revision):
        raise SystemExit('--revision differs from ASR_REVISION in this checkout')
    started = time.perf_counter()
    pcm16 = Path(args.pcm).read_bytes()
    engine = ParakeetCPU(revision)
    if args.spans:
        words = transcribe_spans(pcm16, args.language, json.loads(Path(args.spans).read_text()), engine=engine)
    elif args.windows == 'vad':
        words = transcribe(pcm16, args.language, engine=engine, windows='vad')
    else:
        words = transcribe_pcm(pcm16, args.language, engine=engine, window_seconds=args.window_seconds)
    value = {
        'revision': revision,
        'model': model_key(revision),
        'seconds': round(time.perf_counter() - started, 3),
        'words': [{'start': w.start, 'end': w.end, 'text': w.text} for w in words],
    }
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(value, handle)
    return 0


if __name__ == '__main__':
    sys.exit(main())
