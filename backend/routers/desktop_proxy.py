import asyncio
import json
import os
import re
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from database import redis_db
from llm_gateway.gateway.accounting import ProviderResponseMetadata, vertex_usage_from_response
from llm_gateway.gateway.providers import VertexAccessTokenSupplier
from utils.byok import get_byok_key
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import (
    get_desktop_gemini_client,
    get_desktop_gemini_semaphore,
    get_desktop_gemini_stream_client,
)
from utils.llm import vertex_pt_routing as ptr
from utils.llm import desktop_gemini_gateway
from utils.llm.managed_spend_ledger import DESKTOP_PROXY_CALLER, ManagedAttempt, schedule_managed_attempt
from utils.llm.desktop_llm_stub import (
    llm_stub_enabled,
    stub_gemini_proxy_json,
    stub_gemini_proxy_stream_chunks,
)
from utils.journey_metrics_contract import ClientKind, resolve_client_kind_from_headers
from utils.observability.fallback import record_fallback
from utils.observability.journeys import ClientJourneyAttempt
from utils.managed_compute import Decision, authorize_managed_compute
from utils.other.endpoints import get_current_user_uid
from utils.subscription import RELEASE_PROBE_UID, is_desktop_trial_paywalled

router = APIRouter()

_ALLOWED_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent', 'batchEmbedContents'})
_ALLOWED_MODELS = frozenset(
    {
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-2.5-pro',
        'gemini-3.1-flash-lite',
        'gemini-embedding-001',
    }
)
_VERTEX_MODELS = frozenset(
    {
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-2.5-pro',
        'gemini-3.1-flash-lite',
        'gemini-embedding-001',
    }
)
# Vertex batch embedding is not wire-compatible with the AI Studio batch method.
# Keep the provider decision explicit instead of silently trying one API shape on
# another provider.
_VERTEX_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent'})
# Company-paid Flash text is reserved on Vertex PT. Changing this pin without
# updating the matching tests and backend/docs/vertex-pt-flash.md is the
# 2026-08-04 AI Studio double-pay regression.
VERTEX_PT_MODEL = ptr.PT_MODEL_CURRENT
# Migration target. A PT order for gemini-3.1-flash-lite provisions in ~10
# business days; the proxy promotes itself the first time `dedicated` answers
# on it, with no deploy. See backend/docs/vertex-pt-flash.md.
VERTEX_PT_TARGET_MODEL = ptr.PT_MODEL_TARGET
# Emergency operator pins. Both beat auto-detection so a bad promotion or a
# bad overflow target can be corrected without shipping code. The env names
# live in vertex_pt_routing so the gateway's provider and this kill-switch
# path read the same strings.
_PT_MODEL_OVERRIDE_ENV = ptr.PT_MODEL_OVERRIDE_ENV
_OVERFLOW_MODEL_OVERRIDE_ENV = ptr.OVERFLOW_MODEL_OVERRIDE_ENV
_OVERFLOW_ENABLED_ENV = ptr.OVERFLOW_ENABLED_ENV
# Data-residency pin for the families that have no regional endpoint. `us`
# keeps inference in the US multi-region; `global` would widen it worldwide.
_MULTI_REGION_LOCATION_ENV = ptr.MULTI_REGION_LOCATION_ENV
# How long a PT-capacity observation is trusted before it is re-probed. Bounds
# both the promotion delay after the order lands and the cost of probing.
_PT_PROBE_TTL_SECONDS = 600.0
VERTEX_PT_LOCATION = 'us-central1'
VERTEX_PT_EXPIRES = '~2027-05-28'
VERTEX_PT_CONTRACT = 'Vertex PT: 5 GSU gemini-2.5-flash us-central1, expires ~2027-05-28'
# Over-quota Pro demotes to Flash-Lite (`shared`, on-demand), never to the PT
# model: demoting to `gemini-2.5-flash` silently dumped the Insight tool loop
# (~11% of the reservation) onto the saturated PT lane. Evidence:
# omi-knowledge-base vertex-pt-flash-spend 2026-08-17 workload value ranking.
_QUOTA_DEMOTION_MODEL = 'gemini-2.5-flash-lite'
_MAX_BODY_BYTES = 5 * 1024 * 1024
# Absolute ceiling; also the default for BYOK traffic, which keeps its
# historical behavior.
_MAX_OUTPUT_TOKENS = desktop_gemini_gateway._MAX_OUTPUT_TOKENS  # pyright: ignore[reportPrivateUsage]
# Server-paid requests get a smaller default and clamp. No shipped desktop
# client can emit maxOutputTokens (macOS GenerationConfig has no such field;
# Windows sends none), so every request used to take the 8192 default while the
# largest realistic per-lane budget is ~1024 visible tokens plus a thinking
# budget of up to 1024 (thinking counts toward the output limit on 2.5 models).
# Mean measured output is ~241 tokens — this bounds the paid tail, it does not
# change the mean.
_SERVER_PAID_MAX_OUTPUT_TOKENS = 2048
_DEFAULT_THINKING_BUDGET = desktop_gemini_gateway._DEFAULT_THINKING_BUDGET  # pyright: ignore[reportPrivateUsage]
_MAX_CONTENT_ITEMS = desktop_gemini_gateway._MAX_CONTENT_ITEMS  # pyright: ignore[reportPrivateUsage]
_MAX_CONTENT_PARTS = desktop_gemini_gateway._MAX_CONTENT_PARTS  # pyright: ignore[reportPrivateUsage]
_MAX_INLINE_MEDIA_PARTS = desktop_gemini_gateway._MAX_INLINE_MEDIA_PARTS  # pyright: ignore[reportPrivateUsage]
_BURST_LIMIT = 30
_DAILY_HARD_LIMIT = 1500
_ALLOWED_WORKLOADS = frozenset({'interactive', 'extraction', 'maintenance'})
_ALLOWED_TRAFFIC_TYPES = frozenset({'PROVISIONED_THROUGHPUT', 'ON_DEMAND'})
# Provider routes this proxy calls itself. Company-paid traffic that hops the
# gateway (`llm_gateway`) is already in the ledger under the gateway's own row,
# so only these direct routes write one here; anything else (stub, unselected)
# was never a provider attempt.
_DIRECT_LEDGER_ROUTES = frozenset({'vertex_ai', 'ai_studio', 'ai_studio_byok'})
# The ledger's provider name for Gemini on every route, matching the gateway's
# rate cards (`provider: gemini`), so one query covers gateway and direct rows.
_LEDGER_PROVIDER = 'gemini'

# The deployed Rust proxy originally used a 70/75-second attempt/logical
# contract. A later blind expansion to 235/240 seconds exactly matches the
# incident tail. Restore the bounded non-stream contract while adding the phase
# evidence that was missing. Streaming uses an idle-gap timeout in the shared
# client because a healthy SSE response may legitimately last longer.
_TOTAL_TIMEOUT_SECONDS = 75.0
_CREDENTIAL_TIMEOUT_SECONDS = 5.0
_POOL_WAIT_SECONDS = 5.0
_DISCONNECT_POLL_SECONDS = 0.1
# Both desktop clients already back off on their own (macOS 1s/2s, Windows
# 400/800ms, two retries each), so this only floors how soon a replay may start.
_PROVIDER_UNAVAILABLE_RETRY_AFTER_SECONDS = 1

_REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$')
_REVISION_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$')
_TRACE_PATTERN = re.compile(r'^([0-9a-fA-F]{32})(?:/[^;]+)?(?:;o=[01])?$')
_vertex_tokens = VertexAccessTokenSupplier()

T = TypeVar('T')


@dataclass(frozen=True)
class UpstreamRoute:
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    provider: str
    credential_source: str
    region: str


class RoutingFailure(Exception):
    def __init__(self, *, code: str, message: str, phase: str = 'credential') -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.phase = phase


class _GeminiRateLimitExceeded(HTTPException):
    """Rate-limit response with explicit client replay semantics."""

    def __init__(self, detail: str, *, retryable: bool, retry_after: int) -> None:
        self.retryable = retryable
        super().__init__(
            status_code=429,
            detail=detail,
            headers={
                'Retry-After': str(max(0, int(retry_after))),
                'X-Omi-Retryable': 'true' if retryable else 'false',
            },
        )


class ClientDisconnected(Exception):
    pass


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
        supplied_workload = request.headers.get('x-omi-workload', '').strip().lower()
        self.workload_class = supplied_workload if supplied_workload in _ALLOWED_WORKLOADS else 'unknown'
        self.prompt_token_count: int | None = None
        self.candidates_token_count: int | None = None
        self.total_token_count: int | None = None
        self.cached_content_token_count: int | None = None
        self.thoughts_token_count: int | None = None
        self.traffic_type = 'unknown'
        self.phase = 'validation'
        self.shape = PayloadShape('unknown', 'unknown', 'unknown')
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
            'model': self.model if self.model in _ALLOWED_MODELS else 'unknown',
            'region': _safe_region(self.region),
            'action': self.action if self.action in _ALLOWED_ACTIONS else 'unknown',
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
                api_surface=f'gemini_{self.action}' if self.action in _ALLOWED_ACTIONS else 'gemini_unknown',
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


# Gemini body sanitization moved to utils/llm/desktop_gemini_gateway.py; these
# aliases keep the proxy's call sites and tests stable.
_as_nonnegative_int = desktop_gemini_gateway._as_nonnegative_int  # pyright: ignore[reportPrivateUsage]
_bucket = desktop_gemini_gateway._bucket  # pyright: ignore[reportPrivateUsage]
_payload_shape = desktop_gemini_gateway._payload_shape  # pyright: ignore[reportPrivateUsage]
_sanitize = desktop_gemini_gateway._sanitize  # pyright: ignore[reportPrivateUsage]
_size_bucket = desktop_gemini_gateway._size_bucket  # pyright: ignore[reportPrivateUsage]
PayloadShape = desktop_gemini_gateway.PayloadShape


def _path_parts(path: str) -> tuple[str, str, str]:
    path = path.replace('gemini-3-flash-preview', VERTEX_PT_MODEL)
    prefix, separator, action = path.partition(':')
    model = prefix.removeprefix('models/') if separator and prefix.startswith('models/') else ''
    if action not in _ALLOWED_ACTIONS or model not in _ALLOWED_MODELS:
        raise HTTPException(status_code=403, detail='Gemini model or action is not allowed')
    return path, model, action


def _output_token_cap() -> int:
    """BYOK traffic keeps its historical 8192 ceiling; server-paid requests are
    bounded at 2048 because output burns the PT reservation down at 9x."""
    return _MAX_OUTPUT_TOKENS if get_byok_key('gemini') else _SERVER_PAID_MAX_OUTPUT_TOKENS


def _use_vertex_ai() -> bool:
    return os.getenv('USE_VERTEX_AI', '').strip().lower() in {'1', 'true', 'yes'}


# Observed state of the pending gemini-3.1-flash-lite PT order.
#
# The positive observation is latched: a Provisioned Throughput purchase is a
# long-lived commitment, and expiring it on a TTL would flap the serving model
# every time overflow stopped re-probing. A vanished order still degrades
# safely — requests 429 and overflow absorbs them — and the operator override
# pins the model outright if that is ever not enough.
_pt_target_ready = False
# Learned reachability, per model. A model is entered here only when a real
# `generateContent` attempt came back "no such publisher model", and the entry
# expires on the same TTL as capacity so a routing fix or a serving change
# recovers with no deploy.
#
# Reachability is deliberately NOT probed at startup. The metadata endpoint
# `GET .../publishers/google/models/{m}` is not an oracle — it 404s for
# `gemini-2.5-flash-lite`, which works — so the only honest signal is a real
# inference attempt, and burning one per model per instance is unaffordable on
# Cloud Run, which churns instances constantly. Traffic teaches this table.
#
# Absent key means "never observed unreachable", which is distinct from
# "observed at monotonic 0". time.monotonic() is measured from an arbitrary
# origin — on a freshly started container it can legitimately be smaller than
# the TTL, so seeding an observation with 0.0 would mark a model dead for the
# first _PT_PROBE_TTL_SECONDS of every new instance's life.
_model_unavailable_at: dict[str, float] = {}
# None means "never probed", same sentinel rule as above.
_pt_target_probed_at: float | None = None


def _pt_target_is_ready() -> bool:
    return _pt_target_ready and _model_believed_available(VERTEX_PT_TARGET_MODEL)


def _model_believed_available(model: str) -> bool:
    observed = _model_unavailable_at.get(model)
    if observed is None:
        return True
    return (time.monotonic() - observed) >= _PT_PROBE_TTL_SECONDS


def _unreachable_models() -> frozenset[str]:
    return frozenset(model for model in _model_unavailable_at if not _model_believed_available(model))


def _learns_reachability() -> bool:
    """Whether the current request may teach the reachability table.

    BYOK traffic goes to AI Studio on the user's own key, so its answers say
    nothing about what this project can reach on Vertex. One user's key must
    never be able to latch a model dead for the whole fleet.
    """
    return not get_byok_key('gemini')


def _record_model_unavailable(model: str) -> None:
    global _pt_target_ready
    if not _learns_reachability():
        return
    if _model_believed_available(model):
        print(
            f'desktop_proxy model_unreachable model={model} '
            f'location={_vertex_location(model)} reason=publisher_model_not_found_at_endpoint',
            file=sys.stderr,
            flush=True,
        )
    _model_unavailable_at[model] = time.monotonic()
    if model == VERTEX_PT_TARGET_MODEL:
        # A model that cannot be reached cannot be holding prepaid capacity.
        _pt_target_ready = False


def _record_model_available(model: str) -> None:
    if not _learns_reachability():
        return
    _model_unavailable_at.pop(model, None)


