from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from collections.abc import Mapping
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database._client import get_customer_firestore_client
from database import redis_db, users as users_db
from models.users import PlanType, Subscription
from utils.env_loader import EnvStage, resolve_stage_from_env
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.desktop_llm_stub import llm_stub_enabled
from utils.llm.gateway_client import llm_gateway_headers
from utils.llm.gateway_observability import record_direct_exception_surface
from utils.llm.providers import get_openai_api_key
from utils.observability.fallback import record_fallback
from utils.other.endpoints import get_current_user_uid
from utils.subscription import (
    DESKTOP_ACCESS_TIER_ARCHITECT,
    DESKTOP_ACCESS_TIER_FULL,
    effective_desktop_access_tier,
    is_desktop_trial_paywalled,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_REQUEST_BYTES = 5 * 1024 * 1024
_QUOTA_WINDOW_SECONDS = 24 * 60 * 60
_OPERATION_DAILY_LIMITS = {
    # Extraction can precede reasoning for several context buckets. Keep its
    # server ceiling at twice the Maximum client director budget so lower
    # notification levels remain governed by their device-side frequency gate.
    "proactive_extraction": 200,
    "proactive_reasoning": 100,
}
_OPERATION_LANES = {
    "proactive_extraction": "omi:auto:desktop-proactive-extraction",
    "proactive_reasoning": "omi:auto:desktop-proactive-reasoning",
}
_DIRECT_MODELS = {
    "proactive_extraction": "gpt-5-nano",
    "proactive_reasoning": "gpt-5.6-luna",
}
_DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS = 2400


@dataclass(frozen=True)
class _ProviderRequest:
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]
    fallback_class: str


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
        headers = llm_gateway_headers(feature=f"desktop_{request.operation.value}")
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
    # finish_reason=length instead of the required strict JSON payload.
    payload["reasoning_effort"] = "minimal" if request.operation == ProactiveOperation.EXTRACTION else "medium"
    # These are gateway cache extensions, not OpenAI request fields.
    payload["messages"] = request.messages
    payload.pop("prompt_cache_key", None)
    payload.pop("prompt_cache_options", None)
    payload.pop("metadata", None)
    record_fallback(
        component="llm_gateway",
        from_mode="gateway",
        to_mode="direct_openai",
        reason="config_incomplete",
        outcome="recovered",
        log=logger,
    )
    record_direct_exception_surface(surface="desktop_context_proactivity.dev_direct_openai")
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
    multiplier = 4 if tier == DESKTOP_ACCESS_TIER_ARCHITECT else 2 if tier == DESKTOP_ACCESS_TIER_FULL else 1
    return _OPERATION_DAILY_LIMITS[operation.value] * multiplier


class ProactiveOperation(str, Enum):
    EXTRACTION = "proactive_extraction"
    REASONING = "proactive_reasoning"


class ProactiveCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ProactiveOperation
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=16)
    response_format: dict[str, Any]
    max_completion_tokens: int = Field(default=1024, ge=1, le=4096)
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


