from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel

LLM_GATEWAY_CHAT_EXTRACTION_ENABLED_ENV_VAR = 'OMI_LLM_GATEWAY_CHAT_EXTRACTION_ENABLED'
LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'OMI_LLM_GATEWAY_SERVICE_TOKEN'
LEGACY_LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR = 'LLM_GATEWAY_SERVICE_TOKEN'
LLM_GATEWAY_URL_ENV_VAR = 'OMI_LLM_GATEWAY_URL'
DEFAULT_LLM_GATEWAY_URL = 'http://127.0.0.1:9080'
LLM_GATEWAY_AUTO_LANE_PREFIX = 'omi:auto:'
CHAT_STRUCTURED_AUTO_LANE_ID = 'omi:auto:chat-structured'
LLM_GATEWAY_CALLER = 'backend'
CHAT_EXTRACTION_TIMEOUT_SECONDS = 10.0

StructuredOutput = TypeVar('StructuredOutput', bound=BaseModel)


def get_llm_gateway_base_url() -> str:
    configured = os.getenv(LLM_GATEWAY_URL_ENV_VAR, '').strip()
    return configured.rstrip('/') if configured else DEFAULT_LLM_GATEWAY_URL


def get_llm_gateway_service_token() -> str | None:
    for env_var in (LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR, LEGACY_LLM_GATEWAY_SERVICE_TOKEN_ENV_VAR):
        configured = os.getenv(env_var)
        if configured is not None and configured.strip():
            return configured.strip()
    return None


def is_llm_gateway_chat_extraction_enabled() -> bool:
    configured = os.getenv(LLM_GATEWAY_CHAT_EXTRACTION_ENABLED_ENV_VAR, '')
    return configured.strip().lower() in {'1', 'true', 'yes', 'on'}


def is_auto_lane_id(model_or_lane: object) -> bool:
    return isinstance(model_or_lane, str) and model_or_lane.startswith(LLM_GATEWAY_AUTO_LANE_PREFIX)


def invoke_chat_structured_gateway(
    prompt: str,
    output_model: type[StructuredOutput],
    *,
    feature: str,
) -> StructuredOutput | None:
    try:
        response = httpx.post(
            f'{get_llm_gateway_base_url()}/v1/chat/completions',
            headers=_gateway_headers(),
            json=_chat_structured_payload(prompt, output_model, feature=feature),
            timeout=CHAT_EXTRACTION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = _extract_choice_content(response.json())
        if not isinstance(content, str) or not content.strip():
            return None
        decoded = json.loads(content)
        if not isinstance(decoded, Mapping):
            return None
        return _validate_output_model(output_model, decoded)
    except Exception:
        return None


def _gateway_headers() -> dict[str, str]:
    headers = {
        'Content-Type': 'application/json',
        'X-Omi-Service-Caller': LLM_GATEWAY_CALLER,
    }
    service_token = get_llm_gateway_service_token()
    if service_token is not None:
        headers['Authorization'] = f'Bearer {service_token}'
    return headers


def _chat_structured_payload(prompt: str, output_model: type[BaseModel], *, feature: str) -> dict:
    return {
        'model': CHAT_STRUCTURED_AUTO_LANE_ID,
        'messages': [{'role': 'user', 'content': prompt}],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': output_model.__name__,
                'strict': True,
                'schema': _model_json_schema(output_model),
            },
        },
        'metadata': {
            'omi_feature': feature,
            'prompt_version': f'{feature}.v1',
            'parser_version': f'{output_model.__name__}.v1',
        },
    }


def _model_json_schema(output_model: type[BaseModel]) -> dict:
    if hasattr(output_model, 'model_json_schema'):
        return output_model.model_json_schema()
    return output_model.schema()


def _extract_choice_content(response_body: object) -> object:
    if not isinstance(response_body, Mapping):
        return None
    choices = response_body.get('choices')
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return None
    message = first_choice.get('message')
    if not isinstance(message, Mapping):
        return None
    return message.get('content')


def _validate_output_model(
    output_model: type[StructuredOutput],
    decoded: Mapping[str, object],
) -> StructuredOutput:
    if hasattr(output_model, 'model_validate'):
        return output_model.model_validate(decoded)
    return output_model.parse_obj(decoded)
