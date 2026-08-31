from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from copy import deepcopy
from openai import AsyncOpenAI, OpenAI
from typing import Any, TypeVar, cast

import httpx
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, PrivateAttr, ValidationError

from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_observability import record_direct_exception_surface, record_gateway_request_result
from utils.llm.gateway_resilience import gateway_circuit, gateway_transport_timeout, observe_gateway_first_byte
from utils.llm.usage_tracker import get_current_context

LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'OMI_LLM_GATEWAY_SERVICE_TOKEN'
LEGACY_LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'LLM_GATEWAY_SERVICE_TOKEN'
LLM_GATEWAY_URL_ENV_VAR = 'OMI_LLM_GATEWAY_URL'
DEFAULT_LLM_GATEWAY_URL = 'http://127.0.0.1:9080'
LLM_GATEWAY_AUTO_LANE_PREFIX = 'omi:auto:'
CHAT_STRUCTURED_AUTO_LANE_ID = 'omi:auto:chat-structured'
CHAT_AGENT_AUTO_LANE_ID = 'omi:auto:chat-agent'
PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE = 'public_shared_conversation_chat'
PUBLIC_SHARED_CONVERSATION_CHAT_AUTO_LANE_ID = 'omi:auto:public-shared-conversation-chat'
LLM_GATEWAY_FEATURE_MODE_ENV_VAR = 'OMI_LLM_GATEWAY_FEATURE_MODE'
LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR = 'OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE'
LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR = 'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION'
# Narrow agentic-chat route pin. Independent of FEATURE_MODE so gateway can stay
# on for non-chat features while chat stays on direct Anthropic (or the reverse).
LLM_CHAT_AGENT_ROUTE_ENV_VAR = 'OMI_LLM_CHAT_AGENT_ROUTE'
CHAT_AGENT_ROUTE_DIRECT = 'direct'
CHAT_AGENT_ROUTE_GATEWAY = 'gateway'
_CHAT_AGENT_ROUTE_DIRECT_VALUES = frozenset({'direct', 'off', '0', 'false', 'no'})
_CHAT_AGENT_ROUTE_GATEWAY_VALUES = frozenset({'gateway', '1', 'true', 'yes', 'luna', 'on'})
LLM_GATEWAY_CALLER = 'backend'
LLM_GATEWAY_USER_UID_HEADER = 'X-Omi-User-Uid'
LLM_GATEWAY_USAGE_FEATURE_HEADER = 'X-Omi-LLM-Feature'
LLM_GATEWAY_APP_PLATFORM_HEADER = 'X-Omi-App-Platform'
# Closed enum, mirroring the gateway's own normalization. Client-supplied platform
# strings are never forwarded verbatim: unknown values are dropped so accounting
# stays aggregatable and arbitrary client text never reaches an outbound header.
LLM_GATEWAY_APP_PLATFORMS = frozenset({'desktop', 'mobile', 'web'})
CHAT_EXTRACTION_TIMEOUT_SECONDS = 10.0
BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS = 35.0
GATEWAY_TRANSPORT_STATUS_CODES = frozenset({502, 504})

StructuredOutput = TypeVar('StructuredOutput', bound=BaseModel)
JsonDict = dict[str, Any]
JsonList = list[Any]
_BYOK_GATEWAY_HEADER_PREFIX = 'X-Omi-Byok-'
_BYOK_GATEWAY_HEADER_SUFFIX = '-Key'


def byok_gateway_header_name(provider: str) -> str:
    """Envelope header that forwards a user's BYOK key to the gateway."""
    return f'{_BYOK_GATEWAY_HEADER_PREFIX}{provider.strip().lower()}{_BYOK_GATEWAY_HEADER_SUFFIX}'


class PublicSharedConversationChatGatewayUnavailable(Exception):
    """The gateway-only public shared-chat lane could not produce an answer."""

    pass


