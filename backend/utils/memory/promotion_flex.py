"""Bounded OpenAI Flex routing for scheduled Short-term memory promotion.

The static capability is deliberately default-off. Once deployed with the
capability enabled, operators can return new calls to Standard without a
redeploy by updating ``llm_runtime_controls/memory_promotion`` in Firestore.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional, cast

from utils.llm.clients import get_llm
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

MEMORY_PROMOTION_FLEX_CAPABLE_ENV = "MEMORY_CANONICAL_PROMOTION_FLEX_CAPABLE"
MEMORY_PROMOTION_FLEX_CONTROL_PATH = "llm_runtime_controls/memory_promotion"
MEMORY_PROMOTION_FLEX_TIMEOUT_SECONDS = 900.0
MEMORY_PROMOTION_FLEX_LEASE_SECONDS = 1_200
MEMORY_MAINTENANCE_JOB_BUDGET_SECONDS = 3_600.0
MEMORY_PROMOTION_FLEX_JOB_SAFETY_SECONDS = 300.0
MAX_MEMORY_PROMOTION_FLEX_CALLS_PER_RUN = 2
_TRANSIENT_FLEX_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
_TRANSIENT_FLEX_EXCEPTION_NAMES = frozenset(
    {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError"}
)


class PromotionFlexControlChanged(RuntimeError):
    """The live control changed while a Flex result was in flight."""


class PromotionFlexDeferred(RuntimeError):
    """Flex could not serve now; retry later without consuming quality budget."""


@dataclass(frozen=True)
class PromotionFlexControl:
    mode: Literal["standard", "flex"] = "standard"
    generation: int = 0
    sample_percent: int = 0
    max_calls_per_run: int = 0

    @property
    def enabled(self) -> bool:
        return self.mode == "flex" and self.sample_percent > 0 and self.max_calls_per_run > 0


def promotion_flex_capable() -> bool:
    return os.getenv(MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _standard_control() -> PromotionFlexControl:
    return PromotionFlexControl()


def read_promotion_flex_control(*, db_client: Any) -> PromotionFlexControl:
    """Read strict live control, failing safely to Standard on any problem."""
    if not promotion_flex_capable():
        return _standard_control()
    try:
        snapshot = db_client.document(MEMORY_PROMOTION_FLEX_CONTROL_PATH).get()
        if not getattr(snapshot, "exists", False):
            return _standard_control()
        payload = snapshot.to_dict()
        if not isinstance(payload, dict) or set(payload) != {
            "mode",
            "generation",
            "sample_percent",
            "max_calls_per_run",
        }:
            raise ValueError("invalid fields")
        mode = payload["mode"]
        generation = payload["generation"]
        sample_percent = payload["sample_percent"]
        max_calls = payload["max_calls_per_run"]
        if mode not in {"standard", "flex"}:
            raise ValueError("invalid mode")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise ValueError("invalid generation")
        if not isinstance(sample_percent, int) or isinstance(sample_percent, bool) or not 0 <= sample_percent <= 100:
            raise ValueError("invalid sample percent")
        if (
            not isinstance(max_calls, int)
            or isinstance(max_calls, bool)
            or not 0 <= max_calls <= MAX_MEMORY_PROMOTION_FLEX_CALLS_PER_RUN
        ):
            raise ValueError("invalid call cap")
        return PromotionFlexControl(
            mode=cast(Literal["standard", "flex"], mode),
            generation=generation,
            sample_percent=sample_percent,
            max_calls_per_run=max_calls,
        )
    except Exception as exc:
        logger.warning("memory_promotion_flex_control_invalid error=%s", type(exc).__name__)
        return _standard_control()


def _sampled(uid: str, control: PromotionFlexControl) -> bool:
    cohort_key = f"{control.generation}:{uid}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(cohort_key).digest()[:4], "big") % 10_000
    return bucket < control.sample_percent * 100


def _response_text(response: Any) -> str:
    return cast(str, getattr(response, "content", str(response)))


class PromotionFlexRunRouter:
    """Own one maintenance run's deterministic cohort and global Flex budget."""

    def __init__(
        self,
        *,
        db_client: Any,
        control_reader: Callable[..., PromotionFlexControl] = read_promotion_flex_control,
        llm_factory: Callable[..., Any] = get_llm,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_client = db_client
        self._control_reader = control_reader
        self._llm_factory = llm_factory
        self._monotonic = monotonic
        self._started_at = monotonic()
        self.control = control_reader(db_client=db_client)
        self._flex_calls_started = 0
        self._last_call_used_flex = False

    def llm_invoke_for_uid(self, uid: str) -> Optional[Callable[[str], str]]:
        if (
            not self.control.enabled
            or not _sampled(uid, self.control)
            or self._flex_calls_started >= self.control.max_calls_per_run
        ):
            return None
        return lambda prompt: self._invoke(uid=uid, prompt=prompt)

    def _read_current_control(self) -> PromotionFlexControl:
        return self._control_reader(db_client=self._db_client)

    def assert_control_current(self) -> None:
        if self._read_current_control() != self.control:
            raise PromotionFlexControlChanged("control changed before Flex result apply")

    def assert_result_current(self) -> None:
        if self._last_call_used_flex:
            self.assert_control_current()

    @staticmethod
    def _is_transient_flex_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        return (
            status_code in _TRANSIENT_FLEX_STATUS_CODES
            or type(exc).__name__ in _TRANSIENT_FLEX_EXCEPTION_NAMES
            or isinstance(exc, (ConnectionError, TimeoutError))
        )

    def _invoke(self, *, uid: str, prompt: str) -> str:
        elapsed = max(self._monotonic() - self._started_at, 0.0)
        flex_has_time = (
            elapsed + MEMORY_PROMOTION_FLEX_TIMEOUT_SECONDS
            <= MEMORY_MAINTENANCE_JOB_BUDGET_SECONDS - MEMORY_PROMOTION_FLEX_JOB_SAFETY_SECONDS
        )
        if self._flex_calls_started >= self.control.max_calls_per_run or not flex_has_time:
            self._last_call_used_flex = False
            record_fallback(
                component="other",
                from_mode="memory_promotion_flex",
                to_mode="memory_promotion_standard",
                reason="other",
                outcome="recovered",
                log=logger,
            )
            return _response_text(self._llm_factory("memory_conflict").invoke(prompt))

        self.assert_control_current()

        self._flex_calls_started += 1
        self._last_call_used_flex = True
        logger.info(
            "memory_promotion_flex_request uid=%s generation=%d ordinal=%d",
            uid,
            self.control.generation,
            self._flex_calls_started,
        )
        try:
            response = (
                self._llm_factory(
                    "memory_conflict_flex",
                    request_timeout=MEMORY_PROMOTION_FLEX_TIMEOUT_SECONDS,
                )
                .bind(service_tier="flex")
                .invoke(prompt)
            )
        except Exception as exc:
            if self._is_transient_flex_error(exc):
                raise PromotionFlexDeferred(type(exc).__name__) from exc
            raise
        self.assert_control_current()
        return _response_text(response)


__all__ = [
    "MAX_MEMORY_PROMOTION_FLEX_CALLS_PER_RUN",
    "MEMORY_MAINTENANCE_JOB_BUDGET_SECONDS",
    "MEMORY_PROMOTION_FLEX_CAPABLE_ENV",
    "MEMORY_PROMOTION_FLEX_CONTROL_PATH",
    "MEMORY_PROMOTION_FLEX_LEASE_SECONDS",
    "MEMORY_PROMOTION_FLEX_JOB_SAFETY_SECONDS",
    "MEMORY_PROMOTION_FLEX_TIMEOUT_SECONDS",
    "PromotionFlexControl",
    "PromotionFlexControlChanged",
    "PromotionFlexDeferred",
    "PromotionFlexRunRouter",
    "promotion_flex_capable",
    "read_promotion_flex_control",
]
