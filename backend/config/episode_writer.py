"""Pure episode writer settings; read mutable configuration at the call boundary."""

import os
from dataclasses import dataclass

EFFORTS = ('default', 'high', 'xhigh')


@dataclass(frozen=True)
class EpisodeWriterSettings:
    effort: str = 'default'
    claims: bool = False
    thinking_max_input_bytes: int = 0
    tiered: bool = False
    tier_min_words: int = 1500
    tier_min_source_kinds: int = 2
    writer_timeout: float = 120
    c6_timeout: float = 180
    apply_deadlines: bool = False


def episode_writer_settings() -> EpisodeWriterSettings:
    effort = os.getenv('MEETING_NOTES_EPISODE_EFFORT', 'default')
    try:
        thinking_max_input_bytes = int(os.getenv('MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES', '0'))
    except ValueError:
        thinking_max_input_bytes = 0
    if thinking_max_input_bytes != 0 and not 4000 <= thinking_max_input_bytes <= 240000:
        thinking_max_input_bytes = 0
    return EpisodeWriterSettings(
        effort=effort if effort in EFFORTS else 'default',
        thinking_max_input_bytes=thinking_max_input_bytes,
        tiered=True,
        tier_min_words=1500,
        tier_min_source_kinds=2,
        writer_timeout=120,
        c6_timeout=180,
    )
