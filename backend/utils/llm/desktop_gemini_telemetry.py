"""Terminal telemetry and request-state for the desktop Gemini proxy."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import time
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute

from config.desktop_gemini_attribution_generated import (
    GEMINI_CLIENT_PLATFORMS,
    GEMINI_LANES,
    GEMINI_WORKLOADS,
)
from llm_gateway.gateway.accounting import ProviderResponseMetadata, vertex_usage_from_response
from utils.journey_metrics_contract import resolve_client_kind_from_headers
from utils.llm import desktop_gemini_gateway, vertex_pt_routing as ptr
from utils.llm.managed_spend_ledger import DESKTOP_PROXY_CALLER, ManagedAttempt, schedule_managed_attempt

ALLOWED_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent', 'batchEmbedContents'})
ALLOWED_MODELS = frozenset(
    {
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-2.5-pro',
        'gemini-3.1-flash-lite',
        'gemini-embedding-001',
    }
)
_ALLOWED_WORKLOADS = GEMINI_WORKLOADS
_ALLOWED_TRAFFIC_TYPES = frozenset({'PROVISIONED_THROUGHPUT', 'ON_DEMAND'})
# Provider routes this proxy calls itself. Company-paid traffic that hops the
# gateway (`llm_gateway`) is already in the ledger under the gateway's own row,
# so only these direct routes write one here; anything else (stub, unselected)
# was never a provider attempt.
_DIRECT_LEDGER_ROUTES = frozenset({'vertex_ai', 'ai_studio', 'ai_studio_byok'})
# The ledger's provider name for Gemini on every route, matching the gateway's
# rate cards (`provider: gemini`), so one query covers gateway and direct rows.
_LEDGER_PROVIDER = 'gemini'

_REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$')
_REVISION_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$')
_TRACE_PATTERN = re.compile(r'^([0-9a-fA-F]{32})(?:/[^;]+)?(?:;o=[01])?$')

_LEGACY_PREVIEW_MODEL = 'gemini-3-flash-preview'

_PROXY_TELEMETRY_ATTR = 'desktop_gemini_proxy_telemetry'

_PLATFORM_BY_CLIENT_KIND: Mapping[str, str] = {
    'desktop_macos': 'macos',
    'desktop_windows': 'windows',
    'mobile_android': 'other',
    'mobile_ios': 'other',
    'desktop_linux': 'other',
    'web': 'other',
    'dart_mobile_unknown_os': 'other',
}


@dataclass(frozen=True)
class UpstreamRoute:
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    provider: str
    credential_source: str
    region: str


def _canonical_outcome(outcome: str) -> tuple[str, str]:
    """Telemetry outcomes → the ledger's `success | error | cancelled` with the detail as error_class."""
    if outcome == 'success':
        return 'success', 'none'
    if outcome == 'client_cancelled':
        return 'cancelled', 'client_cancelled'
    return 'error', outcome


def _safe_revision(value: object) -> str:
    text = str(value or '').strip()
    return text if _REVISION_PATTERN.fullmatch(text) else 'unknown'


def _safe_region(value: object) -> str:
    # Regional (`us-central1`) and multi-region (`us`, `eu`, `global`) labels
    # are both legitimate now that 3.x traffic is addressed multi-region, so
    # the bare form must survive telemetry instead of being logged as 'none'.
    text = str(value or '').strip().lower()
    return text if re.fullmatch(r'[a-z]{2,16}(?:-[a-z0-9]{1,16}){0,2}', text) else 'none'


def _status_class(status: int | None) -> str:
    if status is None:
        return 'none'
    if status == 429:
        return '429'
    if 100 <= status <= 599:
        return f'{status // 100}xx'
    return 'unknown'


