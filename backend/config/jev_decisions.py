"""Pure runtime contract for the Jev decision model (TypeSafe "System One", #14835).

Jev answers typed questions about one shared state (a probability for a yes/no
question, a distribution for a choice) instead of generating text. The backend
reaches it only through the LLM gateway's ``openrouter.systemone`` lane; the
gateway owns the OpenRouter credential. Both the lane definition
(``llm_gateway/gateway/config_loader.py``) and the backend client
(``utils/llm/jev_client.py``) read the pinned model and route from here.

Each decision that consults Jev has its own deployment flag. Every flag
defaults off, and flags are read at the call boundary, never at import.
"""

from __future__ import annotations

import os

JEV_AUTO_LANE_ID = 'omi:auto:jev-decisions'
# Pinned: a new Jev version changes calibration, and every threshold below was
# measured on 1.13. Bump only with a re-measured threshold.
JEV_MODEL = 'typesafe/jev-1.13'
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

CONVERSATION_RELEVANCE_JEV_ENABLED_ENV = 'CONVERSATION_RELEVANCE_JEV_ENABLED'
MEMORY_OWNER_JEV_FLIP_ENABLED_ENV = 'MEMORY_OWNER_JEV_FLIP_ENABLED'

_TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def _flag(name: str) -> bool:
    return os.getenv(name, '').strip().lower() in _TRUE_VALUES


def conversation_relevance_jev_enabled() -> bool:
    """The model tier of conversation relevance asks Jev instead of ``conv_discard``."""
    return _flag(CONVERSATION_RELEVANCE_JEV_ENABLED_ENV)


def memory_owner_jev_flip_enabled() -> bool:
    """Capture may re-attribute a third-party memory candidate to the user on a confident Jev answer."""
    return _flag(MEMORY_OWNER_JEV_FLIP_ENABLED_ENV)
