"""Resource limits for owner-scoped agent sessions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionLimits:
    bucket: str = 'light'
    turns: int = 64
    tools: int = 128
    read_bytes: int = 64000
    read_call_bytes: int = 64000
    tokens: int = 96000
    verification_tokens: int = 32768
    completion_tokens: int = 4096
    verifier_completion_tokens: int = 4096
    edits: int = 25
    questions: int = 3
    model_seconds: int = 480
    verifier_seconds: int = 120
