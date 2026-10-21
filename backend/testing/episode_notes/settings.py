"""Offline experiment settings; these never configure the serving writer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodeEvalSettings:
    effort: str = 'default'
    claims: bool = False
    thinking_max_input_bytes: int = 0
    tiered: bool = False
    tier_min_words: int = 1500
    tier_min_source_kinds: int = 2
    writer_timeout: float = 120
    c6_timeout: float = 180
    apply_deadlines: bool = False
