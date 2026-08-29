"""Provisioned-Throughput policy for the gateway Vertex adapter.

Every decision delegates to utils.llm.vertex_pt_routing - the single
policy module the desktop BFF mirrors on its kill-switch path. The
promotion latch and reachability table moved here from the desktop proxy:
process-local, taught by traffic, never probed at startup.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.vertex_wire import _bounded_error_text  # pyright: ignore[reportPrivateUsage]
from utils.llm import vertex_pt_routing as ptr

logger = logging.getLogger(__name__)

DEFAULT_GCP_LOCATION = 'us-central1'
VERTEX_API_VERSION = 'v1'


class VertexPTPolicyMixin:
    """PT pin/overflow/host-split decisions and their process-local state."""

    _pt_model_override_env: str
    _overflow_model_override_env: str
    _overflow_enabled_env: str
    _multi_region_location_env: str
    _probe_ttl_seconds: float
    _now: Callable[[], float]
    _project_env: str
    _location_env: str
    _pt_target_ready: bool
    _pt_target_probed_at: float | None
    _model_unavailable_at: dict[str, float]

    def _attempt_plan(self, anchor: str) -> list[tuple[str, str]]:
        serving = self._serving_model(anchor)
        return [(serving, self._capacity_for(serving))]

    def _serving_model(self, anchor: str) -> str:
        intended = ptr.desktop_serving_model(
            anchor,
            target_dedicated_ready=self._pt_target_is_ready(),
            override=self._env(self._pt_model_override_env),
        )
        return self._first_reachable(intended)

    def _provisioned_model(self) -> str:
        return ptr.resolve_pt_model(
            target_dedicated_ready=self._pt_target_is_ready(),
            override=self._env(self._pt_model_override_env),
        )

    def _capacity_for(self, model: str) -> str:
        return ptr.request_type_for(model=model, pt_model=self._provisioned_model())

    def _recovery_attempts(self, served_model: str, status_code: int, preview: bytes) -> list[tuple[str, str]]:
        message = _bounded_error_text(preview)
        if ptr.is_model_unavailable(status_code, message):
            self._record_model_unavailable(served_model)
            return [(rung, ptr.REQUEST_TYPE_SHARED) for rung in self._fallback_chain(served_model)]
        if self._overflow_triggered(status_code, message):
            return self._overflow_plan(served_model)
        return []

    def _observe_attempt(self, model: str, capacity: str, status_code: int, preview: bytes) -> None:
        """Latch PT-target probe outcomes from a dedicated attempt."""
        if capacity != ptr.REQUEST_TYPE_DEDICATED:
            return
        message = _bounded_error_text(preview)
        unavailable = ptr.is_model_unavailable(status_code, message)
        exhausted = self._overflow_triggered(status_code, message)
        if not unavailable:
            self._record_pt_target_observation(not exhausted)

    def _overflow_triggered(self, status_code: int, message: str) -> bool:
        return ptr.is_provisioned_capacity_exhausted(status_code, message) or ptr.is_provisioned_capacity_absent(
            status_code, message
        )

    def _overflow_plan(self, served_model: str) -> list[tuple[str, str]]:
        if not self._overflow_enabled():
            return []
        pt_model = self._provisioned_model()
        if served_model != pt_model:
            return []
        try:
            ladder = ptr.resolve_overflow_ladder(
                pt_model=pt_model, override=self._env(self._overflow_model_override_env)
            )
        except ValueError:
            return []
        plan: list[tuple[str, str]] = []
        for rung in ladder:
            if not self._model_believed_available(rung):
                continue
            if rung == ptr.PT_MODEL_TARGET and self._pt_probe_due():
                plan.append((rung, ptr.REQUEST_TYPE_DEDICATED))
            plan.append((rung, ptr.REQUEST_TYPE_SHARED))
        return plan

    def _fallback_chain(self, model: str) -> tuple[str, ...]:
        try:
            return ptr.resolve_fallback_chain(
                model=model,
                pt_model=self._provisioned_model(),
                unreachable=self._unreachable_models(),
                override=self._env(self._overflow_model_override_env),
            )
        except ValueError:
            return ()

    def _pt_target_is_ready(self) -> bool:
        return self._pt_target_ready and self._model_believed_available(ptr.PT_MODEL_TARGET)

    def _model_believed_available(self, model: str) -> bool:
        observed = self._model_unavailable_at.get(model)
        if observed is None:
            return True
        return (self._now() - observed) >= self._probe_ttl_seconds

    def _unreachable_models(self) -> frozenset[str]:
        return frozenset(model for model in self._model_unavailable_at if not self._model_believed_available(model))

    def _first_reachable(self, model: str) -> str:
        if self._model_believed_available(model):
            return model
        for rung in self._fallback_chain(model):
            if self._model_believed_available(rung):
                return rung
        return model

    def _record_model_unavailable(self, model: str) -> None:
        self._model_unavailable_at[model] = self._now()
        if model == ptr.PT_MODEL_TARGET:
            self._pt_target_ready = False

    def _record_model_available(self, model: str) -> None:
        self._model_unavailable_at.pop(model, None)

    def _pt_probe_due(self) -> bool:
        if self._pt_target_probed_at is None:
            return True
        return (self._now() - self._pt_target_probed_at) >= self._probe_ttl_seconds

    def _record_pt_target_observation(self, ready: bool) -> None:
        became_ready = ready and not self._pt_target_ready
        self._pt_target_ready = ready
        self._pt_target_probed_at = self._now()
        if became_ready:
            logger.info('llm_gateway vertex pt_promotion target=%s', ptr.PT_MODEL_TARGET)

    def _overflow_enabled(self) -> bool:
        return self._env(self._overflow_enabled_env, 'true').strip().lower() not in {'0', 'false', 'no', 'off'}

    def _multi_region_location(self) -> str:
        return (
            self._env(self._multi_region_location_env, ptr.MULTI_REGION_LOCATION).strip() or ptr.MULTI_REGION_LOCATION
        )

    @staticmethod
    def _env(name: str, default: str = '') -> str:
        return os.getenv(name, default)

    def _endpoint(self, model: str, *, method: str) -> str:
        project = os.getenv(self._project_env, '').strip()
        if not project:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
        # Gemini 3.x has no regional endpoint: it needs the un-prefixed host
        # plus a multi-region `locations/{loc}` path segment. Building a
        # regional URL for it is what made every 3.x request 404 in
        # production on 2026-08-18 (see vertex_pt_routing).
        host, location = ptr.vertex_endpoint(
            model=model,
            regional_location=os.getenv(self._location_env, DEFAULT_GCP_LOCATION).strip() or DEFAULT_GCP_LOCATION,
            multi_region_location=self._multi_region_location(),
        )
        return (
            f'https://{host}/{VERTEX_API_VERSION}/projects/{project}'
            f'/locations/{location}/publishers/google/models/{model}:{method}'
        )
