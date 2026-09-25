from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.schemas import LaneConfig, StructuredOutputMode


@dataclass(frozen=True)
class ValidatedChatCompletionRequest:
    model: str
    messages: tuple[Mapping[str, Any], ...]
    response_format: Mapping[str, Any] | None
    forwarded_params: Mapping[str, Any]


@dataclass(frozen=True)
class ValidatedEmbeddingRequest:
    model: str
    inputs: tuple[str, ...]
    task_type: str | None = None
    title: str | None = None


MAX_EMBEDDING_INPUTS = 2048


@dataclass(frozen=True)
class ValidatedSystemOneRequest:
    """A decision-model request: one shared state, typed questions, no text generation."""

    model: str
    state: str
    questions: Mapping[str, Mapping[str, Any]]


# The upstream route's context window is 32k tokens. Callers truncate first;
# this bound only keeps an oversized body from reaching the provider at all.
MAX_SYSTEMONE_STATE_CHARS = 96_000
MAX_SYSTEMONE_QUESTIONS = 16
SYSTEMONE_QUESTION_TYPES = frozenset({'noul', 'choice', 'score'})
_SYSTEMONE_QUESTION_KEYS = frozenset({'type', 'instructions', 'criteria'})
_MAX_SYSTEMONE_CHOICES = 255
_MIN_SYSTEMONE_SCORE_RUNGS = 2
_MAX_SYSTEMONE_SCORE_RUNGS = 10
CONTROL_PARAMS = frozenset({'model', 'messages', 'response_format', 'stream', 'tools', 'tool_choice'})
GATEWAY_LOCAL_PARAMS = frozenset({'metadata'})
FORWARDED_CHAT_COMPLETION_PARAMS = frozenset(
    {
        'frequency_penalty',
        'google',
        'logit_bias',
        'logprobs',
        'max_completion_tokens',
        'max_tokens',
        'n',
        'presence_penalty',
        'prompt_cache_options',
        'prompt_cache_key',
        'reasoning_effort',
        'seed',
        'service_tier',
        'stop',
        'stream_options',
        'temperature',
        'top_logprobs',
        'top_p',
        'user',
    }
)

# Per-request reasoning effort the gateway forwards verbatim. Values follow the
# OpenAI Chat Completions `reasoning_effort` enum; per-model support (e.g.
# gpt-5.6 function tools require `none`) stays with the provider/lane policy.
REASONING_EFFORT_VALUES = frozenset({'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'})

# The OpenAI SDK's `extra_body` convention flattens provider-specific options
# into top-level JSON fields, so the `google` key is the pass-through carrier
# for per-request Gemini options (e.g. thinking budget) on the OpenAI-shaped
# surface; providers that do not understand it ignore it.


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
    forwarded_params = _validate_forwarded_params(request, lane)

    return ValidatedChatCompletionRequest(
        model=model.strip(),
        messages=tuple(messages),
        response_format=response_format,
        forwarded_params=forwarded_params,
    )


def validate_embedding_request(request: Mapping[str, Any], lane: LaneConfig) -> ValidatedEmbeddingRequest:
    """Validate an OpenAI-shaped embeddings request for an embeddings lane."""
    model = request.get('model')
    if not isinstance(model, str) or not model.strip():
        raise GatewayInvalidRequestError('model is required', param='model')

    raw_input = request.get('input')
    inputs: list[str] = []
    if isinstance(raw_input, str):
        inputs = [raw_input]
    elif isinstance(raw_input, list):
        for index, item in enumerate(raw_input):
            if not isinstance(item, str) or not item:
                raise GatewayInvalidRequestError('input items must be non-empty strings', param=f'input[{index}]')
            inputs.append(item)
    else:
        raise GatewayInvalidRequestError('input must be a string or a list of strings', param='input')
    if not inputs or len(inputs) > MAX_EMBEDDING_INPUTS:
        raise GatewayInvalidRequestError(
            f'input must contain between 1 and {MAX_EMBEDDING_INPUTS} items', param='input'
        )

    unsupported = sorted(set(request.keys()) - {'model', 'input', 'task_type', 'title', 'metadata'})
    if unsupported:
        raise GatewayInvalidRequestError(f'unsupported embeddings parameter: {unsupported[0]}', param=unsupported[0])
    task_type = request.get('task_type')
    if task_type is not None and (not isinstance(task_type, str) or not task_type.strip()):
        raise GatewayInvalidRequestError('task_type must be a non-empty string', param='task_type')
    title = request.get('title')
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise GatewayInvalidRequestError('title must be a non-empty string', param='title')
    normalized_task_type = task_type.strip() if isinstance(task_type, str) else None
    normalized_title = title.strip() if isinstance(title, str) else None

    return ValidatedEmbeddingRequest(
        model=model.strip(),
        inputs=tuple(inputs),
        task_type=normalized_task_type,
        title=normalized_title,
    )


