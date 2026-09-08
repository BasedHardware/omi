from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from collections.abc import Mapping
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database._client import get_customer_firestore_client
from database import redis_db, users as users_db
from config.plan_catalog import DESKTOP_PROFILE_DEFAULTS
from models.users import PlanType, Subscription
from utils.env_loader import EnvStage, resolve_stage_from_env
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.desktop_llm_stub import llm_stub_enabled
from utils.llm.gateway_client import llm_gateway_headers
from utils.llm.gateway_observability import record_direct_exception_surface
from utils.llm.prompt_cache import EXPLICIT_CACHE_OPTIONS, has_cacheable_prefix
from utils.llm.providers import get_openai_api_key
from utils.journey_metrics_contract import ClientKind, resolve_client_kind_from_headers
from utils.observability.fallback import record_fallback
from utils.observability.journeys import ClientJourneyAttempt
from utils.other.endpoints import get_current_user_uid
from utils.subscription import (
    DESKTOP_ACCESS_TIER_FREE,
    effective_desktop_access_tier,
    is_desktop_trial_paywalled,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_REQUEST_BYTES = 5 * 1024 * 1024
_QUOTA_WINDOW_SECONDS = redis_db.PROACTIVE_QUOTA_COMMITTED_WINDOW_SECONDS
# The gateway client bounds each provider attempt at 20 seconds and the
# structured-output recovery path allows one retry. A 90-second Redis lease
# leaves headroom for rollout refreshes and executor scheduling while still
# expiring quickly after cancellation or process death.
_QUOTA_LEASE_SECONDS = redis_db.PROACTIVE_QUOTA_LEASE_SECONDS
# The catalog owns these profile allocations. They are deliberately not a
# constant multiple of a shared base row: measured desktop dogfooding runs
# ~37 extraction calls per hour of active use, so the architect extraction
# ceiling is sized for a genuine 24-hour day (~888 calls) plus burst headroom,
# while reasoning is sized for a background reconciler that batches ~2 calls per
# pass on top of the per-visit gate and director calls. Lower tiers are sized
# for a partial day and stay governed by the device-side frequency gate.
_OPERATION_LANES = {
    "proactive_extraction": "omi:auto:desktop-proactive-extraction",
    "proactive_reasoning": "omi:auto:desktop-proactive-reasoning",
}
_DIRECT_MODELS = {
    "proactive_extraction": "gpt-5-nano",
    "proactive_reasoning": "gpt-5.6-luna",
}
# Must match generated_route_overrides.yaml for these features. The direct
# recovery path previously used medium for reasoning, which let luna spend a
# client 800-token cap entirely on hidden reasoning and return truncated JSON.
_DIRECT_REASONING_EFFORT = {
    "proactive_extraction": "minimal",
    "proactive_reasoning": "low",
}
# The Pydantic field maximum is also the last-resort reasoning retry ceiling.
_MAX_COMPLETION_TOKENS = 4096
# Proven recovery budget for length-exhausted structured output. Extraction
# retries at this ceiling. Reasoning uses it as the first-attempt floor: a
# 5-hour dogfood session exhausted the client's 800-token cap on 29/30 luna
# failures (HTTP 200, truncated JSON, 1.7–2.9s). Unused cap is not billed.
_DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS = 2400
_REASONING_MIN_COMPLETION_TOKENS = _DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS
_INVALID_STRUCTURED_OUTPUT_STATUS = 422
_INVALID_STRUCTURED_OUTPUT_DETAIL = "Proactive model returned invalid structured output"


@dataclass(frozen=True)
class _ProviderRequest:
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]
    fallback_class: str


@dataclass(frozen=True)
class ProactiveQuotaState:
    limit: int
    remaining: int
    reset_seconds: int
    reservation_token: str


_QUOTA_LIMIT_HEADER = "X-Proactive-Quota-Limit"
_QUOTA_REMAINING_HEADER = "X-Proactive-Quota-Remaining"
_QUOTA_RESET_HEADER = "X-Proactive-Quota-Reset"


