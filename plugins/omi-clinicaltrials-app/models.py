import re
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


StudyStatus = Literal[
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
    "NOT_YET_RECRUITING",
    "COMPLETED",
    "TERMINATED",
    "WITHDRAWN",
    "SUSPENDED",
    "UNKNOWN",
]

StudyPhase = Literal[
    "EARLY_PHASE1",
    "PHASE1",
    "PHASE2",
    "PHASE3",
    "PHASE4",
    "NA",
]


class _NullMeansDefault(BaseModel):
    """Treat omitted Omi tool parameters as defaults instead of invalid nulls."""

    @model_validator(mode="before")
    @classmethod
    def drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class ChatToolResponse(BaseModel):
    """Omi chat-tool response containing exactly one of result or error."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_outcome(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error must be provided")
        return self


class SearchTrialsRequest(_NullMeansDefault):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    condition: Optional[str] = Field(default=None, min_length=1, max_length=120)
    intervention: Optional[str] = Field(default=None, min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, min_length=1, max_length=120)
    status: StudyStatus = "RECRUITING"
    phase: Optional[StudyPhase] = None
    page_size: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def require_search_term(self):
        if not any((self.condition, self.intervention, self.location)):
            raise ValueError(
                "provide at least one of condition, intervention, or location"
            )
        return self


class RecruitingTrialsRequest(_NullMeansDefault):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    condition: str = Field(..., min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, min_length=1, max_length=120)
    page_size: int = Field(default=5, ge=1, le=10)


class TrialDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    nct_id: str = Field(
        ...,
        min_length=11,
        max_length=11,
        description="ClinicalTrials.gov study identifier, for example NCT04280705.",
    )

    @field_validator("nct_id", mode="before")
    @classmethod
    def normalize_nct_id(cls, value):
        if not isinstance(value, str):
            raise ValueError("nct_id must be a string")
        normalized = value.strip().upper()
        if not re.fullmatch(r"NCT\d{8}", normalized):
            raise ValueError("nct_id must use the form NCT followed by 8 digits")
        return normalized
