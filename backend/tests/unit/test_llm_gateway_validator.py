from __future__ import annotations

import pytest

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.validator import validate_chat_completion_request

LANE_ID = 'omi:auto:chat-structured'


def test_accepts_non_streaming_text_messages_with_json_schema_output():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    validated = validate_chat_completion_request(valid_request(), lane)

    assert validated.model == LANE_ID
    assert len(validated.messages) == 2
    assert validated.response_format['type'] == 'json_schema'


def test_accepts_prompt_parser_style_request_without_response_format():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request()
    request.pop('response_format')

    validated = validate_chat_completion_request(request, lane)

    assert validated.model == LANE_ID
    assert len(validated.messages) == 2
    assert validated.response_format is None


def test_forwards_prompt_cache_key():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(prompt_cache_key='omi-extract-actions')

    validated = validate_chat_completion_request(request, lane)

    assert validated.forwarded_params['prompt_cache_key'] == 'omi-extract-actions'


@pytest.mark.parametrize(
    'lane_id',
    ['omi:auto:memory-conflict-flex', 'omi:auto:memory-l2-flex', 'omi:auto:x-memory-extraction-flex'],
)
def test_forwards_flex_only_for_scheduled_background_lanes(lane_id):
    lane = load_gateway_config(prod_mode=True).lanes[lane_id]
    request = valid_request(service_tier='flex')
    request.pop('response_format')

    validated = validate_chat_completion_request(request, lane)

    assert validated.forwarded_params['service_tier'] == 'flex'


def test_rejects_flex_for_other_lanes():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    with pytest.raises(GatewayCapabilityMismatchError, match='scheduled background memory work'):
        validate_chat_completion_request(valid_request(service_tier='flex'), lane)


def test_rejects_unbounded_service_tier_values():
    lane = load_gateway_config(prod_mode=True).lanes['omi:auto:memory-conflict-flex']
    request = valid_request(service_tier='auto')
    request.pop('response_format')

    with pytest.raises(GatewayInvalidRequestError, match='service_tier'):
        validate_chat_completion_request(request, lane)


def test_forwards_explicit_gpt56_cache_contract_on_a_text_content_block():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        prompt_cache_key='omi-extract-actions-v1-b0',
        prompt_cache_options={'mode': 'explicit', 'ttl': '30m'},
        messages=[
            {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Stable instructions.',
                        'prompt_cache_breakpoint': {'mode': 'explicit'},
                    }
                ],
            },
            {'role': 'user', 'content': 'Dynamic content.'},
        ],
    )

    validated = validate_chat_completion_request(request, lane)

    assert validated.messages == tuple(request['messages'])
    assert validated.forwarded_params['prompt_cache_options'] == {
        'mode': 'explicit',
        'ttl': '30m',
    }


@pytest.mark.parametrize(
    'prompt_cache_options',
    [
        None,
        {},
        {'mode': 'implicit', 'ttl': '30m'},
        {'mode': 'explicit'},
        {'mode': 'explicit', 'ttl': '24h'},
    ],
)
def test_rejects_invalid_gpt56_cache_options(prompt_cache_options):
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    with pytest.raises(GatewayInvalidRequestError, match='prompt_cache_options'):
        validate_chat_completion_request(valid_request(prompt_cache_options=prompt_cache_options), lane)


def test_rejects_invalid_cache_breakpoint_shape():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        messages=[
            {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Stable instructions.',
                        'prompt_cache_breakpoint': {'mode': 'implicit'},
                    }
                ],
            }
        ]
    )

    with pytest.raises(GatewayInvalidRequestError, match='prompt_cache_breakpoint'):
        validate_chat_completion_request(request, lane)


def test_accepts_matching_output_limit_aliases():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    validated = validate_chat_completion_request(valid_request(max_tokens=128, max_completion_tokens=128), lane)

    assert validated.forwarded_params['max_tokens'] == 128
    assert validated.forwarded_params['max_completion_tokens'] == 128


def test_rejects_conflicting_output_limit_aliases():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    with pytest.raises(GatewayInvalidRequestError, match='must match'):
        validate_chat_completion_request(valid_request(max_tokens=64, max_completion_tokens=128), lane)


@pytest.mark.parametrize('key', ['max_tokens', 'max_completion_tokens'])
def test_rejects_invalid_output_limits(key):
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    with pytest.raises(GatewayInvalidRequestError, match='positive integer'):
        validate_chat_completion_request(valid_request(**{key: 0}), lane)


