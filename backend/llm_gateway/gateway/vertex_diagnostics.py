"""Attempt correlation and closed-vocabulary Vertex rejection metadata.

Provider bodies and schema property names never leave this boundary.
"""

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

from llm_gateway.gateway.schemas import ProviderRef, RouteArtifact

request_id_context: ContextVar[str] = ContextVar('vertex_request_id', default='unknown')
_route_context: ContextVar[tuple[str, str]] = ContextVar('vertex_attempt_route', default=('unknown', 'unknown'))
_STATUSES = frozenset(
    {
        'INVALID_ARGUMENT',
        'FAILED_PRECONDITION',
        'OUT_OF_RANGE',
        'UNAUTHENTICATED',
        'PERMISSION_DENIED',
        'NOT_FOUND',
        'RESOURCE_EXHAUSTED',
        'DEADLINE_EXCEEDED',
        'ABORTED',
        'UNIMPLEMENTED',
        'INTERNAL',
        'UNAVAILABLE',
        'DATA_LOSS',
        'UNKNOWN',
    }
)
_FIELDS = {
    'generation_config.response_json_schema': 'generationConfig.responseJsonSchema',
    'generation_config.response_schema': 'generationConfig.responseSchema',
    'generation_config.response_mime_type': 'generationConfig.responseMimeType',
    'generation_config.max_output_tokens': 'generationConfig.maxOutputTokens',
    'generation_config.thinking_config': 'generationConfig.thinkingConfig',
    'generation_config.temperature': 'generationConfig.temperature',
    'generation_config.top_p': 'generationConfig.topP',
    'generation_config.stop_sequences': 'generationConfig.stopSequences',
    'system_instruction': 'systemInstruction',
    'contents': 'contents',
    'tools': 'tools',
    'tool_config': 'toolConfig',
}


@contextmanager
def vertex_attempt_scope(route: RouteArtifact, provider: ProviderRef) -> Iterator[None]:
    # Route IDs come from validated configuration, never messages or a body field.
    token = _route_context.set(
        (route.lane_id, route.route_artifact_id) if provider.provider == 'gemini' else ('unknown', 'unknown')
    )
    try:
        yield
    finally:
        _route_context.reset(token)


def vertex_attempt_labels() -> dict[str, str]:
    lane, route = _route_context.get()
    return {'request_id': request_id_context.get(), 'lane': lane, 'route': route, 'provider': 'gemini'}


def vertex_error_metadata(preview: bytes) -> dict[str, str]:
    """Return only exact Google RPC statuses and fixed API field prefixes.

    Paths stop before schema properties, definitions, indexes or tool names.
    Unknown or truncated responses remain unknown rather than echoing text.
    """
    result = {'vertex_status': 'unknown', 'vertex_field': 'unknown'}
    try:
        parsed = json.loads(preview)
    except (ValueError, UnicodeDecodeError):
        return result
    error = parsed.get('error') if isinstance(parsed, Mapping) else None
    if not isinstance(error, Mapping):
        return result
    status = error.get('status')
    if isinstance(status, str) and status in _STATUSES:
        result['vertex_status'] = status
    details = error.get('details')
    fields = set()
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, Mapping) or detail.get('@type') != 'type.googleapis.com/google.rpc.BadRequest':
            continue
        violations = detail.get('fieldViolations')
        for violation in violations if isinstance(violations, list) else []:
            field = violation.get('field') if isinstance(violation, Mapping) else None
            if not isinstance(field, str):
                continue
            for snake, camel in _FIELDS.items():
                for prefix in (snake, camel):
                    if field == prefix or field.startswith((prefix + '.', prefix + '[')):
                        fields.add(camel)
    if fields:
        result['vertex_field'] = ','.join(sorted(fields))
    return result
