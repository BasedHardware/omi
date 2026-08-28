"""Gemini↔OpenAI translation for company-paid desktop traffic on the LLM gateway.

The desktop proxy (``routers/desktop_proxy.py``) stays the BFF: Firebase auth,
trial paywall, redis metering, body limits, and the model allowlist never move.
The *model call* hops the gateway's OpenAI-compatible surfaces — chat
completions on the ``omi:auto:desktop-vertex-*`` lanes and embeddings on
``omi:auto:gemini-embeddings`` — so company-paid Vertex spend lands in the one
gateway ledger. The Mac app keeps its Gemini wire format; translation happens
here (BFF) and in the gateway's Vertex adapter, never in a desktop client.

Lane selection, PT pin/overflow, and the regional vs multi-region host split
live in ``utils.llm.vertex_pt_routing`` and the gateway's ``VertexGeminiProvider``.

Gemini BYOK keeps the thin direct AI Studio path in the proxy: the gateway's
Vertex adapter fail-closes BYOK by design.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm import vertex_pt_routing as ptr
from utils.llm.gateway_client import (
    GEMINI_EMBEDDINGS_AUTO_LANE_ID,
    get_llm_gateway_base_url,
    llm_gateway_headers,
)

DESKTOP_GATEWAY_FEATURE = 'desktop_proactivity'
DESKTOP_GATEWAY_TIMEOUT_SECONDS = 75.0
_GATEWAY_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent'})


class DesktopGeminiGatewayError(Exception):
    """The gateway hop failed; the proxy maps this to its error envelope."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class GatewayChatResult:
    """A translated gateway chat response in Gemini wire shape."""

    gemini_payload: Mapping[str, Any]


@dataclass(frozen=True)
class GatewayEmbeddingResult:
    values: list[float]


def desktop_gateway_actions() -> frozenset[str]:
    """Actions whose company-paid traffic can hop the gateway."""
    return _GATEWAY_ACTIONS


def desktop_gateway_text_lane(model: str) -> str | None:
    return ptr.desktop_text_lane_id(model)


def _join_system_text(payload: Mapping[str, Any]) -> str | None:
    instruction = payload.get('systemInstruction') or payload.get('system_instruction')
    if not isinstance(instruction, Mapping):
        return None
    parts = instruction.get('parts')
    if not isinstance(parts, list):
        return None
    texts = [part.get('text') for part in parts if isinstance(part, Mapping) and isinstance(part.get('text'), str)]
    joined = '\n'.join(text for text in texts if text)
    return joined or None


