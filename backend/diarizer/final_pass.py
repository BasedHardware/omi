"""In-memory community-1 turns and Omi v2-space voice centroids."""

import io
import time
import wave
from functools import lru_cache
from typing import Any
import os

import numpy as np
import torch  # type: ignore[reportMissingImports]  # GPU runtime dependency
from fastapi import HTTPException
from pyannote.audio import Pipeline  # type: ignore[reportMissingImports]  # GPU runtime dependency
from metrics import AUDIO, RTF, GPU_MEMORY
from utils.stt.diarization_turns import overlap_regions, exclusive_from_activity
from utils.stt.voice_centroids import (
    COMMUNITY_MODEL_REVISION,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    EMBEDDING_SPACE,
    select_evidence,
    pool_centroids,
)

from admission import GPU_LOCK
from embedding import embedding_inference_v2

MODEL_REVISION = COMMUNITY_MODEL_REVISION
MAX_AUDIO_SECONDS = 7200


@lru_cache(maxsize=1)
def pipeline() -> Any:
    model = Pipeline.from_pretrained(
        'pyannote/speaker-diarization-community-1', revision=MODEL_REVISION, token=os.getenv('HUGGINGFACE_TOKEN')
    )
    return model.to(torch.device('cuda' if torch.cuda.is_available() else 'cpu'))


def decode_audio(body: bytes | bytearray, content_type: str) -> Any:
    if content_type == 'audio/wav':
        try:
            with wave.open(io.BytesIO(body), 'rb') as handle:
                if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, 16000):
                    raise ValueError
                body = handle.readframes(handle.getnframes())
        except (wave.Error, EOFError, ValueError):
            raise HTTPException(422, 'expected 16kHz mono PCM16 WAV') from None
    elif content_type != 'audio/pcm':
        raise HTTPException(415, 'use audio/pcm (16kHz mono PCM16 little-endian) or audio/wav')
    if not body or len(body) % 2 or len(body) > MAX_AUDIO_SECONDS * 32000:
        raise HTTPException(422, 'invalid audio length')
    return torch.from_numpy(np.frombuffer(body, dtype='<i2').astype(np.float32) / 32768).unsqueeze(0)


def turns(annotation: Any) -> list[dict[str, Any]]:
    return [{'start': float(t.start), 'end': float(t.end), 'speaker': str(s)} for t, s in annotation]


def infer(waveform: Any, min_speakers: int | None = None, max_speakers: int | None = None) -> dict[str, Any]:
    started = time.monotonic()
    seconds = waveform.shape[-1] / 16000
    with GPU_LOCK, torch.inference_mode():
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        options = {k: v for k, v in [('min_speakers', min_speakers), ('max_speakers', max_speakers)] if v is not None}
        output = pipeline()({'waveform': waveform, 'sample_rate': 16000}, **options)
        activity = turns(output.speaker_diarization)
        native_exclusive = getattr(output, 'exclusive_speaker_diarization', None)
        exclusive = turns(native_exclusive) if native_exclusive is not None else exclusive_from_activity(activity)
        overlaps = overlap_regions(activity)
        centroids = {}
        # Use the same bounded evidence/pooling policy as the batch worker.
        for speaker, clips in select_evidence(exclusive, overlaps, duration_seconds=seconds).items():
            vectors = []
            for left, right in clips:
                clip = waveform[:, int(left * 16000) : int(right * 16000)]
                vector = embedding_inference_v2({'waveform': clip, 'sample_rate': 16000})
                vectors.append((vector, right - left))
            centroid = pool_centroids(vectors)
            if centroid is not None:
                centroids[speaker] = centroid
        if torch.cuda.is_available():
            GPU_MEMORY.set(torch.cuda.max_memory_allocated())
    elapsed = time.monotonic() - started
    AUDIO.inc(seconds)
    RTF.observe(elapsed / seconds)
    return {
        'turns': exclusive,
        'overlaps': overlaps,
        'centroids': centroids,
        'audio_seconds': seconds,
        'inference_seconds': elapsed,
        'model_revision': MODEL_REVISION,
        'embedding_space': EMBEDDING_SPACE,
        'version': 'community-1:' + MODEL_REVISION,
        'provenance': {
            'backend': 'pyannote',
            'pipeline': 'pyannote.audio==4.0.3',
            'model_revision': MODEL_REVISION,
            'embedding_model': EMBEDDING_MODEL,
            'embedding_revision': EMBEDDING_REVISION,
            'exclusive_method': 'native' if native_exclusive is not None else 'longest_active_turn',
        },
    }
