"""Strict, content-free contracts for the local Chat-first E2E harness."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ChatFirstE2EFixtureCase(str, Enum):
    enabled = 'enabled'
    question = 'question'
    out_of_cohort = 'out_of_cohort'
    unreachable_control = 'unreachable_control'
    cold_start = 'cold_start'


class ChatFirstE2EControlEndpointMode(str, Enum):
    reachable = 'reachable'
    unreachable = 'unreachable'


class ChatFirstE2EExpectedShell(str, Enum):
    legacy = 'legacy'
    chat_first = 'chat_first'


class _StrictHarnessModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ChatFirstE2EPrepareRequest(_StrictHarnessModel):
    fixture_case: ChatFirstE2EFixtureCase


class ChatFirstE2EAdvanceRequest(_StrictHarnessModel):
    seconds: int = Field(ge=1, le=172800)


class ChatFirstE2EFixtureSnapshot(_StrictHarnessModel):
    """Shape-only observations. Product text and entity payloads never leave here."""

    fixture_case: ChatFirstE2EFixtureCase
    fixture_revision: int = Field(ge=1)
    expected_shell: ChatFirstE2EExpectedShell
    control_endpoint_mode: ChatFirstE2EControlEndpointMode
    advanced_seconds: int = Field(ge=0)
    materialized_intent_count: int = Field(ge=0)
    ready_intent_count: int = Field(ge=0)
    proactive_intent_count: int = Field(ge=0)
    pending_deferral_count: int = Field(ge=0)


__all__ = [
    'ChatFirstE2EAdvanceRequest',
    'ChatFirstE2EControlEndpointMode',
    'ChatFirstE2EExpectedShell',
    'ChatFirstE2EFixtureCase',
    'ChatFirstE2EFixtureSnapshot',
    'ChatFirstE2EPrepareRequest',
]
