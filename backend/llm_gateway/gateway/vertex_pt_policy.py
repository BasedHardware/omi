"""Provisioned-Throughput policy for the gateway Vertex adapter.

Every decision delegates to utils.llm.vertex_pt_routing - the single
policy module the desktop BFF mirrors on its kill-switch path. Reservation evidence is shared across services; reachability remains process-local.
Only declared, synthetic probes may confirm that the exclusive order moved.
"""

from __future__ import annotations

import logging
import json
import os
from contextvars import ContextVar
from typing import TypeVar
from collections.abc import Callable

from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.vertex_wire import _bounded_error_text  # pyright: ignore[reportPrivateUsage]
from llm_gateway.gateway.vertex_wire import _vertex_rejection_reason  # pyright: ignore[reportPrivateUsage]
from utils.llm import vertex_pt_routing as ptr
from config.vertex_reservations import RESERVATIONS, State
from utils.llm.vertex_reservation_state import effective_states

logger = logging.getLogger(__name__)
T = TypeVar('T')

DEFAULT_GCP_LOCATION = 'us-central1'
VERTEX_API_VERSION = 'v1'


class VertexPTPolicyMixin:
    """Apply the shared state snapshot; keep only reachability local."""

    _pt_model_override_env: str
    _overflow_model_override_env: str
    _overflow_enabled_env: str
    _multi_region_location_env: str
    _probe_ttl_seconds: float
    _now: Callable[[], float]
    _project_env: str
    _location_env: str
    _reservation_state_context: ContextVar[dict[str, State]]
    _model_unavailable_at: dict[str, float]

    @property
    def _reservation_states(self) -> dict[str, State]:
        return self._reservation_state_context.get()

    @_reservation_states.setter
    def _reservation_states(self, states: dict[str, State]) -> None:
        self._reservation_state_context.set(states)

    def _attempt_plan(self, anchor: str, *, origin_model: str = '') -> list[tuple[str, str]]:
        try:
            model = ptr.reserved_generation_model(
                anchor,
                effective_states(self._reservation_states, os.environ),
                override=self._env(self._pt_model_override_env),
            )
        except ValueError as exc:
            raise ProviderFailure(FailureClass.INVALID_CONFIG, str(exc)) from exc
        if model is None:
            raise ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)
        return [(model, ptr.REQUEST_TYPE_DEDICATED)]

    def _recovery_attempts(
        self, served_model: str, status_code: int, preview: bytes, *, origin_model: str = '', capacity: str = ''
    ) -> list[tuple[str, str]]:
        message = _bounded_error_text(preview)
        if capacity == ptr.REQUEST_TYPE_DEDICATED and (
            ptr.is_provisioned_capacity_exhausted(status_code, message)
            or ptr.is_provisioned_capacity_absent(status_code, message)
            or ptr.is_model_unavailable(status_code, message)
        ):
            raise ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)
        return []

    def _observe_attempt(
        self,
        model: str,
        capacity: str,
        status_code: int,
        preview: bytes,
        *,
        traffic_type: str | None = None,
    ) -> None:
        """Record strict positive capacity evidence in the request snapshot."""
        if 400 <= status_code < 500:
            # JSON stdout is parsed into jsonPayload by Cloud Logging. Values
            # are allowlisted metadata; never include the raw provider error.
            print(
                json.dumps(
                    {
                        'severity': 'WARNING',
                        'event': 'vertex_provider_rejection',
                        'served_model': model if model in ptr.DESKTOP_TEXT_LANES else 'other',
                        'status': status_code,
                        'reason': _vertex_rejection_reason(preview),
                    }
                )
            )
        if model not in RESERVATIONS or capacity != ptr.REQUEST_TYPE_DEDICATED:
            return
        if 200 <= status_code < 300 and traffic_type == 'PROVISIONED_THROUGHPUT':
            self._reservation_states = {**self._reservation_states, model: State.ACTIVE}

    def _record_model_available(self, model: str) -> None:
        self._model_unavailable_at.pop(model, None)

    def _overflow_enabled(self) -> bool:
        return self._env(self._overflow_enabled_env, 'true').strip().lower() not in {'0', 'false', 'no', 'off'}

    def _multi_region_location(self) -> str:
        return (
            self._env(self._multi_region_location_env, ptr.MULTI_REGION_LOCATION).strip() or ptr.MULTI_REGION_LOCATION
        )

    @staticmethod
    def _env(name: str, default: str = '') -> str:
        return os.getenv(name, default)

    def _endpoint(self, model: str, *, method: str, capacity: str = '') -> str:
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
        if model in RESERVATIONS and capacity == ptr.REQUEST_TYPE_DEDICATED:
            try:
                host, location = ptr.reservation_endpoint(model, os.environ)
            except ValueError as exc:
                raise ProviderFailure(FailureClass.INVALID_CONFIG) from exc
        return (
            f'https://{host}/{VERTEX_API_VERSION}/projects/{project}'
            f'/locations/{location}/publishers/google/models/{model}:{method}'
        )
