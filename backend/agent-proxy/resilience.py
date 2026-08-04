"""Pure resilience helpers for the agent proxy.

Kept import-light (stdlib only) so hermetic unit tests can cover the
classification and circuit-breaker decisions without Firebase/GCE imports.
The seven categories mirror desktop/macos/agent-cloud/errors.mjs — the
cross-language contract: the category decides the user-plane message and the
retry policy; the raw exception always goes whole to the internal log.
"""

import asyncio
import re
from typing import Any, Dict, Literal

ErrorCategory = Literal["transient", "auth", "invalid_request", "unavailable", "aborted", "interrupted", "internal"]

_TRANSIENT_RE = re.compile(
    r"(429|529|50[0234]|rate.?limit|overloaded|timed?\s?out|timeout|connect|reset|refused|unavailable|EOF)",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(r"(401|403|unauthoriz|forbidden|invalid_token|authentication|expired|revoked)", re.IGNORECASE)
_INVALID_RE = re.compile(r"(400|413|422|invalid request|too large|length limit)", re.IGNORECASE)


def classify_error(exc: BaseException) -> ErrorCategory:
    if isinstance(exc, asyncio.CancelledError):
        return "aborted"
    text = f"{type(exc).__name__} {exc}"
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return "transient"
    if _AUTH_RE.search(text):
        return "auth"
    if _TRANSIENT_RE.search(text):
        return "transient"
    if _INVALID_RE.search(text):
        return "invalid_request"
    return "internal"


# --- VM restart circuit breaker ---------------------------------------------
# 3 consecutive restart failures open the circuit for COOLDOWN_SECONDS; the
# first attempt after cooldown is the half-open probe (its outcome re-trips or
# resets the counter). State lives in the Firestore agentVm doc so both restart
# paths (proxy + agent_tools router) and every proxy instance share it.

RESTART_FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 30 * 60


def circuit_open(vm: Dict[str, Any], now_ts: float) -> bool:
    failures = vm.get("restartFailures") or 0
    if failures < RESTART_FAILURE_THRESHOLD:
        return False
    last = vm.get("lastRestartFailureAt")
    last_ts = getattr(last, "timestamp", lambda: None)() if last is not None else None
    if isinstance(last, (int, float)):
        last_ts = float(last)
    if last_ts is None:
        return False  # malformed state fails open: allow the attempt, it self-heals the fields
    return (now_ts - last_ts) < COOLDOWN_SECONDS
