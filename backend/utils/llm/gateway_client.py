from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, TypeVar, cast

import httpx
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from pydantic import BaseModel, ValidationError

from utils.llm.gateway_observability import record_direct_exception_surface, record_gateway_request_result

LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'OMI_LLM_GATEWAY_SERVICE_TOKEN'
LEGACY_LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'LLM_GATEWAY_SERVICE_TOKEN'
LLM_GATEWAY_URL_ENV_VAR = 'OMI_LLM_GATEWAY_URL'
DEFAULT_LLM_GATEWAY_URL = 'http://127.0.0.1:9080'
LLM_GATEWAY_AUTO_LANE_PREFIX = 'omi:auto:'
CHAT_STRUCTURED_AUTO_LANE_ID = 'omi:auto:chat-structured'
CHAT_AGENT_AUTO_LANE_ID = 'omi:auto:chat-agent'
LLM_GATEWAY_FEATURE_MODE_ENV_VAR = 'OMI_LLM_GATEWAY_FEATURE_MODE'
LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR = 'OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE'
LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR = 'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION'
LLM_GATEWAY_CALLER = 'backend'
CHAT_EXTRACTION_TIMEOUT_SECONDS = 10.0
BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS = 35.0
GATEWAY_TRANSPORT_STATUS_CODES = frozenset({502, 504})

StructuredOutput = TypeVar('StructuredOutput', bound=BaseModel)
JsonDict = dict[str, Any]
JsonList = list[Any]


def is_gateway_transport_status_code(status_code: object) -> bool:
    return isinstance(status_code, int) and status_code in GATEWAY_TRANSPORT_STATUS_CODES


def _as_json_dict(value: object) -> JsonDict | None:
    return cast(JsonDict, value) if isinstance(value, dict) else None


def _as_json_list(value: object) -> JsonList | None:
    return cast(JsonList, value) if isinstance(value, list) else None


def get_llm_gateway_base_url() -> str:
    configured = os.getenv(LLM_GATEWAY_URL_ENV_VAR, '').strip()
    return configured.rstrip('/') if configured else DEFAULT_LLM_GATEWAY_URL


def get_llm_gateway_service_token() -> str | None:
    for env_var in (LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR, LEGACY_LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR):
        configured = os.getenv(env_var)
        if configured is not None and configured.strip():
            return configured.strip()
    return None


def is_auto_lane_id(model_or_lane: object) -> bool:
    return isinstance(model_or_lane, str) and model_or_lane.startswith(LLM_GATEWAY_AUTO_LANE_PREFIX)


def feature_auto_lane_id(feature: str) -> str:
    return f"{LLM_GATEWAY_AUTO_LANE_PREFIX}{feature.replace('_', '-')}"


def should_route_features_through_gateway() -> bool:
    enabled = os.getenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes', 'gateway'}
    if not enabled:
        return False
    if _is_local_or_dev_runtime():
        return True
    if os.getenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, '').strip().lower() not in {'1', 'true', 'yes'}:
        raise RuntimeError(
            f'{LLM_GATEWAY_FEATURE_MODE_ENV_VAR}=gateway is blocked outside dev/local unless '
            f'{LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR}=true is set'
        )
    if not os.getenv(LLM_GATEWAY_URL_ENV_VAR, '').strip():
        raise RuntimeError(
            f'{LLM_GATEWAY_FEATURE_MODE_ENV_VAR}=gateway outside dev/local requires {LLM_GATEWAY_URL_ENV_VAR}'
        )
    return True


def raise_if_gateway_feature_mode_blocks_direct_model_surface(surface: str) -> None:
    if not should_route_features_through_gateway():
        return
    if os.getenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}:
        record_direct_exception_surface(surface=surface, reason='acknowledged')
        return
    raise RuntimeError(
        f'{surface} is a direct provider LLM surface and is blocked while '
        f'{LLM_GATEWAY_FEATURE_MODE_ENV_VAR}=gateway. Route it through the LLM gateway or set '
        f'{LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR}=true for an explicitly acknowledged exception.'
    )