def _pt_probe_due() -> bool:
    """Whether the next overflow request should ask for `dedicated` capacity.

    Probing rides an existing overflow request, so detection costs no extra
    call: overflow only happens when the current reservation is already full,
    which is exactly when a second order matters.
    """
    if _pt_target_ready:
        return False
    if _pt_target_probed_at is None:
        return True
    return (time.monotonic() - _pt_target_probed_at) >= _PT_PROBE_TTL_SECONDS


def _record_pt_target_observation(ready: bool) -> None:
    global _pt_target_ready, _pt_target_probed_at
    _pt_target_probed_at = time.monotonic()
    if ready and not _pt_target_ready:
        _pt_target_ready = True
        print(
            f'desktop_proxy pt_promotion model={VERTEX_PT_TARGET_MODEL} '
            f'reason=dedicated_capacity_observed previous={ptr.PT_MODEL_CURRENT}',
            file=sys.stderr,
            flush=True,
        )


def _provisioned_model() -> str:
    """The model that currently owns prepaid capacity."""
    return ptr.resolve_pt_model(
        target_dedicated_ready=_pt_target_is_ready(),
        override=os.getenv(_PT_MODEL_OVERRIDE_ENV, ''),
    )


def _overflow_enabled() -> bool:
    return os.getenv(_OVERFLOW_ENABLED_ENV, 'true').strip().lower() not in {'0', 'false', 'no', 'off'}


def _fallback_chain(model: str) -> tuple[str, ...]:
    """Reachable models that may serve `model`'s traffic, best first."""
    try:
        return ptr.resolve_fallback_chain(
            model=model,
            pt_model=_provisioned_model(),
            unreachable=_unreachable_models(),
            override=os.getenv(_OVERFLOW_MODEL_OVERRIDE_ENV, ''),
        )
    except ValueError:
        return ()


def _first_reachable(model: str) -> str:
    """`model`, or the best rung of its chain if traffic has proved it dead.

    Falling back before dispatch is what keeps a known-unreachable model from
    costing a wasted round trip on every single request.
    """
    if _model_believed_available(model):
        return model
    for candidate in _fallback_chain(model):
        return candidate
    # Nothing declared and reachable. Keep the request honest and let the
    # provider answer rather than inventing a substitute.
    return model


def _serving_model(model: str) -> str:
    """Map a requested model onto the model that will actually serve it.

    BYOK is never remapped: the user pays for the model they asked for.

    Two server-paid remaps, both cheaper per token than what they replace:
      gemini-2.5-pro   -> gemini-3.1-flash-lite  ($10.00 -> $1.50 out)
      gemini-2.5-flash -> whichever model holds prepaid capacity

    Whatever comes out is then resolved against learned reachability, so a
    model traffic has proved uncallable is stepped past using its declared
    chain instead of failing the request.

    Client-pinned gemini-2.5-flash-lite lanes are deliberately untouched:
    gemini-3.1-flash-lite costs 3.75x more per output token, so promoting those
    lanes would be a large cost regression, not a saving. Its chain is empty
    for exactly that reason.
    """
    if get_byok_key('gemini'):
        return model
    if model == 'gemini-2.5-pro':
        intended = VERTEX_PT_TARGET_MODEL
    elif model == ptr.PT_MODEL_CURRENT:
        intended = _provisioned_model()
    else:
        intended = model
    return _first_reachable(intended)


def _retarget_path(path: str, model: str, action: str) -> str:
    served = _serving_model(model)
    if served == model:
        return path
    return f'models/{served}:{action}'


def _server_paid_flash_text(model: str, action: str) -> bool:
    """Whether this is company-paid PT-class text that must never reach AI Studio.

    Covers both the current reservation and the migration target so the
    2026-08-04 double-pay regression cannot reappear mid-migration.
    """
    return model in {ptr.PT_MODEL_CURRENT, ptr.PT_MODEL_TARGET} and action in {
        'generateContent',
        'streamGenerateContent',
    }


def _vertex_required(model: str, action: str) -> bool:
    if action not in _VERTEX_ACTIONS or model not in _VERTEX_MODELS:
        return False
    return _server_paid_flash_text(model, action) or _use_vertex_ai()


def _regional_location() -> str:
    return os.getenv('GCP_LOCATION', VERTEX_PT_LOCATION).strip() or VERTEX_PT_LOCATION


def _multi_region_location() -> str:
    """Multi-region for the model families that have no regional endpoint.

    Defaults to `us`, not `global`: both answer, but `global` may serve from
    anywhere in the world while every other server-paid call in this service
    runs in `us-central1`. Widening the residency of users' conversations and
    transcripts is an operator decision, so it is one env flip and not a
    literal buried in a URL builder.
    """
    return os.getenv(_MULTI_REGION_LOCATION_ENV, ptr.MULTI_REGION_LOCATION).strip() or ptr.MULTI_REGION_LOCATION


def _vertex_endpoint(model: str) -> tuple[str, str]:
    """The (host, location) a model is actually addressed at.

    Per model, never per process: `gemini-3.x` has no regional endpoint, so a
    fallback chain that crosses families also crosses endpoints.
    """
    return ptr.vertex_endpoint(
        model=model,
        regional_location=_regional_location(),
        multi_region_location=_multi_region_location(),
    )


def _vertex_location(model: str) -> str:
    return _vertex_endpoint(model)[1]


def _vertex_url(model: str, action: str) -> str | None:
    project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
    if model not in _VERTEX_MODELS or action not in _VERTEX_ACTIONS or not project:
        return None
    # Gemini 3.x has no regional endpoint: it needs the un-prefixed host plus a
    # multi-region `locations/{loc}`. Building a regional URL for it is what
    # made every 3.x request 404 in production on 2026-08-18 while the model
    # itself was perfectly callable.
    host, location = _vertex_endpoint(model)
    return f'https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}'


def _studio_url(path: str) -> str:
    return f'https://generativelanguage.googleapis.com/v1beta/{path}'


def _safe_provider_query(query: dict[str, str]) -> dict[str, str]:
    forbidden = {'key', 'access_token', 'oauth_token'}
    if any(key.casefold() in forbidden for key in query):
        raise HTTPException(status_code=400, detail='Provider credential query parameters are not allowed')
    return query


