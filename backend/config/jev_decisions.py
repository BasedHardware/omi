"""Pure runtime contract for the Jev decision model (TypeSafe "System One", #14835).

Jev answers typed questions about one shared state (a probability for a yes/no
question, a distribution for a choice) instead of generating text. The backend
reaches it only through the LLM gateway's ``openrouter.systemone`` lane; the
gateway owns the OpenRouter credential. Both the lane definition
(``llm_gateway/gateway/config_loader.py``) and the backend client
(``utils/llm/jev_client.py``) read the pinned model and route from here.

The conversation relevance Jev cohort is selected by one percentage flag,
read at the call boundary. An unset percentage defaults off so a formerly
disabled host cannot become enabled when the old gate is removed.
"""

from __future__ import annotations

import math
import os

from config.policy.batch import cohort_bucket
from typing import Literal

JEV_AUTO_LANE_ID = 'omi:auto:jev-decisions'
SCREEN_TASK_JEV_AUTO_LANE_ID = 'omi:auto:jev-screen-task'
# Pinned: a new Jev version changes calibration, and every threshold below was
# measured on 1.13. Bump only with a re-measured threshold.
JEV_MODEL = 'typesafe/jev-1.13'
SCREEN_TASK_JEV_MODEL = 'typesafe/jev-1.14'
JEV_PROVIDER = 'openrouter'
# The upstream route's context window is 32k tokens. Characters are a
# conservative proxy (CJK text can approach one token per character), and the
# instructions/criteria share that window, so states are cut well below it.
JEV_MAX_STATE_CHARS = 24_000
# Gateway provider deadline; the backend client's own deadline sits just above
# it so a slow provider surfaces as a gateway timeout rather than a hung hop.
JEV_GATEWAY_REQUEST_MS = 2_500
JEV_CLIENT_TIMEOUT_SECONDS = 3.0
# One retry, only for transport failures and 5xx — never for a malformed answer.
JEV_CLIENT_MAX_ATTEMPTS = 2

RelevanceArm = Literal['jev', 'nano']
CONVERSATION_RELEVANCE_JEV_PERCENT_ENV = 'CONVERSATION_RELEVANCE_JEV_PERCENT'


def uid_bucket(uid: str, salt: str) -> float:
    """Stable salted identity bucket; ``uid`` may also be a conversation ID."""
    return cohort_bucket(uid, salt, bits=64, separator='\0', clamp_upper=True, empty_salt_prefix=True)


def percentage(name: str, *, default: float = 0.0) -> float:
    """Invalid, non-finite and out-of-range configuration admits nobody."""
    try:
        value = float(os.getenv(name, str(default)))
        return value if math.isfinite(value) and 0 <= value <= 100 else 0.0
    except ValueError:
        return 0.0


def relevance_arm(conversation_id: str) -> RelevanceArm:
    """Select the Jev cohort by stable conversation hash; invalid values fail closed."""
    bucket = uid_bucket(conversation_id, 'relevance-arm-v2')
    return 'jev' if bucket < percentage(CONVERSATION_RELEVANCE_JEV_PERCENT_ENV, default=0.0) else 'nano'


def relevance_experiment_active() -> bool:
    """Record the selected arm when a host explicitly configures the percentage."""
    return os.getenv(CONVERSATION_RELEVANCE_JEV_PERCENT_ENV) is not None