def _inline_data_to_image_part(part: Mapping[str, Any]) -> dict[str, Any]:
    inline = part.get('inlineData') or part.get('inline_data')
    mime = inline.get('mimeType') or inline.get('mime_type') or 'image/jpeg' if isinstance(inline, Mapping) else ''
    data = inline.get('data') if isinstance(inline, Mapping) else ''
    return {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{data}'}}


def _gemini_parts_to_openai(parts: list[Any]) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        if isinstance(part.get('text'), str):
            translated.append({'type': 'text', 'text': part['text']})
        elif 'inlineData' in part or 'inline_data' in part:
            translated.append(_inline_data_to_image_part(part))
    return translated


def _tool_call_id(name: str, ordinal: int) -> str:
    return f'call_{name}_{ordinal}'


def gemini_body_to_openai_chat(
    payload: Mapping[str, Any],
    *,
    lane_id: str,
    stream: bool,
) -> dict[str, Any]:
    """Translate a Gemini generateContent body into a gateway chat-completions request."""
    messages: list[dict[str, Any]] = []
    system_text = _join_system_text(payload)
    if system_text:
        messages.append({'role': 'system', 'content': system_text})

    contents = payload.get('contents')
    tool_name_by_id: dict[str, str] = {}
    tool_ordinal = 0
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, Mapping):
                continue
            role = content.get('role') or 'user'
            parts = content.get('parts') if isinstance(content.get('parts'), list) else []
            function_responses = [p for p in parts if isinstance(p, Mapping) and ('functionResponse' in p)]
            function_calls = [p for p in parts if isinstance(p, Mapping) and ('functionCall' in p)]
            if function_responses:
                for part in function_responses:
                    response = part.get('functionResponse')
                    name = response.get('name') if isinstance(response, Mapping) else None
                    if not isinstance(name, str) or not name:
                        name = tool_name_by_id.get(_tool_call_id('', tool_ordinal - 1), '')
                    payload_out = response.get('response') if isinstance(response, Mapping) else None
                    if not isinstance(payload_out, Mapping):
                        payload_out = {}
                    messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': _tool_call_id(name or 'fn', tool_ordinal),
                            'name': name or 'fn',
                            'content': json.dumps(dict(payload_out)),
                        }
                    )
                continue
            if role in {'model', 'assistant'} and function_calls:
                tool_calls = []
                for part in function_calls:
                    call = part.get('functionCall')
                    if not isinstance(call, Mapping):
                        continue
                    name = str(call.get('name') or '')
                    arguments = call.get('args') if isinstance(call.get('args'), Mapping) else {}
                    call_id = _tool_call_id(name, tool_ordinal)
                    tool_name_by_id[call_id] = name
                    tool_ordinal += 1
                    tool_calls.append(
                        {
                            'id': call_id,
                            'type': 'function',
                            'function': {'name': name, 'arguments': json.dumps(dict(arguments))},
                        }
                    )
                text_parts = [p.get('text') for p in parts if isinstance(p, Mapping) and isinstance(p.get('text'), str)]
                messages.append(
                    {
                        'role': 'assistant',
                        'content': ''.join(text for text in text_parts if text) or None,
                        'tool_calls': tool_calls,
                    }
                )
                continue
            translated_parts = _gemini_parts_to_openai(parts)
            if translated_parts or role not in {'model', 'assistant'}:
                messages.append(
                    {
                        'role': 'assistant' if role in {'model', 'assistant'} else 'user',
                        'content': translated_parts,
                    }
                )

    if not messages:
        messages.append({'role': 'user', 'content': [{'type': 'text', 'text': ''}]})

    request: dict[str, Any] = {'model': lane_id, 'messages': messages, 'stream': stream}
    config = payload.get('generationConfig') or payload.get('generation_config')
    if isinstance(config, Mapping):
        if isinstance(config.get('maxOutputTokens') or config.get('max_output_tokens'), int):
            request['max_completion_tokens'] = config.get('maxOutputTokens') or config.get('max_output_tokens')
        if isinstance(config.get('temperature'), (int, float)):
            request['temperature'] = config['temperature']
        if isinstance(config.get('topP') or config.get('top_p'), (int, float)):
            request['top_p'] = config.get('topP') or config.get('top_p')
        stop = config.get('stopSequences') or config.get('stop_sequences')
        if isinstance(stop, list) and stop:
            request['stop'] = stop
        thinking = config.get('thinkingConfig') or config.get('thinking_config')
        if isinstance(thinking, Mapping) and isinstance(
            thinking.get('thinkingBudget') or thinking.get('thinking_budget'), int
        ):
            budget = thinking.get('thinkingBudget') or thinking.get('thinking_budget')
            request['google'] = {'thinking_config': {'thinking_budget': budget}}
        response_schema = config.get('responseSchema') or config.get('response_schema')
        mime = config.get('responseMimeType') or config.get('response_mime_type')
        if isinstance(response_schema, Mapping):
            request['response_format'] = {
                'type': 'json_schema',
                'json_schema': {'name': 'desktop_response', 'schema': dict(response_schema)},
            }
        elif mime == 'application/json':
            request['response_format'] = {'type': 'json_object'}

    tools = _gemini_tools_to_openai(payload.get('tools'))
    if tools is not None:
        request['tools'] = tools
    tool_choice = _gemini_tool_config_to_openai(payload.get('toolConfig') or payload.get('tool_config'))
    if tool_choice is not None:
        request['tool_choice'] = tool_choice
    return request