async def _upstream(
    path: str,
    model: str,
    action: str,
    query: dict[str, str],
    *,
    request_type: str | None = None,
) -> UpstreamRoute:
    query = _safe_provider_query(query)
    byok_key = get_byok_key('gemini')
    if byok_key:
        return UpstreamRoute(_studio_url(path), {}, {**query, 'key': byok_key}, 'ai_studio_byok', 'byok', 'global')
    vertex_url = _vertex_url(model, action)
    if vertex_url:
        try:
            async with asyncio.timeout(_CREDENTIAL_TIMEOUT_SECONDS):
                token = await _vertex_tokens.get_access_token()
        except TimeoutError as exc:
            raise RoutingFailure(
                code='routing_credential_timeout',
                message='Gemini routing credentials timed out before provider dispatch',
            ) from exc
        except Exception as exc:
            # A configured Vertex route is an operator/security boundary. Never
            # hide a broken identity by silently moving the request to AI Studio.
            raise RoutingFailure(
                code='routing_credentials_unavailable',
                message='Gemini routing credentials are unavailable',
            ) from exc
        url = vertex_url.rsplit(':', 1)[0] + ':predict' if action == 'embedContent' else vertex_url
        # Without this header Vertex silently spills over-cap requests onto
        # pay-as-you-go. Asking for `dedicated` turns that into a 429 the proxy
        # can route deliberately; everything else is pinned to `shared` so it
        # can never draw down the reservation.
        capacity = request_type or ptr.request_type_for(model=model, pt_model=_provisioned_model())
        return UpstreamRoute(
            url,
            {'Authorization': f'Bearer {token}', ptr.REQUEST_TYPE_HEADER: capacity},
            query,
            'vertex_ai',
            'application_default_credentials',
            _vertex_location(model),
        )
    if _vertex_required(model, action):
        # Missing GOOGLE_CLOUD_PROJECT is the 2026-08-04 production bug: Flash
        # fell through to GEMINI_API_KEY / AI Studio and bypassed Vertex PT.
        raise RoutingFailure(
            code='routing_vertex_not_configured',
            message=f'Gemini Vertex route is required. {VERTEX_PT_CONTRACT}',
            phase='routing',
        )
    server_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not server_key:
        raise RoutingFailure(
            code='routing_not_configured', message='Gemini provider route is not configured', phase='routing'
        )
    return UpstreamRoute(_studio_url(path), {}, {**query, 'key': server_key}, 'ai_studio', 'server_key', 'global')


def _overflow_plan(served_model: str) -> list[tuple[str, str]]:
    """Ordered (model, request_type) attempts to try after prepaid capacity is full.

    Only traffic that was actually routed at the reservation can exhaust it, so
    anything else returns an empty plan and keeps its own error.

    When a probe is due the first attempt asks the migration target for
    `dedicated` capacity. That single request is the whole auto-detection
    mechanism: if a gemini-3.1-flash-lite PT order has landed it succeeds and
    the proxy promotes itself permanently, and if it has not it 429s and the
    plan falls through to the same on-demand call it would have made anyway.
    """
    if not _overflow_enabled():
        return []
    pt_model = _provisioned_model()
    if served_model != pt_model:
        return []
    try:
        ladder = ptr.resolve_overflow_ladder(pt_model=pt_model, override=os.getenv(_OVERFLOW_MODEL_OVERRIDE_ENV, ''))
    except ValueError:
        return []
    plan: list[tuple[str, str]] = []
    for rung in ladder:
        if not _model_believed_available(rung):
            # Skip a rung traffic has proved unreachable; trying it would spend
            # a round trip to fail on every single overflow request.
            continue
        if rung == ptr.PT_MODEL_TARGET and _pt_probe_due():
            plan.append((rung, ptr.REQUEST_TYPE_DEDICATED))
        plan.append((rung, ptr.REQUEST_TYPE_SHARED))
    return plan


def _recovery_plan(served_model: str, status: int, message: str) -> list[tuple[str, str]]:
    """Attempts to make after a response this proxy can route around.

    Two distinct recoverable conditions, for ANY routable model rather than
    just the migration target:
      * the model is not reachable  -> latch the observation so later requests
        skip it entirely, and walk its declared fallback chain
      * the reservation is full     -> walk the overflow ladder

    BYOK responses teach this proxy nothing: they come from a different
    provider and a different project, so one user's key must never latch a
    model dead for everyone.
    """
    if get_byok_key('gemini'):
        return []
    if ptr.is_model_unavailable(status, message):
        _record_model_unavailable(served_model)
        return [(rung, ptr.REQUEST_TYPE_SHARED) for rung in _fallback_chain(served_model)]
    if _overflow_triggered(status, message):
        return _overflow_plan(served_model)
    return []


def _overflow_triggered(status: int, message: str) -> bool:
    return ptr.is_provisioned_capacity_exhausted(status, message) or ptr.is_provisioned_capacity_absent(status, message)


async def _meter_server_request(uid: str, path: str, model: str, action: str) -> str:
    if get_byok_key('gemini'):
        return path
    try:
        burst_allowed, _, burst_retry_after = await run_blocking(
            critical_executor, redis_db.check_rate_limit, uid, 'desktop_gemini_burst', _BURST_LIMIT, 60
        )
        if not burst_allowed:
            raise _GeminiRateLimitExceeded(
                'Gemini request rate limit exceeded', retryable=True, retry_after=burst_retry_after
            )
        daily_allowed, daily_remaining, daily_retry_after = await run_blocking(
            critical_executor,
            redis_db.check_rate_limit,
            uid,
            'desktop_gemini_daily',
            _DAILY_HARD_LIMIT,
            86_400,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Gemini rate limiter is unavailable') from exc
    if not daily_allowed:
        raise _GeminiRateLimitExceeded(
            'Gemini daily request limit exceeded', retryable=False, retry_after=daily_retry_after
        )
    daily_used = _DAILY_HARD_LIMIT - int(daily_remaining)
    soft_limit = 300 if os.getenv('OMI_MODEL_TIER', '').strip().lower() == 'max' else 30
    if daily_used > soft_limit and action not in {'embedContent', 'batchEmbedContents'} and model == 'gemini-2.5-pro':
        record_fallback(
            component='gemini_model',
            from_mode='pro',
            to_mode='flash_lite',
            reason='quota',
            outcome='degraded',
        )
        return f'models/{_QUOTA_DEMOTION_MODEL}:{action}'
    return path


# gemini-embedding-001 single embed uses Vertex :predict when a project is
# configured (~$278/30d). batchEmbedContents stays on AI Studio because the
# Vertex batch wire shape is not compatible.
def _vertex_embedding_request(body: bytes) -> bytes:
    payload = json.loads(body)
    try:
        text = payload['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='embedContent requires content.parts[0].text') from exc
    instance = {'content': text}
    for source, destination in (('taskType', 'task_type'), ('title', 'title')):
        if source in payload:
            instance[destination] = payload[source]
    return json.dumps({'instances': [instance]}, separators=(',', ':')).encode()


def _vertex_embedding_response(body: bytes) -> bytes:
    try:
        values = json.loads(body)['predictions'][0]['embeddings']['values']
    except (KeyError, IndexError, TypeError, ValueError):
        return body
    return json.dumps({'embedding': {'values': values}}, separators=(',', ':')).encode()


async def _wait_for_disconnect(request: Request) -> None:
    while not await request.is_disconnected():
        await asyncio.sleep(_DISCONNECT_POLL_SECONDS)


async def _await_value(awaitable: Awaitable[T]) -> T:
    return await awaitable


async def _cancel_on_disconnect(request: Request, awaitable: Awaitable[T]) -> T:
    upstream_task = asyncio.create_task(_await_value(awaitable), name='desktop-gemini-upstream')
    disconnect_task = asyncio.create_task(_wait_for_disconnect(request), name='desktop-gemini-disconnect')
    try:
        done, _ = await asyncio.wait((upstream_task, disconnect_task), return_when=asyncio.FIRST_COMPLETED)
        if upstream_task in done:
            return await upstream_task
        raise ClientDisconnected
    finally:
        upstream_task.cancel()
        with suppress(asyncio.CancelledError):
            await upstream_task
        disconnect_task.cancel()
        with suppress(asyncio.CancelledError):
            await disconnect_task


async def _read_request_body(request: Request) -> bytes:
    content_length = request.headers.get('content-length')
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdigit():
            raise HTTPException(status_code=400, detail='Content-Length must be a non-negative integer')
        declared_length = int(content_length)
        if declared_length > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail='Request body is too large')

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail='Request body is too large')
        body.extend(chunk)
    return bytes(body)