def validate_systemone_request(request: Mapping[str, Any]) -> ValidatedSystemOneRequest:
    """Validate a decision-model request before it reaches the provider."""
    model = request.get('model')
    if not isinstance(model, str) or not model.strip():
        raise GatewayInvalidRequestError('model is required', param='model')
    unsupported = sorted(set(request.keys()) - {'model', 'state', 'questions', 'metadata'})
    if unsupported:
        raise GatewayInvalidRequestError(f'unsupported systemone parameter: {unsupported[0]}', param=unsupported[0])
    state = request.get('state')
    if not isinstance(state, str) or not state.strip():
        raise GatewayInvalidRequestError('state must be a non-empty string', param='state')
    if len(state) > MAX_SYSTEMONE_STATE_CHARS:
        raise GatewayInvalidRequestError(f'state must be at most {MAX_SYSTEMONE_STATE_CHARS} characters', param='state')
    raw_questions = request.get('questions')
    if not isinstance(raw_questions, Mapping) or not raw_questions:
        raise GatewayInvalidRequestError('questions must be a non-empty object', param='questions')
    questions_map = cast(Mapping[object, object], raw_questions)
    if len(questions_map) > MAX_SYSTEMONE_QUESTIONS:
        raise GatewayInvalidRequestError(
            f'questions must contain at most {MAX_SYSTEMONE_QUESTIONS} entries', param='questions'
        )
    questions: dict[str, Mapping[str, Any]] = {}
    for name, question in questions_map.items():
        param = f'questions.{name}'
        if not isinstance(name, str) or not name.strip():
            raise GatewayInvalidRequestError('question names must be non-empty strings', param='questions')
        if not isinstance(question, Mapping):
            raise GatewayInvalidRequestError('each question must be an object', param=param)
        questions[name] = _validate_systemone_question(cast(Mapping[str, Any], question), param=param)
    return ValidatedSystemOneRequest(model=model.strip(), state=state, questions=questions)


def _validate_systemone_question(question: Mapping[str, Any], *, param: str) -> Mapping[str, Any]:
    unsupported = sorted(set(question.keys()) - _SYSTEMONE_QUESTION_KEYS)
    if unsupported:
        raise GatewayInvalidRequestError(f'unsupported question field: {unsupported[0]}', param=param)
    question_type = question.get('type')
    if question_type not in SYSTEMONE_QUESTION_TYPES:
        raise GatewayInvalidRequestError('question type must be noul, choice, or score', param=f'{param}.type')
    instructions = question.get('instructions')
    if not isinstance(instructions, str) or not instructions.strip():
        raise GatewayInvalidRequestError('question instructions are required', param=f'{param}.instructions')
    criteria = question.get('criteria')
    if question_type == 'noul':
        if criteria is not None and not _is_string_map(criteria, allowed_keys=frozenset({'true', 'false'})):
            raise GatewayInvalidRequestError('noul criteria must map true/false to strings', param=f'{param}.criteria')
    elif question_type == 'choice':
        if not _is_string_map(criteria) or not 2 <= len(cast(Mapping[str, str], criteria)) <= _MAX_SYSTEMONE_CHOICES:
            raise GatewayInvalidRequestError(
                f'choice criteria must map 2-{_MAX_SYSTEMONE_CHOICES} options to strings', param=f'{param}.criteria'
            )
    else:
        rungs = cast(list[object], criteria) if isinstance(criteria, list) else None
        if (
            rungs is None
            or not _MIN_SYSTEMONE_SCORE_RUNGS <= len(rungs) <= _MAX_SYSTEMONE_SCORE_RUNGS
            or not all(isinstance(rung, str) and rung.strip() for rung in rungs)
        ):
            raise GatewayInvalidRequestError(
                f'score criteria must list {_MIN_SYSTEMONE_SCORE_RUNGS}-{_MAX_SYSTEMONE_SCORE_RUNGS} rungs',
                param=f'{param}.criteria',
            )
    return dict(question)


def _is_string_map(value: object, *, allowed_keys: frozenset[str] | None = None) -> bool:
    if not isinstance(value, Mapping):
        return False
    items = cast(Mapping[object, object], value)
    if allowed_keys is not None and not set(items.keys()) <= allowed_keys:
        return False
    return all(
        isinstance(key, str) and key.strip() and isinstance(text, str) and text.strip() for key, text in items.items()
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
        content = typed_message.get('content')
        if 'content' not in typed_message or content is None:
            if role == 'assistant':
                typed_message = {**dict(typed_message), 'content': ''}
            else:
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
        and all(_is_supported_content_part(part) for part in cast(list[object], content))
    ):
        return

    raise GatewayCapabilityMismatchError(
        'only text, image_url, or file message content is supported for this lane', param=param
    )


