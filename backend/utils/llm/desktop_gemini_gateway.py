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

from fastapi import HTTPException

import httpx

from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.byok import get_byok_key
from utils.llm import vertex_pt_routing as ptr
from utils.llm.gateway_client import should_route_features_through_gateway
from utils.llm.gateway_client import (
    GEMINI_EMBEDDINGS_AUTO_LANE_ID,
    get_llm_gateway_base_url,
    llm_gateway_headers,
)

DESKTOP_GATEWAY_FEATURE = 'desktop_proactivity'
DESKTOP_GATEWAY_TIMEOUT_SECONDS = 75.0
# BYOK keeps its historical output ceiling; server-paid clamps lower in the proxy.
_MAX_OUTPUT_TOKENS = 8192
_DEFAULT_THINKING_BUDGET = 1024
_MAX_CONTENT_ITEMS = 128
_MAX_CONTENT_PARTS = 512
_MAX_INLINE_MEDIA_PARTS = 16
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
    tool_id_by_name: dict[str, str] = {}
    tool_ordinal = 0
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, Mapping):
                continue
            role = content.get('role') or 'user'
            raw_parts = content.get('parts')
            parts: list[Any] = raw_parts if isinstance(raw_parts, list) else []
            function_responses = [p for p in parts if isinstance(p, Mapping) and ('functionResponse' in p)]
            function_calls = [p for p in parts if isinstance(p, Mapping) and ('functionCall' in p)]
            if function_responses:
                for part in function_responses:
                    response = part.get('functionResponse')
                    name = response.get('name') if isinstance(response, Mapping) else None
                    if not isinstance(name, str) or not name:
                        name = tool_name_by_id.get(_tool_call_id('', max(tool_ordinal - 1, 0)), '')
                    payload_out = response.get('response') if isinstance(response, Mapping) else None
                    if not isinstance(payload_out, Mapping):
                        payload_out = {}
                    call_id = tool_id_by_name.get(name or '') or _tool_call_id(name or 'fn', max(tool_ordinal - 1, 0))
                    messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': call_id,
                            'name': name or 'fn',
                            'content': json.dumps(dict(payload_out)),
                        }
                    )
                continue
            if role in {'model', 'assistant'} and function_calls:
                tool_calls: list[dict[str, Any]] = []
                for part in function_calls:
                    call = part.get('functionCall')
                    if not isinstance(call, Mapping):
                        continue
                    name = str(call.get('name') or '')
                    raw_args = call.get('args')
                    arguments: dict[str, Any] = dict(raw_args) if isinstance(raw_args, Mapping) else {}
                    call_id = _tool_call_id(name, tool_ordinal)
                    tool_name_by_id[call_id] = name
                    if name:
                        tool_id_by_name[name] = call_id
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
    raw_choices = body.get('choices')
    choices = raw_choices if isinstance(raw_choices, list) else []
    choice = choices[0] if choices and isinstance(choices[0], Mapping) else {}
    raw_message = choice.get('message')
    message = raw_message if isinstance(raw_message, Mapping) else {}
    parts: list[dict[str, Any]] = []
    if isinstance(message.get('content'), str) and message['content']:
        parts.append({'text': message['content']})
    raw_tool_calls = message.get('tool_calls')
    for call in raw_tool_calls if isinstance(raw_tool_calls, list) else []:
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
    raw_choices = payload.get('choices')
    choices = raw_choices if isinstance(raw_choices, list) else []
    choice = choices[0] if choices and isinstance(choices[0], Mapping) else {}
    raw_delta = choice.get('delta')
    delta = raw_delta if isinstance(raw_delta, Mapping) else {}
    parts: list[dict[str, Any]] = []
    if isinstance(delta.get('content'), str) and delta['content']:
        parts.append({'text': delta['content']})
    raw_calls = delta.get('tool_calls')
    for call in raw_calls if isinstance(raw_calls, list) else []:
        if not isinstance(call, Mapping):
            continue
        raw_index = call.get('index')
        index = raw_index if isinstance(raw_index, int) else 0
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


@dataclass(frozen=True)
class ProxyEnvelope:
    """Proxy-owned response helpers the gateway hop needs to answer in-shape.

    routers/desktop_proxy.py stays the BFF; this bundle passes its response
    envelope, disconnect handling, and timeout classification so the gateway
    hop answers with the exact wire contract desktop clients already parse.
    """

    error_response: Any
    response_headers: Any
    stream_error_event: Any
    cancel_on_disconnect: Any
    timeout_phase: Any
    client_disconnected: Any
    provider_unavailable_retry_after: int


def company_paid_via_gateway(model: str, action: str) -> bool:
    """Whether this request's model call hops the LLM gateway.

    Company-paid text and single-embed traffic only: BYOK keeps the thin
    direct AI Studio path (the gateway Vertex adapter fail-closes BYOK) and
    batchEmbedContents stays on AI Studio because the Vertex batch wire shape
    is not compatible. FEATURE_MODE=off keeps the legacy direct Vertex path.
    """
    if get_byok_key('gemini'):
        return False
    if action not in desktop_gateway_actions():
        return False
    try:
        if not should_route_features_through_gateway():
            return False
    except RuntimeError:
        return False
    if action == 'embedContent':
        return model == ptr.DESKTOP_EMBEDDING_MODEL
    return desktop_gateway_text_lane(model) is not None


