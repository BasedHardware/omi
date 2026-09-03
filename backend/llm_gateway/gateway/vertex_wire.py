"""Gemini-native wire translation for the gateway Vertex adapter.

Pure OpenAI <-> Gemini translation: request building (contents, tools,
toolConfig, generationConfig, thinking), response/SSE normalization, and
the :predict embeddings shapes. No HTTP and no PT policy here - those live
in providers.py and vertex_pt_policy.py.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any, cast

from llm_gateway.gateway.accounting import ProviderUsage
from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.provider_types import _openai_usage_payload  # pyright: ignore[reportPrivateUsage]
from llm_gateway.gateway.schemas import FailureClass
from utils.llm import vertex_pt_routing as ptr

__all__ = [
    '_bounded_error_text',
    '_json_schema_to_vertex_response_schema',
    '_nonnegative_int_or_zero',
    '_openai_sse',
    '_openai_sse_done',
    '_system_text_parts',
    '_text_content',
    '_validate_embeddings_response_shape',
    '_vertex_embedding_predict_request',
    '_vertex_headers',
    '_vertex_predict_to_openai_embeddings',
    '_vertex_request',
    '_vertex_to_openai_response',
    '_vertex_to_openai_stream_chunk',
]


def _vertex_headers(access_token: str, capacity: str) -> dict[str, str]:
    if not access_token.strip():
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
    # Without the capacity header Vertex silently spills over-cap dedicated
    # requests onto pay-as-you-go; asking for `dedicated` turns that into a
    # 429 the PT ladder can act on, and everything else is pinned `shared` so
    # it can never draw down the reservation.
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        ptr.REQUEST_TYPE_HEADER: capacity,
    }


def _vertex_request(request: Mapping[str, Any]) -> dict[str, Any]:
    unsupported_params = sorted(
        key
        for key in (
            'frequency_penalty',
            'logit_bias',
            'logprobs',
            'n',
            'presence_penalty',
            'prompt_cache_key',
            'seed',
            'top_logprobs',
            'user',
        )
        if key in request
    )
    if unsupported_params:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)

    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    raw_messages = request.get('messages')
    if not isinstance(raw_messages, list):
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    tool_names_by_id: dict[str, str] = {}
    for message in raw_messages:
        if not isinstance(message, Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        role = message.get('role')
        if role == 'system':
            # Vertex systemInstruction takes text parts only. _vertex_parts raises rather
            # than silently flattening an image here, same as everywhere else below.
            system_parts.extend(_system_text_parts(message.get('content')))
            continue
        if role == 'tool':
            contents.append(_vertex_function_response_content(message, tool_names_by_id))
            continue
        if role == 'assistant' and isinstance(message.get('tool_calls'), list):
            content, names = _vertex_model_tool_call_content(message, tool_names_by_id)
            tool_names_by_id.update(names)
            contents.append(content)
            continue
        if role not in {'user', 'assistant'}:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        contents.append(
            {
                'role': 'model' if role == 'assistant' else 'user',
                'parts': _vertex_parts(message.get('content')),
            }
        )

    generation_config: dict[str, Any] = {}
    for request_key, vertex_key in (('temperature', 'temperature'), ('top_p', 'topP')):
        if request_key in request:
            generation_config[vertex_key] = request[request_key]
    if 'stop' in request:
        stop = request['stop']
        if isinstance(stop, str):
            generation_config['stopSequences'] = [stop]
        elif isinstance(stop, list) and all(isinstance(item, str) for item in stop):
            generation_config['stopSequences'] = stop
        else:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    output_limit = _output_limit(request)
    if output_limit is not None:
        generation_config['maxOutputTokens'] = output_limit
    thinking_budget = _thinking_budget(request)
    if thinking_budget is not None:
        generation_config['thinkingConfig'] = {'thinkingBudget': thinking_budget}
    response_format = request.get('response_format')
    if isinstance(response_format, Mapping):
        format_type = response_format.get('type')
        if format_type == 'json_object':
            generation_config['responseMimeType'] = 'application/json'
        else:
            json_schema = response_format.get('json_schema')
            if not isinstance(json_schema, Mapping) or not isinstance(json_schema.get('schema'), Mapping):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            generation_config['responseMimeType'] = 'application/json'
            generation_config['responseSchema'] = _json_schema_to_vertex_response_schema(
                cast(Mapping[str, Any], json_schema['schema'])
            )

    payload: dict[str, Any] = {'contents': contents}
    if system_parts:
        payload['systemInstruction'] = {'parts': system_parts}
    if generation_config:
        payload['generationConfig'] = generation_config
    tools = _vertex_tools(request.get('tools'))
    if tools is not None:
        payload['tools'] = tools
    tool_config = _vertex_tool_config(request.get('tool_choice'))
    if tool_config is not None:
        payload['toolConfig'] = tool_config
    return payload


_JSON_SCHEMA_META_KEYS = frozenset({'$defs', 'definitions', '$schema', '$id', '$comment'})
_LOCAL_REF_PREFIXES = ('#/$defs/', '#/definitions/')


def _json_schema_to_vertex_response_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Convert OpenAI/Pydantic JSON Schema into Vertex ``responseSchema``.

    Vertex ``responseSchema`` is an OpenAPI 3 subset that accepts ``defs``/``ref``,
    not JSON Schema ``$defs``/``$ref``. Copying a nested Pydantic schema as-is
    yields ``InvalidArgument`` 400. Inline local refs and drop JSON-Schema-only
    meta keys so a legal nested schema stays a legal Vertex request.
    """
    converted = _inline_json_schema(schema, _collect_json_schema_defs(schema), frozenset())
    if not isinstance(converted, dict):
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return converted


