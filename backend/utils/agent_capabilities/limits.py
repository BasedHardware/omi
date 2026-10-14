"""Resource limits for owner-scoped agent sessions."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class SessionLimits:
    bucket: str = 'light'
    turns: int = 3
    tools: int = 16
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

    @classmethod
    def for_size(cls, items: int, *, token_ceiling: int = 256000, edit_ceiling: int = 25):
        if items >= 80:
            limits = cls(
                bucket='heavy', turns=12, tools=64, read_bytes=512000, tokens=256000, verification_tokens=131072
            )
        elif items >= 20:
            limits = cls(
                bucket='medium', turns=6, tools=48, read_bytes=192000, tokens=160000, verification_tokens=65536
            )
        else:
            limits = cls(bucket='empty' if items == 0 else 'light')
        tokens = min(limits.tokens, max(0, token_ceiling))
        return replace(
            limits,
            tokens=tokens,
            edits=min(limits.edits, max(0, edit_ceiling)),
            verification_tokens=min(limits.verification_tokens, tokens // 2),
        )
