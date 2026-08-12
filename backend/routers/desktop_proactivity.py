from __future__ import annotations

import json
from collections.abc import Mapping
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database import redis_db
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.other.endpoints import get_current_user_uid
from utils.subscription import is_trial_paywalled

router = APIRouter()

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
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


async def _consume_quota(uid: str, operation: ProactiveOperation) -> None:
    operation_value = operation.value
    try:
        allowed, _, retry_after = await run_blocking(
            critical_executor,
            redis_db.check_rate_limit,
            uid,
            f"desktop_{operation_value}",
            _OPERATION_DAILY_LIMITS[operation_value],
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

    The desktop client sends the stable bucket prompt as the first text part and the
    current frame as a later image part.  Keep the marker before image content so the
    gateway can cache the text prefix without changing the visible prompt.
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
            image_index = next(
                (
                    index
                    for index, part in enumerate(parts)
                    if isinstance(part, dict) and part.get("type") == "image_url"
                ),
                len(parts),
            )
            parts.insert(image_index, marker)
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


@router.post("/v1/desktop/proactivity/completions", response_model=ProactiveCompletionEnvelope)
async def proactive_completion(
    request: ProactiveCompletionRequest,
    uid: str = Depends(_authorized_desktop_user),
) -> ProactiveCompletionEnvelope:
    await _consume_quota(uid, request.operation)
    operation = request.operation.value
    lane = _OPERATION_LANES[operation]
    request_id = str(uuid4())
    headers = llm_gateway_headers(feature=f"desktop_{operation}")
    headers["X-Omi-User-Uid"] = uid
    headers["X-Omi-Request-ID"] = request_id
    try:
        async with get_llm_gateway_semaphore():
            response = await get_llm_gateway_client().post(
                f"{get_llm_gateway_base_url()}/v1/chat/completions",
                headers=headers,
                json=_gateway_payload(request),
            )
        response.raise_for_status()
        response_body = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Proactive model unavailable") from exc
    if not isinstance(response_body, dict):
        raise HTTPException(status_code=502, detail="Proactive model returned an invalid response")
    _validate_gateway_output(response_body, request)
    usage = _usage_envelope(response_body)
    provider_model = response_body.get("model")
    return ProactiveCompletionEnvelope(
        operation=request.operation,
        lane=lane,
        provider_model=provider_model if isinstance(provider_model, str) else "unknown",
        usage=usage,
        cache_write=usage.cache_write_tokens > 0,
        fallback_class="unknown",
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
