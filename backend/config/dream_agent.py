"""Default-off dream admission and bounded budgets, read at invocation time."""

import math
import os
from dataclasses import dataclass


def mode() -> str:
    value = os.getenv('DREAM_AGENT_MODE', 'off').strip().lower()
    return value if value in {'shadow', 'on'} else 'off'


def eligible(uid: str, user: dict) -> bool:
    allowlist = {s.strip() for s in os.getenv('DREAM_AGENT_UID_ALLOWLIST', '').split(',') if s.strip()}
    if uid in allowlist:
        return True
    minimum_build = os.getenv('DREAM_AGENT_TESTFLIGHT_MIN_BUILD', '').strip()
    if not minimum_build or os.getenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'false').lower() != 'true':
        return False
    try:
        minimum = int(minimum_build)
    except ValueError:
        return False
    if minimum < 1:
        return False
    app_build = user.get('dream_app_build')
    return (
        user.get('dream_release_channel') == 'testflight'
        and isinstance(app_build, int)
        and not isinstance(app_build, bool)
        and app_build >= minimum
    )


def number(key: str, default: float) -> float:
    value = float(os.getenv(key, str(default)))
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid dream budget: ' + key)
    return value


@dataclass(frozen=True)
class Caps:
    tokens: int = 24000
    passes: int = 2
    edits: int = 10
    daily_usd: float = 20.0
    max_usd_per_token: float = 0.00001
    undo_rate: float = 0.2
    undo_min_samples: int = 10
    anonymous_k: int = 20

    @classmethod
    def from_env(cls):
        return cls(
            tokens=int(number('DREAM_AGENT_TOKENS_PER_PASS', 24000)),
            passes=int(number('DREAM_AGENT_PASSES_PER_DAY', 2)),
            edits=int(number('DREAM_AGENT_EDITS_PER_PASS', 10)),
            daily_usd=number('DREAM_AGENT_DAILY_USD', 20),
            max_usd_per_token=number('DREAM_AGENT_MAX_USD_PER_TOKEN', 0.00001),
            undo_rate=number('DREAM_AGENT_UNDO_RATE', 0.2),
            undo_min_samples=int(number('DREAM_AGENT_UNDO_MIN_SAMPLES', 10)),
            anonymous_k=max(2, int(number('DREAM_AGENT_FEEDBACK_K', 20))),
        )

    @property
    def reservation_usd(self) -> float:
        return self.tokens * self.max_usd_per_token
