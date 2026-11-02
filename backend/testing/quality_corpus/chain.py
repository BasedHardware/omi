"""Run the production batch-worker model chain on local corpus units.

Builds the worker through ``diarizer.batch_pipeline_startup.load_worker``, the
same constructor the GPU runtime uses, with in-memory artifacts instead of GCS
and Firestore. Payloads are captured in RAM. Callers turn them into aggregate
scores; no transcript text is written unless the caller asks for corpus output
on public audio.

GPU only: requires the batch-pipeline image (torch, NeMo, pyannote) on exactly
one CUDA device. Imports of the GPU stack happen inside ``build_worker``.
"""

from __future__ import annotations

from contextlib import contextmanager
import io
import os
from typing import Any, Iterator, Mapping
import wave

SAMPLE_RATE = 16000
MAX_ITEMS_PER_PULL = 32


def wav_bytes(samples) -> bytes:
    """float32 [-1, 1] mono 16 kHz -> canonical PCM16 WAV bytes (the worker's staging format)."""
    import numpy as np

    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype('<i2')
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def wav_seconds(body: bytes) -> float:
    with wave.open(io.BytesIO(body), 'rb') as handle:
        return handle.getnframes() / float(handle.getframerate())


class MemoryArtifacts:
    """``fetch_audio``/``persist_result`` pair for ``load_worker``; nothing leaves the process."""

    def __init__(self, units: Mapping[str, bytes]):
        self.units = dict(units)
        self.payloads: dict[str, dict[str, Any]] = {}

    def fetch_audio(self, item) -> bytes:
        return self.units[item.segment_id]

    def persist_result(self, item, payload) -> str:
        self.payloads[item.segment_id] = payload
        return 'mem://quality-corpus/' + item.segment_id


@contextmanager
def env(overrides: Mapping[str, str | None]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def work_items(units: Mapping[str, bytes]):
    from utils.batch_pipeline.contracts import Priority, WorkItem

    return [
        WorkItem(
            segment_id=key,
            owner_id='quality-corpus',
            capture_at=1.0 + index,
            audio_uri='mem://quality-corpus/' + key,
            duration_seconds=wav_seconds(body),
            priority=Priority.FRESH,
        )
        for index, (key, body) in enumerate(units.items())
    ]


def run_chain(units: Mapping[str, bytes], overrides: Mapping[str, str | None]) -> dict[str, Any]:
    """One worker build per pass (some flags are read at startup); returns payloads and outcomes.

    ``overrides`` are applied for both construction and processing, so flags
    read per call (e.g. ``BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED``) and at
    startup (e.g. ``BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED``) both take effect.
    """
    from diarizer.batch_pipeline_startup import load_worker

    artifacts = MemoryArtifacts(units)
    outcomes: dict[str, str] = {}
    with env(overrides):
        worker = load_worker(artifacts)
        items = work_items(units)
        for start in range(0, len(items), MAX_ITEMS_PER_PULL):
            for result in worker.process_batch(items[start : start + MAX_ITEMS_PER_PULL]):
                outcomes[result.segment_id] = type(result).__name__ + ':' + str(getattr(result, 'outcome', ''))
        counts = dict(getattr(worker, 'counts', {}))
    return {'payloads': artifacts.payloads, 'outcomes': outcomes, 'counts': counts}


def labelled_words(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Payload words with the speaker production assigns (``assign_words`` over the turns)."""
    from utils.conversations.final_pass_assignment import assign_words

    words = [{'text': w.get('word', ''), 'timestamp': list(w['timestamp'])} for w in payload.get('words') or []]
    turns = (payload.get('diarization') or {}).get('turns') or []
    labelled = assign_words(words, turns) if turns else [{**w, 'speaker': None} for w in words]
    return [
        {
            'text': w['text'],
            'start': float(w['timestamp'][0]),
            'end': float(w['timestamp'][1]),
            'speaker': w.get('speaker'),
        }
        for w in labelled
    ]
