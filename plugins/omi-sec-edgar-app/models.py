from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ChatToolResponse(BaseModel):
    """Omi chat-tool response containing exactly one of result or error."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_outcome(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error must be provided")
        return self


class CompanyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    company: str = Field(..., min_length=1, max_length=120)


class RecentFilingsRequest(CompanyRequest):
    form_type: Optional[str] = Field(default=None, min_length=1, max_length=40)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("limit", mode="before")
    @classmethod
    def default_null_limit(cls, value):
        return 5 if value is None else value


class FinancialSnapshotRequest(CompanyRequest):
    years: int = Field(default=3, ge=1, le=5)

    @field_validator("years", mode="before")
    @classmethod
    def default_null_years(cls, value):
        return 3 if value is None else value
