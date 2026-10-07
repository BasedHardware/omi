"""Desktop Gemini wire compatibility across the Luna and explicit BYOK paths."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from routers import desktop_proxy
from utils.llm import desktop_gemini_gateway as dgg
from utils.llm import vertex_pt_routing as ptr
from utils.llm.model_config import LUNA_MODEL


def _swift_request():
    # GeminiImageToolRequest.CodingKeys and InsightAssistant's execute_sql loop.
    # Synthetic strings only; the real client encodes these snake/camel keys.
    return {
        'contents': [{'role': 'user', 'parts': [{'text': 'Synthetic lookup'}]}],
        'system_instruction': {'parts': [{'text': 'Synthetic assistant'}]},
        'generation_config': {'thinking_config': {'thinking_budget': 1024}},
        'tool_config': {'function_calling_config': {'mode': 'ANY'}},
        'tools': [
            {
                'function_declarations': [
                    {
                        'name': 'execute_sql',
                        'parameters': {
                            'type': 'OBJECT',
                            'properties': {'query': {'type': 'STRING'}},
                            'required': ['query'],
                        },
                    }
                ]
            }
        ],
    }


def _chat(payload, stream=False):
    body = json.loads(dgg._sanitize(json.dumps(payload).encode(), 'generateContent', max_output_tokens=2048))
    return dgg.gemini_body_to_openai_chat(body, lane_id=ptr.desktop_text_lane_id('gemini-2.5-pro'), stream=stream)


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('legacy_client', [False, True])
def test_paid_luna_translates_signed_and_legacy_tool_history_without_signatures(streaming, legacy_client):
    payload = _swift_request()
    tool_call = {'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 1'}}}
    if not legacy_client:
        tool_call['thoughtSignature'] = 'synthetic-signature'
    payload['contents'].extend(
        [
            {'role': 'model', 'parts': [tool_call]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'execute_sql', 'response': {'result': '1'}}}]},
        ]
    )
    original = copy.deepcopy(payload)
    sanitized = json.loads(dgg._sanitize(json.dumps(payload).encode(), 'generateContent', max_output_tokens=2048))
    request = dgg.gemini_body_to_openai_chat(
        sanitized,
        lane_id='omi:auto:desktop-luna',
        stream=streaming,
    )
    assistant = next(message for message in request['messages'] if message.get('tool_calls'))
    tool_result = next(message for message in request['messages'] if message['role'] == 'tool')
    call = assistant['tool_calls'][0]
    assert request['model'] == 'omi:auto:desktop-luna'
    assert request['stream'] is streaming
    assert call['function'] == {'name': 'execute_sql', 'arguments': '{"query": "SELECT 1"}'}
    assert tool_result['tool_call_id'] == call['id']
    assert tool_result['content'] == '{"result": "1"}'
    assert 'thoughtSignature' not in json.dumps(request)
    assert 'thought_signature' not in json.dumps(request)
    assert payload == original
    response = dgg.openai_completion_to_gemini(
        {
            'choices': [
                {
                    'finish_reason': 'tool_calls',
                    'message': {
                        'tool_calls': [
                            {
                                'function': {'name': 'execute_sql', 'arguments': '{"query": "SELECT 1"}'},
                            }
                        ]
                    },
                }
            ]
        },
        requested_model='gemini-2.5-pro',
    )
    response_part = response['candidates'][0]['content']['parts'][0]
    assert response_part['functionCall'] == tool_call['functionCall']
    assert 'thoughtSignature' not in response_part


def test_paid_luna_parallel_tool_calls_preserve_calls_and_drop_signatures():
    parts = [
        {
            'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 1'}},
            'thoughtSignature': 'synthetic-signature',
        },
        {'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 2'}}},
    ]
    payload = {'contents': [{'role': 'model', 'parts': parts}]}
    original = copy.deepcopy(payload)
    request = dgg.gemini_body_to_openai_chat(payload, lane_id='omi:auto:desktop-luna', stream=False)
    calls = request['messages'][0]['tool_calls']
    assert [call['function']['name'] for call in calls] == ['execute_sql', 'execute_sql']
    assert [json.loads(call['function']['arguments']) for call in calls] == [
        {'query': 'SELECT 1'},
        {'query': 'SELECT 2'},
    ]
    assert 'thoughtSignature' not in json.dumps(request)
    assert payload == original

    gemini = dgg.openai_completion_to_gemini(
        {
            'choices': [
                {
                    'finish_reason': 'tool_calls',
                    'message': {
                        'tool_calls': [
                            {'function': {'name': 'execute_sql', 'arguments': '{"query": "SELECT 1"}'}},
                            {'function': {'name': 'execute_sql', 'arguments': '{"query": "SELECT 2"}'}},
                        ]
                    },
                }
            ]
        }
    )
    returned_parts = gemini['candidates'][0]['content']['parts']
    assert [part['functionCall']['args'] for part in returned_parts] == [{'query': 'SELECT 1'}, {'query': 'SELECT 2'}]
    assert all('thoughtSignature' not in part for part in returned_parts)


def test_paid_luna_stream_tool_delta_has_no_gemini_signature():
    pending = {}
    event = dgg.openai_sse_payload_to_gemini_event(
        {
            'choices': [
                {
                    'delta': {
                        'tool_calls': [
                            {
                                'index': 0,
                                'function': {'name': 'execute_sql', 'arguments': '{"query":"SELECT 1"}'},
                            }
                        ]
                    },
                    'finish_reason': 'tool_calls',
                }
            ]
        },
        pending,
    )
    assert event is not None
    part = event['candidates'][0]['content']['parts'][0]
    assert part['functionCall'] == {'name': 'execute_sql', 'args': {'query': 'SELECT 1'}}
    assert 'thoughtSignature' not in part
    assert pending == {}


@pytest.mark.asyncio
async def test_explicit_gemini_byok_keeps_native_signature_and_ai_studio_route(monkeypatch):
    key = 'synthetic-user-key'
    monkeypatch.setattr(dgg, 'get_byok_key', lambda provider: key if provider == 'gemini' else None)
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda provider: key if provider == 'gemini' else None)
    payload = {
        'contents': [
            {
                'role': 'model',
                'parts': [
                    {
                        'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 1'}},
                        'thoughtSignature': 'synthetic-native-signature',
                    }
                ],
            }
        ]
    }

    assert dgg.company_paid_via_gateway('gemini-2.5-pro', 'generateContent') is False
    assert dgg.company_paid_via_gateway(LUNA_MODEL, 'generateContent') is True
    sanitized = json.loads(dgg._sanitize(json.dumps(payload).encode(), 'generateContent', max_output_tokens=8192))
    assert sanitized['contents'][0]['parts'][0]['thoughtSignature'] == 'synthetic-native-signature'

    route = await desktop_proxy._upstream(
        'models/gemini-2.5-pro:generateContent',
        'gemini-2.5-pro',
        'generateContent',
        {},
    )
    assert route.provider == 'ai_studio_byok'
    assert route.credential_source == 'byok'
    assert route.url.endswith('/v1beta/models/gemini-2.5-pro:generateContent')
    assert route.params == {'key': key}


@pytest.mark.asyncio
async def test_vertex_400_logs_only_bounded_reason_and_dispatches_once(monkeypatch, capsys):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    sent = []

    def handle(request):
        sent.append(request)
        return httpx.Response(
            400,
            json={
                'error': {
                    'status': 'INVALID_ARGUMENT',
                    'message': 'Function call is missing a thought_signature. private-tool-name private-user-content',
                }
            },
        )

    async def token():
        return 'synthetic-token'

    async def refresh(*args):
        return {}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        monkeypatch.setattr(provider, '_refresh_reservations', refresh)
        with pytest.raises(ProviderFailure) as error:
            await provider.create_chat_completion(
                _chat(_swift_request()),
                provider_ref=ProviderRef(provider='vertex', model='gemini-2.5-pro'),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=1000,
            )
    assert error.value.failure_class == FailureClass.PROVIDER_INVALID_REQUEST
    assert len(sent) == 1
    assert 'gemini-3.1-flash-lite:generateContent' in str(sent[0].url)
    logged = capsys.readouterr().out
    assert json.loads(logged) == {
        'severity': 'WARNING',
        'event': 'vertex_provider_rejection',
        'served_model': 'gemini-3.1-flash-lite',
        'status': 400,
        'reason': 'missing_thought_signature',
    }
    assert 'private-tool-name' not in logged
    assert 'private-user-content' not in logged


def test_proxy_rejected_gateway_request_is_nonretryable():
    telemetry = SimpleNamespace(complete=Mock())
    envelope = SimpleNamespace(error_response=Mock(), provider_unavailable_retry_after=30)
    dgg._gateway_error_response(
        dgg.DesktopGeminiGatewayError(status_code=400, code='provider_rejected', message='synthetic'),
        telemetry,
        envelope,
    )
    assert telemetry.complete.call_args.kwargs['retryable'] is False
    assert envelope.error_response.call_args.kwargs['status_code'] == 400
    assert envelope.error_response.call_args.kwargs['retryable'] is False


@pytest.mark.asyncio
async def test_streamed_provider_400_stays_nonretryable(monkeypatch):
    async def rejected(*args, **kwargs):
        assert kwargs['request_id'] == 'c168e257-0ec6-4451-8aa9-b00bc0e322d9'
        assert kwargs['product_lane'] == 'insight'
        assert kwargs['client_platform'] == 'macos'
        raise dgg.DesktopGeminiGatewayError(status_code=400, code='provider_rejected', message='synthetic')
        yield b''  # async-generator transport seam

    monkeypatch.setattr(dgg, 'gateway_desktop_chat_stream', rejected)
    telemetry = SimpleNamespace(
        complete=Mock(), request_id='c168e257-0ec6-4451-8aa9-b00bc0e322d9', lane='insight', client_platform='macos'
    )
    envelope = SimpleNamespace(
        response_headers=Mock(return_value={}),
        stream_error_event=Mock(return_value=b'error'),
        stream_observation_factory=lambda: SimpleNamespace(observe=Mock(), has_error=False, has_terminal=False),
    )
    response = await dgg.proxy_company_paid_via_gateway(
        None,
        b'{}',
        model='gemini-2.5-pro',
        action='streamGenerateContent',
        streaming=True,
        uid='synthetic',
        telemetry=telemetry,
        envelope=envelope,
    )
    assert [chunk async for chunk in response.body_iterator] == [b'error']
    assert telemetry.complete.call_args.kwargs['status_code'] == 400
    assert telemetry.complete.call_args.kwargs['upstream_status'] == 400
    assert telemetry.complete.call_args.kwargs['retryable'] is False
