"""Dream caller resource policy; the shared layer accepts supplied limits."""

from dataclasses import replace
from utils.agent_capabilities.limits import SessionLimits as BaseLimits


class SessionLimits(BaseLimits):
    @classmethod
    def for_size(cls, items: int, *, token_ceiling: int = 256000, edit_ceiling: int = 25):
        if items >= 80:
            limits = cls(
                bucket='heavy', turns=64, tools=256, read_bytes=512000, tokens=256000, verification_tokens=131072
            )
        elif items >= 20:
            limits = cls(
                bucket='medium', turns=64, tools=192, read_bytes=192000, tokens=160000, verification_tokens=65536
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