def _collect_json_schema_defs(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    defs: dict[str, Mapping[str, Any]] = {}
    for key in ('$defs', 'definitions'):
        raw = schema.get(key)
        if not isinstance(raw, Mapping):
            continue
        for name, definition in raw.items():
            if isinstance(name, str) and isinstance(definition, Mapping):
                defs[name] = cast(Mapping[str, Any], definition)
    return defs


def _inline_json_schema(node: Any, defs: Mapping[str, Mapping[str, Any]], visiting: frozenset[str]) -> Any:
    if isinstance(node, list):
        return [_inline_json_schema(item, defs, visiting) for item in cast(list[Any], node)]
    if not isinstance(node, Mapping):
        return node
    typed_node = cast(Mapping[str, Any], node)
    local_defs = dict(defs)
    local_defs.update(_collect_json_schema_defs(typed_node))
    ref = typed_node.get('$ref')
    if isinstance(ref, str):
        name = _local_json_schema_ref_name(ref)
        if name is None or name in visiting:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        definition = local_defs.get(name)
        if not isinstance(definition, Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        merged = {**definition, **{key: value for key, value in typed_node.items() if key != '$ref'}}
        return _inline_json_schema(merged, local_defs, visiting | {name})
    return {
        key: _inline_json_schema(value, local_defs, visiting)
        for key, value in typed_node.items()
        if key not in _JSON_SCHEMA_META_KEYS
    }


def _local_json_schema_ref_name(ref: str) -> str | None:
    for prefix in _LOCAL_REF_PREFIXES:
        if ref.startswith(prefix):
            name = ref[len(prefix) :]
            if name and '/' not in name:
                return name
    return None


def _output_limit(request: Mapping[str, Any]) -> int | None:
    max_completion_tokens = request.get('max_completion_tokens')
    max_tokens = request.get('max_tokens')
    value = max_completion_tokens if max_completion_tokens is not None else max_tokens
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return value


def _thinking_budget(request: Mapping[str, Any]) -> int | None:
    if request.get('reasoning_effort') == 'none':
        return 0
    # The OpenAI SDK's extra_body convention flattens `extra_body={'google': …}`
    # into a top-level `google` field, so per-request Gemini options arrive both
    # ways: as a forwarded top-level `google` param and via provider_options.
    google_options = request.get('google')
    if isinstance(google_options, Mapping):
        budget = _thinking_budget_from_google(google_options)
        if budget is not None:
            return budget
    extra_body = request.get('extra_body')
    if isinstance(extra_body, Mapping):
        extra_google = extra_body.get('google')
        if isinstance(extra_google, Mapping):
            budget = _thinking_budget_from_google(extra_google)
            if budget is not None:
                return budget
    return None


def _thinking_budget_from_google(google_options: Mapping[str, Any]) -> int | None:
    thinking_config = google_options.get('thinking_config')
    if not isinstance(thinking_config, Mapping):
        return None
    thinking_budget = thinking_config.get('thinking_budget')
    if not isinstance(thinking_budget, int) or isinstance(thinking_budget, bool) or thinking_budget < 0:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return thinking_budget


def _vertex_tools(value: Any) -> list[dict[str, Any]] | None:
    """Translate OpenAI function tools into a Gemini tools declaration."""
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    declarations: list[dict[str, Any]] = []
    for tool in value:
        if not isinstance(tool, Mapping) or tool.get('type') != 'function':
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        function = tool.get('function')
        if not isinstance(function, Mapping) or not isinstance(function.get('name'), str) or not function['name']:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        declaration: dict[str, Any] = {'name': function['name']}
        description = function.get('description')
        if isinstance(description, str) and description:
            declaration['description'] = description
        parameters = function.get('parameters')
        if isinstance(parameters, Mapping) and parameters:
            declaration['parameters'] = dict(cast(Mapping[str, Any], parameters))
        declarations.append(declaration)
    return [{'functionDeclarations': declarations}]


def _vertex_tool_config(value: Any) -> dict[str, Any] | None:
    """Translate OpenAI tool_choice into Gemini functionCallingConfig."""
    if value is None:
        return None
    if value == 'required':
        return {'functionCallingConfig': {'mode': 'ANY'}}
    if value == 'auto':
        return {'functionCallingConfig': {'mode': 'AUTO'}}
    if value == 'none':
        return {'functionCallingConfig': {'mode': 'NONE'}}
    if isinstance(value, Mapping) and value.get('type') == 'function':
        function = value.get('function')
        if isinstance(function, Mapping) and isinstance(function.get('name'), str) and function['name']:
            return {'functionCallingConfig': {'mode': 'ANY', 'allowedFunctionNames': [function['name']]}}
    raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)


def _vertex_model_tool_call_content(
    message: Mapping[str, Any],
    tool_names_by_id: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """An assistant message with OpenAI tool_calls -> a Gemini model functionCall content."""
    parts: list[dict[str, Any]] = []
    if isinstance(message.get('content'), str) and message['content']:
        parts.append({'text': message['content']})
    names: dict[str, str] = {}
    for call in message['tool_calls']:
        if not isinstance(call, Mapping) or call.get('type') != 'function':
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        function = call.get('function')
        if not isinstance(function, Mapping) or not isinstance(function.get('name'), str) or not function['name']:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        raw_arguments = function.get('arguments')
        if isinstance(raw_arguments, Mapping):
            arguments: dict[str, Any] = dict(cast(Mapping[str, Any], raw_arguments))
        elif isinstance(raw_arguments, str) and raw_arguments:
            try:
                decoded = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH) from exc
            if not isinstance(decoded, Mapping):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            arguments = dict(cast(Mapping[str, Any], decoded))
        else:
            arguments = {}
        parts.append({'functionCall': {'name': function['name'], 'args': arguments}})
        call_id = call.get('id')
        if isinstance(call_id, str) and call_id:
            names[call_id] = function['name']
    if not parts:
        parts = [{'text': ''}]
    return {'role': 'model', 'parts': parts}, names


def _vertex_function_response_content(
    message: Mapping[str, Any],
    tool_names_by_id: dict[str, str],
) -> dict[str, Any]:
    """An OpenAI tool-result message -> a Gemini user functionResponse content."""
    raw_content = message.get('content')
    if isinstance(raw_content, Mapping):
        response_payload: dict[str, Any] = dict(cast(Mapping[str, Any], raw_content))
    elif isinstance(raw_content, str) and raw_content:
        try:
            decoded = json.loads(raw_content)
        except json.JSONDecodeError:
            response_payload = {'result': raw_content}
        else:
            response_payload = (
                dict(cast(Mapping[str, Any], decoded)) if isinstance(decoded, Mapping) else {'result': raw_content}
            )
    else:
        response_payload = {}
    name = message.get('name')
    if not isinstance(name, str) or not name:
        name = tool_names_by_id.get(str(message.get('tool_call_id') or ''), '')
    if not name:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)

    return {'role': 'user', 'parts': [{'functionResponse': {'name': name, 'response': response_payload}}]}


