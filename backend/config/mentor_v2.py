"""Versioned mentor prompt/config selection; no live provider or user data."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MentorV2Config(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_version: str = 'legacy-1'
    prefilter_threshold: float | None = Field(default=None, ge=0, le=1)
    dedupe_threshold: float = Field(default=0.525, ge=0, le=1)
    safety_escalation: Literal['suppress', 'allow'] = 'suppress'
    usefulness_judge: Literal['off', 'shadow', 'enforce'] = 'shadow'
    usefulness_threshold: float = Field(default=0.5, ge=0, le=1)


@lru_cache(maxsize=1)
def mentor_config() -> tuple[MentorV2Config, dict[str, str]]:
    raw = json.loads(Path(__file__).with_suffix('.json').read_text())
    config = MentorV2Config.model_validate(raw['mentor_v2'])
    prompts = raw['prompts'][config.prompt_version]
    if set(prompts) != {'gate', 'generate', 'critic'}:
        raise ValueError('invalid mentor prompt version')
    return config, prompts
