"""Provisioned-Throughput policy for the gateway Vertex adapter.

Every decision delegates to utils.llm.vertex_pt_routing - the single
policy module for managed generation. The desktop BFF routes paid requests
through this adapter. Reservation evidence is shared across services.
Only declared, synthetic probes may confirm that the exclusive order moved.
"""

from __future__ import annotations

import logging
import json
import os
from dataclasses import replace
from contextvars import ContextVar
from typing import Any, TypeVar
from collections.abc import Mapping
from collections.abc import Callable

from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.accounting import vertex_usage_from_response
from llm_gateway.gateway.dream_lanes import DREAM_MODEL
from llm_gateway.gateway.dream_provider import capacity_mode
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.vertex_diagnostics import vertex_attempt_labels, vertex_error_metadata
from llm_gateway.gateway.vertex_wire import _bounded_error_text  # pyright: ignore[reportPrivateUsage]
from llm_gateway.gateway.vertex_wire import _vertex_rejection_reason  # pyright: ignore[reportPrivateUsage]
from utils.llm import vertex_pt_routing as ptr
from config.vertex_reservations import RESERVATIONS, State
from utils.llm.vertex_reservation_state import effective_states
from utils.llm.vertex_policy_metrics import (
    observe_decision,
    observe_dispatch,
    observe_reported_traffic,
    observe_forbidden_flash,
)

logger = logging.getLogger(__name__)
T = TypeVar('T')

DEFAULT_GCP_LOCATION = 'us-central1'
VERTEX_API_VERSION = 'v1'