def _gateway_error_response(error: DesktopGeminiGatewayError, telemetry, envelope: ProxyEnvelope):
    if error.status_code == 429:
        status_code, retryable, retry_after = 429, True, 30
    elif error.status_code >= 500:
        status_code, retryable, retry_after = 503, True, envelope.provider_unavailable_retry_after
    else:
        status_code, retryable, retry_after = error.status_code, False, None
    telemetry.complete(
        outcome=error.code,
        status_code=status_code,
        retryable=retryable,
        upstream_status=error.status_code,
        phase='gateway',
    )
    return envelope.error_response(
        telemetry,
        status_code=status_code,
        code=error.code,
        message=error.message,
        phase='gateway',
        retryable=retryable,
        upstream_status=error.status_code,
        retry_after=retry_after,
    )


async def proxy_company_paid_via_gateway(
    request,
    body: bytes,
    *,
    model: str,
    action: str,
    streaming: bool,
    uid: str,
    telemetry,
    envelope: ProxyEnvelope,
):
    """Company-paid hop through the LLM gateway; the desktop proxy stays the BFF."""
    from fastapi.responses import Response, StreamingResponse

    telemetry.provider = 'llm_gateway'
    telemetry.credential_source = 'omi_gateway'
    telemetry.phase = 'gateway'
    try:
        if action == 'embedContent':
            result = await envelope.cancel_on_disconnect(request, gateway_desktop_embed_content(body, uid=uid))
            content = json.dumps({'embedding': {'values': result.values}}, separators=(',', ':')).encode()
            telemetry.complete(outcome='success', status_code=200, retryable=False, phase='gateway')
            return Response(
                content,
                media_type='application/json',
                headers=envelope.response_headers(telemetry),
            )
        if streaming:

            async def stream_gateway():
                try:
                    async for chunk in gateway_desktop_chat_stream(body, model=model, uid=uid):
                        yield chunk
                    telemetry.complete(outcome='success', status_code=200, retryable=False, phase='gateway')
                except DesktopGeminiGatewayError as error:
                    status_code = 429 if error.status_code == 429 else 503 if error.status_code >= 500 else 502
                    telemetry.complete(outcome=error.code, status_code=status_code, retryable=True, phase='gateway')
                    yield envelope.stream_error_event(code=error.code, phase='gateway', telemetry=telemetry)
                except (httpx.TimeoutException, TimeoutError):
                    telemetry.complete(outcome='provider_timeout', status_code=504, retryable=False, phase='gateway')
                    yield envelope.stream_error_event(code='provider_timeout', phase='gateway', telemetry=telemetry)
                except httpx.HTTPError:
                    telemetry.complete(
                        outcome='provider_transport_error', status_code=502, retryable=False, phase='gateway'
                    )
                    yield envelope.stream_error_event(
                        code='provider_transport_error', phase='gateway', telemetry=telemetry
                    )

            return StreamingResponse(
                stream_gateway(),
                media_type='text/event-stream',
                headers=envelope.response_headers(telemetry),
            )
        result = await envelope.cancel_on_disconnect(
            request, gateway_desktop_chat(body, model=model, action=action, uid=uid)
        )
        payload = dict(result.gemini_payload)
        telemetry.observe_gemini_response(payload)
        telemetry.complete(outcome='success', status_code=200, retryable=False, upstream_status=200, phase='gateway')
        return Response(
            json.dumps(payload, separators=(',', ':')).encode(),
            media_type='application/json',
            headers=envelope.response_headers(telemetry),
        )
    except DesktopGeminiGatewayError as error:
        return _gateway_error_response(error, telemetry, envelope)
    except envelope.client_disconnected:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='gateway')
        return envelope.error_response(
            telemetry,
            status_code=499,
            code='client_cancelled',
            message='Client disconnected before the Gemini request completed',
            phase='gateway',
            retryable=False,
        )
    except httpx.TimeoutException as error:
        phase = envelope.timeout_phase(error)
        telemetry.complete(outcome=f'{phase}_timeout', status_code=504, retryable=False, phase='gateway')
        return envelope.error_response(
            telemetry,
            status_code=504,
            code='provider_timeout',
            message=f'Gemini gateway timed out during {phase}',
            phase='gateway',
            retryable=False,
        )
    except TimeoutError:
        telemetry.complete(outcome='provider_deadline_exceeded', status_code=504, retryable=False, phase='gateway')
        return envelope.error_response(
            telemetry,
            status_code=504,
            code='provider_deadline_exceeded',
            message='Gemini gateway request exceeded the Omi logical deadline',
            phase='gateway',
            retryable=False,
        )
    except httpx.HTTPError:
        telemetry.complete(outcome='provider_transport_error', status_code=502, retryable=False, phase='gateway')
        return envelope.error_response(
            telemetry,
            status_code=502,
            code='provider_transport_error',
            message='Gemini gateway transport failed',
            phase='gateway',
            retryable=False,
        )