class GatewayDirectModelSurfaceBlocked(RuntimeError):
    """A direct-provider LLM surface ran while feature mode requires the gateway.

    Callers should treat this as a typed, user-safe failure for that surface — not as an
    unexpected crash that falls through to the generic chat canned reply.
    """

    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.error_code = f'{surface.split(".", 1)[0]}_gateway_blocked'
        super().__init__(
            f'{surface} is a direct provider LLM surface and is blocked while '
            f'{LLM_GATEWAY_FEATURE_MODE_ENV_VAR}=gateway. Route it through the LLM gateway or set '
            f'{LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR}=true for an explicitly acknowledged exception.'
        )


class GatewayContextChatOpenAI(ChatOpenAI):
    """A shared client that adds user attribution at invocation time."""

    _omi_gateway_feature: str | None = PrivateAttr(default=None)

    def __init__(self, *args: Any, omi_gateway_feature: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._omi_gateway_feature = omi_gateway_feature

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        raw_headers = payload.get('extra_headers')
        headers = dict(raw_headers) if isinstance(raw_headers, Mapping) else {}
        headers.update(_gateway_usage_headers(feature=self._omi_gateway_feature))
        if headers:
            payload['extra_headers'] = headers

        raw_metadata = payload.get('metadata')
        metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
        feature = _gateway_feature_for_current_request(self._omi_gateway_feature)
        if feature:
            metadata.setdefault('omi_feature', feature)
        if metadata:
            payload['metadata'] = metadata
        return payload


def is_gateway_transport_status_code(status_code: object) -> bool:
    return isinstance(status_code, int) and status_code in GATEWAY_TRANSPORT_STATUS_CODES


def is_gateway_route_absent(error: object) -> bool:
    """Whether a gateway failure means the deployed gateway has no such route.

    A gateway older than its caller answers an unknown path with Starlette's
    bare ``{"detail": "Not Found"}``. A gateway that owns the route answers a
    real rejection with an OpenAI-shaped ``{"error": {...}}`` body -- and
    ``model_not_found`` is also a 404. So the *body*, not the status, is what
    separates "server predates client" from "server rejected this request";
    treating every 404 as route-absence would silently swallow lane
    misconfiguration.
    """
    if not isinstance(error, httpx.HTTPStatusError):
        return False
    if error.response.status_code != 404:
        return False
    try:
        body: object = error.response.json()
    except Exception:
        # A non-JSON 404 is not something this gateway's error path can emit.
        return True
    return not (isinstance(body, Mapping) and isinstance(body.get('error'), Mapping))


def is_gateway_model_not_found(error: object) -> bool:
    """Whether an OpenAI-compatible gateway rejected an unknown lane id.

    The OpenAI SDK exposes the gateway's ``error.code`` as ``error.code``;
    direct-provider file 404s have the same HTTP status but no
    ``model_not_found`` code. Keep that distinction closed so deploy skew can
    degrade without misclassifying a genuinely deleted attachment.
    """
    if getattr(error, 'status_code', None) != 404:
        return False
    if getattr(error, 'code', None) == 'model_not_found':
        return True
    body = getattr(error, 'body', None)
    if not isinstance(body, Mapping):
        return False
    if body.get('code') == 'model_not_found':
        return True
    nested_error = body.get('error')
    return isinstance(nested_error, Mapping) and nested_error.get('code') == 'model_not_found'


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


def get_chat_agent_route() -> str:
    """Return the effective agentic-chat route: ``direct`` or ``gateway``.

    Explicit ``OMI_LLM_CHAT_AGENT_ROUTE`` wins. When unset, inherit the global
    feature-mode switch so existing deployments keep prior behavior.
    """
    raw = os.getenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, '').strip().lower()
    if raw in _CHAT_AGENT_ROUTE_DIRECT_VALUES:
        return CHAT_AGENT_ROUTE_DIRECT
    if raw in _CHAT_AGENT_ROUTE_GATEWAY_VALUES:
        return CHAT_AGENT_ROUTE_GATEWAY
    if raw:
        raise RuntimeError(
            f'{LLM_CHAT_AGENT_ROUTE_ENV_VAR}={raw!r} is invalid; '
            f'expected one of {sorted(_CHAT_AGENT_ROUTE_DIRECT_VALUES | _CHAT_AGENT_ROUTE_GATEWAY_VALUES)}'
        )
    return CHAT_AGENT_ROUTE_GATEWAY if should_route_features_through_gateway() else CHAT_AGENT_ROUTE_DIRECT