def _is_local_or_dev_runtime() -> bool:
    explicit_stage = os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or os.getenv('APP_ENV')
    if explicit_stage:
        return explicit_stage.strip().lower() in {'dev', 'development', 'local', 'test'}
    if os.getenv('K_SERVICE') or os.getenv('KUBERNETES_SERVICE_HOST'):
        return False
    return True


def invoke_chat_structured_gateway(
    prompt: str,
    output_model: type[StructuredOutput],
    *,
    feature: str,
    timeout_seconds: float = CHAT_EXTRACTION_TIMEOUT_SECONDS,
) -> StructuredOutput | None:
    """Call the LLM gateway for chat structured extraction (pilot).

    This is a **synchronous** function intended to be called only from sync
    ``def`` call sites (e.g. ``requires_context``). When such a sync function
    is invoked by FastAPI it runs inside a threadpool, so the blocking HTTP
    call does not stall the event loop. Do **not** call this from ``async def``
    code without first offloading via ``run_blocking(llm_executor, ...)``.
    """
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f'{get_llm_gateway_base_url()}/v1/chat/completions',
                headers=_gateway_headers(),
                json=_chat_structured_payload(prompt, output_model, feature=feature),
            )
            response.raise_for_status()
            response_body = response.json()
        content = _extract_choice_content(response_body)
        if not isinstance(content, str) or not content.strip():
            record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='empty_content')
            return None
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='invalid_json')
            return None
        if not isinstance(decoded, Mapping):
            record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='invalid_json_shape')
            return None
        result = _validate_output_model(output_model, cast(Mapping[str, object], decoded))
        record_chat_extraction_gateway_result(feature=feature, outcome='success', reason='ok')
        return result
    except httpx.HTTPStatusError as exc:
        reason = f'http_{exc.response.status_code}'
        if is_gateway_transport_status_code(exc.response.status_code):
            record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason=reason)
            return None
        record_chat_extraction_gateway_result(feature=feature, outcome='error', reason=reason)
        raise
    except httpx.TimeoutException:
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='timeout')
        return None
    except httpx.RequestError:
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='request_error')
        return None
    except (ValidationError, JsonSchemaValidationError):
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='schema_validation')
        return None
    except Exception:
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='unexpected_error')
        return None


def record_chat_extraction_gateway_result(*, feature: str, outcome: str, reason: str, mode: str | None = None) -> None:
    record_gateway_request_result(feature=feature, outcome=outcome, reason=reason, mode=mode)


def _gateway_headers() -> dict[str, str]:
    headers = {
        'Content-Type': 'application/json',
        'X-Omi-Service-Caller': LLM_GATEWAY_CALLER,
    }
    service_token = get_llm_gateway_service_token()
    if service_token is not None:
        headers['Authorization'] = f'Bearer {service_token}'
    return headers


def llm_gateway_headers() -> dict[str, str]:
    return _gateway_headers()


def _chat_structured_payload(prompt: str, output_model: type[BaseModel], *, feature: str) -> JsonDict:
    return {
        'model': CHAT_STRUCTURED_AUTO_LANE_ID,
        'messages': [{'role': 'user', 'content': prompt}],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': output_model.__name__,
                'strict': True,
                'schema': _strict_model_json_schema(output_model),
            },
        },
        'metadata': {
            'omi_feature': feature,
            'prompt_version': f'{feature}.v1',
            'parser_version': f'{output_model.__name__}.v1',
        },
    }


def _strict_model_json_schema(output_model: type[BaseModel]) -> JsonDict:
    """Generate a strict-compatible JSON Schema for OpenAI Structured Outputs.

    OpenAI strict structured outputs require every object schema to disallow
    additional properties and mark every declared property as required. Pydantic
    emits defaults for optional/domain fields; strip those from provider schemas
    and represent optional values through their nullable type instead.
    """
    schema = output_model.model_json_schema()
    _normalize_strict_schema(schema)
    _inline_ref_siblings(schema)
    return schema


