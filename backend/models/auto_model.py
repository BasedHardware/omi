"""Auto realtime-voice model selection — response shape for /v1/auto/model-pick.

Source of truth for the model-pick response schema; routers/auto_model.py builds
the dict matching these fields. The daily-cached pick is derived from
Artificial Analysis (https://artificialanalysis.ai/) quality/speed data.
"""

from typing import Any

from pydantic import BaseModel, Field


class AutoModelPick(BaseModel):
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""

    provider: str = Field(description='Desktop provider id of the picked realtime-voice model, e.g. "geminiFlashLive".')
    updated_at: float = Field(description='Unix timestamp (seconds) the cached pick was last refreshed.')
    detail: dict[str, Any] = Field(
        description=(
            'Provenance for the pick. May contain a "reason" string and/or a ' '"scores" map of provider id -> score.'
        )
    )
    attribution: str = Field(description='Required attribution URL for the data source.')
