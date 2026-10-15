"""Worker-only provider selection; no serving path is enabled by these settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    words: str = 'parakeet'
    diarizer: str = 'pyannote'
    batch_size: int = 8
    max_padded_seconds: float = 240
    window_seconds: float = 30
    context_seconds: float = 2
    reuse_live: bool = False

    def __post_init__(self):
        import math

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
    return ProviderConfig(
        words=os.getenv('BATCH_PIPELINE_WORDS_PROVIDER', 'parakeet'),
        diarizer=os.getenv('BATCH_PIPELINE_DIARIZER', 'pyannote'),
        batch_size=int(os.getenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '8')),
        max_padded_seconds=float(os.getenv('BATCH_PIPELINE_PADDED_SECONDS', '240')),
        window_seconds=float(os.getenv('BATCH_PIPELINE_WINDOW_SECONDS', '30')),
        context_seconds=float(os.getenv('BATCH_PIPELINE_CONTEXT_SECONDS', '2')),
        reuse_live=os.getenv('BATCH_PIPELINE_REUSE_LIVE_ENABLED', 'false').lower() == 'true',
    )
