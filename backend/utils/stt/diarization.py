"""Config-selected diarizer adapters; no backend-specific assignment policy."""

import os
import time
from typing import Protocol

import httpx

from models.diarization import DiarizationResult, OMI_EMBEDDING_SPACE
from utils.stt.diarization_turns import exclusive_from_activity, overlap_regions
from utils.stt.speaker_match import mean_embedding
from utils.stt.http_errors import retryable_http_error


class DiarizerBackend(Protocol):
    def diarize(
        self, pcm: bytes | bytearray | memoryview, *, deadline: float, segments, vectors, resolution
    ) -> DiarizationResult: ...


def _pcm_chunks(pcm, deadline):
    view = memoryview(pcm)
    for offset in range(0, len(view), 65536):
        if time.monotonic() >= deadline:
            raise TimeoutError
        yield bytes(view[offset : offset + 65536])
    if time.monotonic() >= deadline:
        raise TimeoutError


class HttpDiarizer:
    def __init__(self, backend: str, *, reserve_attempt=None):
        self.backend = backend
        self.reserve_attempt = reserve_attempt

    def diarize(self, pcm, *, deadline, segments=None, vectors=None, resolution=None):
        variable = 'HOSTED_DIARIZATION_API_URL' if self.backend == 'pyannote' else 'HOSTED_NEMOTRON_DIARIZATION_API_URL'
        url = os.getenv(variable, '').rstrip('/')
        if not url:
            raise ValueError('diarizer_unconfigured')
        buffered = isinstance(pcm, (memoryview, bytearray))
        headers = {'Content-Type': 'audio/pcm'}
        if buffered:
            headers['Content-Length'] = str(len(pcm))
        attempts_left = 2
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if self.reserve_attempt is not None and not self.reserve_attempt(len(pcm) / 32000):
                raise RuntimeError('diarizer_attempt_budget')
            try:
                response = httpx.post(
                    url + '/v2/diarization',
                    # httpx treats a naked memoryview as an iterable of ints.
                    # Stream bounded byte chunks, restarting on each retry.
                    content=_pcm_chunks(pcm, deadline) if buffered else pcm,
                    headers=headers,
                    timeout=httpx.Timeout(remaining, connect=min(5, remaining)),
                )
                response.raise_for_status()
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                # Inference is stateless and idempotent; one retry covers a batch
                # pod disappearing mid-request (node preemption, HPA scale-down).
                transient = retryable_http_error(error)
                if not transient or attempts_left == 1:
                    raise
                attempts_left -= 1
                continue
            # httpx read timeouts bound each chunk wait, not total wall time;
            # never accept a result that arrived past the caller's deadline.
            if time.monotonic() > deadline:
                raise TimeoutError
            break
        result = DiarizationResult.model_validate(response.json())
        if result.provenance.get('backend') != self.backend:
            raise ValueError('diarizer_backend_mismatch')
        return result


class LegacyAHC:
    def diarize(self, pcm, *, deadline, segments, vectors, resolution):
        if resolution is None:
            raise ValueError('legacy_resolution_unavailable')
        turns, grouped = [], {}
        for segment in sorted(segments, key=lambda s: s.start):
            voice = resolution.speaker_ids.get(segment.id)
            if voice is None:
                continue
            label = f'SPEAKER_{voice:02d}'
            if segment.end <= segment.start:
                continue
            turns.append({'start': segment.start, 'end': segment.end, 'speaker': label})
            if segment.id in vectors:
                grouped.setdefault(label, []).append((vectors[segment.id], segment.end - segment.start))
        centroids = {
            key: {
                'embedding': mean_embedding([v for v, _ in values]).reshape(-1).tolist(),
                'evidence_seconds': sum(s for _, s in values),
            }
            for key, values in grouped.items()
        }
        return DiarizationResult.model_validate(
            {
                'turns': exclusive_from_activity(turns),
                'overlaps': overlap_regions(turns),
                'centroids': centroids,
                'embedding_space': OMI_EMBEDDING_SPACE,
                'version': 'legacy-ahc-v2',
                'provenance': {'backend': 'legacy_ahc', 'exclusive_method': 'longest_active_turn'},
            }
        )


def get_diarizer_backend() -> DiarizerBackend:
    backend = os.getenv('TRANSCRIPTION_FINAL_PASS_BACKEND', 'pyannote')
    if backend == 'legacy_ahc':
        return LegacyAHC()
    if backend in {'pyannote', 'nemotron'}:
        return HttpDiarizer(backend)
    raise ValueError('unknown_diarizer_backend')