@pytest.mark.parametrize('effort', ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'])
def test_forwards_known_reasoning_effort_values(effort):
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    validated = validate_chat_completion_request(valid_request(reasoning_effort=effort), lane)

    assert validated.forwarded_params['reasoning_effort'] == effort


@pytest.mark.parametrize('effort', ['instant', '', 3, None])
def test_rejects_unknown_reasoning_effort_values(effort):
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    with pytest.raises(GatewayInvalidRequestError, match='reasoning_effort'):
        validate_chat_completion_request(valid_request(reasoning_effort=effort), lane)


def test_rejects_streaming():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(stream=True)

    with pytest.raises(GatewayCapabilityMismatchError, match='streaming'):
        validate_chat_completion_request(request, lane)


def test_rejects_tools():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(tools=[{'type': 'function'}])

    with pytest.raises(GatewayCapabilityMismatchError, match='tools'):
        validate_chat_completion_request(request, lane)


def test_rejects_missing_messages():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request()
    request.pop('messages')

    with pytest.raises(GatewayInvalidRequestError, match='messages'):
        validate_chat_completion_request(request, lane)


def test_rejects_invalid_messages():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(messages=[])

    with pytest.raises(GatewayInvalidRequestError, match='messages'):
        validate_chat_completion_request(request, lane)


def test_accepts_image_url_message_content():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        messages=[
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'describe'},
                    {
                        'type': 'image_url',
                        'image_url': {'url': 'https://example.com/image.png'},
                    },
                ],
            }
        ]
    )

    validated = validate_chat_completion_request(request, lane)

    assert validated.messages[0]['content'][1]['type'] == 'image_url'


def test_accepts_assistant_tool_call_history_without_content():
    lane = load_gateway_config(prod_mode=True).lanes['omi:auto:chat-agent']
    request = {
        'model': 'omi:auto:chat-agent',
        'messages': [
            {
                'role': 'assistant',
                'tool_calls': [
                    {
                        'id': 'call_1',
                        'type': 'function',
                        'function': {'name': 'weather', 'arguments': '{"city":"NYC"}'},
                    }
                ],
            },
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'sunny'},
            {'role': 'assistant', 'content': None},
        ],
        'tools': [
            {
                'type': 'function',
                'function': {'name': 'weather', 'parameters': {'type': 'object'}},
            }
        ],
    }

    validated = validate_chat_completion_request(request, lane)

    assert validated.messages[0]['content'] == ''
    assert validated.messages[0]['tool_calls'][0]['id'] == 'call_1'
    assert validated.messages[1]['content'] == 'sunny'
    assert validated.messages[2]['content'] == ''


@pytest.mark.parametrize('role', ['developer', 'system', 'tool', 'user'])
def test_rejects_null_content_outside_assistant_tool_history(role):
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(messages=[{'role': role, 'content': None}])

    with pytest.raises(GatewayInvalidRequestError, match='message content is required'):
        validate_chat_completion_request(request, lane)


def test_rejects_unsupported_message_content_parts():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        messages=[
            {
                'role': 'user',
                'content': [{'type': 'input_audio', 'input_audio': {'data': 'abc'}}],
            }
        ]
    )

    with pytest.raises(GatewayCapabilityMismatchError, match='text, image_url, or file message content'):
        validate_chat_completion_request(request, lane)


def test_json_object_is_accepted_and_unknown_modes_rejected():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]

    # json_object maps Gemini's responseMimeType=application/json without a
    # schema (desktop BFF translation) and is valid on structured lanes.
    validated = validate_chat_completion_request(valid_request(response_format={'type': 'json_object'}), lane)
    assert validated.response_format == {'type': 'json_object'}

    request = valid_request(response_format={'type': 'text'})
    with pytest.raises(GatewayCapabilityMismatchError, match='json_schema'):
        validate_chat_completion_request(request, lane)


def test_rejects_missing_json_schema_body():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(response_format={'type': 'json_schema'})

    with pytest.raises(GatewayInvalidRequestError, match='response_format.json_schema'):
        validate_chat_completion_request(request, lane)


def test_rejects_missing_json_schema_name():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        response_format={
            'type': 'json_schema',
            'json_schema': {
                'strict': True,
                'schema': {'type': 'object', 'properties': {'x': {'type': 'string'}}},
            },
        }
    )

    with pytest.raises(GatewayInvalidRequestError, match='response_format.json_schema.name'):
        validate_chat_completion_request(request, lane)


def valid_request(**overrides):
    request = {
        'model': LANE_ID,
        'messages': [
            {'role': 'system', 'content': 'Return structured JSON.'},
            {'role': 'user', 'content': 'Extract the memory.'},
        ],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'memory_extraction',
                'strict': True,
                'schema': {
                    'type': 'object',
                    'properties': {'memory': {'type': 'string'}},
                    'required': ['memory'],
                    'additionalProperties': False,
                },
            },
        },
    }
    request.update(overrides)
    return request