def _response_headers(
    telemetry: ProxyTelemetry,
    *,
    provider: str | None = None,
    error_class: str | None = None,
    phase: str | None = None,
    retryable: bool | None = None,
    upstream_status: int | None = None,
) -> dict[str, str]:
    headers = {
        'X-Request-Id': telemetry.request_id,
        'X-Omi-Request-Id': telemetry.request_id,
        'X-Omi-Provider': provider or telemetry.provider,
    }
    if error_class:
        headers['X-Omi-Error-Class'] = error_class
    if phase:
        headers['X-Omi-Failure-Phase'] = phase
    if retryable is not None:
        headers['X-Omi-Retryable'] = 'true' if retryable else 'false'
    if upstream_status is not None:
        headers['X-Omi-Upstream-Status'] = str(upstream_status)
    return headers


def _error_response(
    telemetry: ProxyTelemetry,
    *,
    status_code: int,
    code: str,
    message: str,
    phase: str,
    retryable: bool,
    upstream_status: int | None = None,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = _response_headers(
        telemetry,
        error_class=code,
        phase=phase,
        retryable=retryable,
        upstream_status=upstream_status,
    )
    if retry_after is not None:
        headers['Retry-After'] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={'error': code, 'message': message, 'request_id': telemetry.request_id, 'retryable': retryable},
    )


def _timeout_phase(exc: httpx.TimeoutException) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return 'connect'
    if isinstance(exc, httpx.WriteTimeout):
        return 'write'
    if isinstance(exc, httpx.PoolTimeout):
        return 'pool'
    if isinstance(exc, httpx.ReadTimeout):
        return 'read'
    return 'provider'


def _provider_error(response: httpx.Response, telemetry: ProxyTelemetry) -> Response:
    status = response.status_code
    if status == 429:
        code, proxy_status, message, retryable, retry_after = (
            'provider_rate_limited',
            429,
            'Gemini provider rate limited the request',
            True,
            30,
        )
    elif status in {408, 504}:
        code, proxy_status, message, retryable, retry_after = (
            'provider_timeout',
            504,
            'Gemini provider timed out before returning a terminal response',
            False,
            None,
        )
    elif status in {502, 503}:
        # An upstream availability fault is a capacity signal, not a verdict on
        # the request: nothing was delivered, so re-issuing is safe. This proxy
        # delegates the re-issue to the caller, and both desktop clients gate on
        # what it reports here — macOS on `X-Omi-Retryable`, Windows on seeing
        # 503 itself. Collapsing it into a non-retryable 502 revoked that
        # authorization on both, so one provider blip failed the user's call.
        code, proxy_status, message, retryable, retry_after = (
            'provider_unavailable',
            503,
            'Gemini provider is temporarily unavailable',
            True,
            _PROVIDER_UNAVAILABLE_RETRY_AFTER_SECONDS,
        )
    elif status >= 500:
        code, proxy_status, message, retryable, retry_after = (
            'provider_unavailable',
            502,
            'Gemini provider returned an unavailable response',
            False,
            None,
        )
    else:
        code, proxy_status, message, retryable, retry_after = (
            'provider_rejected',
            status,
            'Gemini provider rejected the request',
            False,
            None,
        )
    telemetry.complete(
        outcome=code,
        status_code=proxy_status,
        retryable=retryable,
        upstream_status=status,
        phase='provider',
    )
    return _error_response(
        telemetry,
        status_code=proxy_status,
        code=code,
        message=message,
        phase='provider',
        retryable=retryable,
        upstream_status=status,
        retry_after=retry_after,
    )


async def _acquire_provider_slot(semaphore: asyncio.Semaphore) -> None:
    try:
        async with asyncio.timeout(_POOL_WAIT_SECONDS):
            await semaphore.acquire()
    except TimeoutError as exc:
        raise httpx.PoolTimeout('Desktop Gemini concurrency pool wait exceeded') from exc


def _stream_error_event(*, code: str, phase: str, telemetry: ProxyTelemetry) -> bytes:
    event = {'error': code, 'phase': phase, 'request_id': telemetry.request_id, 'retryable': False}
    return f'data: {json.dumps(event, separators=(",", ":"))}\n\n'.encode()


class _StreamingUsageObserver:
    """Incrementally inspect SSE data fields without retaining response content."""

    # A single SSE event larger than this is not a usage event; stop observing
    # the response rather than retaining provider content or re-scanning it.
    MAX_EVENT_BYTES = 1024 * 1024

    def __init__(self, telemetry: ProxyTelemetry) -> None:
        self.telemetry = telemetry
        self.buffer = bytearray()
        self.disabled = False

    def feed(self, chunk: bytes) -> None:
        if self.disabled:
            return
        self.buffer.extend(chunk)
        if len(self.buffer) > self.MAX_EVENT_BYTES:
            self.buffer = bytearray()
            self.disabled = True
            return
        self.buffer = bytearray(bytes(self.buffer).replace(b'\r\n', b'\n'))
        while b'\n\n' in self.buffer:
            event, _, remainder = self.buffer.partition(b'\n\n')
            self.buffer = bytearray(remainder)
            self._observe_event(bytes(event))

    def finish(self) -> None:
        if self.disabled:
            return
        if self.buffer:
            self._observe_event(bytes(self.buffer))
            self.buffer.clear()

    def _observe_event(self, event: bytes) -> None:
        data_lines = [line[5:].lstrip() for line in event.splitlines() if line.startswith(b'data:')]
        if not data_lines:
            return
        try:
            payload = json.loads(b'\n'.join(data_lines))
        except (TypeError, ValueError):
            return
        if isinstance(payload, dict):
            self.telemetry.observe_gemini_response(payload)


