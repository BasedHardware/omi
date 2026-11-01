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

from admission import GPU_LOCK
from embedding import embedding_inference_v2

MODEL_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
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
        # Separate v2 WeSpeaker model intentionally: community-1's internal
        # embeddings are not an Omi enrollment-space compatibility guarantee.
        for speaker in sorted({t['speaker'] for t in exclusive}):
            samples = []
            for turn in exclusive:
                if turn['speaker'] != speaker:
                    continue
                # Exclude simultaneous speech from biometric evidence.
                cuts = [(turn['start'], turn['end'])]
                for region in overlaps:
                    cuts = [
                        (a, b)
                        for l, r in cuts
                        for a, b in [(l, min(r, region['start'])), (max(l, region['end']), r)]
                        if b > a
                    ]
                for l, r in cuts:
                    if r - l >= 0.5:
                        samples.append((l, r))
            vectors, evidence = [], 0.0
            # Bounded, duration-weighted evidence; avoid concatenating hours.
            for l, r in sorted(samples, key=lambda x: x[1] - x[0], reverse=True)[:3]:
                r = min(r, l + 10)
                clip = waveform[:, int(l * 16000) : int(r * 16000)]
                vector = np.asarray(embedding_inference_v2({'waveform': clip, 'sample_rate': 16000})).reshape(-1)
                norm = np.linalg.norm(vector)
                if norm > 0 and np.isfinite(vector).all():
                    vectors.append((vector / norm, r - l))
                    evidence += r - l
            if vectors:
                centroid: Any = sum(v * w for v, w in vectors) / evidence
                norm = float(np.linalg.norm(centroid))
                if norm <= 0 or not np.isfinite(centroid).all():
                    continue
                centroid /= norm
                centroids[speaker] = {'embedding': centroid.tolist(), 'evidence_seconds': evidence}
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
        'embedding_space': 'pyannote/wespeaker-voxceleb-resnet34-LM:v2',
        'version': 'community-1:' + MODEL_REVISION,
        'provenance': {
            'backend': 'pyannote',
            'pipeline': 'pyannote.audio==4.0.3',
            'model_revision': MODEL_REVISION,
            'embedding_revision': '837717ddb9ff5507820346191109dc79c958d614',
            'exclusive_method': 'native' if native_exclusive is not None else 'longest_active_turn',
        },
    }
