"""Historical anonymous feedback payload; planning lives in dream_harness."""

from typing import Literal
from pydantic import Field
from models.dream_edit import Strict


class Feedback(Strict):
    component: Literal['transcription', 'notes', 'memory', 'people', 'entities', 'tasks', 'dream']
    failure_class: Literal[
        'spelling', 'duplicate', 'missing_evidence', 'stale_state', 'routing', 'budget', 'success', 'none', 'ok'
    ]
    severity: Literal['info', 'warning', 'error']
    count: int = Field(ge=1, le=10000)
    latency_ms: float = Field(ge=0, le=3600000, allow_inf_nan=False)
    error_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    reproduction: str = Field(min_length=1, max_length=500)