@dataclass(frozen=True)
class PayloadShape:
    size_bucket: str
    content_parts_bucket: str
    inline_media_bucket: str


def _as_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _bucket(value: int, thresholds: tuple[tuple[int, str], ...], overflow: str) -> str:
    for maximum, label in thresholds:
        if value <= maximum:
            return label
    return overflow


def _size_bucket(size: int) -> str:
    return _bucket(
        size,
        ((16_384, '0-16kb'), (131_072, '16-128kb'), (524_288, '128-512kb'), (1_048_576, '512kb-1mb')),
        '1mb+',
    )


def _payload_shape(body: bytes) -> PayloadShape:  # pyright: ignore[reportUnusedFunction]
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return PayloadShape(_size_bucket(len(body)), 'unknown', 'unknown')
    if not isinstance(payload, dict):
        return PayloadShape(_size_bucket(len(body)), 'unknown', 'unknown')
    contents = payload.get('contents')
    content_count = len(contents) if isinstance(contents, list) else 0
    part_count = 0
    inline_media_count = 0
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, dict) or not isinstance(content.get('parts'), list):
                continue
            parts = content['parts']
            part_count += len(parts)
            for part in parts:
                if isinstance(part, dict) and ('inlineData' in part or 'inline_data' in part):
                    inline_media_count += 1
    if content_count > _MAX_CONTENT_ITEMS:
        raise HTTPException(status_code=413, detail='Gemini request has too many content items')
    if part_count > _MAX_CONTENT_PARTS:
        raise HTTPException(status_code=413, detail='Gemini request has too many content parts')
    if inline_media_count > _MAX_INLINE_MEDIA_PARTS:
        raise HTTPException(status_code=413, detail='Gemini request has too many inline media parts')
    return PayloadShape(
        _size_bucket(len(body)),
        _bucket(part_count, ((2, '0-2'), (8, '3-8'), (32, '9-32'), (128, '33-128')), '129+'),
        _bucket(inline_media_count, ((0, '0'), (1, '1'), (4, '2-4')), '5+'),
    )


def _sanitize(  # pyright: ignore[reportUnusedFunction]
    body: bytes,
    action: str,
    *,
    max_output_tokens: int = _MAX_OUTPUT_TOKENS,
) -> bytes:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail='Request body must be valid JSON') from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='Request body must be a JSON object')
    for key in ('safety_settings', 'safetySettings', 'cached_content', 'cachedContent'):
        payload.pop(key, None)
    contents = payload.get('contents')
    if isinstance(contents, list):
        system_parts: list[Any] = []
        remaining = []
        for content in contents:
            if not isinstance(content, dict):
                remaining.append(content)
                continue
            role = content.setdefault('role', 'user')
            if role == 'system':
                if isinstance(content.get('parts'), list):
                    system_parts.extend(content['parts'])
            else:
                remaining.append(content)
        payload['contents'] = remaining
        if system_parts:
            key = 'system_instruction' if 'system_instruction' in payload else 'systemInstruction'
            instruction = payload.get(key)
            if isinstance(instruction, dict) and isinstance(instruction.get('parts'), list):
                instruction['parts'].extend(system_parts)
            else:
                payload['systemInstruction'] = {'parts': system_parts}
    if action not in {'embedContent', 'batchEmbedContents'}:
        for key in ('candidate_count', 'candidateCount'):
            value = _as_nonnegative_int(payload.get(key))
            if value is not None and value > 1:
                raise HTTPException(status_code=400, detail='candidate_count must be 1 or absent')
        generation_configs = [
            payload[key] for key in ('generation_config', 'generationConfig') if isinstance(payload.get(key), dict)
        ]
        if not generation_configs:
            payload['generationConfig'] = {
                'maxOutputTokens': max_output_tokens,
                'thinkingConfig': ptr.thinking_config_for(budget=_DEFAULT_THINKING_BUDGET),
            }
        for config in generation_configs:
            for key in ('candidate_count', 'candidateCount'):
                value = _as_nonnegative_int(config.get(key))
                if value is not None and value > 1:
                    raise HTTPException(status_code=400, detail='candidate_count must be 1 or absent')
            output_key_present = False
            for key in ('max_output_tokens', 'maxOutputTokens'):
                value = _as_nonnegative_int(config.get(key))
                if value is not None:
                    output_key_present = True
                    if value > max_output_tokens:
                        config[key] = max_output_tokens
            if not output_key_present:
                config['maxOutputTokens'] = max_output_tokens
            if 'thinking_config' not in config and 'thinkingConfig' not in config:
                config['thinkingConfig'] = ptr.thinking_config_for(budget=_DEFAULT_THINKING_BUDGET)
    return json.dumps(payload, separators=(',', ':')).encode()
