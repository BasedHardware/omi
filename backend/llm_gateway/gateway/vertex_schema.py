"""Normalize JSON Schema for Vertex v1 responseJsonSchema.

Generation constraints are a subset; callers must validate the returned JSON
against their original schema (including Pydantic validators).
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass

# https://cloud.google.com/java/docs/reference/google-cloud-vertexai/latest/com.google.cloud.vertexai.api.GenerationConfig
# Unlike responseSchema, this field understands $defs/$ref and type: null.
_VALUE_KEYS = frozenset(
    {
        '$id',
        '$anchor',
        'type',
        'format',
        'title',
        'description',
        'enum',
        'minItems',
        'maxItems',
        'minimum',
        'maximum',
        'required',
        'propertyOrdering',
    }
)
_SCHEMA_MAP_KEYS = frozenset({'properties', '$defs', 'definitions'})
_SCHEMA_LIST_KEYS = frozenset({'anyOf', 'oneOf', 'prefixItems'})
_UNSUPPORTED_COMBINATORS = frozenset({'allOf', 'not', 'if', 'then', 'else'})


def vertex_response_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve reusable definitions and strip unsupported generation constraints.

    Walk schema positions only: property/definition names and enum values are
    data, even when named 'default', '$ref', or 'const'. $ref siblings are inlined
    because Vertex forbids non-$ siblings on a referenced sub-schema. Ordinary
    references remain compact, avoiding Plan's repeated ReviewItem expansion.
    """

    def resolve(ref: str) -> Mapping[str, Any]:
        if not ref.startswith('#/'):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        target: Any = schema
        for part in ref[2:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            if not isinstance(target, Mapping) or key not in target:
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            target = target[key]
        if not isinstance(target, Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        return target

    def convert(node: Mapping[str, Any], visiting: frozenset[str] = frozenset()) -> dict[str, Any]:
        if _UNSUPPORTED_COMBINATORS.intersection(node):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        ref = node.get('$ref')
        if ref is not None:
            if not isinstance(ref, str):
                raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
            definition = resolve(ref)
            siblings = {
                key: value
                for key, value in node.items()
                if not key.startswith('$')
                and key
                in (_VALUE_KEYS | _SCHEMA_MAP_KEYS | _SCHEMA_LIST_KEYS | {'items', 'additionalProperties', 'const'})
            }
            if siblings:
                if ref in visiting:
                    raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
                return convert(
                    {**definition, **{key: value for key, value in node.items() if key != '$ref'}}, visiting | {ref}
                )
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key == '$ref':
                result[key] = value.replace('#/definitions/', '#/$defs/', 1)
            elif key in _VALUE_KEYS:
                result[key] = deepcopy(value)
            elif key in _SCHEMA_MAP_KEYS:
                if not isinstance(value, Mapping) or not all(
                    isinstance(name, str) and isinstance(child, Mapping) for name, child in value.items()
                ):
                    raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
                result['$defs' if key == 'definitions' else key] = {
                    name: convert(child, visiting) for name, child in value.items()
                }
            elif key in _SCHEMA_LIST_KEYS:
                if not isinstance(value, list) or not all(isinstance(child, Mapping) for child in value):
                    raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
                result[key] = [convert(child, visiting) for child in value]
            elif key in {'items', 'additionalProperties'}:
                if isinstance(value, Mapping):
                    result[key] = convert(value, visiting)
                elif key == 'additionalProperties' and isinstance(value, bool):
                    result[key] = value
                else:
                    raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        if 'const' in node:
            # Literal values become supported singleton enums; no user value is logged.
            literal = node['const']
            if isinstance(literal, (str, int, float)) and not isinstance(literal, bool):
                result['enum'] = [deepcopy(literal)]
            elif literal is None:
                result['type'] = 'null'
        return result

    return convert(schema)