async def _stream_provider(
    request: Request,
    route: UpstreamRoute,
    body: bytes,
    telemetry: ProxyTelemetry,
    *,
    model: str = '',
    action: str = '',
    query: Mapping[str, str] | None = None,
) -> AsyncIterator[bytes]:
    client = get_desktop_gemini_stream_client()
    semaphore = get_desktop_gemini_semaphore()
    usage_observer = _StreamingUsageObserver(telemetry)

    async def open_attempt(attempt_route: UpstreamRoute, attempt_body: bytes) -> tuple[Any, httpx.Response]:
        """Open one upstream stream, holding a provider slot. Caller closes both."""
        telemetry.phase = 'pool'
        await _acquire_provider_slot(semaphore)
        try:
            telemetry.phase = 'connect'
            telemetry.note_dispatch(attempt_route)
            context = client.stream(
                'POST',
                attempt_route.url,
                params=attempt_route.params,
                content=attempt_body,
                headers={'Content-Type': 'application/json', **attempt_route.headers},
            )
            upstream = await _cancel_on_disconnect(request, context.__aenter__())
        except BaseException:
            semaphore.release()
            raise
        return context, upstream

    context: Any | None = None
    upstream: httpx.Response | None = None
    held = False
    try:
        # Each entry is one upstream attempt. Overflow attempts are appended
        # only after the reservation actually reports itself full, so the
        # ordinary path opens exactly one stream as before.
        pending: list[tuple[UpstreamRoute, bytes, str, str]] = [(route, body, model, '')]
        while pending:
            attempt_route, attempt_body, attempt_model, capacity = pending.pop(0)
            async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
                context, upstream = await open_attempt(attempt_route, attempt_body)
                held = True
            telemetry.phase = 'first_byte'
            if upstream.status_code < 400:
                # Positive proof of reachability, which is the only kind this
                # proxy trusts. Clears any stale latch on this model.
                _record_model_available(attempt_model)
                break
            # The body carries the difference between 'reservation full' and
            # ordinary rate limiting, and a streamed error body is not read yet.
            await upstream.aread()
            unavailable = ptr.is_model_unavailable(upstream.status_code, upstream.text)
            exhausted = _overflow_triggered(upstream.status_code, upstream.text)
            if capacity == ptr.REQUEST_TYPE_DEDICATED and not unavailable:
                _record_pt_target_observation(not exhausted)
            # This dispatch is over; record it before recovery routing can fail.
            telemetry.record_attempt('error', _attempt_error_class(upstream.status_code, upstream.text))
            if not pending and query is not None:
                for overflow_model, overflow_capacity in _recovery_plan(
                    attempt_model, upstream.status_code, upstream.text
                ):
                    pending.append(
                        (
                            await _upstream(
                                f'models/{overflow_model}:{action}',
                                overflow_model,
                                action,
                                dict(query),
                                request_type=overflow_capacity,
                            ),
                            body,
                            overflow_model,
                            overflow_capacity,
                        )
                    )
            if pending:
                if context is not None:
                    with suppress(Exception):
                        await context.__aexit__(None, None, None)
                context = None
                semaphore.release()
                held = False
                telemetry.set_route(pending[0][0])
                telemetry.model = pending[0][2]
                continue
            response = _provider_error(upstream, telemetry)
            event = json.loads(bytes(response.body))
            yield f'data: {json.dumps(event, separators=(",", ":"))}\n\n'.encode()
            return
        assert upstream is not None
        async for chunk in upstream.aiter_bytes():
            usage_observer.feed(chunk)
            yield chunk
        usage_observer.finish()
        telemetry.complete(outcome='success', status_code=upstream.status_code, retryable=False, phase='body')
    except ClientDisconnected:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        yield _stream_error_event(code='client_cancelled', phase='client_disconnect', telemetry=telemetry)
    except httpx.TimeoutException as exc:
        phase = _timeout_phase(exc)
        telemetry.complete(outcome=f'{phase}_timeout', status_code=504, retryable=False, phase=phase)
        yield _stream_error_event(code='provider_timeout', phase=phase, telemetry=telemetry)
    except TimeoutError:
        phase = telemetry.phase
        telemetry.complete(outcome='provider_deadline_exceeded', status_code=504, retryable=False, phase=phase)
        yield _stream_error_event(code='provider_deadline_exceeded', phase=phase, telemetry=telemetry)
    except asyncio.CancelledError:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        raise
    except httpx.HTTPError:
        telemetry.complete(outcome='transport_error', status_code=502, retryable=False, phase='body')
        yield _stream_error_event(code='provider_transport_error', phase=telemetry.phase, telemetry=telemetry)
    finally:
        if context is not None:
            with suppress(Exception):
                await context.__aexit__(None, None, None)
        if held:
            semaphore.release()


class _DesktopProactivityStreamOutcome:
    """Prove a Gemini SSE stream emitted content and a terminal candidate."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.has_content = False
        self.has_terminal = False
        self.has_error = False

    def observe(self, item: object) -> None:
        if isinstance(item, str):
            chunk = item.encode('utf-8')
        elif isinstance(item, (bytes, bytearray, memoryview)):
            chunk = bytes(item)
        else:
            return
        self._buffer.extend(chunk)
        normalized = bytes(self._buffer).replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        self._buffer = bytearray(normalized)
        while b'\n\n' in self._buffer:
            frame, _, remainder = self._buffer.partition(b'\n\n')
            self._buffer = bytearray(remainder)
            data = b'\n'.join(line[5:].lstrip() for line in frame.splitlines() if line.startswith(b'data:'))
            if not data:
                continue
            if data.strip() == b'[DONE]':
                continue
            try:
                payload = json.loads(data)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, Mapping):
                continue
            if payload.get('error'):
                self.has_error = True
            content, terminal = _gemini_payload_outcome(payload)
            self.has_content = self.has_content or content
            self.has_terminal = self.has_terminal or terminal

    def failure_when(self, item: object) -> bool:
        self.observe(item)
        return self.has_error

    def success_when(self, _item: object) -> bool:
        return self.has_content and self.has_terminal


def _gemini_payload_outcome(payload: Mapping[str, object]) -> tuple[bool, bool]:
    has_content = False
    has_terminal = False
    candidates = payload.get('candidates')
    if not isinstance(candidates, list):
        return has_content, has_terminal
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        finish_reason = candidate.get('finishReason', candidate.get('finish_reason'))
        has_terminal = has_terminal or isinstance(finish_reason, str) and bool(finish_reason.strip())
        content = candidate.get('content')
        parts = content.get('parts') if isinstance(content, Mapping) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            text = part.get('text') if isinstance(part, Mapping) else None
            if isinstance(text, str) and text.strip():
                has_content = True
    return has_content, has_terminal


def _proxy_client_kind(request: Request) -> ClientKind:
    return resolve_client_kind_from_headers(request.headers)


def _attempt_error_class(status_code: int, body: str) -> str:
    """Why a direct provider attempt failed, for the ledger's bounded error_class."""
    if ptr.is_model_unavailable(status_code, body):
        return 'model_unavailable'
    if _overflow_triggered(status_code, body):
        return 'provider_capacity'
    return _proxy_issue_class(status_code)


def _proxy_issue_class(status_code: int) -> str:
    if status_code in {408, 504}:
        return 'upstream_timeout'
    if status_code == 503:
        return 'dependency_unavailable'
    if status_code >= 500:
        return 'provider_error'
    if status_code >= 400:
        return 'upstream_rejected'
    return 'invalid_response'