def _quota_headers(state: ProactiveQuotaState, *, include_retry_after: bool = False) -> dict[str, str]:
    headers = {
        _QUOTA_LIMIT_HEADER: str(state.limit),
        _QUOTA_REMAINING_HEADER: str(state.remaining),
        _QUOTA_RESET_HEADER: str(state.reset_seconds),
    }
    if include_retry_after:
        headers["Retry-After"] = str(state.reset_seconds)
    return headers


def _apply_quota_headers(response: Response | None, state: ProactiveQuotaState | None) -> None:
    if response is None or state is None:
        return
    for name, value in _quota_headers(state).items():
        response.headers[name] = value


def _dev_direct_provider_allowed() -> bool:
    stage = resolve_stage_from_env()
    if stage in {EnvStage.DEV.value, EnvStage.LOCAL.value}:
        return True
    release_channel = os.getenv("OMI_DESKTOP_BACKEND_RELEASE_CHANNEL", "").strip().lower()
    return release_channel in {"development", "local"}


def _proactive_provider_request(request: "ProactiveCompletionRequest", uid: str, request_id: str) -> _ProviderRequest:
    payload = _gateway_payload(request)
    gateway_url = os.getenv("OMI_LLM_GATEWAY_URL", "").strip()
    if gateway_url:
        # This surface is desktop-only traffic, so the platform is known statically.
        headers = llm_gateway_headers(feature=f"desktop_{request.operation.value}", platform="desktop")
        headers["X-Omi-User-Uid"] = uid
        headers["X-Omi-Request-ID"] = request_id
        return _ProviderRequest(
            url=f"{gateway_url.rstrip('/')}/v1/chat/completions",
            headers=headers,
            payload=payload,
            fallback_class="none",
        )

    if not _dev_direct_provider_allowed():
        raise HTTPException(status_code=503, detail="Proactive model gateway is not configured")
    api_key = get_openai_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Proactive model provider is not configured")
    payload["model"] = _DIRECT_MODELS[request.operation.value]
    # OpenAI reasoning models otherwise default to spending the entire completion
    # budget on hidden reasoning. Extraction then returns an empty message with
    # finish_reason=length instead of the required strict JSON payload. Reasoning
    # matches the gateway lane (low), not medium: medium plus the client's 800-token
    # cap is the combination that returned truncated JSON as a 502.
    payload["reasoning_effort"] = _DIRECT_REASONING_EFFORT[request.operation.value]
    # Keep the breakpointed messages built above. The desktop client packs the stable
    # bucket prompt, the volatile frame metadata and the screenshot into ONE user
    # message, and the provider only serves a cache read from a prefix that ends on a
    # message boundary or on an explicit breakpoint. Replacing these with the raw
    # request messages removes the only readable boundary in the prompt, which charges
    # a full cache write on every call and lets no read ever hit.
    # prompt_cache_options and metadata are gateway extensions, not OpenAI request
    # fields; prompt_cache_key is a real OpenAI field and is kept.
    payload.pop("prompt_cache_options", None)
    payload.pop("metadata", None)
    return _ProviderRequest(
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
        fallback_class="dev_direct_openai",
    )


def _quota_limit_for_subscription(operation: ProactiveOperation, subscription: Subscription | None) -> int:
    """Return the server-authoritative proactive ceiling for a verified plan."""
    plan = subscription.plan if subscription is not None else PlanType.basic
    tier = effective_desktop_access_tier(plan, subscription)
    # Keep the lookup total: an unrecognised tier resolves to the catalog's
    # free profile rather than raising, so a new tier string can never 500 the
    # lane. The router owns the meter and reservation mechanics; the catalog
    # owns the per-profile allocation.
    profile = DESKTOP_PROFILE_DEFAULTS.get(tier, DESKTOP_PROFILE_DEFAULTS[DESKTOP_ACCESS_TIER_FREE])
    limits = profile['proactivity_daily']
    return int(limits[operation.value])


class ProactiveOperation(str, Enum):
    EXTRACTION = "proactive_extraction"
    REASONING = "proactive_reasoning"


class ProactiveCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ProactiveOperation
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=16)
    response_format: dict[str, Any]
    max_completion_tokens: int = Field(default=1024, ge=1, le=_MAX_COMPLETION_TOKENS)
    cache_key: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> "ProactiveCompletionRequest":
        if self.cache_key is not None and self.operation != ProactiveOperation.REASONING:
            raise ValueError("explicit caching is available only for proactive_reasoning")
        if self.response_format.get("type") != "json_schema":
            raise ValueError("response_format.type must be json_schema")
        json_schema = self.response_format.get("json_schema")
        if not isinstance(json_schema, dict):
            raise ValueError("response_format.json_schema must be an object")
        name = json_schema.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("response_format.json_schema.name is required")
        if json_schema.get("strict") is not True:
            raise ValueError("response_format.json_schema.strict must be true")
        schema = json_schema.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("response_format.json_schema.schema must be an object")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ValueError("response_format.json_schema.schema is invalid") from exc
        encoded = json.dumps(self.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise ValueError("request exceeds the 5 MiB proactive payload limit")
        return self


class ProactiveUsageEnvelope(BaseModel):
    cached_tokens: int = 0
    cache_write_tokens: int = 0


class ProactiveCompletionEnvelope(BaseModel):
    operation: ProactiveOperation
    lane: str
    provider_model: str
    usage: ProactiveUsageEnvelope
    cache_write: bool
    fallback_class: str
    response: dict[str, Any]


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
    if await run_blocking(db_executor, is_desktop_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


def _customer_subscription(uid: str) -> Subscription | None:
    return users_db.get_user_valid_subscription(
        uid,
        firestore_client=get_customer_firestore_client(),
        provision=False,
    )


async def _consume_quota(uid: str, operation: ProactiveOperation) -> ProactiveQuotaState:
    operation_value = operation.value
    try:
        subscription = await run_blocking(
            db_executor,
            _customer_subscription,
            uid,
        )
        limit = _quota_limit_for_subscription(operation, subscription)
        allowed, remaining, reset_seconds, reservation_token = await run_blocking(
            critical_executor,
            redis_db.reserve_proactive_rate_limit,
            uid,
            f"desktop_{operation_value}",
            limit,
            _QUOTA_WINDOW_SECONDS,
            lease_seconds=_QUOTA_LEASE_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Proactive metering is temporarily unavailable") from exc
    state = ProactiveQuotaState(
        limit=limit,
        remaining=remaining,
        reset_seconds=reset_seconds,
        reservation_token=reservation_token or "",
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Proactive request limit exceeded",
            headers=_quota_headers(state, include_retry_after=True),
        )
    if not state.reservation_token:
        raise HTTPException(status_code=503, detail="Proactive metering lease is unavailable")
    return state


async def _renew_quota(uid: str, operation: ProactiveOperation, reservation_token: str) -> None:
    if not reservation_token:
        raise HTTPException(status_code=503, detail="Proactive metering lease is unavailable")
    try:
        renewed, _ = await run_blocking(
            critical_executor,
            redis_db.renew_proactive_rate_limit,
            uid,
            f"desktop_{operation.value}",
            reservation_token,
            window=_QUOTA_WINDOW_SECONDS,
            lease_seconds=_QUOTA_LEASE_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Proactive metering is temporarily unavailable") from exc
    if not renewed:
        raise HTTPException(status_code=503, detail="Proactive metering lease expired")


async def _finalize_quota(uid: str, operation: ProactiveOperation, reservation_token: str) -> int:
    if not reservation_token:
        raise HTTPException(status_code=503, detail="Proactive metering lease is unavailable")
    try:
        finalized, reset_seconds = await run_blocking(
            critical_executor,
            redis_db.finalize_proactive_rate_limit,
            uid,
            f"desktop_{operation.value}",
            reservation_token,
            window=_QUOTA_WINDOW_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Proactive metering is temporarily unavailable") from exc
    if not finalized:
        raise HTTPException(status_code=503, detail="Proactive metering lease expired")
    return reset_seconds


_pending_proactive_finalizations: set[asyncio.Task[int]] = set()


async def _finalize_quota_after_success(
    uid: str,
    operation: ProactiveOperation,
    reservation_token: str,
) -> int:
    """Submit successful-work finalization even if response delivery is cancelled.

    The task is strongly retained only until its Redis call settles. It is not
    part of the ordinary background-task registry and is never cancellation- or
    shutdown-drained: process death intentionally leaves the pending lease to
    expire, while request cancellation after validation cannot prevent a
    submitted finalization from counting successful provider work.
    """
    finalization_task = asyncio.create_task(
        _finalize_quota(uid, operation, reservation_token),
        name="proactive-quota-finalize",
    )
    _pending_proactive_finalizations.add(finalization_task)

    def observe_finalization(completed: asyncio.Task[int]) -> None:
        _pending_proactive_finalizations.discard(completed)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error("Proactive quota finalization failed: %s", type(error).__name__)

    finalization_task.add_done_callback(observe_finalization)
    return await asyncio.shield(finalization_task)


async def _release_quota(uid: str, operation: ProactiveOperation, reservation_token: str) -> None:
    if not reservation_token:
        return
    try:
        await run_blocking(
            critical_executor,
            redis_db.release_proactive_rate_limit,
            uid,
            f"desktop_{operation.value}",
            reservation_token,
        )
    except Exception:
        logger.exception("Failed to release proactive quota reservation uid=%s operation=%s", uid, operation.value)


def _stub_value_for_schema(schema: Mapping[str, Any]) -> Any:
    if "const" in schema:
        return schema["const"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[-1] if "silence" in enum_values else enum_values[0]
    for branch_key in ("oneOf", "anyOf"):
        branches = schema.get(branch_key)
        if isinstance(branches, list) and branches and isinstance(branches[0], Mapping):
            return _stub_value_for_schema(branches[0])
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((value for value in schema_type if value != "null"), "null")
    if schema_type == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            return {}
        return {
            name: _stub_value_for_schema(properties[name])
            for name in required
            if name in properties and isinstance(properties[name], Mapping)
        }
    if schema_type == "array":
        items = schema.get("items")
        minimum = schema.get("minItems")
        count = minimum if isinstance(minimum, int) and minimum > 0 else 0
        value = _stub_value_for_schema(items) if isinstance(items, Mapping) else None
        return [value for _ in range(count)]
    if schema_type == "string":
        minimum = schema.get("minLength")
        return "x" * (minimum if isinstance(minimum, int) and minimum > 0 else 0)
    if schema_type in {"integer", "number"}:
        minimum = schema.get("minimum")
        return minimum if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) else 0
    if schema_type == "boolean":
        return False
    return None


def _offline_stub_response(request: ProactiveCompletionRequest) -> dict[str, Any]:
    json_schema = request.response_format["json_schema"]
    schema = json_schema["schema"]
    content = json.dumps(_stub_value_for_schema(schema), separators=(",", ":"))
    response: dict[str, Any] = {
        "id": "desktop-proactivity-offline-stub",
        "model": "omi-offline-stub",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    _validate_gateway_output(response, request)
    return response


def _gateway_payload(request: ProactiveCompletionRequest) -> dict[str, Any]:
    operation = request.operation.value
    payload: dict[str, Any] = {
        "model": _OPERATION_LANES[operation],
        "messages": request.messages,
        "response_format": request.response_format,
        "max_completion_tokens": _effective_max_completion_tokens(request),
        "metadata": {
            **request.metadata,
            "omi_feature": f"desktop_{operation}",
            "prompt_version": f"desktop_{operation}.v1",
            "parser_version": "desktop_proactive_json.v1",
        },
    }
    if request.cache_key is not None and has_cacheable_prefix(_stable_prefix_text(request.messages)):
        payload["prompt_cache_key"] = request.cache_key
        payload["prompt_cache_options"] = dict(EXPLICIT_CACHE_OPTIONS)
        payload["messages"] = _add_explicit_cache_breakpoint(request.messages)
    return payload


def _stable_prefix_text(messages: list[dict[str, Any]]) -> str:
    """Return the text a breakpoint would mark as cacheable, for a size preflight.

    A prefix under the provider minimum is never served back as a read, so marking
    it buys nothing. Mirrors the message chosen by ``_add_explicit_cache_breakpoint``.
    """
    for message in reversed(messages):
        content = message.get("content")
        if isinstance(content, list):
            first = next((part for part in content if isinstance(part, dict)), None)
            if first is not None and first.get("type") == "text" and isinstance(first.get("text"), str):
                return first["text"]
            return ""
        if isinstance(content, str):
            return content
    return ""


def _add_explicit_cache_breakpoint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the stable prompt prefix for the gateway's explicit cache protocol.

    The desktop client sends the stable bucket prompt as the first text part, followed
    by volatile task/frame metadata and then the current image. Keep the marker after
    only that first text part so per-frame timestamps do not rewrite the cache prefix.
    """
    copied = [dict(message) for message in messages]
    for message in reversed(copied):
        content = message.get("content")
        if isinstance(content, list):
            parts = [dict(part) if isinstance(part, dict) else part for part in content]
            if any(
                isinstance(part, dict) and part.get("prompt_cache_breakpoint") == {"mode": "explicit"} for part in parts
            ):
                return copied
            marker = {"type": "text", "text": "", "prompt_cache_breakpoint": {"mode": "explicit"}}
            first_volatile_index = next(
                (
                    index
                    for index, part in enumerate(parts[1:], start=1)
                    if isinstance(part, dict) and part.get("type") in {"text", "image_url"}
                ),
                len(parts),
            )
            parts.insert(first_volatile_index, marker)
            message["content"] = parts
            return copied
        if isinstance(content, str):
            message["content"] = [
                {"type": "text", "text": content},
                {"type": "text", "text": "", "prompt_cache_breakpoint": {"mode": "explicit"}},
            ]
            return copied
    return copied


def _usage_envelope(response: Mapping[str, Any]) -> ProactiveUsageEnvelope:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return ProactiveUsageEnvelope()
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, Mapping):
        details = usage.get("input_tokens_details")
    if not isinstance(details, Mapping):
        return ProactiveUsageEnvelope()

    def token_count(name: str) -> int:
        value = details.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0

    return ProactiveUsageEnvelope(
        cached_tokens=token_count("cached_tokens"),
        cache_write_tokens=token_count("cache_write_tokens"),
    )


def _effective_max_completion_tokens(request: ProactiveCompletionRequest) -> int:
    """Return the completion cap actually forwarded to the provider.

    The desktop client sizes ``max_completion_tokens`` for visible JSON. A
    reasoning model can spend that entire cap on hidden tokens, so reasoning
    requests are raised to the budget that already recovers extraction length
    exhaustion. Unused cap is not billed; a retry that doubles delivery-path
    latency is reserved for the remaining truncations.
    """
    requested = request.max_completion_tokens
    if request.operation == ProactiveOperation.REASONING:
        return max(requested, _REASONING_MIN_COMPLETION_TOKENS)
    return requested


def _retry_max_completion_tokens(operation: ProactiveOperation) -> int:
    if operation == ProactiveOperation.REASONING:
        return _MAX_COMPLETION_TOKENS
    return _DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS


def _looks_like_truncated_json(content: str) -> bool:
    stripped = content.rstrip()
    if not stripped:
        return True
    try:
        json.loads(stripped)
    except json.JSONDecodeError as exc:
        if exc.msg.startswith("Unterminated string"):
            return True
        if exc.msg == "Extra data":
            return False
        # A length-limited JSON object/array normally ends at an unfinished
        # structural token. Do not retry arbitrary malformed JSON whose parse
        # error occurs away from the end of the provider content.
        if exc.pos == len(stripped):
            return True
        if exc.pos < max(len(stripped) - 1, 0):
            return False
        return stripped.endswith(("{", "[", ":", ",", '"'))
    return False


def _should_retry_truncated_structured_output(
    response: Any,
    request: ProactiveCompletionRequest,
    *,
    attempted_max_completion_tokens: int,
) -> bool:
    """Retry once when a reasoning model spent the completion cap on hidden tokens.

    The backend resizes the budget on retry, which a client retry of the same
    800-token request cannot do. Transport errors are not retried here: 429 must
    reach the client cooldown, and a 4xx/5xx without a changed request would
    hide an outage as a transient blip.
    """
    if attempted_max_completion_tokens >= _retry_max_completion_tokens(request.operation):
        return False
    if not isinstance(response, Mapping):
        return False
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return False
    choice = choices[0]
    if not isinstance(choice, Mapping) or choice.get("finish_reason") != "length":
        return False
    message = choice.get("message")
    if not isinstance(message, Mapping) or message.get("refusal"):
        return False
    content = message.get("content")
    return isinstance(content, str) and _looks_like_truncated_json(content)


def _record_length_retry_outcome(provider_request: _ProviderRequest, outcome: str) -> None:
    """Record one terminal event for the bounded structured-output length retry."""
    direct = provider_request.fallback_class == "dev_direct_openai"
    record_fallback(
        component="llm_gateway",
        from_mode="direct_openai" if direct else "gateway",
        to_mode="direct_openai_retry" if direct else "gateway_retry",
        reason="capability_mismatch",
        outcome=outcome,
        log=logger,
    )


async def _post_provider_completion(
    provider_request: _ProviderRequest,
    *,
    uid: str,
    operation: ProactiveOperation,
    reservation_token: str,
    max_completion_tokens: int | None = None,
) -> Any:
    async with get_llm_gateway_semaphore():
        # Queue before the gateway slot is not paid provider work.  Do not let
        # an unbounded wait consume lease time.
        await _renew_quota(uid, operation, reservation_token)
        payload = provider_request.payload
        if max_completion_tokens is not None:
            payload = {**payload, "max_completion_tokens": max_completion_tokens}
        response = await get_llm_gateway_client().post(
            provider_request.url,
            headers=provider_request.headers,
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def _proactivity_client_kind(x_app_platform: object, user_agent: object) -> ClientKind:
    headers: dict[str, str] = {}
    if isinstance(x_app_platform, str):
        headers['x-app-platform'] = x_app_platform
    if isinstance(user_agent, str):
        headers['user-agent'] = user_agent
    return resolve_client_kind_from_headers(headers)


def _proactivity_issue_class(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return 'upstream_timeout'
    if isinstance(exc, HTTPException):
        if exc.status_code in {408, 504}:
            return 'upstream_timeout'
        if exc.status_code == _INVALID_STRUCTURED_OUTPUT_STATUS:
            return 'invalid_response'
        if exc.status_code == 503:
            return 'dependency_unavailable'
        if exc.status_code >= 500:
            return 'provider_error'
        return 'upstream_rejected'
    if isinstance(exc, httpx.HTTPStatusError):
        return 'upstream_rejected'
    return 'provider_error'


def _preserve_proactivity_error_headers(exc: HTTPException, response: Response) -> None:
    """Carry response headers onto exception responses emitted by FastAPI.

    FastAPI's HTTPException handler builds a new response, so headers already
    placed on the injected ``Response`` (quota state and the gateway join key)
    would otherwise disappear on 4xx/5xx exits. Exception-specific headers,
    such as ``Retry-After``, remain authoritative when both responses supply a
    value; the request ID generated by this route remains the exact join key.
    """
    headers = {
        name: response.headers[name]
        for name in (
            _QUOTA_LIMIT_HEADER,
            _QUOTA_REMAINING_HEADER,
            _QUOTA_RESET_HEADER,
            'Retry-After',
        )
        if response.headers.get(name) is not None
    }
    if exc.headers:
        headers.update({name: value for name, value in exc.headers.items() if name.lower() != 'content-length'})
    request_id = response.headers.get('X-Omi-Request-ID')
    if request_id:
        headers['X-Omi-Request-ID'] = request_id
    exc.headers = headers or None


async def _proactive_completion_unobserved(
    request: ProactiveCompletionRequest,
    response: Response,
    uid: str = Depends(_authorized_desktop_user),
) -> ProactiveCompletionEnvelope:
    # This route is the released proactivity lane that shipped desktop clients
    # poll continuously. It is deliberately NOT gated on the JIT cohort: gating
    # it would silently kill context-bucket extraction for the entire deployed
    # fleet the moment the backend ships, long before any client migrates to
    # the JIT trigger runtime. The JIT lanes enforce admission on their own
    # reservation routes; retiring this lane is a later, explicit operation.
    operation = request.operation.value
    lane = _OPERATION_LANES[operation]
    if llm_stub_enabled():
        response_body = _offline_stub_response(request)
        return ProactiveCompletionEnvelope(
            operation=request.operation,
            lane=lane,
            provider_model="omi-offline-stub",
            usage=ProactiveUsageEnvelope(),
            cache_write=False,
            fallback_class="offline_stub",
            response=response_body,
        )

    quota: ProactiveQuotaState | None = None
    quota_reserved = False
    quota_released = False

    async def release_quota_once() -> None:
        nonlocal quota_released
        if not quota_reserved or quota_released:
            return
        quota_released = True
        assert quota is not None
        await _release_quota(uid, request.operation, quota.reservation_token)

    # Return the same backend-generated correlation id that is sent to the
    # gateway.  This is a join key for durable gateway-attempt accounting; it
    # does not grant a caller any authority and is deliberately absent from
    # the JSON envelope to preserve the client contract.
    request_id = str(uuid4())
    response.headers["X-Omi-Request-ID"] = request_id
    provider_request: _ProviderRequest | None = None
    length_retry_attempted = False
    try:
        quota = await _consume_quota(uid, request.operation)
        quota_reserved = True
        _apply_quota_headers(response, quota)
        provider_request = _proactive_provider_request(request, uid, request_id)
        attempted_max_completion_tokens = provider_request.payload["max_completion_tokens"]
        response_body = await _post_provider_completion(
            provider_request,
            uid=uid,
            operation=request.operation,
            reservation_token=quota.reservation_token,
        )
        if _should_retry_truncated_structured_output(
            response_body,
            request,
            attempted_max_completion_tokens=attempted_max_completion_tokens,
        ):
            length_retry_attempted = True
            retry_max = _retry_max_completion_tokens(request.operation)
            choice = response_body["choices"][0]
            message = choice.get("message") if isinstance(choice, Mapping) else None
            content = message.get("content") if isinstance(message, Mapping) else None
            logger.warning(
                "desktop_proactivity_length_retry operation=%s finish_reason=%s "
                "choices_count=%s content_type=%s content_length=%s initial_max_completion_tokens=%s "
                "retry_max_completion_tokens=%s",
                operation,
                choice.get("finish_reason") if isinstance(choice, Mapping) else "unknown",
                len(response_body["choices"]),
                type(content).__name__,
                len(content) if isinstance(content, str) else 0,
                attempted_max_completion_tokens,
                retry_max,
            )
            response_body = await _post_provider_completion(
                provider_request,
                uid=uid,
                operation=request.operation,
                reservation_token=quota.reservation_token,
                max_completion_tokens=retry_max,
            )
    except asyncio.CancelledError:
        # Cancellation is a failed attempt after reservation. Release exactly
        # once, but keep cancellation visible to the request/task owner.
        await release_quota_once()
        raise
    except HTTPException as exc:
        if length_retry_attempted and provider_request is not None:
            _record_length_retry_outcome(provider_request, "exhausted")
        await release_quota_once()
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        if length_retry_attempted and provider_request is not None:
            _record_length_retry_outcome(provider_request, "exhausted")
        await release_quota_once()
        if isinstance(exc, httpx.HTTPStatusError):
            logger.warning(
                "desktop_proactivity_provider_http_error operation=%s fallback_class=%s status=%s",
                operation,
                provider_request.fallback_class if provider_request is not None else "unknown",
                exc.response.status_code,
            )
        else:
            logger.warning(
                "desktop_proactivity_provider_error operation=%s fallback_class=%s error_type=%s",
                operation,
                provider_request.fallback_class if provider_request is not None else "unknown",
                type(exc).__name__,
            )
        raise HTTPException(status_code=502, detail="Proactive model unavailable") from exc
    if not isinstance(response_body, dict):
        if length_retry_attempted:
            _record_length_retry_outcome(provider_request, "exhausted")
        await release_quota_once()
        raise HTTPException(status_code=502, detail="Proactive model returned an invalid response")
    try:
        _validate_gateway_output(response_body, request)
    except HTTPException as exc:
        if length_retry_attempted:
            _record_length_retry_outcome(provider_request, "exhausted")
        await release_quota_once()
        logger.warning(
            "desktop_proactivity_invalid_structured_output operation=%s fallback_class=%s "
            "provider_model=%s status=%s detail=%s",
            operation,
            provider_request.fallback_class,
            response_body.get("model", "unknown"),
            exc.status_code,
            exc.detail,
        )
        raise
    usage = _usage_envelope(response_body)
    provider_model = response_body.get("model")
    assert provider_request is not None
    assert quota is not None
    finalized_reset_seconds = await _finalize_quota_after_success(uid, request.operation, quota.reservation_token)
    _apply_quota_headers(
        response,
        ProactiveQuotaState(
            limit=quota.limit,
            remaining=quota.remaining,
            reset_seconds=finalized_reset_seconds,
            reservation_token=quota.reservation_token,
        ),
    )
    if length_retry_attempted:
        _record_length_retry_outcome(provider_request, "recovered")
    if provider_request.fallback_class == "dev_direct_openai":
        # A direct provider is only a recovered fallback once the response has
        # passed schema validation and the reservation has been committed. Do
        # not emit recovery telemetry for provider or output-validation errors.
        record_fallback(
            component="llm_gateway",
            from_mode="gateway",
            to_mode="direct_openai",
            reason="config_incomplete",
            outcome="recovered",
            log=logger,
        )
        record_direct_exception_surface(surface="desktop_context_proactivity.dev_direct_openai")
    return ProactiveCompletionEnvelope(
        operation=request.operation,
        lane=lane,
        provider_model=provider_model if isinstance(provider_model, str) else "unknown",
        usage=usage,
        cache_write=usage.cache_write_tokens > 0,
        fallback_class=provider_request.fallback_class,
        response=response_body,
    )


def _invalid_structured_output() -> HTTPException:
    return HTTPException(status_code=_INVALID_STRUCTURED_OUTPUT_STATUS, detail=_INVALID_STRUCTURED_OUTPUT_DETAIL)


def _validate_gateway_output(response: Mapping[str, Any], request: ProactiveCompletionRequest) -> None:
    """Fail closed if the gateway/provider did not honor the strict JSON contract."""
    response_format = request.response_format.get("json_schema")
    schema = response_format.get("schema") if isinstance(response_format, Mapping) else None
    choices = response.get("choices")
    if not isinstance(schema, Mapping) or not isinstance(choices, list) or not choices:
        raise _invalid_structured_output()
    validator = Draft202012Validator(schema)
    for choice in choices:
        if not isinstance(choice, Mapping):
            raise _invalid_structured_output()
        message = choice.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise _invalid_structured_output()
        try:
            decoded = json.loads(content)
            validator.validate(decoded)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise _invalid_structured_output() from exc


@router.post("/v1/desktop/proactivity/completions", response_model=ProactiveCompletionEnvelope)
async def proactive_completion(
    request: ProactiveCompletionRequest,
    response: Response,
    uid: str = Depends(_authorized_desktop_user),
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    user_agent: str | None = Header(None, alias='User-Agent'),
) -> ProactiveCompletionEnvelope:
    attempt = ClientJourneyAttempt(
        'desktop_proactivity',
        _proactivity_client_kind(x_app_platform, user_agent),
    )
    try:
        result = await _proactive_completion_unobserved(request, response, uid=uid)
    except asyncio.CancelledError:
        attempt.cancel()
        raise
    except Exception as exc:
        if isinstance(exc, HTTPException):
            _preserve_proactivity_error_headers(exc, response)
        if isinstance(exc, HTTPException) and exc.status_code == 429:
            attempt.degrade('quota_capped')
        else:
            attempt.fail(_proactivity_issue_class(exc))
        raise
    attempt.succeed()
    return result
