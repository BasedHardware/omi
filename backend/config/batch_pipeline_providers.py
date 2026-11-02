"""Worker-only provider selection; no serving path is enabled by these settings."""

from config.refactor_switches import default_off as rollout_default_off

import os
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    pool_kind: str = 'dedicated_batch'
    max_unit_seconds: float = 7200
    words: str = 'parakeet'
    diarizer: str = 'pyannote'
    batch_size: int = 8
    max_padded_seconds: float = 272
    window_seconds: float = 30
    context_seconds: float = 2
    reuse_live: bool = False
    # Left context from the same owner's contiguous predecessor for a unit whose
    # speech starts at sample 0 (TDT start-state empties). 0 disables; off until
    # the L4 community-1 replay qualifies it.
    asr_left_context_seconds: float = 0.0
    asr_left_context_units: int = 64
    # Batch pyannote segmentation/embeddings across the items of one locked
    # flight. Per-forward model batches keep the pinned batch size, so peak
    # VRAM does not grow; the audio-seconds budget bounds host-side features.
    # Off until the L4 paired run on the production checkpoint passes
    # (diarizer/batch_pipeline_flight_qualify.py).
    flight_batching: bool = False
    flight_batch_seconds: float = 1800

    def __post_init__(self):
        if self.pool_kind not in {'dedicated_batch', 'shared_live'}:
            raise ValueError('unknown GPU pool kind')
        limit = 120 if self.pool_kind == 'shared_live' else 7200
        if not math.isfinite(self.max_unit_seconds) or not 0 < self.max_unit_seconds <= limit:
            raise ValueError('unit exceeds pool duration limit')
        if self.pool_kind == 'shared_live' and self.max_padded_seconds > 120:
            raise ValueError('shared-live model batch must fit 120 audio seconds')
        if not self.words or not self.diarizer:
            raise ValueError('provider names must be nonempty')
        if not 1 <= self.batch_size <= 32:
            raise ValueError('batch size must be in [1, 32]')
        values = (self.max_padded_seconds, self.window_seconds, self.context_seconds)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('window limits must be finite')
        if not 0 < self.window_seconds <= 120 or not 0 <= self.context_seconds < self.window_seconds / 2:
            raise ValueError('invalid ASR window/context')
        if self.max_padded_seconds < self.window_seconds + 2 * self.context_seconds:
            raise ValueError('padded budget must fit one context window')
        if not math.isfinite(self.asr_left_context_seconds) or not 0 <= self.asr_left_context_seconds <= 30:
            raise ValueError('ASR left context must be in [0, 30] seconds')
        if not 0 <= self.asr_left_context_units <= 1024:
            raise ValueError('ASR left context cache must hold [0, 1024] units')
        if not math.isfinite(self.flight_batch_seconds) or not 0 < self.flight_batch_seconds <= 7200:
            raise ValueError('flight batch budget must be in (0, 7200] audio seconds')


def provider_config() -> ProviderConfig:
    pool_kind = os.getenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    return ProviderConfig(
        pool_kind=pool_kind,
        max_unit_seconds=float(
            os.getenv('BATCH_PIPELINE_UNIT_SECONDS', '120' if pool_kind == 'shared_live' else '7200')
        ),
        words=os.getenv('BATCH_PIPELINE_WORDS_PROVIDER', 'parakeet'),
        diarizer=os.getenv('BATCH_PIPELINE_DIARIZER', 'pyannote'),
        batch_size=int(os.getenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '8')),
        max_padded_seconds=float(
            os.getenv('BATCH_PIPELINE_PADDED_SECONDS', '120' if pool_kind == 'shared_live' else '272')
        ),
        window_seconds=float(os.getenv('BATCH_PIPELINE_WINDOW_SECONDS', '30')),
        context_seconds=float(os.getenv('BATCH_PIPELINE_CONTEXT_SECONDS', '2')),
        reuse_live=rollout_default_off(
            'BATCH_PIPELINE_REUSE_LIVE_ENABLED',
            os.getenv('BATCH_PIPELINE_REUSE_LIVE_ENABLED', 'false').lower() == 'true',
        ),
        # Off by default; set seconds (e.g. 8) to enable on a qualified pool.
        asr_left_context_seconds=float(os.getenv('BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS', '0')),
        asr_left_context_units=int(os.getenv('BATCH_PIPELINE_ASR_LEFT_CONTEXT_UNITS', '64')),
        # Dark until qualified: only an explicit 'true' enables packing.
        flight_batching=rollout_default_off(
            'BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED',
            os.getenv('BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED', 'false').strip().lower() == 'true',
        ),
        flight_batch_seconds=float(os.getenv('BATCH_PIPELINE_FLIGHT_BATCH_SECONDS', '1800')),
    )