def _company_paid_via_gateway(model: str, action: str) -> bool:
    return desktop_gemini_gateway.company_paid_via_gateway(model, action)


def _gateway_envelope() -> desktop_gemini_gateway.ProxyEnvelope:
    return desktop_gemini_gateway.ProxyEnvelope(
        error_response=_error_response,
        response_headers=_response_headers,
        stream_error_event=_stream_error_event,
        cancel_on_disconnect=_cancel_on_disconnect,
        timeout_phase=_timeout_phase,
        client_disconnected=ClientDisconnected,
        provider_unavailable_retry_after=_PROVIDER_UNAVAILABLE_RETRY_AFTER_SECONDS,
    )


async def _proxy_via_gateway(
    request: Request,
    body: bytes,
    *,
    model: str,
    action: str,
    streaming: bool,
    uid: str,
    telemetry: ProxyTelemetry,
) -> Response:
    return await desktop_gemini_gateway.proxy_company_paid_via_gateway(
        request,
        body,
        model=model,
        action=action,
        streaming=streaming,
        uid=uid,
        telemetry=telemetry,
        envelope=_gateway_envelope(),
    )


async def _proxy(request: Request, path: str, streaming: bool, uid: str) -> Response:
    try:
        _, _, action = _path_parts(path)
    except (HTTPException, ValueError):
        return await _proxy_unobserved(request, path, streaming, uid)
    if action not in {'generateContent', 'streamGenerateContent'}:
        return await _proxy_unobserved(request, path, streaming, uid)

    attempt = ClientJourneyAttempt('desktop_proactivity', _proxy_client_kind(request))
    try:
        response = await _proxy_unobserved(request, path, streaming, uid)
    except asyncio.CancelledError:
        attempt.cancel()
        raise
    except Exception as exc:
        if isinstance(exc, HTTPException) and exc.status_code == 429:
            attempt.degrade('quota_capped')
        elif isinstance(exc, HTTPException):
            attempt.fail(_proxy_issue_class(exc.status_code))
        elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            attempt.fail('upstream_timeout')
        else:
            attempt.fail('provider_error')
        raise

    if isinstance(response, StreamingResponse):
        outcome = _DesktopProactivityStreamOutcome()
        response.body_iterator = attempt.observe_stream(
            response.body_iterator,
            success_when=outcome.success_when,
            failure_when=outcome.failure_when,
            failure_class='provider_error',
            missing_success_class='empty_answer',
        )
        return response

    if response.status_code >= 400:
        attempt.fail(_proxy_issue_class(response.status_code))
        return response
    try:
        payload = json.loads(bytes(response.body))
    except (TypeError, ValueError):
        attempt.fail('invalid_response')
    else:
        if isinstance(payload, Mapping) and payload.get('error'):
            attempt.fail('provider_error')
        elif isinstance(payload, Mapping) and _gemini_payload_outcome(payload)[0]:
            attempt.succeed()
        else:
            attempt.fail('empty_answer')
    return response


