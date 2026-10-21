"""Read-time coverage of synced screen observations, independent of semantic memory."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScreenActivityCoverage(BaseModel):
    source: Literal['synced_screen_activity'] = 'synced_screen_activity'
    row_limit: int = Field(ge=1)
    truncated: bool
    first_observed_at: Optional[str] = None
    last_observed_at: Optional[str] = None
    # A bounded cloud query cannot attest to device capture state or unsynced rows.
    capture_completeness: Literal['unknown'] = 'unknown'