class ProxyTelemetry:
    def __init__(self, request: Request, *, streaming: bool) -> None:
        supplied_request_id = request.headers.get('x-omi-request-id') or request.headers.get('x-request-id') or ''
        self.request_id = supplied_request_id if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
        trace_header = request.headers.get('x-cloud-trace-context', '')
        trace_match = _TRACE_PATTERN.fullmatch(trace_header)
        self.trace_id = trace_match.group(1).lower() if trace_match else ''
        self.route = 'stream' if streaming else 'nonstream'
        self.provider = 'unselected'
        self.credential_source = 'none'
        self.region = 'none'
        self.model = 'unknown'
        self.action = 'unknown'
        supplied_lane = request.headers.get('x-omi-lane', '').strip().lower()
        self.lane = supplied_lane if supplied_lane in GEMINI_LANES else 'unknown'
        supplied_workload = request.headers.get('x-omi-workload', '').strip().lower()
        self.workload_class = supplied_workload if supplied_workload in _ALLOWED_WORKLOADS else 'unknown'
        self.client_platform = _PLATFORM_BY_CLIENT_KIND.get(
            resolve_client_kind_from_headers(request.headers), 'unknown'
        )
        if self.client_platform not in GEMINI_CLIENT_PLATFORMS:
            self.client_platform = 'unknown'
        self.prompt_token_count: int | None = None
        self.candidates_token_count: int | None = None
        self.total_token_count: int | None = None
        self.cached_content_token_count: int | None = None
        self.thoughts_token_count: int | None = None
        self.traffic_type = 'unknown'
        self.phase = 'validation'
        self.shape = desktop_gemini_gateway.PayloadShape('unknown', 'unknown', 'unknown')
        self.started = time.monotonic()
        self.completed = False
        # Ledger attribution only. Never written to the log event above. One
        # invocation per request; one attempt per provider dispatch.
        self.uid: str | None = None
        self.payer = 'omi'
        self.invocation_id = str(uuid4())
        self.attempts = 0
        self._pending_attempt: str | None = None
        self.provider_metadata: ProviderResponseMetadata | None = None

    def identify(self, path: str) -> None:
        candidate = path.replace(_LEGACY_PREVIEW_MODEL, ptr.PT_MODEL_CURRENT)
        prefix, separator, action = candidate.partition(':')
        model = prefix.removeprefix('models/') if separator and prefix.startswith('models/') else ''
        self.model = model if model in ALLOWED_MODELS else 'unknown'
        self.action = action if action in ALLOWED_ACTIONS else 'unknown'

    def set_route(self, route: UpstreamRoute) -> None:
        self.provider = route.provider
        self.credential_source = route.credential_source
        self.region = route.region

    def observe_gemini_response(self, response: Mapping[str, Any]) -> None:
        """Retain only bounded billing metadata from a Gemini response."""
        metadata = vertex_usage_from_response(response)
        if metadata.traffic_type in _ALLOWED_TRAFFIC_TYPES:
            self.traffic_type = metadata.traffic_type
        if metadata.usage is None:
            return
        # Streaming chunks carry cumulative counts; the latest block wins.
        self.provider_metadata = metadata
        usage = metadata.usage
        self.prompt_token_count = usage.prompt_tokens
        self.candidates_token_count = usage.output_tokens
        self.total_token_count = usage.total_tokens
        self.cached_content_token_count = usage.cached_input_tokens
        self.thoughts_token_count = usage.reasoning_tokens

    def complete(
        self,
        *,
        outcome: str,
        status_code: int,
        retryable: bool,
        upstream_status: int | None = None,
        phase: str | None = None,
    ) -> None:
        if self.completed:
            return
        self.completed = True
        phase = phase or self.phase
        event: dict[str, object] = {
            'severity': 'INFO' if 200 <= status_code < 400 else 'WARNING',
            'message': 'desktop_gemini_proxy_terminal',
            'event': 'desktop_gemini_proxy_terminal',
            'service': 'desktop-backend',
            'runtime_implementation': 'python',
            'revision': _safe_revision(os.getenv('K_REVISION')),
            'release_sha': _safe_revision(os.getenv('OMI_DESKTOP_BACKEND_RELEASE_SHA')),
            'request_id': self.request_id,
            'route': self.route,
            'provider_route': self.provider,
            'credential_source': self.credential_source,
            'model': self.model if self.model in ALLOWED_MODELS else 'unknown',
            'region': _safe_region(self.region),
            'action': self.action if self.action in ALLOWED_ACTIONS else 'unknown',
            'lane': self.lane if self.lane in GEMINI_LANES else 'unknown',
            'client_platform': self.client_platform if self.client_platform in GEMINI_CLIENT_PLATFORMS else 'unknown',
            'workload_class': self.workload_class,
            'traffic_type': self.traffic_type,
            'attempt': 1,
            'phase': phase,
            'outcome': outcome,
            'status_code': status_code,
            'upstream_status': upstream_status or 0,
            'upstream_status_class': _status_class(upstream_status),
            'retryable': retryable,
            'payload_size_bucket': self.shape.size_bucket,
            'content_parts_bucket': self.shape.content_parts_bucket,
            'inline_media_parts_bucket': self.shape.inline_media_bucket,
            'elapsed_ms': round((time.monotonic() - self.started) * 1000),
        }
        if self.prompt_token_count is not None:
            event.update(
                {
                    'prompt_token_count': self.prompt_token_count,
                    'candidates_token_count': self.candidates_token_count,
                    'total_token_count': self.total_token_count,
                    'cached_content_token_count': self.cached_content_token_count,
                    'thoughts_token_count': self.thoughts_token_count,
                }
            )
        project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
        if self.trace_id and project:
            event['logging.googleapis.com/trace'] = f'projects/{project}/traces/{self.trace_id}'
        # One exact JSON object is ingested as jsonPayload in Cloud Logging.
        # The fixed allowlist above intentionally excludes UIDs, prompts, media,
        # URLs, headers, tokens, raw exceptions, and upstream response bodies.
        sys.stdout.write(json.dumps(event, separators=(',', ':'), sort_keys=True) + '\n')
        sys.stdout.flush()
        self.record_attempt(*_canonical_outcome(outcome))

    def note_dispatch(self, route: UpstreamRoute) -> None:
        """A provider request is about to leave for `route`. Only these become ledger rows.

        Anything that fails before a dispatch (validation, credentials, routing)
        was never a provider attempt and writes nothing.
        """
        if route.provider not in _DIRECT_LEDGER_ROUTES:
            return
        self.attempts += 1
        self._pending_attempt = route.provider
        self.provider_metadata = None

    def record_attempt(self, outcome: str, error_class: str) -> None:
        """Close the pending provider attempt with one ledger row, best-effort.

        Overflow recovery calls this for each attempt that failed before moving
        to the next route; `complete()` closes the last one. Gateway-routed and
        stub traffic never dispatch here (the gateway writes its own row).
        """
        route = self._pending_attempt
        self._pending_attempt = None
        if route is None or not self.uid:
            return
        schedule_managed_attempt(
            ManagedAttempt(
                request_id=self.request_id,
                caller=DESKTOP_PROXY_CALLER,
                user_uid=self.uid,
                feature=desktop_gemini_gateway.DESKTOP_GATEWAY_FEATURE,
                api_surface=f'gemini_{self.action}' if self.action in ALLOWED_ACTIONS else 'gemini_unknown',
                payer=self.payer,
                provider=_LEDGER_PROVIDER,
                configured_model=self.model,
                outcome=outcome,
                error_class=error_class,
                route_artifact_id=f'{DESKTOP_PROXY_CALLER}.{route}',
                metadata=self.provider_metadata,
                invocation_id=self.invocation_id,
                ordinal=self.attempts,
                retry_ordinal=self.attempts,
                fallback_reason='overflow_recovery' if self.attempts > 1 else None,
            )
        )