async def _proxy_unobserved(request: Request, path: str, streaming: bool, uid: str) -> Response:
    telemetry = ProxyTelemetry(request, streaming=streaming)
    telemetry.uid = uid
    telemetry.payer = 'byok' if get_byok_key('gemini') else 'omi'
    try:
        body = await _read_request_body(request)
        telemetry.shape = _payload_shape(body)
        path, model, action = _path_parts(path)
        telemetry.model = model
        telemetry.action = action
        if llm_stub_enabled():
            body_text = body.decode('utf-8', errors='replace')
            telemetry.provider = 'offline_stub'
            telemetry.credential_source = 'none'
            if streaming or action == 'streamGenerateContent':
                chunks = stub_gemini_proxy_stream_chunks(body_text)

                async def stub_stream() -> AsyncIterator[bytes]:
                    for chunk in chunks:
                        yield chunk.encode('utf-8')

                telemetry.complete(outcome='success', status_code=200, retryable=False, phase='stub')
                return StreamingResponse(
                    stub_stream(), media_type='text/event-stream', headers=_response_headers(telemetry)
                )
            payload = stub_gemini_proxy_json(body_text)
            telemetry.complete(outcome='success', status_code=200, retryable=False, phase='stub')
            return Response(
                json.dumps(payload, separators=(',', ':')).encode('utf-8'),
                media_type='application/json',
                headers=_response_headers(telemetry),
            )
        telemetry.phase = 'metering'
        path = await _meter_server_request(uid, path, model, action)
        if _company_paid_via_gateway(model, action):
            # The gateway owns pin/overflow/host policy for company-paid
            # traffic; the requested model (post quota-demotion) picks the
            # lane and this proxy keeps only its BFF limits.
            body = _sanitize(body, action, max_output_tokens=_output_token_cap())
            telemetry.shape = _payload_shape(body)
            return await _proxy_via_gateway(
                request, body, model=model, action=action, streaming=streaming, uid=uid, telemetry=telemetry
            )
        path = _retarget_path(*_path_parts(path))
        _, model, action = _path_parts(path)
        telemetry.model = model
        telemetry.action = action
        body = _sanitize(body, action, max_output_tokens=_output_token_cap())
        telemetry.shape = _payload_shape(body)
    except HTTPException as exc:
        outcome = 'rate_limited' if exc.status_code == 429 else 'validation_rejected'
        phase = telemetry.phase if telemetry.phase == 'metering' else 'validation'
        retryable = exc.retryable if isinstance(exc, _GeminiRateLimitExceeded) else exc.status_code == 429
        telemetry.complete(outcome=outcome, status_code=exc.status_code, retryable=retryable, phase=phase)
        exc.headers = {
            **(exc.headers or {}),
            **_response_headers(telemetry, error_class=outcome, phase=phase, retryable=retryable),
        }
        raise

    try:
        async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
            telemetry.phase = 'routing'
            route = await _upstream(path, model, action, dict(request.query_params))
            telemetry.set_route(route)
            if route.provider == 'vertex_ai' and action == 'embedContent':
                body = _vertex_embedding_request(body)
            if streaming:
                return StreamingResponse(
                    _stream_provider(
                        request,
                        route,
                        body,
                        telemetry,
                        model=model,
                        action=action,
                        query=dict(request.query_params),
                    ),
                    media_type='text/event-stream',
                    headers=_response_headers(telemetry),
                )
            client = get_desktop_gemini_client()
            semaphore = get_desktop_gemini_semaphore()

            async def post(attempt_route: UpstreamRoute, attempt_body: bytes) -> httpx.Response:
                telemetry.phase = 'pool'
                await _acquire_provider_slot(semaphore)
                try:
                    telemetry.phase = 'connect'
                    telemetry.note_dispatch(attempt_route)
                    return await client.post(
                        attempt_route.url,
                        params=attempt_route.params,
                        content=attempt_body,
                        headers={'Content-Type': 'application/json', **attempt_route.headers},
                    )
                finally:
                    semaphore.release()

            response = await _cancel_on_disconnect(request, post(route, body))
            if response.status_code < 400:
                _record_model_available(model)
            recovery = _recovery_plan(model, response.status_code, response.text)
            if recovery:
                query = dict(request.query_params)
                for overflow_model, capacity in recovery:
                    # The attempt that just came back full or unavailable is
                    # its own ledger row before anything else can fail.
                    telemetry.record_attempt('error', _attempt_error_class(response.status_code, response.text))
                    overflow_path = f'models/{overflow_model}:{action}'
                    overflow_route = await _upstream(
                        overflow_path, overflow_model, action, query, request_type=capacity
                    )
                    telemetry.set_route(overflow_route)
                    telemetry.model = overflow_model
                    response = await _cancel_on_disconnect(request, post(overflow_route, body))
                    probing = capacity == ptr.REQUEST_TYPE_DEDICATED
                    unavailable = ptr.is_model_unavailable(response.status_code, response.text)
                    exhausted = _overflow_triggered(response.status_code, response.text)
                    if unavailable:
                        _record_model_unavailable(overflow_model)
                    elif response.status_code < 400:
                        _record_model_available(overflow_model)
                    if probing and not unavailable:
                        _record_pt_target_observation(not exhausted)
                    if not exhausted and not unavailable:
                        break
            telemetry.phase = 'body'
    except HTTPException as exc:
        phase = telemetry.phase if telemetry.phase in {'routing', 'credential'} else 'validation'
        telemetry.complete(outcome='validation_rejected', status_code=exc.status_code, retryable=False, phase=phase)
        exc.headers = {
            **(exc.headers or {}),
            **_response_headers(
                telemetry,
                error_class='validation_rejected',
                phase=phase,
                retryable=False,
            ),
        }
        raise
    except RoutingFailure as exc:
        telemetry.complete(outcome=exc.code, status_code=503, retryable=False, phase=exc.phase)
        return _error_response(
            telemetry,
            status_code=503,
            code=exc.code,
            message=exc.message,
            phase=exc.phase,
            retryable=False,
        )
    except ClientDisconnected:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        return _error_response(
            telemetry,
            status_code=499,
            code='client_cancelled',
            message='Client disconnected before the Gemini request completed',
            phase='client_disconnect',
            retryable=False,
        )
    except httpx.TimeoutException as exc:
        phase = _timeout_phase(exc)
        telemetry.complete(outcome=f'{phase}_timeout', status_code=504, retryable=False, phase=phase)
        return _error_response(
            telemetry,
            status_code=504,
            code='provider_timeout',
            message=f'Gemini provider timed out during {phase}',
            phase=phase,
            retryable=False,
        )
    except TimeoutError:
        phase = telemetry.phase
        status_code = 503 if phase in {'routing', 'credential'} else 504
        code = 'routing_timeout' if status_code == 503 else 'provider_deadline_exceeded'
        telemetry.complete(outcome=code, status_code=status_code, retryable=False, phase=phase)
        return _error_response(
            telemetry,
            status_code=status_code,
            code=code,
            message='Gemini request exceeded the Omi logical deadline',
            phase=phase,
            retryable=False,
        )
    except asyncio.CancelledError:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        raise
    except httpx.HTTPError:
        telemetry.complete(outcome='transport_error', status_code=502, retryable=False, phase=telemetry.phase)
        return _error_response(
            telemetry,
            status_code=502,
            code='provider_transport_error',
            message='Gemini provider transport failed',
            phase=telemetry.phase,
            retryable=False,
        )

    if response.status_code >= 400:
        return _provider_error(response, telemetry)
    content = (
        _vertex_embedding_response(response.content)
        if route.provider == 'vertex_ai' and action == 'embedContent'
        else response.content
    )
    if action == 'generateContent':
        try:
            response_payload = json.loads(response.content)
        except (TypeError, ValueError):
            response_payload = None
        if isinstance(response_payload, dict):
            telemetry.observe_gemini_response(response_payload)
    telemetry.complete(
        outcome='success',
        status_code=response.status_code,
        retryable=False,
        upstream_status=response.status_code,
        phase='body',
    )
    return Response(
        content,
        status_code=response.status_code,
        media_type=response.headers.get('content-type'),
        headers=_response_headers(telemetry),
    )


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
    if await run_blocking(
        db_executor,
        is_desktop_trial_paywalled,
        uid,
        'desktop',
        required_byok_provider='gemini',
    ):
        raise HTTPException(status_code=402, detail='trial_expired')
    return uid


# Gen-1 Gemini generate/stream is the screen-intelligence spend path (free-tier S14).
# screen_frame_judge is the configured Gemini-provider feature, so a request-scoped
# Gemini BYOK key satisfies authorize_managed_compute. embedContent stays ungated
# here (TBD-4 / S24). desktop_proactivity completions are the JIT/context-bucket
# lane and are intentionally not gated in this shard — a blanket 402 there would
# kill the ambient nano triage (S24) and the shipped completion lane
# (test_legacy_clients_are_not_gated_by_jit_rollout).
_PLAN_GATED_PROXY_ACTIONS = frozenset({'generateContent', 'streamGenerateContent'})
_PLAN_GATED_PROXY_FEATURE = 'screen_frame_judge'


def _plan_gate_detail(decision: Decision) -> dict[str, str]:
    plan_type = decision.plan.value if decision.plan is not None else 'basic'
    return {'error': 'plan_gated', 'plan_type': plan_type, 'reason': decision.reason}


async def _enforce_managed_plan_gate(uid: str, path: str) -> None:
    try:
        _, _, action = _path_parts(path)
    except HTTPException:
        return
    if action not in _PLAN_GATED_PROXY_ACTIONS:
        return
    # Same exemption as enforce_chat_quota: dest's candidate probe signs in as
    # this fixed non-human Free-plan UID to prove the Gemini provider path.
    # Gating it 402s every desktop-backend auto-dev promotion (seen on
    # 9cbe134a3c / #12839: `gemini_proxy: HTTP 402 (untyped)`).
    if uid == RELEASE_PROBE_UID:
        return
    funding_owner = 'byok' if get_byok_key('gemini') else 'omi'
    decision = await run_blocking(
        db_executor,
        authorize_managed_compute,
        uid,
        _PLAN_GATED_PROXY_FEATURE,
        funding_owner,
    )
    if decision.allowed:
        return
    if decision.reason == 'authorization_unavailable':
        raise HTTPException(status_code=503, detail='plan authorization is temporarily unavailable')
    raise HTTPException(status_code=402, detail=_plan_gate_detail(decision))


@router.post('/v1/proxy/gemini/{path:path}')
async def gemini_proxy(request: Request, path: str, uid: str = Depends(_authorized_desktop_user)) -> Response:
    await _enforce_managed_plan_gate(uid, path)
    return await _proxy(request, path, False, uid)


@router.post('/v1/proxy/gemini-stream/{path:path}')
async def gemini_stream_proxy(request: Request, path: str, uid: str = Depends(_authorized_desktop_user)) -> Response:
    await _enforce_managed_plan_gate(uid, path)
    return await _proxy(request, path, True, uid)
