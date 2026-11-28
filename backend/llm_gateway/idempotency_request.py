"""Canonical fingerprint input shared by the gateway and replay fixture."""

from collections.abc import Iterator, Mapping
from enum import Enum
import json
import re
from typing import Any


class CredentialSource(str, Enum):
    OMI_MANAGED = 'omi_managed'
    SERVICE_FORWARDED_BYOK = 'service_forwarded_byok'
    INTERNAL_KEY_REFERENCE = 'internal_key_reference'


_BYOK_PROVIDER_NAME_RE = re.compile(r'^[a-z][a-z0-9_-]*$')


def parse_forwarded_byok_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Parse service-forwarded BYOK keys from internal gateway envelope headers."""
    envelope_prefix = 'x-omi-byok-'
    envelope_suffix = '-key'
    forwarded: dict[str, str] = {}
    for header_name, raw_value in headers.items():
        normalized_name = header_name.strip().casefold()
        if not normalized_name.startswith(envelope_prefix) or not normalized_name.endswith(envelope_suffix):
            continue
        provider = normalized_name.removeprefix(envelope_prefix).removesuffix(envelope_suffix).strip().lower()
        if not provider or not _BYOK_PROVIDER_NAME_RE.fullmatch(provider):
            continue
        stripped = raw_value.strip()
        if stripped:
            forwarded[provider] = stripped
    return forwarded


def _property_orders(schema: object, path: tuple[str | int, ...]) -> Iterator[tuple[tuple[str | int, ...], list[str]]]:
    if not isinstance(schema, dict):
        return
    properties = schema.get('properties')
    if isinstance(properties, dict):
        yield path, list(properties)

    # Follow schema-valued keywords only. Objects in examples, enum values
    # and defaults are ordinary JSON values, even if they contain "properties".
    for keyword in ('properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas', 'dependencies'):
        children = schema.get(keyword)
        if isinstance(children, dict):
            for name in sorted(children):
                yield from _property_orders(children[name], (*path, keyword, name))
    for keyword in ('allOf', 'anyOf', 'oneOf', 'prefixItems', 'items'):
        children = schema.get(keyword)
        if isinstance(children, list):
            for position, child in enumerate(children):
                yield from _property_orders(child, (*path, keyword, position))
    for keyword in (
        'additionalItems',
        'additionalProperties',
        'contains',
        'contentSchema',
        'else',
        'if',
        'items',
        'not',
        'propertyNames',
        'then',
        'unevaluatedItems',
        'unevaluatedProperties',
    ):
        yield from _property_orders(schema.get(keyword), (*path, keyword))


def _structured_property_orders(body: dict[str, Any]) -> Iterator[tuple[tuple[str | int, ...], list[str]]]:
    response_format = body.get('response_format')
    if isinstance(response_format, dict) and response_format.get('type') == 'json_schema':
        definition = response_format.get('json_schema')
        if isinstance(definition, dict):
            yield from _property_orders(definition.get('schema'), ('response_format', 'json_schema', 'schema'))
    tools = body.get('tools')
    if isinstance(tools, list):
        for position, tool in enumerate(tools):
            function = tool.get('function') if isinstance(tool, dict) else None
            if isinstance(function, dict):
                yield from _property_orders(function.get('parameters'), ('tools', position, 'function', 'parameters'))


def canonical_request(body: dict[str, Any], credential_source: str, forwarded_keys: dict[str, str]) -> bytes:
    canonical: list[object] = [body, credential_source, forwarded_keys]
    property_orders = list(_structured_property_orders(body))
    if property_orders:
        canonical.append(property_orders)
    return json.dumps(canonical, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