def _nonnegative_int_or_zero(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _bounded_error_text(preview: bytes) -> str:
    return preview.decode('utf-8', errors='replace')


def _vertex_embedding_predict_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """An OpenAI embeddings request -> a Vertex :predict instances payload."""
    inputs = request.get('input')
    if isinstance(inputs, str):
        inputs = [inputs]
    if not isinstance(inputs, list) or not inputs:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    instances: list[dict[str, Any]] = []
    for text in inputs:
        if not isinstance(text, str) or not text:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        instance: dict[str, Any] = {'content': text}
        task_type = request.get('task_type')
        if isinstance(task_type, str) and task_type:
            instance['task_type'] = task_type
        title = request.get('title')
        if isinstance(title, str) and title:
            instance['title'] = title
        instances.append(instance)
    return {'instances': instances}


def _vertex_predict_to_openai_embeddings(response: Mapping[str, Any], *, model: str) -> dict[str, Any]:
    predictions = response.get('predictions')
    data: list[dict[str, Any]] = []
    if isinstance(predictions, list):
        for index, prediction in enumerate(predictions):
            embeddings = prediction.get('embeddings') if isinstance(prediction, Mapping) else None
            values = embeddings.get('values') if isinstance(embeddings, Mapping) else None
            if not isinstance(values, list):
                values = []
            data.append({'object': 'embedding', 'embedding': [float(value) for value in values], 'index': index})
    return {'object': 'list', 'data': data, 'model': model}


def _validate_embeddings_response_shape(response: Mapping[str, Any]) -> None:
    if response.get('object') != 'list' or not isinstance(response.get('data'), list) or not response['data']:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    for item in response['data']:
        if not isinstance(item, Mapping) or not isinstance(item.get('embedding'), list):
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)


