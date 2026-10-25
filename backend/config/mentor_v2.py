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
def _load_mentor_bundle() -> tuple[MentorV2Config, dict[str, dict[str, str]]]:
    raw = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
    config = MentorV2Config.model_validate(raw['mentor_v2'])
    for prompts in raw['prompts'].values():
        if set(prompts) != {'gate', 'generate', 'critic'}:
            raise ValueError('invalid mentor prompt version')
    if config.prompt_version not in raw['prompts']:
        raise ValueError('invalid mentor prompt version')
    return config, raw['prompts']


@lru_cache(maxsize=1)
def mentor_config() -> tuple[MentorV2Config, dict[str, str]]:
    config, all_prompts = _load_mentor_bundle()
    return config, all_prompts[config.prompt_version]


def mentor_prompts(version: str) -> dict[str, str]:
    _, all_prompts = _load_mentor_bundle()
    prompts = all_prompts.get(version)
    if not isinstance(prompts, dict) or set(prompts) != {'gate', 'generate', 'critic'}:
        raise ValueError('invalid mentor prompt version')
    return prompts
