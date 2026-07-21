from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


# Shared type alias for lane_id so the pattern lives in exactly one place.
LaneId = Annotated[str, Field(pattern=r'^omi:auto:[a-z0-9][a-z0-9-]*$')]


class Surface(str, Enum):
    OPENAI_CHAT_COMPLETIONS = 'openai.chat_completions'
    ANTHROPIC_MESSAGES = 'anthropic.messages'


class StructuredOutputMode(str, Enum):
    NONE = 'none'
    JSON_OBJECT = 'json_object'
    JSON_SCHEMA = 'json_schema'


class CredentialMode(str, Enum):
    OMI_PAID = 'omi_paid'
    BYOK = 'byok'


class RolloutStage(str, Enum):
    DISABLED = 'disabled'
    SHADOW = 'shadow'
    CANARY = 'canary'
    ACTIVE = 'active'


class FailureClass(str, Enum):
    TIMEOUT_BEFORE_OUTPUT = 'timeout_before_output'
    PROVIDER_429_OMI_PAID = 'provider_429_omi_paid'
    PROVIDER_5XX_OMI_PAID = 'provider_5xx_omi_paid'
    BYOK_AUTH = 'byok_auth'
    BYOK_QUOTA = 'byok_quota'
    BYOK_RATE_LIMIT = 'byok_rate_limit'
    BYOK_UNSUPPORTED_PROVIDER = 'byok_unsupported_provider'
    MISSING_BYOK_KEY = 'missing_byok_key'
    CAPABILITY_MISMATCH = 'capability_mismatch'
    INVALID_CONFIG = 'invalid_config'


class BenchmarkSource(str, Enum):
    OMI_EVAL = 'omi_eval'
    EXTERNAL_BENCHMARK = 'external_benchmark'
    MOCK = 'mock'
    DEV_FIXTURE = 'dev_fixture'


class Capabilities(StrictBaseModel):
    text_input: bool
    streaming: bool
    structured_output: StructuredOutputMode
    tools: bool


class Objective(StrictBaseModel):
    quality: float = Field(ge=0.0, le=1.0)
    latency: float = Field(ge=0.0, le=1.0)
    cost: float = Field(ge=0.0, le=1.0)

    @model_validator(mode='after')
    def validate_weights(self):
        total = self.quality + self.latency + self.cost
        if abs(total - 1.0) > 0.0001:
            raise ValueError('objective weights must sum to 1.0')
        return self


class ProviderRef(StrictBaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


def _empty_failure_classes() -> list[FailureClass]:
    return []


def _empty_provider_refs() -> list[ProviderRef]:
    return []


class GeneratedRouteOverride(StrictBaseModel):
    """Gateway-only route selection for a lane generated from the legacy profile."""

    feature: str = Field(min_length=1)
    primary: ProviderRef
    provider_options: dict[str, Any] = Field(default_factory=dict)


class TimeoutPolicy(StrictBaseModel):
    request_ms: int = Field(gt=0)


class RetryPolicy(StrictBaseModel):
    max_attempts: int = Field(ge=1)


class RolloutPolicy(StrictBaseModel):
    stage: RolloutStage
    percent: float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode='after')
    def validate_stage_percent(self):
        if self.stage == RolloutStage.ACTIVE and self.percent != 100.0:
            raise ValueError('active rollout stage must use percent 100')
        if self.stage in (RolloutStage.SHADOW, RolloutStage.DISABLED) and self.percent != 0.0:
            raise ValueError(f'{self.stage.value} rollout stage must use percent 0')
        return self


class Evidence(StrictBaseModel):
    benchmark_snapshot: str = Field(min_length=1)
    eval_report: str = Field(min_length=1)
    benchmark_source: BenchmarkSource
    dev_only: bool = False

    def is_prod_eligible(self) -> bool:
        return not self.dev_only and self.benchmark_source not in {
            BenchmarkSource.MOCK,
            BenchmarkSource.DEV_FIXTURE,
        }


class CredentialPolicy(StrictBaseModel):
    mode: CredentialMode
    allow_byok_to_omi_paid_fallback: bool = False
    fallback_eligible_failure_classes: list[FailureClass] = Field(default_factory=_empty_failure_classes)
    never_fallback_failure_classes: list[FailureClass] = Field(default_factory=_empty_failure_classes)

    @model_validator(mode='after')
    def validate_failure_class_sets(self):
        overlap = set(self.fallback_eligible_failure_classes) & set(self.never_fallback_failure_classes)
        if overlap:
            names = ', '.join(sorted(overlap))
            raise ValueError(f'credential fallback class sets overlap: {names}')
        return self


class FallbackPolicy(StrictBaseModel):
    fallback_on: list[FailureClass] = Field(default_factory=_empty_failure_classes)
    never_fallback_on: list[FailureClass] = Field(default_factory=_empty_failure_classes)

    @model_validator(mode='after')
    def validate_failure_class_sets(self):
        overlap = set(self.fallback_on) & set(self.never_fallback_on)
        if overlap:
            names = ', '.join(sorted(overlap))
            raise ValueError(f'fallback_on and never_fallback_on overlap: {names}')
        return self


class OutputBudgetPolicy(StrictBaseModel):
    """An opt-in per-route output cap, never a global provider default."""

    experiment: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_-]*$')
    max_completion_tokens: int = Field(ge=1, le=8192)


class LaneConfig(StrictBaseModel):
    lane_id: LaneId
    surface: Surface
    capabilities: Capabilities
    objective: Objective
    credential_policy: CredentialPolicy
    active_route: str = Field(min_length=1)
    last_known_good: str = Field(min_length=1)


class RouteArtifact(StrictBaseModel):
    route_artifact_id: str = Field(min_length=1)
    lane_id: LaneId
    surface: Surface
    primary: ProviderRef
    fallbacks: list[ProviderRef] = Field(default_factory=_empty_provider_refs)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    output_budget: OutputBudgetPolicy | None = None
    timeouts: TimeoutPolicy
    retry: RetryPolicy
    capabilities: Capabilities
    evidence: Evidence
    rollout: RolloutPolicy
    credential_policy: CredentialPolicy
    fallback_policy: FallbackPolicy
    artifact_digest: str | None = None

    @field_validator('artifact_digest')
    @classmethod
    def validate_artifact_digest(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith('sha256:'):
            raise ValueError('artifact_digest must use sha256:<hex> format')
        return value

    @computed_field
    @property
    def content_digest(self) -> str:
        return compute_route_artifact_digest(self)


class FeatureBundle(StrictBaseModel):
    feature: str = Field(min_length=1)
    lane_id: LaneId
    prompt_version: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    eval_suite: str = Field(min_length=1)
    promotion_gates: dict[str, str] = Field(default_factory=dict)


def compute_route_artifact_digest(artifact: RouteArtifact | dict[str, Any]) -> str:
    if isinstance(artifact, RouteArtifact):
        payload = artifact.model_dump(
            mode='json',
            exclude={'artifact_digest', 'content_digest'},
            exclude_none=True,
            exclude_defaults=True,
        )
    else:
        payload = dict(artifact)
        payload.pop('artifact_digest', None)
        payload.pop('content_digest', None)
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return f'sha256:{hashlib.sha256(canonical.encode("utf-8")).hexdigest()}'


ConfigFileName = Literal[
    'lanes.yaml',
    'route_artifacts.yaml',
    'feature_bundles.yaml',
    'generated_route_overrides.yaml',
]
