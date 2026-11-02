"""Old Gemini-wire proxy requests traverse the real gateway after a simulated move."""

import json
from unittest.mock import AsyncMock
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request

from config import vertex_reservations as vr
from llm_gateway.main import app as gateway_app
from llm_gateway.routers import dependencies
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, VertexGeminiProvider
from routers import desktop_proxy as proxy
from utils.llm import desktop_gemini_gateway as bridge, vertex_pt_routing as ptr


def screen_payload():
    source = (
        Path(__file__).resolve().parents[3]
        / 'desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/ScreenTaskPrompt.swift'
    ).read_text()
    schema = json.loads(source.split('private static let schemaJSON = #"""', 1)[1].split('"""#', 1)[0])
    return {
        'systemInstruction': {'parts': [{'text': 'Invented test task extractor'}]},
        'contents': [
            {
                'role': 'user',
                'parts': [
                    {'text': 'Invented app and task context'},
                    {'inlineData': {'mimeType': 'image/jpeg', 'data': 'AQID'}},
                ],
            }
        ],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': schema,
            'maxOutputTokens': 2048,
            'thinkingConfig': {'thinkingLevel': 'low'},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['macos', 'windows'])
@pytest.mark.parametrize('tag', ['task_extraction', 'screen_synthesis', 'live_notes', 'suggestions', 'unknown'])
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('anchor', ['gemini-2.5-flash', 'gemini-3.8-flash'])
@pytest.mark.parametrize('phase', ['active', 'unknown', 'moved'])
async def test_proxy_flash_screenshot_schema_cutover(monkeypatch, platform, tag, stream, anchor, phase):
    await run_proxy(monkeypatch, platform, tag, stream, anchor, phase, screen_payload())


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(
    'shape',
    [
        'audio',
        'video',
        'file',
        'builtin_tool',
        'output_audio',
        'unknown_part',
        'system_image',
        'invalid_parts',
        'text_file',
        'text_file_snake',
        'text_audio',
        'text_mixed_inline',
        'system_text_file',
        'system_text_audio',
    ],
)
async def test_unsupported_screenshot_shape_is_graceful_no_task(monkeypatch, stream, shape):
    payload = screen_payload()
    parts = payload['contents'][0]['parts']
    if shape in {'audio', 'video'}:
        parts[1]['inlineData']['mimeType'] = 'audio/wav' if shape == 'audio' else 'video/mp4'
    elif shape == 'file':
        parts[1] = {'fileData': {'fileUri': 'gs://synthetic-only/screen', 'mimeType': 'image/jpeg'}}
    elif shape == 'builtin_tool':
        payload['tools'] = [{'googleSearch': {}}]
    elif shape == 'output_audio':
        payload['generationConfig']['responseModalities'] = ['AUDIO']
    elif shape == 'system_image':
        payload['systemInstruction']['parts'].append(parts[1])
    elif shape == 'invalid_parts':
        payload['contents'][0]['parts'] = 1
    elif shape in {'text_file', 'text_file_snake'}:
        parts[1] = {
            'text': 'invented',
            'fileData' if shape == 'text_file' else 'file_data': {'fileUri': 'gs://synthetic-only/screen'},
        }
    elif shape == 'text_audio':
        parts[1] = {'text': 'invented', 'inline_data': {'mime_type': 'audio/wav', 'data': 'AQID'}}
    elif shape == 'text_mixed_inline':
        parts[1].update(text='invented', inline_data={'mime_type': 'audio/wav', 'data': 'AQID'})
    elif shape == 'system_text_file':
        payload['systemInstruction']['parts'][0]['fileData'] = {'fileUri': 'gs://synthetic-only/screen'}
    elif shape == 'system_text_audio':
        payload['systemInstruction']['parts'][0]['inlineData'] = {'mimeType': 'audio/wav', 'data': 'AQID'}
    else:
        parts[1] = {'executableCode': {'code': 'synthetic'}}
    await run_proxy(monkeypatch, 'macos', 'task_extraction', stream, 'gemini-3.8-flash', 'moved', payload, refused=True)


