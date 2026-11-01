"""Pure episode writer settings; read mutable configuration at the call boundary."""

from config.refactor_switches import default_off as rollout_default_off

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
        tiered=rollout_default_off(
            'MEETING_NOTES_EPISODE_TIERED_ENABLED',
            os.getenv('MEETING_NOTES_EPISODE_TIERED_ENABLED', 'true').strip().lower() in {'true', '1', 'yes'},
        ),
        tier_min_words=int(_number('MEETING_NOTES_EPISODE_TIER_MIN_WORDS', 1500, 1, 100000)),
        tier_min_source_kinds=int(_number('MEETING_NOTES_EPISODE_TIER_MIN_SOURCE_KINDS', 2, 1, 12)),
        writer_timeout=_number('MEETING_NOTES_EPISODE_WRITER_TIMEOUT_SECONDS', 120, 15, 120),
        c6_timeout=_number('MEETING_NOTES_EPISODE_C6_TIMEOUT_SECONDS', 180, 15, 300),
        claims=rollout_default_off(
            'MEETING_NOTES_EPISODE_CLAIMS_ENABLED',
            os.getenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'false').strip().lower() in {'true', '1', 'yes'},
        ),
    )


def _number(name, default, minimum, maximum):
    try:
        value = float(os.getenv(name, str(default)))
        return value if minimum <= value <= maximum else default
    except ValueError:
        return default
