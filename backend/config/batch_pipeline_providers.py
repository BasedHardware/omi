"""Worker-only provider selection; no serving path is enabled by these settings."""

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
        reuse_live=os.getenv('BATCH_PIPELINE_REUSE_LIVE_ENABLED', 'false').lower() == 'true',
    )
