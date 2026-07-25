from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from llm_gateway.gateway.errors import GatewayCapabilityMismatchError, GatewayInvalidRequestError
from llm_gateway.gateway.schemas import LaneConfig, StructuredOutputMode


@dataclass(frozen=True)
class ValidatedChatCompletionRequest:
    model: str
    messages: tuple[Mapping[str, Any], ...]
    response_format: Mapping[str, Any] | None
    forwarded_params: Mapping[str, Any]


CONTROL_PARAMS = frozenset({'model', 'messages', 'response_format', 'stream', 'tools', 'tool_choice'})
GATEWAY_LOCAL_PARAMS = frozenset({'metadata'})
FORWARDED_CHAT_COMPLETION_PARAMS = frozenset(
    {
        'frequency_penalty',
        'logit_bias',
        'logprobs',
        'max_completion_tokens',
        'max_tokens',
        'n',
        'presence_penalty',
        'prompt_cache_options',
        'prompt_cache_key',
        'seed',
        'stop',
        'stream_options',
        'temperature',
        'top_logprobs',
        'top_p',
        'user',
    }
)


def validate_chat_completion_request(
    request: Mapping[str, Any],
    lane: LaneConfig,
) -> ValidatedChatCompletionRequest:
    model = request.get('model')
    if not isinstance(model, str) or not model.strip():
        raise GatewayInvalidRequestError('model is required', param='model')

    if request.get('stream') is True and not lane.capabilities.streaming:
        raise GatewayCapabilityMismatchError('streaming is not supported for this lane', param='stream')
    if 'tools' in request and not lane.capabilities.tools:
        raise GatewayCapabilityMismatchError('tools are not supported for this lane', param='tools')
    if 'tool_choice' in request and request.get('tool_choice') not in (None, 'none') and not lane.capabilities.tools:
        raise GatewayCapabilityMismatchError('tool_choice is not supported for this lane', param='tool_choice')

    messages = _validate_messages(request.get('messages'))
    response_format = _validate_response_format(request.get('response_format'), lane)
    forwarded_params = _validate_forwarded_params(request)

    return ValidatedChatCompletionRequest(
        model=model.strip(),
        messages=tuple(messages),
        response_format=response_format,
        forwarded_params=forwarded_params,
    )


def _validate_messages(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise GatewayInvalidRequestError('messages must be a non-empty list', param='messages')

    validated: list[Mapping[str, Any]] = []
    messages = cast(list[object], value)
    for index, message in enumerate(messages):
        param = f'messages[{index}]'
        if not isinstance(message, Mapping):
            raise GatewayInvalidRequestError('each message must be an object', param=param)
        typed_message = cast(Mapping[str, Any], message)
        role = typed_message.get('role')
        if not isinstance(role, str) or not role:
            raise GatewayInvalidRequestError('message role is required', param=f'{param}.role')
        if 'content' not in typed_message:
            raise GatewayInvalidRequestError('message content is required', param=f'{param}.content')
        _validate_text_content(typed_message.get('content'), param=f'{param}.content')
        validated.append(typed_message)
    return validated


def _validate_text_content(content: object, *, param: str) -> None:
    if isinstance(content, str):
        return

    if (
        isinstance(content, list)
        and content
        and all(_is_text_content_part(part) for part in cast(list[object], content))
    ):
        return

    raise GatewayCapabilityMismatchError('only text message content is supported for this lane', param=param)


def _is_text_content_part(part: object) -> bool:
    if not isinstance(part, Mapping):
        return False
    typed_part = cast(Mapping[str, object], part)
    if typed_part.get('type') != 'text' or not isinstance(typed_part.get('text'), str):
        return False
    if 'prompt_cache_breakpoint' in typed_part:
        _validate_prompt_cache_breakpoint(typed_part['prompt_cache_breakpoint'])
    return True


def _validate_response_format(value: object, lane: LaneConfig) -> Mapping[str, Any] | None:
    if value is None:
        return None

    if not isinstance(value, Mapping):
        raise GatewayInvalidRequestError('response_format with json_schema is required', param='response_format')

    response_format = cast(Mapping[str, Any], value)
    response_format_type = response_format.get('type')
    if response_format_type != StructuredOutputMode.JSON_SCHEMA.value:
        raise GatewayCapabilityMismatchError(
            'only json_schema structured output is supported for this lane',
            param='response_format.type',
        )

    if lane.capabilities.structured_output != StructuredOutputMode.JSON_SCHEMA:
        raise GatewayCapabilityMismatchError(
            'lane does not support json_schema structured output', param='response_format'
        )

    json_schema = response_format.get('json_schema')
    if not isinstance(json_schema, Mapping):
        raise GatewayInvalidRequestError(
            'response_format.json_schema must be an object', param='response_format.json_schema'
        )
    typed_json_schema = cast(Mapping[str, Any], json_schema)
    name = typed_json_schema.get('name')
    if not isinstance(name, str) or not name.strip():
        raise GatewayInvalidRequestError(
            'response_format.json_schema.name is required', param='response_format.json_schema.name'
        )
    schema = typed_json_schema.get('schema')
    if not isinstance(schema, Mapping):
        raise GatewayInvalidRequestError(
            'response_format.json_schema.schema must be an object',
            param='response_format.json_schema.schema',
        )

    return response_format


def _validate_forwarded_params(request: Mapping[str, Any]) -> Mapping[str, Any]:
    unsupported = sorted(set(request.keys()) - CONTROL_PARAMS - GATEWAY_LOCAL_PARAMS - FORWARDED_CHAT_COMPLETION_PARAMS)
    if unsupported:
        raise GatewayInvalidRequestError(
            f'unsupported chat completion parameter: {unsupported[0]}',
            param=unsupported[0],
        )
    forwarded = {key: request[key] for key in FORWARDED_CHAT_COMPLETION_PARAMS if key in request}
    _validate_output_limit_aliases(forwarded)
    if 'prompt_cache_options' in forwarded:
        _validate_prompt_cache_options(forwarded['prompt_cache_options'])
    for key in ('tools', 'tool_choice', 'stream'):
        if key in request:
            forwarded[key] = request[key]
    return forwarded


def _validate_prompt_cache_options(value: object) -> None:
    if not isinstance(value, Mapping):
        raise GatewayInvalidRequestError('prompt_cache_options must be an object', param='prompt_cache_options')
    if set(value) != {'mode', 'ttl'} or value.get('mode') != 'explicit' or value.get('ttl') != '30m':
        raise GatewayInvalidRequestError(
            'prompt_cache_options must be {"mode": "explicit", "ttl": "30m"}',
            param='prompt_cache_options',
        )


def _validate_prompt_cache_breakpoint(value: object) -> None:
    if not isinstance(value, Mapping) or dict(value) != {'mode': 'explicit'}:
        raise GatewayInvalidRequestError(
            'prompt_cache_breakpoint must be {"mode": "explicit"}',
            param='prompt_cache_breakpoint',
        )


def _validate_output_limit_aliases(forwarded: Mapping[str, Any]) -> None:
    max_tokens = forwarded.get('max_tokens')
    max_completion_tokens = forwarded.get('max_completion_tokens')
    for key, value in (
        ('max_tokens', max_tokens),
        ('max_completion_tokens', max_completion_tokens),
    ):
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise GatewayInvalidRequestError(f'{key} must be a positive integer', param=key)
    if max_tokens is not None and max_completion_tokens is not None and max_tokens != max_completion_tokens:
        raise GatewayInvalidRequestError(
            'max_tokens and max_completion_tokens must match when both are provided',
            param='max_completion_tokens',
        )