def _is_supported_content_part(part: object) -> bool:
    return _is_text_content_part(part) or _is_image_url_content_part(part) or _is_file_content_part(part)


def _is_file_content_part(part: object) -> bool:
    if not isinstance(part, Mapping):
        return False
    typed_part = cast(Mapping[str, object], part)
    if typed_part.get('type') != 'file':
        return False
    file_ref = typed_part.get('file')
    return isinstance(file_ref, Mapping) and isinstance(cast(Mapping[str, object], file_ref).get('file_id'), str)


def _is_text_content_part(part: object) -> bool:
    if not isinstance(part, Mapping):
        return False
    typed_part = cast(Mapping[str, object], part)
    if typed_part.get('type') != 'text' or not isinstance(typed_part.get('text'), str):
        return False
    if 'prompt_cache_breakpoint' in typed_part:
        _validate_prompt_cache_breakpoint(typed_part['prompt_cache_breakpoint'])
    return True


def _is_image_url_content_part(part: object) -> bool:
    if not isinstance(part, Mapping):
        return False
    typed_part = cast(Mapping[str, object], part)
    if typed_part.get('type') != 'image_url':
        return False
    image_url = typed_part.get('image_url')
    return isinstance(image_url, Mapping) and isinstance(cast(Mapping[str, object], image_url).get('url'), str)


def _validate_response_format(value: object, lane: LaneConfig) -> Mapping[str, Any] | None:
    if value is None:
        return None

    if not isinstance(value, Mapping):
        raise GatewayInvalidRequestError('response_format with json_schema is required', param='response_format')

    response_format = cast(Mapping[str, Any], value)
    response_format_type = response_format.get('type')
    if response_format_type == StructuredOutputMode.JSON_OBJECT.value:
        # Gemini's responseMimeType=application/json without a schema maps to
        # json_object; it carries no schema so nothing further to validate.
        if lane.capabilities.structured_output == StructuredOutputMode.NONE:
            raise GatewayCapabilityMismatchError(
                'lane does not support structured output',
                param='response_format',
            )
        return response_format
    if response_format_type != StructuredOutputMode.JSON_SCHEMA.value:
        raise GatewayCapabilityMismatchError(
            'only json_schema structured output is supported for this lane',
            param='response_format.type',
        )

    if lane.capabilities.structured_output != StructuredOutputMode.JSON_SCHEMA:
        raise GatewayCapabilityMismatchError(
            'lane does not support json_schema structured output',
            param='response_format',
        )

    json_schema = response_format.get('json_schema')
    if not isinstance(json_schema, Mapping):
        raise GatewayInvalidRequestError(
            'response_format.json_schema must be an object',
            param='response_format.json_schema',
        )
    typed_json_schema = cast(Mapping[str, Any], json_schema)
    name = typed_json_schema.get('name')
    if not isinstance(name, str) or not name.strip():
        raise GatewayInvalidRequestError(
            'response_format.json_schema.name is required',
            param='response_format.json_schema.name',
        )
    schema = typed_json_schema.get('schema')
    if not isinstance(schema, Mapping):
        raise GatewayInvalidRequestError(
            'response_format.json_schema.schema must be an object',
            param='response_format.json_schema.schema',
        )

    return response_format


def _validate_forwarded_params(request: Mapping[str, Any], lane: LaneConfig) -> Mapping[str, Any]:
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
    if 'reasoning_effort' in forwarded:
        _validate_reasoning_effort(forwarded['reasoning_effort'])
    if 'service_tier' in forwarded:
        _validate_service_tier(forwarded['service_tier'], lane)
    for key in ('tools', 'tool_choice', 'stream'):
        if key in request:
            forwarded[key] = request[key]
    return forwarded


def _validate_reasoning_effort(value: object) -> None:
    """A forwarded effort must be a known enum value, typed 400 otherwise.

    The forwarded value intentionally overrides the lane's configured
    `provider_options.reasoning_effort` in the executor, so the enum check is
    the bound on what a caller can switch per request.
    """
    if not isinstance(value, str) or value not in REASONING_EFFORT_VALUES:
        raise GatewayInvalidRequestError(
            f'reasoning_effort must be one of {sorted(REASONING_EFFORT_VALUES)}',
            param='reasoning_effort',
        )


def _validate_service_tier(value: object, lane: LaneConfig) -> None:
    if value != 'flex':
        raise GatewayInvalidRequestError('service_tier must be flex', param='service_tier')
    if lane.lane_id not in {
        'omi:auto:memory-conflict-flex',
        'omi:auto:memory-l2-flex',
        'omi:auto:x-memory-extraction-flex',
    }:
        raise GatewayCapabilityMismatchError(
            'Flex processing is only enabled for scheduled background memory work',
            param='service_tier',
        )


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