def _normalize_strict_schema(schema: JsonDict) -> None:
    """Recursively normalize a Pydantic JSON schema for strict provider output."""
    schema.pop('default', None)
    if schema.get('type') == 'object':
        schema['additionalProperties'] = False
    properties = _as_json_dict(schema.get('properties'))
    if properties is not None:
        schema['required'] = list(properties.keys())
        for prop_schema in properties.values():
            prop_schema_dict = _as_json_dict(prop_schema)
            if prop_schema_dict is not None:
                _normalize_strict_schema(prop_schema_dict)
    # Recurse into nested schemas under $defs, properties, items, etc.
    for key in ('$defs', 'definitions'):
        defs = _as_json_dict(schema.get(key))
        if defs is not None:
            for def_schema in defs.values():
                def_schema_dict = _as_json_dict(def_schema)
                if def_schema_dict is not None:
                    _normalize_strict_schema(def_schema_dict)
    items = _as_json_dict(schema.get('items'))
    if items is not None:
        _normalize_strict_schema(items)
    for ref_key in ('anyOf', 'oneOf', 'allOf'):
        alternatives = _as_json_list(schema.get(ref_key))
        if alternatives is not None:
            for alt_schema in alternatives:
                alt_schema_dict = _as_json_dict(alt_schema)
                if alt_schema_dict is not None:
                    _normalize_strict_schema(alt_schema_dict)


def _inline_ref_siblings(schema: JsonDict) -> None:
    """Inline local ``$ref`` schemas that carry sibling metadata.

    Pydantic emits enum fields as ``{"$ref": "#/$defs/Enum", "description": ...}``.
    That is valid JSON Schema, but OpenAI strict structured outputs reject some
    ``$ref`` nodes with sibling keywords. Pure local refs are left intact because
    nested object refs are accepted and keep large schemas compact.
    """

    definitions = _as_json_dict(schema.get('$defs')) or _as_json_dict(schema.get('definitions')) or {}

    def resolve_ref(ref: str) -> JsonDict | None:
        prefix = '#/$defs/'
        if not ref.startswith(prefix):
            return None
        target = _as_json_dict(definitions.get(ref.removeprefix(prefix)))
        return deepcopy(target) if target is not None else None

    def walk(node: object) -> None:
        node_dict = _as_json_dict(node)
        if node_dict is not None:
            ref = node_dict.get('$ref')
            if isinstance(ref, str) and len(node_dict) > 1:
                resolved = resolve_ref(ref)
                if resolved is not None:
                    siblings: JsonDict = {key: value for key, value in node_dict.items() if key != '$ref'}
                    node_dict.clear()
                    node_dict.update(resolved)
                    node_dict.update(siblings)
            for value in list(node_dict.values()):
                walk(value)
            return
        node_list = _as_json_list(node)
        if node_list is not None:
            for value in node_list:
                walk(value)

    walk(schema)


def _extract_choice_content(response_body: object) -> object:
    if not isinstance(response_body, Mapping):
        return None
    response_mapping = cast(Mapping[str, object], response_body)
    choices = _as_json_list(response_mapping.get('choices'))
    if choices is None or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return None
    choice_mapping = cast(Mapping[str, object], first_choice)
    message = choice_mapping.get('message')
    if not isinstance(message, Mapping):
        return None
    message_mapping = cast(Mapping[str, object], message)
    return message_mapping.get('content')


def _validate_output_model(
    output_model: type[StructuredOutput],
    decoded: Mapping[str, object],
) -> StructuredOutput:
    validate_json_schema(instance=decoded, schema=_strict_model_json_schema(output_model))
    return output_model.model_validate(decoded)


def generate_image_via_gateway(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    n: int,
    response_format: str,
    timeout_seconds: float = 120.0,
) -> Mapping[str, object]:
    """Call the gateway-owned image generation surface."""

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            f'{get_llm_gateway_base_url()}/v1/images/generations',
            headers=_gateway_headers(),
            json={
                'model': model,
                'prompt': prompt,
                'size': size,
                'quality': quality,
                'n': n,
                'response_format': response_format,
            },
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, Mapping):
        raise ValueError('gateway image response must be an object')
    return cast('Mapping[str, object]', body)
