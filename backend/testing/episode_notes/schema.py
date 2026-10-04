"""Offline fixture and result schema; no provider or database imports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FIXTURES = Path(__file__).with_name('fixtures') / 'episodes.json'


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    time: str | None = None
    actor: str | None = None
    content: str
    sensitivity: Literal['standard', 'private'] = 'standard'
    source_ref: str | None = None
    diarization_key: str | None = None
    wake_word_invocation: bool = False


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    started_at: str
    finished_at: str
    transcript_segments: list[Observation] = Field(default_factory=list)
    screen_moments: list[Observation] = Field(default_factory=list)
    screen_ocr: list[Observation] = Field(default_factory=list)
    messages: list[Observation] = Field(default_factory=list)
    roster: list[Observation] = Field(default_factory=list)
    calendar: list[Observation] = Field(default_factory=list)
    prior_conversations: list[Observation] = Field(default_factory=list)
    open_tasks: list[Observation] = Field(default_factory=list)
    device_state: list[Observation] = Field(default_factory=list)


class ExpectedProperties(BaseModel):
    must_cover: list[str]
    must_not_claim: list[str] = Field(default_factory=list)
    provenance: dict[str, Literal['said', 'shown', 'written', 'inferred']] = Field(default_factory=dict)
    private_claims: list[str] = Field(default_factory=list)


class EpisodeFixture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    stratum: str
    split: Literal['dev', 'held_out']
    evidence: EvidenceBundle
    expected: ExpectedProperties


class FixtureSet(BaseModel):
    schema_version: Literal['episode_notes.v1']
    synthetic: bool
    episodes: list[EpisodeFixture]


class JudgeScore(BaseModel):
    informativeness_gap: float = Field(ge=0, le=1)
    unsupported_claims: int = Field(ge=0)
    wrong_provenance_claims: int = Field(ge=0)
    sensitive_tagging_misses: int = Field(ge=0)
    vacuous: bool
    property_failures: list[str]
    reasons: list[str]


def load_fixtures(path: Path = FIXTURES) -> FixtureSet:
    fixtures = FixtureSet.model_validate_json(path.read_text())
    if not fixtures.synthetic and path.resolve() == FIXTURES.resolve():
        raise ValueError('non-synthetic fixtures require an explicit external path')
    ids = [episode.id for episode in fixtures.episodes]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate episode ids')
    for episode in fixtures.episodes:
        item_ids = [
            item.id
            for field in EvidenceBundle.model_fields
            if field not in {'started_at', 'finished_at'}
            for item in getattr(episode.evidence, field)
        ]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError('duplicate evidence ids')
    return fixtures


@dataclass(frozen=True)
class LLMResult:
    content: dict
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = None
    finish_reason: str | None = None

    def cost(self) -> dict:
        return {
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'latency_seconds': self.latency_seconds,
        }


def _result(value: dict | LLMResult) -> LLMResult:
    # Legacy fake callbacks have no measured usage; never invent zero counts.
    return value if isinstance(value, LLMResult) else LLMResult(content=value)


class LLMCallError(Exception):
    """Bounded failure class and usage receipt, never provider/evidence text."""

    def __init__(self, error_class: str, result: LLMResult):
        super().__init__(error_class)
        self.error_class = error_class
        self.result = result