def get_proxy_telemetry(request: Request, *, streaming: bool) -> ProxyTelemetry:
    telemetry = getattr(request.state, _PROXY_TELEMETRY_ATTR, None)
    if telemetry is None:
        telemetry = ProxyTelemetry(request, streaming=streaming)
        setattr(request.state, _PROXY_TELEMETRY_ATTR, telemetry)
    return telemetry


def _dependency_outcome(exc: HTTPException) -> str:
    if exc.status_code == 402:
        return 'trial_expired' if exc.detail == 'trial_expired' else 'plan_gated'
    if exc.status_code == 503:
        return 'authorization_unavailable'
    if exc.status_code == 429:
        return 'rate_limited'
    return 'authorization_rejected'


async def _terminal_stream_guard(source: AsyncIterable[Any], telemetry: ProxyTelemetry) -> AsyncIterator[Any]:
    iterator = source.__aiter__()
    try:
        async for chunk in iterator:
            yield chunk
        if not telemetry.completed:
            telemetry.complete(outcome='incomplete_stream', status_code=502, retryable=False, phase='body')
    except (asyncio.CancelledError, GeneratorExit):
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        raise
    except BaseException:
        telemetry.complete(outcome='stream_iterator_error', status_code=500, retryable=False, phase='body')
        raise
    finally:
        aclose = getattr(iterator, 'aclose', None)
        if aclose is not None:
            with contextlib.suppress(GeneratorExit):
                await aclose()


class DesktopGeminiProxyRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        route_streaming = 'gemini-stream' in self.path

        async def handler(request: Request) -> Response:
            telemetry = get_proxy_telemetry(request, streaming=route_streaming)
            path = request.path_params.get('path')
            if isinstance(path, str):
                telemetry.identify(path)
            if route_streaming or telemetry.action == 'streamGenerateContent':
                telemetry.route = 'stream'
            try:
                response = await original(request)
            except HTTPException as exc:
                telemetry.complete(
                    outcome=_dependency_outcome(exc),
                    status_code=exc.status_code,
                    retryable=exc.status_code == 429,
                    phase='authorization',
                )
                raise
            except asyncio.CancelledError:
                telemetry.complete(
                    outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect'
                )
                raise
            except Exception:
                telemetry.complete(outcome='internal_error', status_code=500, retryable=False, phase=telemetry.phase)
                raise
            if isinstance(response, StreamingResponse):
                response.body_iterator = _terminal_stream_guard(response.body_iterator, telemetry)
            elif not telemetry.completed:
                telemetry.complete(
                    outcome='success' if response.status_code < 400 else 'unobserved_error',
                    status_code=response.status_code,
                    retryable=False,
                    phase='body',
                )
            return response

        return handler
