"""Task due precision shared by extraction, Candidates and task readers."""

from datetime import date as Date
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class TaskDue(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: Literal['none', 'date', 'instant', 'unresolved']
    date: Optional[str] = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    timezone: Optional[str] = None
    instant: Optional[AwareDatetime] = None
    expression: Optional[str] = Field(default=None, max_length=512)
    year_basis: Optional[Literal['spoken', 'source_relative', 'next_future_occurrence']] = None
    reason: Optional[str] = Field(default=None, max_length=128)

    @model_validator(mode='after')
    def validate_precision(self):
        if self.kind == 'date':
            if not self.date or not self.timezone or self.instant is not None:
                raise ValueError('date due requires a local date and timezone, without an instant')
            Date.fromisoformat(self.date)
        elif self.kind == 'instant':
            if self.instant is None or not self.timezone or self.date is not None:
                raise ValueError('instant due requires an instant and timezone')
        elif self.date is not None or self.instant is not None:
            raise ValueError('none/unresolved due cannot carry a date or instant')
        if self.kind == 'unresolved' and not self.reason:
            raise ValueError('unresolved due requires a reason')
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError) as error:
                raise ValueError('invalid IANA timezone') from error
        return self


class ReminderIntent(BaseModel):
    """Model annotation, validated against exact source turns before admission."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal['explicit_reminder', 'quoted', 'hypothetical', 'current_session', 'status', 'waiting_on']
    due_expression: Optional[str] = Field(default=None, max_length=512)


class ReminderOrigin(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    policy_revision: Literal['explicit-reminders-v1'] = 'explicit-reminders-v1'
    input_revision: str = Field(min_length=1, max_length=128)
    speaker_evidence_revision: str = Field(min_length=1, max_length=128)
    source_at: Optional[AwareDatetime] = None
    extracted_at: AwareDatetime
    review_reason: Optional[Literal['owner_unresolved']] = None