def should_route_chat_agent_through_gateway() -> bool:
    """Whether managed agentic chat should use the gateway OpenAI-compatible lane.

    Requires both the chat-agent route pin and global feature mode. This keeps
    ``OMI_LLM_CHAT_AGENT_ROUTE=direct`` safe while ``FEATURE_MODE=gateway`` for
    other features (the 2026-08 chat outage footgun class).
    """
    if get_chat_agent_route() != CHAT_AGENT_ROUTE_GATEWAY:
        return False
    return should_route_features_through_gateway()


def raise_if_gateway_feature_mode_blocks_direct_model_surface(surface: str) -> None:
    if not should_route_features_through_gateway():
        return
    if os.getenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}:
        record_direct_exception_surface(surface=surface, reason='acknowledged')
        return
    raise GatewayDirectModelSurfaceBlocked(surface)


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
    if not gateway_circuit.allow_request():
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='circuit_open')
        return None

    gateway_started_at = time.monotonic()
    try:
        with httpx.Client(timeout=_gateway_timeout(timeout_seconds)) as client:
            response = client.post(
                f'{get_llm_gateway_base_url()}/v1/chat/completions',
                headers=_gateway_headers(feature=feature),
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
        gateway_circuit.record_transport_success()
        observe_gateway_first_byte(feature=feature, started_at=gateway_started_at, outcome='success')
        record_chat_extraction_gateway_result(feature=feature, outcome='success', reason='ok')
        return result
    except httpx.HTTPStatusError as exc:
        reason = f'http_{exc.response.status_code}'
        if is_gateway_transport_status_code(exc.response.status_code):
            gateway_circuit.record_transport_failure()
            observe_gateway_first_byte(feature=feature, started_at=gateway_started_at, outcome='transport_failure')
            record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason=reason)
            return None
        record_chat_extraction_gateway_result(feature=feature, outcome='error', reason=reason)
        raise
    except httpx.TimeoutException:
        gateway_circuit.record_transport_failure()
        observe_gateway_first_byte(feature=feature, started_at=gateway_started_at, outcome='transport_failure')
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='timeout')
        return None
    except httpx.RequestError:
        gateway_circuit.record_transport_failure()
        observe_gateway_first_byte(feature=feature, started_at=gateway_started_at, outcome='transport_failure')
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='request_error')
        return None
    except (ValidationError, JsonSchemaValidationError):
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='schema_validation')
        return None
    except Exception:
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='unexpected_error')
        return None