def _gemini_tools_to_openai(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    tools: list[dict[str, Any]] = []
    for tool in value:
        if not isinstance(tool, Mapping):
            continue
        declarations = tool.get('functionDeclarations') or tool.get('function_declarations')
        if not isinstance(declarations, list):
            continue
        for declaration in declarations:
            if isinstance(declaration, Mapping) and isinstance(declaration.get('name'), str):
                function: dict[str, Any] = {'name': declaration['name']}
                if isinstance(declaration.get('description'), str):
                    function['description'] = declaration['description']
                if isinstance(declaration.get('parameters'), Mapping):
                    function['parameters'] = dict(declaration['parameters'])
                tools.append({'type': 'function', 'function': function})
    return tools or None


def _gemini_tool_config_to_openai(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return None
    config = value.get('functionCallingConfig') or value.get('function_calling_config')
    if not isinstance(config, Mapping):
        return None
    mode = config.get('mode')
    allowed = config.get('allowedFunctionNames') or config.get('allowed_function_names')
    if mode in {'ANY', 'MODE_ANY'}:
        if isinstance(allowed, list) and allowed and isinstance(allowed[0], str):
            return {'type': 'function', 'function': {'name': allowed[0]}}
        return 'required'
    if mode in {'AUTO', 'MODE_AUTO'}:
        return 'auto'
    if mode in {'NONE', 'MODE_NONE'}:
        return 'none'
    return None


_OPENAI_TO_GEMINI_FINISH_REASON = {
    'stop': 'STOP',
    'length': 'MAX_TOKENS',
    'content_filter': 'SAFETY',
    'tool_calls': 'STOP',
}


def openai_completion_to_gemini(body: Mapping[str, Any]) -> dict[str, Any]:
    """Translate a gateway chat-completions response back into Gemini wire shape."""
    choices = body.get('choices') if isinstance(body.get('choices'), list) else []
    choice = choices[0] if choices and isinstance(choices[0], Mapping) else {}
    message = choice.get('message') if isinstance(choice.get('message'), Mapping) else {}
    parts: list[dict[str, Any]] = []
    if isinstance(message.get('content'), str) and message['content']:
        parts.append({'text': message['content']})
    for call in message.get('tool_calls') or []:
        if not isinstance(call, Mapping):
            continue
        function = call.get('function')
        if not isinstance(function, Mapping):
            continue
        try:
            arguments = json.loads(function.get('arguments') or '{}')
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, Mapping):
            arguments = {}
        parts.append({'functionCall': {'name': function.get('name'), 'args': dict(arguments)}})
    if not parts:
        parts = [{'text': ''}]
    candidate: dict[str, Any] = {
        'content': {'parts': parts},
        'finishReason': _OPENAI_TO_GEMINI_FINISH_REASON.get(str(choice.get('finish_reason') or ''), 'STOP'),
    }
    response: dict[str, Any] = {'candidates': [candidate]}
    if isinstance(body.get('model'), str):
        response['modelVersion'] = body['model']
    usage = body.get('usage') if isinstance(body.get('usage'), Mapping) else None
    if usage is not None:
        response['usageMetadata'] = {
            'promptTokenCount': usage.get('prompt_tokens', 0),
            'candidatesTokenCount': usage.get('completion_tokens', 0),
            'totalTokenCount': usage.get('total_tokens', 0),
        }
    return response


def openai_sse_payload_to_gemini_event(
    payload: Mapping[str, Any],
    pending_tool_calls: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    """Translate one OpenAI SSE data payload into one Gemini SSE event.

    Text deltas stream one Gemini event per chunk. Tool-call argument fragments
    accumulate in ``pending_tool_calls`` keyed by tool index and are emitted as
    a single functionCall part on the terminal chunk, matching Gemini's
    whole-object functionCall semantics.
    """
    choices = payload.get('choices') if isinstance(payload.get('choices'), list) else []
    choice = choices[0] if choices and isinstance(choices[0], Mapping) else {}
    delta = choice.get('delta') if isinstance(choice.get('delta'), Mapping) else {}
    parts: list[dict[str, Any]] = []
    if isinstance(delta.get('content'), str) and delta['content']:
        parts.append({'text': delta['content']})
    for call in delta.get('tool_calls') or []:
        if not isinstance(call, Mapping):
            continue
        index = call.get('index') if isinstance(call.get('index'), int) else 0
        accumulated = pending_tool_calls.setdefault(index, {'name': '', 'arguments': ''})
        function = call.get('function')
        if isinstance(function, Mapping):
            if isinstance(function.get('name'), str) and function['name']:
                accumulated['name'] = function['name']
            if isinstance(function.get('arguments'), str):
                accumulated['arguments'] += function['arguments']
    finish_reason = choice.get('finish_reason')
    if finish_reason:
        for accumulated in pending_tool_calls.values():
            try:
                arguments = json.loads(accumulated['arguments'] or '{}')
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, Mapping):
                arguments = {}
            parts.append({'functionCall': {'name': accumulated['name'], 'args': dict(arguments)}})
        pending_tool_calls.clear()
        return {
            'candidates': [
                {
                    'content': {'parts': parts or [{'text': ''}]},
                    'finishReason': _OPENAI_TO_GEMINI_FINISH_REASON.get(str(finish_reason), 'STOP'),
                }
            ]
        }
    if not parts:
        return None
    return {'candidates': [{'content': {'parts': parts}}]}


def _gateway_error(result: httpx.Response) -> DesktopGeminiGatewayError:
    try:
        body = result.json()
        message = str(body.get('error', {}).get('message') or body.get('detail') or 'gateway request failed')
    except ValueError:
        message = 'gateway request failed'
    status = result.status_code
    code = (
        'provider_rate_limited' if status == 429 else 'provider_unavailable' if status >= 500 else 'provider_rejected'
    )
    return DesktopGeminiGatewayError(status_code=status, code=code, message=message)


def _desktop_gateway_headers(*, uid: str) -> dict[str, str]:
    headers = llm_gateway_headers(feature=DESKTOP_GATEWAY_FEATURE, platform='desktop')
    headers['X-Omi-User-Uid'] = uid
    return headers


async def gateway_desktop_chat(
    body: bytes,
    *,
    model: str,
    action: str,
    uid: str,
) -> GatewayChatResult:
    """Run a company-paid desktop generateContent request through the gateway."""
    payload = json.loads(body)
    lane_id = ptr.desktop_text_lane_id(model)
    if lane_id is None:
        raise DesktopGeminiGatewayError(
            status_code=400, code='validation_rejected', message=f'Gemini model {model} has no gateway lane'
        )
    request = gemini_body_to_openai_chat(payload, lane_id=lane_id, stream=False)
    async with get_llm_gateway_semaphore():
        client = get_llm_gateway_client()
        result = await client.post(
            f'{get_llm_gateway_base_url()}/v1/chat/completions',
            headers=_desktop_gateway_headers(uid=uid),
            json=request,
            timeout=DESKTOP_GATEWAY_TIMEOUT_SECONDS,
        )
    if result.status_code >= 400:
        raise _gateway_error(result)
    return GatewayChatResult(gemini_payload=openai_completion_to_gemini(result.json()))


async def gateway_desktop_chat_stream(
    body: bytes,
    *,
    model: str,
    uid: str,
) -> AsyncIterator[bytes]:
    """Stream a company-paid desktop streamGenerateContent request through the gateway."""
    payload = json.loads(body)
    lane_id = ptr.desktop_text_lane_id(model)
    if lane_id is None:
        raise DesktopGeminiGatewayError(
            status_code=400, code='validation_rejected', message=f'Gemini model {model} has no gateway lane'
        )
    request = gemini_body_to_openai_chat(payload, lane_id=lane_id, stream=True)
    async with get_llm_gateway_semaphore():
        client = get_llm_gateway_client()
        async with client.stream(
            'POST',
            f'{get_llm_gateway_base_url()}/v1/chat/completions',
            headers=_desktop_gateway_headers(uid=uid),
            json=request,
            timeout=DESKTOP_GATEWAY_TIMEOUT_SECONDS,
        ) as result:
            if result.status_code >= 400:
                await result.aread()
                raise _gateway_error(result)
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            buffer = ''
            async for chunk in result.aiter_text():
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line.startswith('data:'):
                        continue
                    data = line.removeprefix('data:').strip()
                    if not data or data == '[DONE]':
                        continue
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(parsed, Mapping):
                        continue
                    event = openai_sse_payload_to_gemini_event(parsed, pending_tool_calls)
                    if event is not None:
                        yield f'data: {json.dumps(event, separators=(",", ":"))}\n\n'.encode('utf-8')


async def gateway_desktop_embed_content(body: bytes, *, uid: str) -> GatewayEmbeddingResult:
    """Run a company-paid desktop embedContent request through the gateway embeddings lane."""
    payload = json.loads(body)
    try:
        text = payload['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError) as exc:
        raise DesktopGeminiGatewayError(
            status_code=400, code='validation_rejected', message='embedContent requires content.parts[0].text'
        ) from exc
    request: dict[str, Any] = {'model': GEMINI_EMBEDDINGS_AUTO_LANE_ID, 'input': [text]}
    if isinstance(payload.get('taskType') or payload.get('task_type'), str):
        request['task_type'] = payload.get('taskType') or payload.get('task_type')
    if isinstance(payload.get('title'), str):
        request['title'] = payload['title']
    async with get_llm_gateway_semaphore():
        client = get_llm_gateway_client()
        result = await client.post(
            f'{get_llm_gateway_base_url()}/v1/embeddings',
            headers=_desktop_gateway_headers(uid=uid),
            json=request,
            timeout=DESKTOP_GATEWAY_TIMEOUT_SECONDS,
        )
    if result.status_code >= 400:
        raise _gateway_error(result)
    data = result.json().get('data')
    values = data[0].get('embedding') if isinstance(data, list) and data and isinstance(data[0], Mapping) else None
    if not isinstance(values, list):
        raise DesktopGeminiGatewayError(
            status_code=502, code='invalid_response', message='gateway embeddings response had no vector'
        )
    return GatewayEmbeddingResult(values=[float(value) for value in values])
