"""One live switch for bounded OpenAI Flex routing in scheduled background work.

Once the owning jobs are deployed capable, operators can move every eligible
scheduled call between Flex and the legacy Standard path without a redeploy by
updating the single environment-scoped Firestore document for that stage.

The dev and prod jobs can share the customer Firestore project, so the control
document is deliberately stage-scoped. A missing, unsupported, or malformed
``OMI_ENV_STAGE`` fails closed to Standard rather than risking a cross-stage
toggle.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, cast

from utils.llm.clients import feature_auto_lane_id, get_or_create_omi_gateway_llm
from utils.llm.prompt_cache import EXPLICIT_CACHE_OPTIONS

logger = logging.getLogger(__name__)

BACKGROUND_FLEX_CAPABLE_ENV = "OMI_BACKGROUND_FLEX_CAPABLE"
BACKGROUND_FLEX_CONTROL_COLLECTION = "llm_runtime_controls"
BACKGROUND_FLEX_CONTROL_DOCUMENT_PREFIX = "background_flex"
BACKGROUND_FLEX_TIMEOUT_SECONDS = 900.0
BACKGROUND_FLEX_LEASE_SECONDS = 1_200
BACKGROUND_FLEX_JOB_BUDGET_SECONDS = 3_600.0
BACKGROUND_FLEX_JOB_SAFETY_SECONDS = 300.0

# The maintenance cron still imports this lease constant while its call sites
# migrate to the shared Flex router.
MEMORY_PROMOTION_FLEX_LEASE_SECONDS = BACKGROUND_FLEX_LEASE_SECONDS

_TRANSIENT_FLEX_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
_TRANSIENT_FLEX_EXCEPTION_NAMES = frozenset(
    {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError"}
)


CONSOLIDATION_FLEX_CACHE_KEY = "omi-canonical-consolidation-v1"


def _get_gateway_flex_llm(feature: str, *, request_timeout: float) -> Any:
    llm = get_or_create_omi_gateway_llm(
        feature_auto_lane_id(feature),
        options={"request_timeout": request_timeout, "max_retries": 0},
        feature=feature,
    )
    if feature != "memory_conflict_flex":
        return llm
    return llm.bind(
        prompt_cache_key=CONSOLIDATION_FLEX_CACHE_KEY,
        extra_body={"prompt_cache_options": EXPLICIT_CACHE_OPTIONS},
    )


class PromotionFlexDeferred(RuntimeError):
    """Flex could not serve now; durable scheduled work should retry later."""


class PromotionFlexControlChanged(PromotionFlexDeferred):
    """The shared live control changed while a Flex result was in flight."""


@dataclass(frozen=True)
class PromotionFlexControl:
    enabled: bool = False
    generation: int = 0


def promotion_flex_capable() -> bool:
    return os.getenv(BACKGROUND_FLEX_CAPABLE_ENV, "false").strip().lower() in {"1", "true", "yes"}


def background_flex_control_path() -> Optional[str]:
    """Return the strict stage-scoped control document path.

    Dev and prod intentionally use separate Firestore documents because their
    jobs may read the same customer-data project. Other stages are not allowed
    to read or write a live Flex switch; callers must use the Standard path.
    """

    stage = os.getenv("OMI_ENV_STAGE", "").strip().lower()
    if stage not in {"dev", "prod"}:
        return None
    return f"{BACKGROUND_FLEX_CONTROL_COLLECTION}/{BACKGROUND_FLEX_CONTROL_DOCUMENT_PREFIX}_{stage}"


def _standard_control() -> PromotionFlexControl:
    return PromotionFlexControl()


def read_promotion_flex_control(*, db_client: Any) -> PromotionFlexControl:
    """Read the strict shared control, failing safely to Standard."""
    control_path = background_flex_control_path()
    if not promotion_flex_capable() or control_path is None:
        return _standard_control()
    try:
        snapshot = db_client.document(control_path).get()
        if not getattr(snapshot, "exists", False):
            return _standard_control()
        payload = snapshot.to_dict()
        if not isinstance(payload, dict) or set(payload) != {"enabled", "generation"}:
            raise ValueError("invalid fields")
        enabled = payload["enabled"]
        generation = payload["generation"]
        if not isinstance(enabled, bool):
            raise ValueError("invalid enabled flag")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise ValueError("invalid generation")
        return PromotionFlexControl(enabled=enabled, generation=generation)
    except Exception as exc:
        logger.warning("background_flex_control_invalid error=%s", type(exc).__name__)
        return _standard_control()


def _response_text(response: Any) -> str:
    return cast(str, getattr(response, "content", str(response)))


class _BackgroundFlexModel:
    def __init__(
        self,
        router: "PromotionFlexRunRouter",
        *,
        uid: str,
        standard_feature: str,
        flex_feature: str,
        workload: str,
    ) -> None:
        self._router = router
        self._uid = uid
        self._standard_feature = standard_feature
        self._flex_feature = flex_feature
        self._workload = workload

    def invoke(self, payload: Any) -> Any:
        return self._router.invoke_flex(
            uid=self._uid,
            payload=payload,
            standard_feature=self._standard_feature,
            flex_feature=self._flex_feature,
            workload=self._workload,
        )


class PromotionFlexRunRouter:
    """Own one job run's snapshot of the shared background Flex switch."""

    def __init__(
        self,
        *,
        db_client: Any,
        control_reader: Callable[..., PromotionFlexControl] = read_promotion_flex_control,
        flex_llm_factory: Callable[..., Any] = _get_gateway_flex_llm,
        monotonic: Callable[[], float] = time.monotonic,
        started_at: Optional[float] = None,
        force_enabled: bool = False,
    ) -> None:
        self._db_client = db_client
        self._control_reader = control_reader
        self._flex_llm_factory = flex_llm_factory
        self._monotonic = monotonic
        self._started_at = monotonic() if started_at is None else started_at
        self.control = control_reader(db_client=db_client)
        self._forced = bool(force_enabled) and promotion_flex_capable()
        if self._forced:
            generation = self.control.generation if self.control.generation >= 1 else 1
            self.control = PromotionFlexControl(enabled=True, generation=generation)
        self._flex_calls_started = 0

    def llm_for_uid(
        self,
        uid: str,
        *,
        standard_feature: str,
        flex_feature: str,
        workload: str,
    ) -> Optional[Any]:
        if not self.control.enabled:
            return None
        return _BackgroundFlexModel(
            self,
            uid=uid,
            standard_feature=standard_feature,
            flex_feature=flex_feature,
            workload=workload,
        )

    def llm_invoke_for_uid(self, uid: str) -> Optional[Callable[[Any], str]]:
        model = self.llm_for_uid(
            uid,
            standard_feature="memory_conflict",
            flex_feature="memory_conflict_flex",
            workload="memory_promotion",
        )
        if model is None:
            return None
        return lambda prompt: _response_text(model.invoke(prompt))

    def _read_current_control(self) -> PromotionFlexControl:
        return self._control_reader(db_client=self._db_client)

    def assert_control_current(self) -> None:
        if self._forced:
            return
        if self._read_current_control() != self.control:
            raise PromotionFlexControlChanged("background Flex control changed before result apply")

    def assert_result_current(self) -> None:
        if self.control.enabled:
            self.assert_control_current()

    @staticmethod
    def _is_transient_flex_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        return (
            status_code in _TRANSIENT_FLEX_STATUS_CODES
            or type(exc).__name__ in _TRANSIENT_FLEX_EXCEPTION_NAMES
            or isinstance(exc, (ConnectionError, TimeoutError))
        )

    def job_budget_fits(self) -> bool:
        """Whether one more Flex reservation still fits the one-hour job budget."""
        elapsed = max(self._monotonic() - self._started_at, 0.0)
        return (
            elapsed + BACKGROUND_FLEX_TIMEOUT_SECONDS
            <= BACKGROUND_FLEX_JOB_BUDGET_SECONDS - BACKGROUND_FLEX_JOB_SAFETY_SECONDS
        )

    def require_job_budget(self) -> None:
        """Stop in-UID TTL/outbox work when the same one-hour clock is gone."""
        if not self.job_budget_fits():
            raise PromotionFlexDeferred("job_budget")

    def invoke_flex(
        self,
        *,
        uid: str,
        payload: Any,
        standard_feature: str,
        flex_feature: str,
        workload: str,
    ) -> Any:
        if not self.job_budget_fits():
            raise PromotionFlexDeferred("job_budget")

        self.assert_control_current()
        self._flex_calls_started += 1
        logger.info(
            "background_flex_request workload=%s uid=%s generation=%d ordinal=%d",
            workload,
            uid,
            self.control.generation,
            self._flex_calls_started,
        )
        try:
            response = (
                self._flex_llm_factory(flex_feature, request_timeout=BACKGROUND_FLEX_TIMEOUT_SECONDS)
                .bind(service_tier="flex")
                .invoke(payload)
            )
        except Exception as exc:
            if self._is_transient_flex_error(exc):
                raise PromotionFlexDeferred(type(exc).__name__) from exc
            raise
        self.assert_control_current()
        return response


__all__ = [
    "BACKGROUND_FLEX_CAPABLE_ENV",
    "BACKGROUND_FLEX_CONTROL_COLLECTION",
    "BACKGROUND_FLEX_CONTROL_DOCUMENT_PREFIX",
    "BACKGROUND_FLEX_JOB_BUDGET_SECONDS",
    "BACKGROUND_FLEX_JOB_SAFETY_SECONDS",
    "BACKGROUND_FLEX_LEASE_SECONDS",
    "BACKGROUND_FLEX_TIMEOUT_SECONDS",
    "MEMORY_PROMOTION_FLEX_LEASE_SECONDS",
    "PromotionFlexControl",
    "PromotionFlexControlChanged",
    "PromotionFlexDeferred",
    "PromotionFlexRunRouter",
    "background_flex_control_path",
    "promotion_flex_capable",
    "read_promotion_flex_control",
]