async def invoke_public_shared_conversation_chat_gateway(messages: list[dict[str, str]]) -> str:
    """Invoke the dedicated non-streaming public shared-conversation lane.

    This surface is deliberately gateway-only. Every transport, status, or
    response-shape fault becomes a typed unavailable result for the public API;
    it never constructs or invokes a direct provider client.
    """

    started_at = time.monotonic()
    if not gateway_circuit.allow_request():
        record_gateway_request_result(
            feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
            outcome='error',
            reason='circuit_open',
            mode='gateway',
        )
        raise PublicSharedConversationChatGatewayUnavailable()

    try:
        async with get_llm_gateway_semaphore():
            response = await get_llm_gateway_client().post(
                f'{get_llm_gateway_base_url()}/v1/chat/completions',
                headers=_gateway_headers(feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE),
                json={
                    'model': PUBLIC_SHARED_CONVERSATION_CHAT_AUTO_LANE_ID,
                    'messages': messages,
                    'stream': False,
                    'max_completion_tokens': 600,
                    'metadata': {
                        'omi_feature': PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
                        'prompt_version': 'public_shared_conversation_chat.v1',
                        'parser_version': 'plain_text.v1',
                    },
                },
            )
        response.raise_for_status()
        content = _extract_choice_content(response.json())
        if not isinstance(content, str) or not content.strip():
            raise ValueError('gateway returned empty public shared-chat content')
    except PublicSharedConversationChatGatewayUnavailable:
        raise
    except Exception as exc:
        if isinstance(exc, (httpx.RequestError, httpx.TimeoutException)) or (
            isinstance(exc, httpx.HTTPStatusError) and is_gateway_transport_status_code(exc.response.status_code)
        ):
            gateway_circuit.record_transport_failure()
            observe_gateway_first_byte(
                feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
                started_at=started_at,
                outcome='transport_failure',
            )
        record_gateway_request_result(
            feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
            outcome='error',
            reason='gateway_unavailable',
            mode='gateway',
        )
        raise PublicSharedConversationChatGatewayUnavailable() from exc

    gateway_circuit.record_transport_success()
    observe_gateway_first_byte(
        feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
        started_at=started_at,
        outcome='success',
    )
    record_gateway_request_result(
        feature=PUBLIC_SHARED_CONVERSATION_CHAT_FEATURE,
        outcome='success',
        reason='ok',
        mode='gateway',
    )
    return content.strip()


def record_chat_extraction_gateway_result(*, feature: str, outcome: str, reason: str, mode: str | None = None) -> None:
    record_gateway_request_result(feature=feature, outcome=outcome, reason=reason, mode=mode)


def _gateway_headers(*, feature: str | None = None, platform: str | None = None) -> dict[str, str]:
    headers = {
        'Content-Type': 'application/json',
        'X-Omi-Service-Caller': LLM_GATEWAY_CALLER,
    }
    service_token = get_llm_gateway_service_token()
    if service_token is not None:
        headers['Authorization'] = f'Bearer {service_token}'
    headers.update(_gateway_usage_headers(feature=feature, platform=platform))
    return headers


def llm_gateway_headers(*, feature: str | None = None, platform: str | None = None) -> dict[str, str]:
    """Gateway headers for one request.

    ``platform`` is the client app platform when the caller knows it. It is
    normalized to ``LLM_GATEWAY_APP_PLATFORMS``; an absent or unrecognized value
    sends no header at all, so the attempt stays unattributed rather than guessed.
    """
    return _gateway_headers(feature=feature, platform=platform)


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


def _gateway_timeout(timeout_seconds: float) -> httpx.Timeout:
    """Keep feature-specific total budgets while bounding the gateway connect/read hop."""

    shared = gateway_transport_timeout()
    bounded = min(timeout_seconds, shared.read or timeout_seconds)
    return httpx.Timeout(
        connect=shared.connect,
        read=bounded,
        write=bounded,
        pool=shared.pool,
    )


def generate_image_via_gateway(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    n: int,
    timeout_seconds: float = 120.0,
) -> Mapping[str, object]:
    """Call the gateway-owned image generation surface."""

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            f'{get_llm_gateway_base_url()}/v1/images/generations',
            headers=_gateway_headers(feature='app_generator'),
            json={
                'model': model,
                'prompt': prompt,
                'size': size,
                'quality': quality,
                'n': n,
            },
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, Mapping):
        raise ValueError('gateway image response must be an object')
    return cast('Mapping[str, object]', body)


