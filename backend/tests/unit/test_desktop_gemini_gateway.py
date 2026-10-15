"""Desktop BFF Gemini↔OpenAI translation on the gateway hop.

The Mac app keeps its Gemini wire format; ``utils/llm/desktop_gemini_gateway``
translates at the BFF and the gateway's Vertex adapter translates back. These
tests pin the translation contract, including the function-calling loop the
image tool uses.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.gateway.schemas import ProviderRef
from utils.llm import desktop_gemini_gateway as dgg


def _mac_style_payload() -> dict:
    return {
        'contents': [
            {'parts': [{'text': 'What is on screen?'}]},
        ],
        'systemInstruction': {'parts': [{'text': 'You are a screen assistant.'}]},
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': {
                'type': 'OBJECT',
                'properties': {
                    'answer': {'type': 'STRING'},
                    'optional_note': {'type': 'STRING', 'nullable': True},
                },
            },
            'thinkingConfig': {'thinkingBudget': 1024},
            'maxOutputTokens': 2048,
            'temperature': 0.2,
            'topP': 0.4,
            'stopSequences': ['STOP'],
        },
    }


def test_gemini_request_translates_to_gateway_chat_shape():
    request = dgg.gemini_body_to_openai_chat(_mac_style_payload(), lane_id='omi:auto:desktop-luna', stream=False)

    assert request['model'] == 'omi:auto:desktop-luna'
    assert request['stream'] is False
    assert request['messages'][0] == {'role': 'system', 'content': 'You are a screen assistant.'}
    assert request['messages'][1]['role'] == 'user'
    assert request['messages'][1]['content'] == [{'type': 'text', 'text': 'What is on screen?'}]
    assert request['max_completion_tokens'] == 2048
    assert request['temperature'] == 0.2
    assert request['top_p'] == 0.4
    assert request['stop'] == ['STOP']
    assert request['google'] == {'thinking_config': {'thinking_budget': 1024}}
    assert request['response_format']['type'] == 'json_schema'
    assert request['response_format']['json_schema']['schema'] == {
        'type': 'object',
        'properties': {
            'answer': {'type': 'string'},
            'optional_note': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
        },
    }


def test_schema_normalization_preserves_user_defined_property_names_and_defaults():
    schema = dgg._normalize_gemini_schema(
        {
            'type': 'OBJECT',
            'properties': {
                'nullable': {'type': 'STRING'},
                'type': {'type': 'BOOLEAN'},
                'default': {'type': 'STRING', 'default': {'type': 'STRING'}},
            },
        }
    )

    assert schema == {
        'type': 'object',
        'properties': {
            'nullable': {'type': 'string'},
            'type': {'type': 'boolean'},
            'default': {'type': 'string', 'default': {'type': 'STRING'}},
        },
    }


def test_gemini_inline_image_becomes_data_uri_content_part():
    payload = {
        'contents': [
            {
                'role': 'user',
                'parts': [{'text': 'describe'}, {'inlineData': {'mimeType': 'image/webp', 'data': 'AAA'}}],
            },
        ]
    }
    request = dgg.gemini_body_to_openai_chat(payload, lane_id='omi:auto:desktop-luna', stream=False)

    parts = request['messages'][0]['content']
    assert parts[1] == {'type': 'image_url', 'image_url': {'url': 'data:image/webp;base64,AAA'}}


def test_gemini_tool_loop_round_trips_function_calls():
    payload = {
        'contents': [
            {'role': 'user', 'parts': [{'text': 'take a photo of the park'}]},
            {
                'role': 'model',
                'parts': [
                    {
                        'functionCall': {'name': 'take_photo', 'args': {'q': 'the park'}},
                        'thoughtSignature': 'gemini-only-signature',
                    }
                ],
            },
            {
                'role': 'user',
                'parts': [{'functionResponse': {'name': 'take_photo', 'response': {'status': 'ok'}}}],
            },
        ],
        'tools': [
            {
                'functionDeclarations': [
                    {
                        'name': 'take_photo',
                        'description': 'Take a photo',
                        'parameters': {'type': 'object', 'properties': {'q': {'type': 'string'}}},
                    }
                ]
            }
        ],
        'toolConfig': {'functionCallingConfig': {'mode': 'ANY'}},
    }
    request = dgg.gemini_body_to_openai_chat(payload, lane_id='omi:auto:desktop-luna', stream=False)

    assert request['tools'] == [
        {
            'type': 'function',
            'function': {
                'name': 'take_photo',
                'description': 'Take a photo',
                'parameters': {'type': 'object', 'properties': {'q': {'type': 'string'}}},
            },
        }
    ]
    assert request['tool_choice'] == 'required'
    assistant = request['messages'][1]
    assert assistant['role'] == 'assistant'
    assert assistant['tool_calls'][0]['function']['name'] == 'take_photo'
    assert assistant['tool_calls'][0]['extra_content']['google']['thought_signature'] == 'gemini-only-signature'
    assert json.loads(assistant['tool_calls'][0]['function']['arguments']) == {'q': 'the park'}
    tool_result = request['messages'][2]
    assert tool_result['role'] == 'tool'
    assert json.loads(tool_result['content']) == {'status': 'ok'}
    # The tool result must reuse the assistant tool_call id, not mint a new one
    # after the ordinal has already advanced.
    assert tool_result['name'] == 'take_photo'
    assert tool_result['tool_call_id'] == assistant['tool_calls'][0]['id']

    repeated = dgg.gemini_body_to_openai_chat(
        {
            'contents': [
                {
                    'role': 'model',
                    'parts': [
                        {'functionCall': {'name': 'take_photo', 'args': {'q': 'one'}}},
                        {'functionCall': {'name': 'take_photo', 'args': {'q': 'two'}}},
                    ],
                },
                {
                    'role': 'user',
                    'parts': [
                        {'functionResponse': {'name': 'take_photo', 'response': {'id': 1}}},
                        {'functionResponse': {'name': 'take_photo', 'response': {'id': 2}}},
                    ],
                },
            ]
        },
        lane_id='omi:auto:desktop-luna',
        stream=False,
    )
    repeated_calls = repeated['messages'][0]['tool_calls']
    repeated_results = repeated['messages'][1:]
    assert [result['tool_call_id'] for result in repeated_results] == [call['id'] for call in repeated_calls]

    # And the response side: an OpenAI tool_calls completion becomes a Gemini
    # functionCall candidate the Mac app can decode.
    gemini = dgg.openai_completion_to_gemini(
        {
            'choices': [
                {
                    'finish_reason': 'tool_calls',
                    'message': {
                        'content': None,
                        'tool_calls': [
                            {
                                'id': 'call_1',
                                'type': 'function',
                                'function': {'name': 'take_photo', 'arguments': '{"q": "the park"}'},
                                'extra_content': {'google': {'thought_signature': 'provider-signature'}},
                            }
                        ],
                    },
                }
            ],
            'model': 'omi:auto:desktop-luna',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        }
    )
    candidate = gemini['candidates'][0]
    assert candidate['finishReason'] == 'STOP'
    assert candidate['content']['parts'] == [
        {'functionCall': {'name': 'take_photo', 'args': {'q': 'the park'}}, 'thoughtSignature': 'provider-signature'}
    ]
    assert candidate['content']['parts'][0]['thoughtSignature'] == 'provider-signature'
    assert gemini['usageMetadata'] == {
        'promptTokenCount': 10,
        'candidatesTokenCount': 5,
        'totalTokenCount': 15,
    }


def test_openai_text_completion_translates_back_to_gemini_text():
    gemini = dgg.openai_completion_to_gemini(
        {
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"answer": "a park"}'}}],
            'model': 'omi:auto:desktop-vertex-flash',
        }
    )
    assert gemini['candidates'][0]['content']['parts'] == [{'text': '{"answer": "a park"}'}]
    assert gemini['candidates'][0]['finishReason'] == 'STOP'


def test_streaming_text_deltas_translate_to_gemini_sse_events():
    pending: dict[int, dict] = {}
    text_event = dgg.openai_sse_payload_to_gemini_event(
        {'choices': [{'delta': {'content': 'hello'}}]}, pending, requested_model='gpt-6-luna'
    )
    assert text_event == {
        'candidates': [{'content': {'parts': [{'text': 'hello'}]}}],
        'modelVersion': 'gpt-6-luna',
    }

    terminal = dgg.openai_sse_payload_to_gemini_event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}, pending)
    assert terminal['candidates'][0]['finishReason'] == 'STOP'


def test_streaming_tool_fragments_assemble_into_one_function_call():
    pending: dict[int, dict] = {}
    dgg.openai_sse_payload_to_gemini_event(
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'name': 'take_photo'}}]}}]}, pending
    )
    dgg.openai_sse_payload_to_gemini_event(
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '{"q":'}}]}}]}, pending
    )
    terminal = dgg.openai_sse_payload_to_gemini_event(
        {
            'choices': [
                {'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': ' "x"}'}}]}, 'finish_reason': None}
            ]
        },
        pending,
    )
    assert terminal is None  # no terminal chunk yet: nothing emitted for fragments
    final = dgg.openai_sse_payload_to_gemini_event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}, pending)
    assert final['candidates'][0]['content']['parts'] == [{'functionCall': {'name': 'take_photo', 'args': {'q': 'x'}}}]


class _TricklingGateway:
    """A gateway body that keeps the socket busy without ever finishing."""

    async def post(self, *args, **kwargs):
        await asyncio.sleep(30)
        raise AssertionError('gateway call ran past the wall-clock deadline')


@pytest.mark.asyncio
async def test_nonstreaming_gateway_calls_stop_at_the_wall_clock_deadline(monkeypatch):
    monkeypatch.setattr(dgg, 'DESKTOP_GATEWAY_TIMEOUT_SECONDS', 0.05)
    monkeypatch.setattr(dgg, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(dgg, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(dgg, 'llm_gateway_headers', lambda **kwargs: {})
    monkeypatch.setattr(dgg, 'get_llm_gateway_client', lambda: _TricklingGateway())
    attribution = dict(
        uid='synthetic-user',
        request_id='11111111-1111-1111-1111-111111111111',
        product_lane='focus',
        client_platform='macos',
    )

    with pytest.raises(TimeoutError):
        await dgg.gateway_desktop_chat(
            b'{"contents":[{"parts":[{"text":"hi"}]}]}',
            model='gemini-2.5-flash',
            action='generateContent',
            **attribution,
        )
    with pytest.raises(TimeoutError):
        await dgg.gateway_desktop_embed_content(
            b'{"content":{"parts":[{"text":"hi"}]}}',
            **attribution,
        )


def test_lane_selection_covers_every_desktop_text_model():
    assert dgg.desktop_gateway_text_lane('gemini-2.5-flash') == 'omi:auto:desktop-vertex-flash'
    assert dgg.desktop_gateway_text_lane('gemini-2.5-pro') == 'omi:auto:desktop-vertex-pro'
    assert dgg.desktop_gateway_text_lane('gemini-3.1-flash-lite') == 'omi:auto:desktop-vertex-target'
    assert dgg.desktop_gateway_text_lane('gemini-2.5-flash-lite') == 'omi:auto:desktop-vertex-flash-lite'
    assert dgg.desktop_gateway_text_lane('gemini-3.8-flash') == 'omi:auto:desktop-vertex-flash-38'
    assert dgg.desktop_gateway_text_lane('gpt-6-luna') == 'omi:auto:desktop-luna'
    assert dgg.desktop_gateway_text_lane('gemini-embedding-001') is None
    assert dgg.desktop_gateway_actions() == {
        'generateContent',
        'streamGenerateContent',
        'embedContent',
        'batchEmbedContents',
    }


@pytest.mark.asyncio
async def test_gateway_bff_request_uses_mandatory_luna_lane(monkeypatch):
    captured = {}

    class Result:
        status_code = 200

        @staticmethod
        def json():
            return {
                'model': 'gpt-6-luna',
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"answer":"ok"}'}}],
            }

    class Client:
        async def post(self, url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, json=json, timeout=timeout)
            return Result()

    monkeypatch.setattr(dgg, 'get_llm_gateway_client', Client)
    monkeypatch.setattr(dgg, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(dgg, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))

    result = await dgg.gateway_desktop_chat(
        json.dumps(_mac_style_payload()).encode(),
        model='gemini-3.8-flash',
        action='generateContent',
        uid='user-1',
        request_id='123e4567-e89b-12d3-a456-426614174000',
        product_lane='task_extraction',
        client_platform='macos',
    )

    assert captured['url'] == 'http://gateway.test/v1/chat/completions'
    assert captured['json']['model'] == 'omi:auto:desktop-vertex-flash-38'
    assert captured['json']['google'] == {'thinking_config': {'thinking_budget': 1024}}
    assert result.gemini_payload['modelVersion'] == 'gemini-3.8-flash'


@pytest.mark.asyncio
async def test_batch_embeddings_route_through_gateway_and_restore_mixed_task_order(monkeypatch):
    requests = []

    class Result:
        status_code = 200

        def __init__(self, vector):
            self.vector = vector

        def json(self):
            return {'data': [{'index': 0, 'embedding': self.vector}]}

    class Client:
        async def post(self, url, *, headers, json, timeout):
            requests.append((url, json, headers['X-Omi-Request-Id']))
            vector = [1.0] if json['task_type'] == 'RETRIEVAL_QUERY' else [2.0]
            return Result(vector)

    monkeypatch.setattr(dgg, 'get_llm_gateway_client', Client)
    monkeypatch.setattr(dgg, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(dgg, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    result = await dgg.gateway_desktop_batch_embed_contents(
        json.dumps(
            {
                'requests': [
                    {'content': {'parts': [{'text': 'document'}]}, 'taskType': 'RETRIEVAL_DOCUMENT'},
                    {'content': {'parts': [{'text': 'query'}]}, 'taskType': 'RETRIEVAL_QUERY'},
                ]
            }
        ).encode(),
        uid='user-1',
        request_id='123e4567-e89b-12d3-a456-426614174000',
        product_lane='embedding',
        client_platform='macos',
    )

    assert [request[0] for request in requests] == [
        'http://gateway.test/v1/embeddings',
        'http://gateway.test/v1/embeddings',
    ]
    assert len({request[2] for request in requests}) == 2
    assert requests[0][2] == '123e4567-e89b-12d3-a456-426614174000'
    assert all(str(UUID(request[2])) == request[2] for request in requests)
    assert result.embeddings == [[2.0], [1.0]]


@pytest.mark.asyncio
async def test_luna_compatible_desktop_request_reaches_openai_provider_without_gemini_options(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-key')
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                'id': 'chatcmpl_desktop_luna',
                'object': 'chat.completion',
                'model': 'gpt-6-luna',
                'choices': [
                    {
                        'index': 0,
                        'message': {'role': 'assistant', 'content': '{"answer":"ok"}'},
                        'finish_reason': 'stop',
                    }
                ],
            },
        )

    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    request = dgg.gemini_body_to_openai_chat(
        {
            **_mac_style_payload(),
            'contents': [
                {
                    'role': 'user',
                    'parts': [
                        {'text': 'summarize this screen'},
                        {'inlineData': {'mimeType': 'image/jpeg', 'data': 'AA=='}},
                    ],
                }
            ],
        },
        lane_id='omi:auto:desktop-luna',
        stream=False,
    )
    request['model'] = 'gpt-6-luna'  # the gateway resolver substitutes its selected provider model
    result = await provider.create_chat_completion(
        request,
        provider_ref=ProviderRef(provider='openai', model='gpt-6-luna'),
        credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
        timeout_ms=8000,
    )

    assert result['choices'][0]['message']['content'] == '{"answer":"ok"}'
    assert seen[0].url == 'https://api.openai.com/v1/chat/completions'
    assert seen[0].headers['authorization'] == 'Bearer unit-test-key'
    sent = json.loads(seen[0].content)
    assert sent['model'] == 'gpt-6-luna'
    assert sent['messages'][0]['content'] == 'You are a screen assistant.'
    assert sent['messages'][1]['content'][1]['image_url']['url'] == 'data:image/jpeg;base64,AA=='
    assert sent['response_format']['json_schema']['schema']['properties']['optional_note'] == {
        'anyOf': [{'type': 'string'}, {'type': 'null'}]
    }
    assert 'google' in sent
    await provider.aclose()


@pytest.mark.asyncio
async def test_mixed_metadata_embedding_batch_shares_one_wall_clock_budget(monkeypatch):
    monkeypatch.setattr(dgg, 'DESKTOP_GATEWAY_TIMEOUT_SECONDS', 0.1)

    async def slow_group(texts, **kwargs):
        await asyncio.sleep(0.06)
        return [[1.0] for _ in texts]

    monkeypatch.setattr(dgg, '_gateway_embedding_vectors', slow_group)
    body = json.dumps(
        {
            'requests': [
                {'content': {'parts': [{'text': 'query'}]}, 'taskType': 'RETRIEVAL_QUERY'},
                {'content': {'parts': [{'text': 'document'}]}, 'taskType': 'RETRIEVAL_DOCUMENT'},
            ]
        }
    ).encode()
    with pytest.raises(TimeoutError):
        await dgg.gateway_desktop_batch_embed_contents(
            body,
            uid='synthetic-user',
            request_id='11111111-1111-1111-1111-111111111111',
            product_lane='focus',
            client_platform='macos',
        )
