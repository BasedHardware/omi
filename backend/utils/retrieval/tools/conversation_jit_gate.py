"""Dependency-free feature gate shared by JIT conversation prompt and tools."""

import os
from typing import Any, Dict, Optional

JIT_CONVERSATION_RETRIEVAL_ENV = "JIT_CONVERSATION_RETRIEVAL_ENABLED"
JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY = "jit_conversation_retrieval_enabled"


def _is_enabled_value(value: Any) -> bool:
    """Accept only explicit boolean gate values and fail closed otherwise."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_jit_conversation_retrieval_enabled(configurable: Optional[Dict[str, Any]]) -> bool:
    """Return whether the additive JIT conversation contract is explicitly enabled.

    A per-request config value wins over the environment feature flag, including an
    explicit false. Keeping the default false preserves released tool behavior until
    a caller or rollout configuration opts in.
    """
    if isinstance(configurable, dict) and JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY in configurable:
        return _is_enabled_value(configurable[JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY])
    return _is_enabled_value(os.getenv(JIT_CONVERSATION_RETRIEVAL_ENV, "false"))
