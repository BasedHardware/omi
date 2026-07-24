from __future__ import annotations

import pytest

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.errors import GatewayCapabilityMismatchError, GatewayInvalidRequestError
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
    assert validated.forwarded_params['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}


@pytest.mark.parametrize(
    'prompt_cache_options',
    [None, {}, {'mode': 'implicit', 'ttl': '30m'}, {'mode': 'explicit'}, {'mode': 'explicit', 'ttl': '24h'}],
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


def test_rejects_non_text_message_content():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(
        messages=[
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://example.com/image.png'}}]}
        ]
    )

    with pytest.raises(GatewayCapabilityMismatchError, match='text message content'):
        validate_chat_completion_request(request, lane)


def test_rejects_structured_output_modes_other_than_json_schema():
    lane = load_gateway_config(prod_mode=True).lanes[LANE_ID]
    request = valid_request(response_format={'type': 'json_object'})

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
