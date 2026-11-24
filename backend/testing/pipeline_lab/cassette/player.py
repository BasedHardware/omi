"""Cassette playback. Never calls a vendor; a missing cassette is an error.

Two lookups:

- ``exact``: the requested audio is byte-identical to a recorded stretch.
  Used when the lane sends the same stretch production sent (sync VAD files).
- ``span``: a conversation-level cassette serves any sub-window of that
  conversation's audio by word midpoint, shifted to the window's clock. Used by
  the record/batch lane, whose worker sends VAD windows the lab cannot send to
  the production GPU model. This is an approximation and drivers label it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from testing.pipeline_lab.cassette.format import Cassette, CassetteKey, Word, load


class CassetteMiss(LookupError):
    """No cassette for this key; run ``record-stt`` first (cold STT is a separate step)."""


@dataclass(frozen=True)
class PlaybackConfig:
    provider: str
    model: str
    language: str | None = None
    vocabulary: tuple[str, ...] = ()


class Player:
    def __init__(self, config: PlaybackConfig, *, root=None):
        self.config, self.root = config, root
        self.served: list[str] = []

    def key_for(self, pcm16: bytes) -> CassetteKey:
        c = self.config
        return CassetteKey.for_audio(
            pcm16, provider=c.provider, model=c.model, language=c.language, vocabulary=c.vocabulary
        )

    def get(self, pcm16: bytes) -> Cassette:
        key = self.key_for(pcm16)
        cassette = load(key, self.root)
        if cassette is None:
            raise CassetteMiss(f'no STT cassette {key.digest[:12]} ({key.provider}/{key.model}/{key.language})')
        self.served.append(key.digest)
        return cassette


class SpanSource:
    """Serve windows of one recorded stretch by their offset into it."""

    def __init__(self, cassette: Cassette):
        self.cassette = cassette

    def words(self, offset: float, duration: float) -> list[Word]:
        return self.cassette.words_between(offset, offset + duration)

    @property
    def all_words(self) -> Sequence[Word]:
        return self.cassette.words
