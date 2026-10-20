"""Provider-independent turn contract; seconds share the submitted PCM clock."""

from pydantic import BaseModel, Field, model_validator
import math

OMI_EMBEDDING_SPACE = 'pyannote/wespeaker-voxceleb-resnet34-LM:v2'


class SpeakerTurn(BaseModel):
    start: float
    end: float
    speaker: str = Field(min_length=1)


class OverlapRegion(BaseModel):
    start: float
    end: float
    speakers: list[str]


class SpeakerCentroid(BaseModel):
    embedding: list[float]
    evidence_seconds: float = Field(ge=0)


class DiarizationResult(BaseModel):
    turns: list[SpeakerTurn]
    overlaps: list[OverlapRegion] = Field(default_factory=list)
    centroids: dict[str, SpeakerCentroid] = Field(default_factory=dict)
    embedding_space: str = Field(min_length=1)
    version: str = Field(min_length=1)
    provenance: dict[str, str]
    # Optional diagnostic metadata from batch; legacy providers omit it.
    audio_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    inference_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_clock(self):
        ordered = sorted(self.turns, key=lambda t: t.start)
        for turn in [*self.turns, *self.overlaps]:
            if not math.isfinite(turn.start) or not math.isfinite(turn.end) or turn.start < 0 or turn.end <= turn.start:
                raise ValueError('invalid diarization clock')
        if any(a.end > b.start for a, b in zip(ordered, ordered[1:])):
            raise ValueError('diarization turns must be exclusive')
        for entry in self.centroids.values():
            if (
                not math.isfinite(entry.evidence_seconds)
                or not entry.embedding
                or not all(math.isfinite(v) for v in entry.embedding)
            ):
                raise ValueError('invalid centroid')
        self.turns = ordered
        return self