async def _consume_quota(uid: str, operation: ProactiveOperation) -> None:
    operation_value = operation.value
    try:
        subscription = await run_blocking(
            db_executor,
            _customer_subscription,
            uid,
        )
        limit = _quota_limit_for_subscription(operation, subscription)
        allowed, _, retry_after = await run_blocking(
            critical_executor,
            redis_db.reserve_rate_limit,
            uid,
            f"desktop_{operation_value}",
            limit,
            _QUOTA_WINDOW_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Proactive metering is temporarily unavailable") from exc
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Proactive request limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


async def _release_quota(uid: str, operation: ProactiveOperation) -> None:
    try:
        await run_blocking(
            critical_executor,
            redis_db.release_rate_limit,
            uid,
            f"desktop_{operation.value}",
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
        "max_completion_tokens": request.max_completion_tokens,
        "metadata": {
            **request.metadata,
            "omi_feature": f"desktop_{operation}",
            "prompt_version": f"desktop_{operation}.v1",
            "parser_version": "desktop_proactive_json.v1",
        },
    }
    if request.cache_key is not None:
        payload["prompt_cache_key"] = request.cache_key
        payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
        payload["messages"] = _add_explicit_cache_breakpoint(request.messages)
    return payload


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


def _should_retry_direct_extraction(
    response: Any,
    request: ProactiveCompletionRequest,
    provider_request: _ProviderRequest,
) -> bool:
    """Retry only the known dev-direct extraction length exhaustion shape."""
    if (
        provider_request.fallback_class != "dev_direct_openai"
        or request.operation != ProactiveOperation.EXTRACTION
        or request.max_completion_tokens >= _DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS
    ):
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


def _record_direct_extraction_retry_outcome(outcome: str) -> None:
    """Record one terminal event for the bounded direct Nano retry."""
    record_fallback(
        component="llm_gateway",
        from_mode="direct_openai",
        to_mode="direct_openai_retry",
        reason="capability_mismatch",
        outcome=outcome,
        log=logger,
    )


async def _post_provider_completion(
    provider_request: _ProviderRequest,
    *,
    max_completion_tokens: int | None = None,
) -> Any:
    payload = provider_request.payload
    if max_completion_tokens is not None:
        payload = {**payload, "max_completion_tokens": max_completion_tokens}
    async with get_llm_gateway_semaphore():
        response = await get_llm_gateway_client().post(
            provider_request.url,
            headers=provider_request.headers,
            json=payload,
        )
    response.raise_for_status()
    return response.json()


@router.post("/v1/desktop/proactivity/completions", response_model=ProactiveCompletionEnvelope)
async def proactive_completion(
    request: ProactiveCompletionRequest,
    uid: str = Depends(_authorized_desktop_user),
) -> ProactiveCompletionEnvelope:
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

    await _consume_quota(uid, request.operation)
    request_id = str(uuid4())
    provider_request: _ProviderRequest | None = None
    direct_extraction_retry_attempted = False
    try:
        provider_request = _proactive_provider_request(request, uid, request_id)
        response_body = await _post_provider_completion(provider_request)
        if _should_retry_direct_extraction(response_body, request, provider_request):
            direct_extraction_retry_attempted = True
            choice = response_body["choices"][0]
            message = choice.get("message") if isinstance(choice, Mapping) else None
            content = message.get("content") if isinstance(message, Mapping) else None
            logger.warning(
                "desktop_proactivity_direct_extraction_length_retry operation=%s finish_reason=%s "
                "choices_count=%s content_type=%s content_length=%s initial_max_completion_tokens=%s "
                "retry_max_completion_tokens=%s",
                operation,
                choice.get("finish_reason") if isinstance(choice, Mapping) else "unknown",
                len(response_body["choices"]),
                type(content).__name__,
                len(content) if isinstance(content, str) else 0,
                request.max_completion_tokens,
                _DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS,
            )
            response_body = await _post_provider_completion(
                provider_request,
                max_completion_tokens=_DIRECT_EXTRACTION_RETRY_MAX_COMPLETION_TOKENS,
            )
    except HTTPException:
        if direct_extraction_retry_attempted:
            _record_direct_extraction_retry_outcome("exhausted")
        await _release_quota(uid, request.operation)
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        if direct_extraction_retry_attempted:
            _record_direct_extraction_retry_outcome("exhausted")
        await _release_quota(uid, request.operation)
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
        if direct_extraction_retry_attempted:
            _record_direct_extraction_retry_outcome("exhausted")
        await _release_quota(uid, request.operation)
        raise HTTPException(status_code=502, detail="Proactive model returned an invalid response")
    try:
        _validate_gateway_output(response_body, request)
    except HTTPException as exc:
        if direct_extraction_retry_attempted:
            _record_direct_extraction_retry_outcome("exhausted")
        await _release_quota(uid, request.operation)
        logger.warning(
            "desktop_proactivity_invalid_structured_output operation=%s fallback_class=%s provider_model=%s detail=%s",
            operation,
            provider_request.fallback_class,
            response_body.get("model", "unknown"),
            exc.detail,
        )
        raise
    if direct_extraction_retry_attempted:
        _record_direct_extraction_retry_outcome("recovered")
    usage = _usage_envelope(response_body)
    provider_model = response_body.get("model")
    return ProactiveCompletionEnvelope(
        operation=request.operation,
        lane=lane,
        provider_model=provider_model if isinstance(provider_model, str) else "unknown",
        usage=usage,
        cache_write=usage.cache_write_tokens > 0,
        fallback_class=provider_request.fallback_class,
        response=response_body,
    )


def _validate_gateway_output(response: Mapping[str, Any], request: ProactiveCompletionRequest) -> None:
    """Fail closed if the gateway/provider did not honor the strict JSON contract."""
    response_format = request.response_format.get("json_schema")
    schema = response_format.get("schema") if isinstance(response_format, Mapping) else None
    choices = response.get("choices")
    if not isinstance(schema, Mapping) or not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="Proactive model returned invalid structured output")
    validator = Draft202012Validator(schema)
    for choice in choices:
        if not isinstance(choice, Mapping):
            raise HTTPException(status_code=502, detail="Proactive model returned invalid structured output")
        message = choice.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="Proactive model returned invalid structured output")
        try:
            decoded = json.loads(content)
            validator.validate(decoded)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Proactive model returned invalid structured output") from exc