class VertexPTPolicyMixin:
    """Apply the shared state snapshot to dedicated-only generation."""

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
    _cache_context: ContextVar[tuple[Mapping[str, Any], str | None, Any] | None]

    @property
    def _reservation_states(self) -> dict[str, State]:
        return self._reservation_state_context.get()

    @_reservation_states.setter
    def _reservation_states(self, states: dict[str, State]) -> None:
        self._reservation_state_context.set(states)

    @property
    def _dream_mode(self) -> str | None:
        context = self._cache_context.get()
        return capacity_mode(context[0], context[1]) if context is not None else None

    def _attempt_plan(self, anchor: str, *, origin_model: str = '') -> list[tuple[str, str]]:
        if self._dream_mode is not None:
            if anchor != DREAM_MODEL:
                raise ProviderFailure(FailureClass.INVALID_CONFIG)
            return [
                (
                    DREAM_MODEL,
                    ptr.REQUEST_TYPE_SHARED if self._dream_mode == 'on_demand' else ptr.REQUEST_TYPE_DEDICATED,
                )
            ]
        try:
            action = ptr.managed_generation_action(
                anchor,
                ptr.cutover_states(
                    self._reservation_states, effective_states(self._reservation_states, os.environ), env=os.environ
                ),
                override=self._env(self._pt_model_override_env),
                lane=self._product_policy_lane,
            )
        except ValueError as exc:
            raise ProviderFailure(FailureClass.INVALID_CONFIG, str(exc)) from exc
        observe_decision(self._product_policy_lane, action.kind)
        if action.kind == 'refuse':
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        if action.kind not in {'dedicated', 'remap'}:
            # Config requires the existing interactive gpt-6-luna fallback.
            raise ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)
        return [(action.model, ptr.REQUEST_TYPE_DEDICATED)]

    def _with_product_policy(self, request: Mapping[str, Any], credentials: Any) -> dict[str, Any]:
        return {
            **request,
            '_vertex_policy_lane': ptr.request_policy_lane(
                request,
                platform=credentials.caller.client_platform,
                tag=credentials.caller.product_lane,
                feature=credentials.caller.usage_feature,
            ),
        }

    @property
    def _product_policy_lane(self) -> str:
        context = self._cache_context.get()
        return str(context[0].get('_vertex_policy_lane', 'desktop_other')) if context is not None else 'desktop_other'

    def _observe_managed_dispatch(self, model: str, capacity: str) -> None:
        self._guard_managed_cutover(model, capacity)
        observe_dispatch(model, capacity, self._product_policy_lane)
        if model == ptr.PT_MODEL_CURRENT and capacity != ptr.REQUEST_TYPE_DEDICATED:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)

    def _guard_managed_cutover(self, model: str, capacity: str) -> None:
        # Raw observed inactivity cannot be undone by an operator model pin.
        # Run before cache preparation, and again at native dispatch, so even
        # stale plans/recovery/LKG cannot consume Dream's moved order.
        if (
            self._dream_mode is None
            and model.startswith('gemini-')
            and 'flash' in model
            and (
                self._reservation_states.get(ptr.PT_MODEL_CURRENT) == State.INACTIVE
                or self._reservation_states.get(ptr.PT_MODEL_TARGET) == State.ACTIVE
                and (
                    model != ptr.PT_MODEL_CURRENT or self._reservation_states.get(ptr.PT_MODEL_CURRENT) != State.ACTIVE
                )
            )
        ):
            observe_forbidden_flash(model, capacity, self._product_policy_lane)
            raise ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)

    def _hold_retiring_stream(self, model: str) -> bool:
        return (
            model == ptr.PT_MODEL_CURRENT
            and self._dream_mode is None
            and (
                self._reservation_states.get(ptr.PT_MODEL_TARGET) == State.ACTIVE
                or self._reservation_states.get(ptr.PT_MODEL_CURRENT) != State.ACTIVE
            )
        )

    def _observe_stream_traffic(self, model: str, payload: Mapping[str, Any], reported: bool) -> bool:
        if not reported and vertex_usage_from_response(payload).traffic_type == 'ON_DEMAND':
            self._observe_managed_traffic(model, 'ON_DEMAND')
            reported = True
        return self._reject_managed_on_demand(model, payload, streaming=True, reported=reported) or reported

    def _reject_managed_on_demand(
        self, model: str, payload: Mapping[str, Any], *, streaming: bool = False, reported: bool = False
    ) -> bool:
        usage = payload.get('usageMetadata')
        nested = usage.get('trafficType') if isinstance(usage, Mapping) else None
        if (
            model == ptr.PT_MODEL_CURRENT
            and self._dream_mode is None
            and (payload.get('trafficType') == 'ON_DEMAND' or nested == 'ON_DEMAND')
        ):
            if payload.get('trafficType') != 'ON_DEMAND' and not reported:
                self._observe_managed_traffic(model, 'ON_DEMAND')
            if streaming and not self._hold_retiring_stream(model):
                return True
            error = ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)
            metadata = replace(vertex_usage_from_response(payload), traffic_type='ON_DEMAND')
            context = self._cache_context.get()
            if context is not None:
                context[2].traffic_type = 'ON_DEMAND'
                metadata = context[2].accounting(metadata)
            error.accounting = metadata
            raise error
        return False

    def _observe_managed_traffic(self, model: str, traffic_type: str | None) -> None:
        observe_reported_traffic(model, traffic_type, self._product_policy_lane)

    def _recovery_attempts(
        self, served_model: str, status_code: int, preview: bytes, *, origin_model: str = '', capacity: str = ''
    ) -> list[tuple[str, str]]:
        if self._dream_mode is not None:
            if capacity == ptr.REQUEST_TYPE_DEDICATED and status_code == 429:
                raise ProviderFailure(FailureClass.RESERVED_CAPACITY_UNAVAILABLE)
            return []
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
            message = _bounded_error_text(preview)
            failure = FailureClass.PROVIDER_INVALID_REQUEST
            if capacity == ptr.REQUEST_TYPE_DEDICATED and (
                ptr.is_provisioned_capacity_exhausted(status_code, message)
                or ptr.is_provisioned_capacity_absent(status_code, message)
                or ptr.is_model_unavailable(status_code, message)
            ):
                failure = FailureClass.RESERVED_CAPACITY_UNAVAILABLE
            elif status_code in {401, 403}:
                failure = FailureClass.INVALID_CONFIG
            elif status_code == 408:
                failure = FailureClass.TIMEOUT_BEFORE_OUTPUT
            elif status_code == 429:
                failure = FailureClass.PROVIDER_429_OMI_PAID
            served_model = model if model in ptr.DESKTOP_TEXT_LANES else 'other'
            print(
                json.dumps(
                    {
                        'severity': 'WARNING',
                        'event': 'vertex_provider_rejection',
                        **vertex_attempt_labels(),
                        **vertex_error_metadata(preview),
                        'served_model': served_model,
                        'model': served_model,
                        'failure_class': failure.value,
                        'status': status_code,
                        'reason': _vertex_rejection_reason(preview),
                    }
                )
            )
        self._observe_managed_traffic(model, traffic_type)
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
        self._guard_managed_cutover(model, capacity)
        project = os.getenv(self._project_env, '').strip()
        if not project:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
        if self._dream_mode is not None:
            if model != DREAM_MODEL:
                raise ProviderFailure(FailureClass.INVALID_CONFIG)
            return f'https://aiplatform.googleapis.com/{VERTEX_API_VERSION}/projects/{project}/locations/us/publishers/google/models/{DREAM_MODEL}:{method}'
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
