"""Swift image/tool request -> desktop BFF -> served Vertex model contract."""

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
from llm_gateway.gateway.vertex_wire import (
    _vertex_request,
    _vertex_to_openai_response,
    _vertex_to_openai_stream_chunk,
)
from utils.llm import desktop_gemini_gateway as dgg
from utils.llm import vertex_pt_routing as ptr


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


def _response(signature='synthetic-signature'):
    return {
        'candidates': [
            {
                'content': {
                    'role': 'model',
                    'parts': [
                        {
                            'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 1'}},
                            'thoughtSignature': signature,
                        }
                    ],
                },
                'finishReason': 'STOP',
            }
        ]
    }


def _chat(payload, stream=False):
    body = json.loads(dgg._sanitize(json.dumps(payload).encode(), 'generateContent', max_output_tokens=2048))
    return dgg.gemini_body_to_openai_chat(body, lane_id=ptr.desktop_text_lane_id('gemini-2.5-pro'), stream=stream)


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('legacy_client', [False, True])
def test_signed_tool_history_survives_both_hops_and_old_client_history_is_admitted(streaming, legacy_client):
    payload = _swift_request()
    # Gemini 2.5 Pro is only the requested model; the real attempt serves 3.1.
    served = ptr.desktop_serving_model('gemini-2.5-pro')
    assert served == 'gemini-3.1-flash-lite'
    initial = ptr.model_payload(_vertex_request(_chat(payload)), served)
    assert initial['generationConfig']['thinkingConfig'] == {'thinkingBudget': 1024}
    assert initial['generationConfig']['maxOutputTokens'] == 2048
    assert initial['toolConfig']['functionCallingConfig']['mode'] == 'ANY'
    if streaming:
        chunk, _ = _vertex_to_openai_stream_chunk(_response(), requested_model=served)
        event = dgg.openai_sse_payload_to_gemini_event(json.loads(chunk.decode().removeprefix('data: ')), {})
    else:
        event = dgg.openai_completion_to_gemini(_vertex_to_openai_response(_response(), requested_model=served))
    part = event['candidates'][0]['content']['parts'][0]
    assert part['thoughtSignature'] == 'synthetic-signature'
    if legacy_client:
        part.pop('thoughtSignature')
    payload['contents'].extend(
        [
            {'role': 'model', 'parts': [part]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'execute_sql', 'response': {'result': '1'}}}]},
        ]
    )
    payload.pop('tool_config')
    original = copy.deepcopy(payload)
    translated = _vertex_request(_chat(payload, streaming))
    attempt = ptr.model_payload(translated, served)
    replayed = attempt['contents'][1]['parts'][0]
    assert replayed['functionCall'] == part['functionCall']
    assert replayed['thoughtSignature'] == (
        'skip_thought_signature_validator' if legacy_client else 'synthetic-signature'
    )
    assert payload == original
    if legacy_client:
        assert 'thoughtSignature' not in translated['contents'][1]['parts'][0]
        assert 'thoughtSignature' not in ptr.model_payload(translated, 'gemini-2.5-flash')['contents'][1]['parts'][0]


def test_parallel_calls_keep_the_signature_on_its_original_part():
    response = _response()
    response['candidates'][0]['content']['parts'].append(
        {'functionCall': {'name': 'execute_sql', 'args': {'query': 'SELECT 2'}}}
    )
    native = response['candidates'][0]['content']
    payload = {'contents': [native]}
    adapted = ptr.model_payload(payload, 'gemini-3.1-flash-lite')
    assert adapted['contents'] == payload['contents']
    assert 'thoughtSignature' not in adapted['contents'][0]['parts'][1]
    completion = _vertex_to_openai_response(response, requested_model='gemini-3.1-flash-lite')
    gemini = dgg.openai_completion_to_gemini(completion)
    assert gemini['candidates'][0]['content']['parts'] == native['parts']


def test_signature_only_stream_delta_survives_until_terminal_chunk():
    pending = {}
    dgg.openai_sse_payload_to_gemini_event(
        {
            'choices': [
                {
                    'delta': {
                        'tool_calls': [
                            {
                                'index': 0,
                                'function': {'name': 'execute_sql', 'arguments': '{}'},
                            }
                        ]
                    }
                }
            ]
        },
        pending,
    )
    dgg.openai_sse_payload_to_gemini_event(
        {
            'choices': [
                {
                    'delta': {
                        'tool_calls': [
                            {
                                'index': 0,
                                'extra_content': {'google': {'thought_signature': 'synthetic-signature'}},
                            }
                        ]
                    }
                }
            ]
        },
        pending,
    )
    event = dgg.openai_sse_payload_to_gemini_event({'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]}, pending)
    assert event['candidates'][0]['content']['parts'][0]['thoughtSignature'] == 'synthetic-signature'
    assert pending == {}


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
    envelope = SimpleNamespace(response_headers=Mock(return_value={}), stream_error_event=Mock(return_value=b'error'))
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