async def run_proxy(monkeypatch, platform, tag, stream, anchor, phase, payload, refused=False):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.delenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', raising=False)
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(vr.STATE_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, 'us')
    monkeypatch.setattr(proxy, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(bridge, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(proxy, 'llm_stub_enabled', lambda: False)
    states = (
        {'gemini-2.5-flash': vr.State.INACTIVE, 'gemini-3.8-flash': vr.State.ACTIVE}
        if phase == 'moved'
        else ({'gemini-2.5-flash': vr.State.ACTIVE} if phase == 'active' else {})
    )
    monkeypatch.setattr(proxy, '_refresh_reservations', AsyncMock(return_value=states))
    monkeypatch.setattr(proxy, '_meter_server_request', AsyncMock(side_effect=lambda uid, path, model, action: path))
    seen = []

    answer = json.dumps({'screen_kind': 'other', 'context_summary': '', 'current_activity': '', 'tasks': []})

    def native(request):
        seen.append(request)
        if '/publishers/google/models/' in request.url.path:
            assert phase != 'moved'
            assert '/models/gemini-2.5-flash:' in request.url.path
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            body = {
                'candidates': [{'content': {'parts': [{'text': answer}]}, 'finishReason': 'STOP'}],
                'trafficType': 'PROVISIONED_THROUGHPUT',
                'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 2},
            }
            return (
                httpx.Response(200, content=f'data: {json.dumps(body)}\n\n'.encode())
                if stream
                else httpx.Response(200, json=body)
            )
        body_out = json.loads(request.content)
        assert phase == 'moved' and not refused
        assert body_out['model'] == 'gpt-6-luna'
        assert body_out['response_format']['json_schema']['schema'] == payload['generationConfig']['responseSchema']
        images = [
            p
            for m in body_out['messages']
            for p in (m.get('content') or [])
            if isinstance(p, dict) and p.get('type') == 'image_url'
        ]
        assert images == [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,AQID'}}]
        if stream:
            chunk = {'choices': [{'delta': {'content': answer}, 'finish_reason': 'stop'}]}
            return httpx.Response(200, content=f'data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n'.encode())
        return httpx.Response(
            200,
            json={
                'id': 'invented-response',
                'object': 'chat.completion',
                'model': 'gpt-6-luna',
                'choices': [{'message': {'role': 'assistant', 'content': answer}, 'finish_reason': 'stop'}],
            },
        )

    bff = FastAPI()

    @bff.post('/proxy/{action}')
    async def endpoint(action: str, request: Request):
        return await proxy._proxy(request, f'models/{anchor}:{action}', stream, 'synthetic-owner')

    async with httpx.AsyncClient(transport=httpx.MockTransport(native)) as native_client:
        vertex = VertexGeminiProvider(
            http_client=native_client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value=states))
        monkeypatch.setattr(vertex._reservations, 'record', AsyncMock())
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=native_client)}
        )
        gateway_app.dependency_overrides[dependencies.get_provider_registry] = lambda: registry
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gateway_app), base_url='http://synthetic-gateway'
            ) as gateway_client:
                monkeypatch.setattr(bridge, 'get_llm_gateway_client', lambda: gateway_client)
                monkeypatch.setattr(bridge, 'get_llm_gateway_base_url', lambda: 'http://synthetic-gateway')
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=bff), base_url='http://synthetic-bff'
                ) as client:
                    response = await client.post(
                        '/proxy/' + ('streamGenerateContent' if stream else 'generateContent'),
                        headers={
                            'x-omi-lane': tag,
                            'x-app-platform': platform,
                            'x-omi-client-platform': platform,
                            'user-agent': (
                                'Omi/12435 CFNetwork/1.0 Darwin/1.0' if platform == 'macos' else 'Omi-Windows/1.0'
                            ),
                        },
                        json=payload,
                    )
            assert response.status_code == 200
            if refused:
                raw = response.text.removeprefix('data: ').strip()
                parts_out = json.loads(raw)['candidates'][0]['content']['parts']
                assert parts_out[0]['functionCall']['name'] == 'no_task_found'
                text = ''.join(p.get('text', '') for p in parts_out)
                assert json.loads(text) == {
                    'screen_kind': 'other',
                    'context_summary': '',
                    'current_activity': '',
                    'tasks': [],
                }
                assert not seen
                proxy._meter_server_request.assert_not_awaited()
            else:
                assert 'tasks' in response.text
                assert len(seen) == 1
                if phase == 'moved':
                    assert all(request.url.path == '/v1/chat/completions' for request in seen)
        finally:
            gateway_app.dependency_overrides.clear()
