"""Rejection metadata never echoes provider text, schema names or request bodies."""

import asyncio
import json

import pytest

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.vertex_diagnostics import (
    request_id_context,
    vertex_attempt_labels,
    vertex_attempt_scope,
    vertex_error_metadata,
)


@pytest.mark.parametrize('preview', [b'private-user-content', b'{', b'[]', b'null', b'{"error": []}'])
def test_malformed_vertex_errors_are_unknown(preview):
    assert vertex_error_metadata(preview) == {'vertex_status': 'unknown', 'vertex_field': 'unknown'}


def test_only_allowlisted_status_and_api_prefixes_leave_error_boundary():
    metadata = vertex_error_metadata(
        json.dumps(
            {
                'error': {
                    'status': 'private-user-content',
                    'message': 'private-user-content',
                    'details': [
                        {
                            '@type': 'type.googleapis.com/google.rpc.BadRequest',
                            'fieldViolations': [
                                {
                                    'field': 'generationConfig.responseJsonSchema.properties.private-user-content',
                                    'description': 'private',
                                },
                                {'field': 'generation_config.thinking_config.thinking_budget'},
                                {'field': 'generationConfig.maxOutputTokens'},
                                {'field': 'contents[0].parts[0].text'},
                                {'field': 'private-user-content'},
                                {'field': 'toolsPrivate'},
                                {'field': ['private']},
                            ],
                        }
                    ],
                }
            }
        ).encode()
    )
    assert metadata == {
        'vertex_status': 'unknown',
        'vertex_field': 'contents,generationConfig.maxOutputTokens,generationConfig.responseJsonSchema,generationConfig.thinkingConfig',
    }


@pytest.mark.parametrize('details', [None, {}, ['private'], [{'fieldViolations': []}]])
def test_unknown_error_details_do_not_escape(details):
    assert vertex_error_metadata(
        json.dumps({'error': {'status': 'INVALID_ARGUMENT', 'details': details}}).encode()
    ) == {
        'vertex_status': 'INVALID_ARGUMENT',
        'vertex_field': 'unknown',
    }


@pytest.mark.asyncio
async def test_attempt_context_isolated_between_requests_and_reset_after_error():
    config = load_gateway_config()
    route = config.route_artifacts[config.lanes['omi:auto:dream-reasoning'].active_route]

    async def observe(request_id):
        token = request_id_context.set(request_id)
        try:
            with vertex_attempt_scope(route, route.primary):
                await asyncio.sleep(0)
                labels = vertex_attempt_labels()
                assert labels['request_id'] == request_id
                assert labels['lane'] == route.lane_id
                with pytest.raises(RuntimeError):
                    with vertex_attempt_scope(route, route.fallbacks[0]):
                        assert vertex_attempt_labels()['lane'] == 'unknown'
                        raise RuntimeError('synthetic')
                assert vertex_attempt_labels() == labels
            assert vertex_attempt_labels()['lane'] == 'unknown'
        finally:
            request_id_context.reset(token)

    await asyncio.gather(observe('request-a'), observe('request-b'))
    assert vertex_attempt_labels() == {
        'request_id': 'unknown',
        'lane': 'unknown',
        'route': 'unknown',
        'provider': 'gemini',
    }