FILE_CHAT_VISION_FEATURE = 'file_chat_vision'
FILE_CHAT_DOCUMENTS_FEATURE = 'file_chat_documents'
FILE_CHAT_VISION_AUTO_LANE_ID = feature_auto_lane_id(FILE_CHAT_VISION_FEATURE)
FILE_CHAT_DOCUMENTS_AUTO_LANE_ID = feature_auto_lane_id(FILE_CHAT_DOCUMENTS_FEATURE)
OPENAI_EMBEDDINGS_AUTO_LANE_ID = 'omi:auto:openai-embeddings'
GEMINI_EMBEDDINGS_AUTO_LANE_ID = 'omi:auto:gemini-embeddings'
EMBEDDINGS_TIMEOUT_SECONDS = 30.0
_FILE_CHAT_GATEWAY_TIMEOUT_SECONDS = 120.0

_file_chat_gateway_async_client: AsyncOpenAI | None = None
_file_chat_gateway_sync_client: OpenAI | None = None


def file_chat_auto_lane_id(*, pdf: bool) -> str:
    """The gateway file-chat lane for a request: PDFs take the file-part lane."""
    return FILE_CHAT_DOCUMENTS_AUTO_LANE_ID if pdf else FILE_CHAT_VISION_AUTO_LANE_ID


def _file_chat_gateway_default_headers() -> dict[str, str]:
    headers = {'X-Omi-Service-Caller': LLM_GATEWAY_CALLER}
    service_token = get_llm_gateway_service_token()
    if service_token:
        headers['Authorization'] = f'Bearer {service_token}'
    return headers


def get_file_chat_gateway_async_client() -> AsyncOpenAI:
    """Async OpenAI SDK client pointed at the gateway's chat-completions surface.

    The gateway is OpenAI-compatible, so file chat keeps its SDK streaming and
    typed-error handling (``openai.NotFoundError`` / ``BadRequestError`` map to
    the gateway's OpenAI-shaped error bodies) while the model call lands in the
    gateway ledger.
    """
    global _file_chat_gateway_async_client
    if _file_chat_gateway_async_client is None:
        _file_chat_gateway_async_client = AsyncOpenAI(
            api_key=get_llm_gateway_service_token() or 'omi-gateway',
            base_url=f'{get_llm_gateway_base_url()}/v1',
            default_headers=_file_chat_gateway_default_headers(),
            timeout=_gateway_timeout(_FILE_CHAT_GATEWAY_TIMEOUT_SECONDS),
            max_retries=0,
        )
    return _file_chat_gateway_async_client


def get_file_chat_gateway_sync_client() -> OpenAI:
    """Sync counterpart of :func:`get_file_chat_gateway_async_client`."""
    global _file_chat_gateway_sync_client
    if _file_chat_gateway_sync_client is None:
        _file_chat_gateway_sync_client = OpenAI(
            api_key=get_llm_gateway_service_token() or 'omi-gateway',
            base_url=f'{get_llm_gateway_base_url()}/v1',
            default_headers=_file_chat_gateway_default_headers(),
            timeout=_gateway_timeout(_FILE_CHAT_GATEWAY_TIMEOUT_SECONDS),
            max_retries=0,
        )
    return _file_chat_gateway_sync_client


def file_chat_feature_header(lane_id: str, *, uid: str | None = None) -> dict[str, str]:
    """Per-request file-chat headers: feature plus the user the spend belongs to.

    The cached SDK client only carries service auth. Attribution has to go on
    the request or the gateway ledger row is unattributed.
    """
    feature = FILE_CHAT_DOCUMENTS_FEATURE if lane_id == FILE_CHAT_DOCUMENTS_AUTO_LANE_ID else FILE_CHAT_VISION_FEATURE
    headers = _gateway_usage_headers(feature=feature)
    if uid:
        headers[LLM_GATEWAY_USER_UID_HEADER] = uid
    return headers


def _embedding_vectors(body: object) -> list[list[float]]:
    if not isinstance(body, Mapping):
        raise ValueError('gateway embeddings response must be an object')
    data = body.get('data')
    if not isinstance(data, list) or not data:
        raise ValueError('gateway embeddings response has no data')
    vectors: list[list[float]] = []
    for item in data:
        embedding = item.get('embedding') if isinstance(item, Mapping) else None
        if not isinstance(embedding, list) or not embedding:
            raise ValueError('gateway embeddings response has an empty vector')
        vectors.append([float(value) for value in embedding])
    return vectors


