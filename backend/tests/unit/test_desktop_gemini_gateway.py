"""Desktop BFF Gemini↔OpenAI translation on the gateway hop.

The Mac app keeps its Gemini wire format; ``utils/llm/desktop_gemini_gateway``
translates at the BFF and the gateway's Vertex adapter translates back. These
tests pin the translation contract, including the function-calling loop the
image tool uses.
"""

from __future__ import annotations

import json

from utils.llm import desktop_gemini_gateway as dgg
from utils.llm.vertex_pt_routing import DESKTOP_TEXT_LANES


def _mac_style_payload() -> dict:
    return {
        'contents': [
            {'parts': [{'text': 'What is on screen?'}]},
        ],
        'systemInstruction': {'parts': [{'text': 'You are a screen assistant.'}]},
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': {'type': 'OBJECT', 'properties': {'answer': {'type': 'STRING'}}},
            'thinkingConfig': {'thinkingBudget': 1024},
            'maxOutputTokens': 2048,
            'temperature': 0.2,
        },
    }


def test_gemini_request_translates_to_gateway_chat_shape():
    request = dgg.gemini_body_to_openai_chat(
        _mac_style_payload(), lane_id=DESKTOP_TEXT_LANES['gemini-2.5-flash'], stream=False
    )

    assert request['model'] == 'omi:auto:desktop-vertex-flash'
    assert request['stream'] is False
    assert request['messages'][0] == {'role': 'system', 'content': 'You are a screen assistant.'}
    assert request['messages'][1]['role'] == 'user'
    assert request['messages'][1]['content'] == [{'type': 'text', 'text': 'What is on screen?'}]
    assert request['max_completion_tokens'] == 2048
    assert request['temperature'] == 0.2
    assert request['google'] == {'thinking_config': {'thinking_budget': 1024}}
    assert request['response_format']['type'] == 'json_schema'
    assert request['response_format']['json_schema']['schema'] == {
        'type': 'OBJECT',
        'properties': {'answer': {'type': 'STRING'}},
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
    request = dgg.gemini_body_to_openai_chat(payload, lane_id='omi:auto:desktop-vertex-flash', stream=False)

    parts = request['messages'][0]['content']
    assert parts[1] == {'type': 'image_url', 'image_url': {'url': 'data:image/webp;base64,AAA'}}


def test_gemini_tool_loop_round_trips_function_calls():
    payload = {
        'contents': [
            {'role': 'user', 'parts': [{'text': 'take a photo of the park'}]},
            {
                'role': 'model',
                'parts': [{'functionCall': {'name': 'take_photo', 'args': {'q': 'the park'}}}],
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
    request = dgg.gemini_body_to_openai_chat(payload, lane_id='omi:auto:desktop-vertex-flash', stream=False)

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
    assert json.loads(assistant['tool_calls'][0]['function']['arguments']) == {'q': 'the park'}
    tool_result = request['messages'][2]
    assert tool_result['role'] == 'tool'
    assert json.loads(tool_result['content']) == {'status': 'ok'}
    # The tool result must reuse the assistant tool_call id, not mint a new one
    # after the ordinal has already advanced.
    assert tool_result['name'] == 'take_photo'
    assert tool_result['tool_call_id'] == assistant['tool_calls'][0]['id']

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
                            }
                        ],
                    },
                }
            ],
            'model': 'omi:auto:desktop-vertex-flash',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        }
    )
    candidate = gemini['candidates'][0]
    assert candidate['finishReason'] == 'STOP'
    assert candidate['content']['parts'] == [{'functionCall': {'name': 'take_photo', 'args': {'q': 'the park'}}}]
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
    text_event = dgg.openai_sse_payload_to_gemini_event({'choices': [{'delta': {'content': 'hello'}}]}, pending)
    assert text_event == {'candidates': [{'content': {'parts': [{'text': 'hello'}]}}]}

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


def test_lane_selection_covers_every_desktop_text_model():
    assert dgg.desktop_gateway_text_lane('gemini-2.5-flash') == 'omi:auto:desktop-vertex-flash'
    assert dgg.desktop_gateway_text_lane('gemini-2.5-pro') == 'omi:auto:desktop-vertex-pro'
    assert dgg.desktop_gateway_text_lane('gemini-3.1-flash-lite') == 'omi:auto:desktop-vertex-target'
    assert dgg.desktop_gateway_text_lane('gemini-2.5-flash-lite') == 'omi:auto:desktop-vertex-flash-lite'
    assert dgg.desktop_gateway_text_lane('gemini-embedding-001') is None
    assert dgg.desktop_gateway_actions() == {'generateContent', 'streamGenerateContent', 'embedContent'}