def _vertex_to_openai_response(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    usage: ProviderUsage | None = None,
) -> dict[str, Any]:
    candidates = response.get('candidates')
    candidate = (
        candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else None
    )
    content = _vertex_candidate_text(candidate)
    finish_reason = _vertex_finish_reason(candidate.get('finishReason') if candidate is not None else 'SAFETY')
    normalized: dict[str, Any] = {
        'id': str(response.get('responseId') or 'vertex_gateway'),
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': requested_model,
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content},
                'finish_reason': finish_reason,
            }
        ],
    }
    if usage is not None:
        normalized['usage'] = _openai_usage_payload(usage)
    return normalized


def _vertex_to_openai_stream_chunk(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    usage: ProviderUsage | None = None,
) -> tuple[bytes | None, bool]:
    candidates = response.get('candidates')
    candidate = (
        candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else None
    )
    if candidate is None and usage is None:
        return None, False
    text = _vertex_candidate_text(candidate)
    raw_finish_reason = candidate.get('finishReason') if candidate is not None else None
    finish_reason = _vertex_finish_reason(raw_finish_reason) if raw_finish_reason else None
    if not text and finish_reason is None and usage is None:
        return None, False
    body: dict[str, Any] = {
        'id': str(response.get('responseId') or 'vertex_gateway'),
        'object': 'chat.completion.chunk',
        'created': int(time.time()),
        'model': requested_model,
        'choices': (
            [
                {
                    'index': 0,
                    'delta': {'content': text} if text else {},
                    'finish_reason': finish_reason,
                }
            ]
            if candidate is not None
            else []
        ),
    }
    if usage is not None:
        body['usage'] = _openai_usage_payload(usage)
    return _openai_sse(body), finish_reason is not None


