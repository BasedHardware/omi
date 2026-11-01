"""Dream caller resource policy; the shared layer accepts supplied limits."""

from dataclasses import replace
from utils.agent_capabilities.limits import SessionLimits as BaseLimits

# Heavy is the ~1M pass ceiling. Medium and light keep the previous 160/256
# and 96/256 ratios of that ceiling (625_000 and 375_000). Verification is not
# a static fraction of the pass; it is reserved from staged evidence later.
HEAVY_TOKENS = 1000000
MEDIUM_TOKENS = 625000
LIGHT_TOKENS = 375000


class SessionLimits(BaseLimits):
    @classmethod
    def for_size(cls, items: int, *, token_ceiling: int = HEAVY_TOKENS, edit_ceiling: int = 25):
        if items >= 80:
            limits = cls(bucket='heavy', turns=64, tools=256, read_bytes=512000, tokens=HEAVY_TOKENS)
        elif items >= 20:
            limits = cls(bucket='medium', turns=64, tools=192, read_bytes=192000, tokens=MEDIUM_TOKENS)
        else:
            limits = cls(bucket='empty' if items == 0 else 'light', tokens=LIGHT_TOKENS)
        tokens = min(limits.tokens, max(0, token_ceiling))
        return replace(
            limits,
            tokens=tokens,
            edits=min(limits.edits, max(0, edit_ceiling)),
            verification_tokens=0,
        )
