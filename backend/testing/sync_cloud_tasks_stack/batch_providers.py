"""Deterministic external provider leaves for the batch-lane gauntlet.

Only model/vendor leaves are fake: the GPU words provider, diarizer and model
VAD in the worker process, and the paid legacy STT call that quarantine
recovery issues in the serving process.  Behavior is selected per owner (by
SHA-256 of the owner id) from a runner-written control file, with env defaults
for latency, empty-result rate, failure rate, and batch capacity.  Evidence is
metadata only: owner/PCM hashes, modes, counts, and timings.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import wave
from pathlib import Path
from typing import Any

from .events import write_event

WORD_TOKENS = ('batch', 'stack', 'words')


def owner_hash(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()[:16]


def pcm_hash(pcm: bytes) -> str:
    return hashlib.sha256(pcm).hexdigest()[:16]


def _control_path(name: str) -> Path | None:
    state_dir = os.getenv('OMI_SYNC_STACK_STATE_DIR', '').strip()
    return Path(state_dir) / 'batch-control' / name if state_dir else None


def _read_control(name: str) -> dict[str, Any]:
    path = _control_path(name)
    if path is None or not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f'{name} must be numeric') from error


def _fraction(value: str) -> float:
    return int(value[:8], 16) / 2**32


def words_behavior(owner_id: str, segment_id: str) -> dict[str, Any]:
    """Per-owner override, else env defaults with deterministic per-segment rates."""
    override = _read_control('words.json').get(owner_hash(owner_id))
    if isinstance(override, dict):
        return {'mode': override.get('mode', 'words'), 'latency_ms': float(override.get('latency_ms', 0))}
    mode = 'words'
    sample = _fraction(segment_id)
    failure_rate = _float_env('OMI_BATCH_STACK_WORDS_FAILURE_RATE', 0.0)
    empty_rate = _float_env('OMI_BATCH_STACK_WORDS_EMPTY_RATE', 0.0)
    if sample < failure_rate:
        mode = 'fail'
    elif sample < failure_rate + empty_rate:
        mode = 'empty'
    return {'mode': mode, 'latency_ms': _float_env('OMI_BATCH_STACK_WORDS_LATENCY_MS', 0.0)}


def _words_for(duration: float) -> list[dict[str, Any]]:
    step = max(0.05, min(0.3, duration / (len(WORD_TOKENS) + 1)))
    return [
        {'word': token, 'timestamp': [round(index * step + 0.01, 3), round((index + 1) * step, 3)]}
        for index, token in enumerate(WORD_TOKENS)
        if (index + 1) * step <= duration
    ]


class FakeWordsProvider:
    """Stands in for ParakeetWords.transcribe_batch / recover_empty."""

    def __init__(self, mode: str, latency_ms: float, segment_ids: list[str]):
        self.mode, self.latency_ms, self.segment_ids = mode, latency_ms, segment_ids

    def transcribe_batch(self, samples: list[Any]) -> list[list[dict[str, Any]]]:
        write_event(
            'providers',
            {
                'event': 'words_started',
                'mode': self.mode,
                'segment_ids': self.segment_ids,
                'windows': len(samples),
                'worker_name': os.getenv('OMI_BATCH_STACK_WORKER_NAME', ''),
            },
        )
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)
        write_event(
            'providers',
            {'event': 'words_completed', 'mode': self.mode, 'segment_ids': self.segment_ids, 'windows': len(samples)},
        )
        if self.mode == 'fail':
            raise RuntimeError('controlled words-provider failure')
        if self.mode == 'empty':
            return [[] for _ in samples]
        return [_words_for(len(window) / 16000) for window in samples]

    def recover_empty(self, samples: Any, _max_padded_seconds: float, **_kwargs: Any) -> list[dict[str, Any]] | None:
        write_event('providers', {'event': 'words_padded_retry', 'mode': self.mode, 'segment_ids': self.segment_ids})
        if self.mode == 'empty':
            return []
        return _words_for(len(samples) / 16000)


def fake_vad(samples: Any) -> list[tuple[float, float]]:
    """Model-VAD leaf: the whole canonical capture is speech."""
    return [(0.0, len(samples) / 16000)]


def fake_diarizer(samples: Any) -> dict[str, Any]:
    return {'turns': [{'start': 0.0, 'end': len(samples) / 16000, 'speaker': 'SPEAKER_00'}]}


class ModeRoutingWorker:
    """Run the real PipelineWorker once per provider mode within one pulled batch."""

    def __init__(self, artifacts: Any):
        self.artifacts = artifacts

    def process_batch(self, items: list[Any], **kwargs: Any) -> list[Any]:
        from config.batch_pipeline_providers import provider_config
        from diarizer.batch_pipeline import PipelineWorker
        from diarizer.batch_pipeline_models import StagedAudio

        groups: dict[tuple[str, float], list[Any]] = {}
        for item in items:
            behavior = words_behavior(item.owner_id, item.segment_id)
            groups.setdefault((behavior['mode'], behavior['latency_ms']), []).append(item)
            write_event(
                'providers',
                {
                    'event': 'worker_item_started',
                    'segment_id': item.segment_id,
                    'owner_hash': owner_hash(item.owner_id),
                    'mode': behavior['mode'],
                    'priority': int(item.priority),
                    'worker_name': os.getenv('OMI_BATCH_STACK_WORKER_NAME', ''),
                },
            )
        results: list[Any] = []
        config = provider_config()
        for (mode, latency_ms), group in groups.items():
            provider = FakeWordsProvider(mode, latency_ms, [item.segment_id for item in group])
            staged = StagedAudio(self.artifacts.fetch_audio)
            worker = PipelineWorker(
                decode=staged.decode,
                vad=fake_vad,
                words_providers={config.words: provider},
                recover_words=provider.recover_empty,
                diarizers={config.diarizer: fake_diarizer},
                persist=self.artifacts.persist_result,
                config=config,
                stream_of=staged.stream,
                language_of=staged.language,
            )
            group_results = list(worker.process_batch(group, **kwargs))
            for result in group_results:
                write_event(
                    'providers',
                    {
                        'event': 'worker_item_result',
                        'segment_id': result.segment_id,
                        'result_type': type(result).__name__,
                        'worker_name': os.getenv('OMI_BATCH_STACK_WORKER_NAME', ''),
                    },
                )
            results.extend(group_results)
        return results


def _paid_words(duration: float) -> list[dict[str, Any]]:
    step = max(0.05, min(0.3, duration / (len(WORD_TOKENS) + 1)))
    return [
        {
            'text': token,
            'timestamp': [round(index * step + 0.02, 3), round((index + 1) * step, 3)],
            'speaker': 'SPEAKER_00',
        }
        for index, token in enumerate(WORD_TOKENS)
        if (index + 1) * step <= duration
    ]


def install_paid_stt_fake() -> None:
    """Replace the paid legacy STT leaf used by quarantine recovery.

    The provider sees only canonical WAV bytes, so calls are attributed by a
    hash of their PCM. Latency/mode are read per call from the control file.
    """
    import utils.stt.pre_recorded as pre_recorded

    def paid(audio: bytes, *, provider: str, language: Any = None, **_kwargs: Any) -> tuple[list[dict], str]:
        with wave.open(io.BytesIO(audio), 'rb') as handle:
            duration = handle.getnframes() / float(handle.getframerate())
            digest = pcm_hash(handle.readframes(handle.getnframes()))
        control = _read_control('paid.json').get(digest) or {}
        latency_ms = float(control.get('latency_ms', _float_env('OMI_BATCH_STACK_PAID_LATENCY_MS', 0.0)))
        mode = control.get('mode', 'words')
        write_event('providers', {'event': 'paid_stt_started', 'pcm_hash': digest, 'provider': provider})
        if latency_ms:
            time.sleep(latency_ms / 1000)
        write_event('providers', {'event': 'paid_stt_completed', 'pcm_hash': digest, 'mode': mode})
        if mode == 'fail':
            raise RuntimeError('controlled paid STT failure')
        words = [] if mode == 'empty' else _paid_words(duration)
        return words, 'en'

    pre_recorded.prerecorded_from_bytes = lambda audio, **kwargs: paid(audio, provider='legacy_sync', **kwargs)
    pre_recorded.modulate_prerecorded_from_bytes = lambda audio, **kwargs: paid(audio, provider='modulate', **kwargs)