def _vertex_candidate_text(candidate: Mapping[str, Any] | None) -> str:
    if candidate is None:
        return ''
    content = candidate.get('content')
    if not isinstance(content, Mapping):
        return ''
    parts = content.get('parts')
    if not isinstance(parts, list):
        return ''
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, Mapping) and isinstance(part.get('text'), str):
            text_parts.append(part['text'])
    return ''.join(text_parts)


def _vertex_finish_reason(value: object) -> str:
    normalized = str(value or '').upper()
    if normalized in {'MAX_TOKENS', 'LENGTH'}:
        return 'length'
    if normalized in {'SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'RECITATION'}:
        return 'content_filter'
    return 'stop'


def _openai_sse(body: Mapping[str, Any]) -> bytes:
    return f'data: {json.dumps(dict(body), separators=(",", ":"))}\n\n'.encode('utf-8')


def _openai_sse_done() -> bytes:
    return b'data: [DONE]\n\n'


# RFC 2397 permits parameters between the media type and the base64 token
# (`data:image/jpeg;charset=utf-8;base64,...`), and browser- or canvas-produced
# data URLs do emit them. Rejecting those would be the mirror of the bug this
# module just fixed: refusing an image we can in fact represent.
_VERTEX_DATA_URL_RE = re.compile(
    r'^data:(?P<mime>[\w.+-]+/[\w.+-]+)(?:;[\w.+-]+=[^;,]*)*;(?i:base64),(?P<data>.+)$',
    re.DOTALL,
)


def _vertex_parts(content: Any) -> list[dict[str, Any]]:
    """Translate OpenAI-shaped message content into Vertex parts.

    Anything this cannot represent raises CAPABILITY_MISMATCH rather than being
    dropped. That distinction is the whole point of this function: the previous
    implementation ran every message through _text_content(), which keeps only
    `type == "text"` parts, so an image attached to a Gemini request vanished
    silently and the model answered about content it never received. For a
    caller like utils/screen_frames/judge.py — a privacy gate that decides
    whether a screenshot may be stored — a confident answer from a model that
    was sent no image is worse than an error, because the caller's fail-closed
    handling never triggers.
    """
    if content is None:
        # See the empty-parts note at the end of this function: None is what an
        # assistant tool-call turn carries, and Vertex rejects a Content with no parts.
        return [{'text': ''}]
    if isinstance(content, str):
        return [{'text': content}]
    if not isinstance(content, list):
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)

    parts: list[dict[str, Any]] = []
    for part in cast(list[object], content):
        if not isinstance(part, Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        typed_part = cast(Mapping[str, Any], part)
        part_type = typed_part.get('type')
        if part_type == 'text':
            text = typed_part.get('text')
            if not isinstance(text, str):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            parts.append({'text': text})
            continue
        if part_type == 'image_url':
            image_url = typed_part.get('image_url')
            if not isinstance(image_url, Mapping):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            url = cast(Mapping[str, Any], image_url).get('url')
            if not isinstance(url, str):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            match = _VERTEX_DATA_URL_RE.match(url)
            if match is None:
                # A remote https:// image is not fetchable by Vertex the way it is by
                # OpenAI; only inline bytes and gs:// URIs are. Refuse rather than send
                # a request the model will answer without the image.
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            parts.append({'inlineData': {'mimeType': match.group('mime'), 'data': match.group('data')}})
            continue
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    # A message with no representable content still needs one part: Vertex rejects a
    # Content with an empty parts array, and the previous implementation always
    # produced [{'text': ''}] here (via _text_content(None) == ''). An assistant
    # tool-call turn carries content=None, so this path is reachable the moment a
    # multi-turn Gemini feature exists.
    return parts or [{'text': ''}]


def _system_text_parts(content: Any) -> list[dict[str, str]]:
    parts = _vertex_parts(content)
    for part in parts:
        if 'text' not in part:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return [{'text': cast(str, part['text'])} for part in parts] or [{'text': ''}]


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in cast(list[object], content):
            if not isinstance(part, Mapping):
                continue
            typed_part = cast(Mapping[str, Any], part)
            if typed_part.get('type') == 'text' and isinstance(typed_part.get('text'), str):
                parts.append(typed_part['text'])
        return '\n'.join(parts)
    return ''