def invoke_openai_embeddings_gateway(
    texts: list[str],
    *,
    timeout_seconds: float = EMBEDDINGS_TIMEOUT_SECONDS,
    byok_api_key: str | None = None,
) -> list[list[float]]:
    """Sync OpenAI text-embedding-3-large hop through the gateway embeddings lane."""
    headers = _gateway_headers(feature='openai_embeddings')
    if byok_api_key:
        headers[byok_gateway_header_name('openai')] = byok_api_key
    with httpx.Client(timeout=_gateway_timeout(timeout_seconds)) as client:
        response = client.post(
            f'{get_llm_gateway_base_url()}/v1/embeddings',
            headers=headers,
            json={'model': OPENAI_EMBEDDINGS_AUTO_LANE_ID, 'input': texts},
        )
        response.raise_for_status()
        body: object = response.json()
    return _embedding_vectors(body)


async def ainvoke_openai_embeddings_gateway(
    texts: list[str],
    *,
    timeout_seconds: float = EMBEDDINGS_TIMEOUT_SECONDS,
    byok_api_key: str | None = None,
) -> list[list[float]]:
    """Async counterpart of :func:`invoke_openai_embeddings_gateway`."""
    from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore

    headers = _gateway_headers(feature='openai_embeddings')
    if byok_api_key:
        headers[byok_gateway_header_name('openai')] = byok_api_key
    async with get_llm_gateway_semaphore():
        client = get_llm_gateway_client()
        response = await client.post(
            f'{get_llm_gateway_base_url()}/v1/embeddings',
            headers=headers,
            json={'model': OPENAI_EMBEDDINGS_AUTO_LANE_ID, 'input': texts},
            timeout=_gateway_timeout(timeout_seconds),
        )
        response.raise_for_status()
        body: object = response.json()
    return _embedding_vectors(body)


def invoke_gemini_embedding_gateway(
    text: str,
    *,
    task_type: str,
    title: str | None = None,
    timeout_seconds: float = EMBEDDINGS_TIMEOUT_SECONDS,
) -> list[float]:
    """Sync Gemini embedding hop through the gateway (Vertex stays an upstream adapter)."""
    payload: dict[str, object] = {
        'model': GEMINI_EMBEDDINGS_AUTO_LANE_ID,
        'input': [text],
        'task_type': task_type,
    }
    if title:
        payload['title'] = title
    with httpx.Client(timeout=_gateway_timeout(timeout_seconds)) as client:
        response = client.post(
            f'{get_llm_gateway_base_url()}/v1/embeddings',
            headers=_gateway_headers(feature='gemini_screen_activity_query_embedding'),
            json=payload,
        )
        response.raise_for_status()
        body: object = response.json()
    vectors = _embedding_vectors(body)
    return vectors[0]


def _gateway_usage_headers(*, feature: str | None, platform: str | None = None) -> dict[str, str]:
    context = get_current_context()
    headers: dict[str, str] = {}
    if context is not None and context.uid:
        headers[LLM_GATEWAY_USER_UID_HEADER] = context.uid
    resolved_feature = context.feature if context is not None and context.feature else feature
    if resolved_feature:
        headers[LLM_GATEWAY_USAGE_FEATURE_HEADER] = resolved_feature
    normalized_platform = platform.strip().lower() if isinstance(platform, str) else None
    if normalized_platform in LLM_GATEWAY_APP_PLATFORMS:
        headers[LLM_GATEWAY_APP_PLATFORM_HEADER] = normalized_platform
    return headers


def _gateway_feature_for_current_request(default: str | None) -> str | None:
    context = get_current_context()
    if context is not None and context.feature:
        return context.feature
    return default
