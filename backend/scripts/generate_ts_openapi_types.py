#!/usr/bin/env python3
"""Generate TypeScript types from an OpenAPI schema.

This is intentionally small and repo-owned. It emits DTO/operation types used by
first-party clients without adding package-manager coupling across every app.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePath
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
DEFAULT_OUTPUTS = [
    ROOT_DIR / 'desktop' / 'windows' / 'src' / 'renderer' / 'src' / 'lib' / 'omiApi.generated.ts',
    ROOT_DIR / 'web' / 'app' / 'src' / 'lib' / 'omiApi.generated.ts',
    ROOT_DIR / 'web' / 'admin' / 'lib' / 'services' / 'omi-api' / 'omiApi.generated.ts',
    ROOT_DIR / 'web' / 'personas-open-source' / 'src' / 'lib' / 'omiApi.generated.ts',
]


IDENTIFIER_RE = re.compile(r'[^A-Za-z0-9_$]')


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def source_label_for_path(spec_path: PurePath, root_dir: PurePath = ROOT_DIR) -> str:
    """Return a stable slash-separated label for generated-file headers."""
    try:
        return spec_path.relative_to(root_dir).as_posix()
    except ValueError:
        return spec_path.as_posix()


def ts_identifier(name: str) -> str:
    candidate = IDENTIFIER_RE.sub('_', name)
    if not candidate or not re.match(r'[A-Za-z_$]', candidate[0]):
        candidate = f'_{candidate}'
    return candidate


def string_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def ref_name(ref: str) -> str:
    prefix = '#/components/schemas/'
    if not ref.startswith(prefix):
        return 'unknown'
    return ts_identifier(ref[len(prefix) :])


def schema_nullable(schema: dict[str, Any]) -> bool:
    if schema.get('nullable') is True:
        return True
    schema_type = schema.get('type')
    return isinstance(schema_type, list) and 'null' in schema_type


def without_nullable_type(schema: dict[str, Any]) -> dict[str, Any]:
    schema_type = schema.get('type')
    if not isinstance(schema_type, list):
        return schema
    non_null = [item for item in schema_type if item != 'null']
    next_schema = dict(schema)
    if len(non_null) == 1:
        next_schema['type'] = non_null[0]
    elif non_null:
        next_schema['type'] = non_null
    else:
        next_schema.pop('type', None)
    return next_schema


def schema_to_ts(schema: Any) -> str:
    if not isinstance(schema, dict):
        return 'unknown'

    nullable = schema_nullable(schema)
    schema = without_nullable_type(schema)

    if '$ref' in schema:
        result = ref_name(str(schema['$ref']))
    elif 'const' in schema:
        result = string_literal(schema['const'])
    elif 'enum' in schema and isinstance(schema['enum'], list):
        values = ['null' if item is None else string_literal(str(item)) for item in schema['enum']]
        result = ' | '.join(values) if values else 'never'
    elif 'allOf' in schema and isinstance(schema['allOf'], list):
        parts = [schema_to_ts(item) for item in schema['allOf']]
        result = ' & '.join(parts) if parts else 'unknown'
    elif 'oneOf' in schema and isinstance(schema['oneOf'], list):
        parts = [schema_to_ts(item) for item in schema['oneOf']]
        result = ' | '.join(parts) if parts else 'unknown'
    elif 'anyOf' in schema and isinstance(schema['anyOf'], list):
        parts = [schema_to_ts(item) for item in schema['anyOf']]
        result = ' | '.join(parts) if parts else 'unknown'
    else:
        schema_type = schema.get('type')
        if schema_type == 'string':
            result = 'string'
        elif schema_type in {'integer', 'number'}:
            result = 'number'
        elif schema_type == 'boolean':
            result = 'boolean'
        elif schema_type == 'null':
            result = 'null'
        elif schema_type == 'array':
            item_type = schema_to_ts(schema.get('items', {}))
            result = f'Array<{item_type}>'
        elif schema_type == 'object' or 'properties' in schema or 'additionalProperties' in schema:
            result = object_schema_to_ts(schema)
        else:
            result = 'unknown'

    if nullable and 'null' not in {part.strip() for part in result.split('|')}:
        result = f'{result} | null'
    return result


def is_plain_object_type_literal(ts_type: str) -> bool:
    """Return True when ts_type is a single `{ ... }` object literal.

    Top-level unions/intersections (e.g. oneOf/anyOf results, or `{...} | null`)
    cannot be expressed as `interface` and must use `type`.
    """
    if not ts_type.startswith('{'):
        return False
    depth = 0
    for index, char in enumerate(ts_type):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return index == len(ts_type) - 1
    return False


def object_schema_to_ts(schema: dict[str, Any]) -> str:
    properties = schema.get('properties')
    additional = schema.get('additionalProperties')

    if not isinstance(properties, dict):
        if isinstance(additional, dict):
            return f'Record<string, {schema_to_ts(additional)}>'
        if additional is True:
            return 'Record<string, unknown>'
        return 'Record<string, unknown>'

    required = set(schema.get('required') or [])
    lines = ['{']
    for prop_name in sorted(properties):
        prop_schema = properties[prop_name]
        optional = '' if prop_name in required else '?'
        key = prop_name if re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*$', prop_name) else string_literal(prop_name)
        lines.append(f'  {key}{optional}: {schema_to_ts(prop_schema)};')

    if isinstance(additional, dict):
        lines.append(f'  [key: string]: {schema_to_ts(additional)};')
    elif additional is True:
        lines.append('  [key: string]: unknown;')

    lines.append('}')
    return '\n'.join(lines)


def response_schema_to_ts(response: dict[str, Any]) -> str:
    content = response.get('content')
    if not isinstance(content, dict):
        return 'void'
    json_content = content.get('application/json') or content.get('application/octet-stream')
    if not isinstance(json_content, dict):
        return 'unknown'
    return schema_to_ts(json_content.get('schema', {}))


SKIP_CONTENT_PREFIXES = (
    'application/octet-stream',
    'text/event-stream',
    'text/plain',
    'text/html',
    'application/xml',
    'audio/',
    'image/',
    'multipart/form-data',
)


def _operation_return_type(operation: dict[str, Any]) -> str | None:
    """Return the TS return type for an operation's success response, or None to skip."""
    responses = operation.get('responses', {})
    if not isinstance(responses, dict):
        return 'void'
    for status in ('200', '201', 'default'):
        resp = responses.get(status)
        if not isinstance(resp, dict):
            continue
        content = resp.get('content', {})
        if not isinstance(content, dict) or not content:
            return 'void'  # 204-style no content
        json_content = content.get('application/json')
        if isinstance(json_content, dict):
            return schema_to_ts(json_content.get('schema', {}))
        # Non-JSON success response → skip this operation
        for ct in content:
            if any(ct.startswith(p) or ct == p for p in SKIP_CONTENT_PREFIXES):
                return None
    # 204 with no 200/201
    if '204' in responses:
        return 'void'
    return 'void'


def generate_client_methods(spec: dict[str, Any]) -> str:
    """Emit typed-fetch client methods for each JSON operation in the spec."""
    paths = spec.get('paths', {})
    if not isinstance(paths, dict):
        return ''

    lines: list[str] = [
        '// --- Client methods (typed fetch wrappers). GENERATED - DO NOT EDIT. ---',
        '',
        'export interface OmiApiClientInit {',
        '  baseURL?: string;',
        '  token?: string;',
        '  headers?: Record<string, string>;',
        '}',
        '',
        'export class OmiApiError extends Error {',
        '  constructor(public status: number, public response: Response) {',
        "    super(`Omi API error: HTTP ${status}`);",
        '    this.name = "OmiApiError";',
        '  }',
        '}',
        '',
    ]

    method_count = 0
    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            continue
        for http_method in ('get', 'post', 'put', 'patch', 'delete'):
            operation = path_item.get(http_method)
            if not isinstance(operation, dict):
                continue
            op_id = operation.get('operationId')
            if not isinstance(op_id, str):
                continue

            return_type = _operation_return_type(operation)
            if return_type is None:
                continue  # non-JSON response — skip

            fn_name = ts_identifier(op_id)

            # Parse parameters
            raw_params = operation.get('parameters', [])
            path_params: list[tuple[str, str]] = []
            query_params: list[tuple[str, str, bool]] = []
            header_params: list[tuple[str, str, bool]] = []
            if isinstance(raw_params, list):
                for p in raw_params:
                    if not isinstance(p, dict):
                        continue
                    location = p.get('in')
                    pname = p.get('name', '')
                    required = p.get('required', False)
                    ts_type = schema_to_ts(p.get('schema', {}))
                    if location == 'path':
                        path_params.append((pname, ts_type))
                    elif location == 'query':
                        query_params.append((pname, ts_type, required))
                    elif location == 'header':
                        header_params.append((pname, ts_type, required))

            # Parse requestBody
            body_type: str | None = None
            req_body = operation.get('requestBody', {})
            if isinstance(req_body, dict):
                content = req_body.get('content', {})
                if isinstance(content, dict):
                    json_content = content.get('application/json')
                    if isinstance(json_content, dict):
                        body_type = schema_to_ts(json_content.get('schema', {}))

            # Build function signature
            sig_parts: list[str] = []
            if path_params:
                fields = ', '.join(f'{ts_identifier(n)}: {t}' for n, t in path_params)
                sig_parts.append(f'path: {{ {fields} }}')
            if query_params:
                fields = ', '.join(f'{ts_identifier(n)}{"?" if not r else ""}: {t}' for n, t, r in query_params)
                sig_parts.append(f'query: {{ {fields} }}')
            if header_params:
                fields = ', '.join(f'{ts_identifier(n)}{"?" if not r else ""}: {t}' for n, t, r in header_params)
                sig_parts.append(f'header: {{ {fields} }}')
            if body_type:
                sig_parts.append(f'body: {body_type}')
            sig_parts.append('init?: OmiApiClientInit')
            sig = ', '.join(sig_parts)

            # Build URL path expression with interpolation
            url_path = path
            for pname, _ in path_params:
                url_path = url_path.replace(f'{{{pname}}}', f'${{path.{ts_identifier(pname)}}}')

            # Build function body
            body_lines = [
                f'export async function {fn_name}({sig}): Promise<{return_type}> {{',
                '  const _base = init?.baseURL ?? "";',
                f'  const _path = `{url_path}`;',
            ]
            if query_params:
                body_lines.append('  const _params = query ? Object.entries(query)')
                body_lines.append("    .filter(([, v]) => v !== undefined && v !== null)")
                body_lines.append("    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&') : '';")
                body_lines.append('  const _search = _params ? `?${_params}` : "";')
            else:
                body_lines.append('  const _search = "";')
            body_lines.append('  const _res = await fetch(`${_base}${_path}${_search}`, {')
            body_lines.append(f'    method: {string_literal(http_method.upper())},')
            body_lines.append('    headers: {')
            if body_type:
                body_lines.append("      ...(body ? { 'Content-Type': 'application/json' } : {}),")
            body_lines.append("      ...(init?.token ? { Authorization: `Bearer ${init.token}` } : {}),")
            body_lines.append('      ...init?.headers,')
            for pname, _ptype, required in header_params:
                prop = ts_identifier(pname)
                if required:
                    body_lines.append(f"      {string_literal(pname)}: String(header.{prop}),")
                else:
                    body_lines.append(
                        f"      ...(header.{prop} !== undefined ? {{ {string_literal(pname)}: String(header.{prop}) }} : {{}}),"
                    )
            body_lines.append('    },')
            if body_type:
                body_lines.append('    body: body ? JSON.stringify(body) : undefined,')
            body_lines.append('  });')
            body_lines.append('  if (!_res.ok) throw new OmiApiError(_res.status, _res);')
            if return_type == 'void':
                body_lines.append('  return;')
            else:
                body_lines.append('  return _res.status === 204 ? (undefined as any) : await _res.json();')
            body_lines.append('}')
            body_lines.append('')

            lines.extend(body_lines)
            method_count += 1

    lines.append(f'// Total: {method_count} client methods generated.')
    return '\n'.join(lines)


def generate(spec: dict[str, Any], source_label: str) -> str:
    schemas = spec.get('components', {}).get('schemas', {})
    if not isinstance(schemas, dict):
        raise ValueError('OpenAPI spec has no components.schemas object')

    lines: list[str] = [
        '// GENERATED CODE - DO NOT EDIT.',
        '/* eslint-disable prettier/prettier, @typescript-eslint/no-explicit-any */',
        f'// Generated by backend/scripts/generate_ts_openapi_types.py from {source_label}.',
        '',
        'export type JsonPrimitive = string | number | boolean | null;',
        'export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };',
        '',
    ]

    for schema_name in sorted(schemas):
        ts_name = ts_identifier(schema_name)
        ts_type = schema_to_ts(schemas[schema_name])
        # Interfaces can only declare a single object shape. Unions/intersections
        # (oneOf/anyOf/allOf, nullable object wrappers) must be `export type`.
        if is_plain_object_type_literal(ts_type):
            lines.append(f'export interface {ts_name} {ts_type}')
        else:
            lines.append(f'export type {ts_name} = {ts_type};')
        lines.append('')

    lines.append('export interface OmiApiSchemas {')
    for schema_name in sorted(schemas):
        lines.append(f'  {string_literal(schema_name)}: {ts_identifier(schema_name)};')
    lines.append('}')
    lines.append('')

    paths = spec.get('paths', {})
    if isinstance(paths, dict):
        lines.append('export interface OmiApiPaths {')
        for path in sorted(paths):
            path_item = paths[path]
            if not isinstance(path_item, dict):
                continue
            lines.append(f'  {string_literal(path)}: {{')
            for method in ['get', 'post', 'put', 'patch', 'delete']:
                operation = path_item.get(method)
                if not isinstance(operation, dict):
                    continue
                operation_id = operation.get('operationId')
                lines.append(f'    {method}: {{')
                if isinstance(operation_id, str):
                    lines.append(f'      operationId: {string_literal(operation_id)};')
                lines.append('      responses: {')
                responses = operation.get('responses', {})
                if isinstance(responses, dict):
                    for status in sorted(responses):
                        response = responses[status]
                        if isinstance(response, dict):
                            lines.append(f'        {string_literal(status)}: {response_schema_to_ts(response)};')
                lines.append('      };')
                lines.append('    };')
            lines.append('  };')
        lines.append('}')
        lines.append('')
    client_code = generate_client_methods(spec)
    if client_code:
        lines.append(client_code.rstrip())
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=DEFAULT_SPEC_PATH)
    parser.add_argument('--output', action='append', type=Path, default=[])
    parser.add_argument('--check', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = args.spec if args.spec.is_absolute() else (Path.cwd() / args.spec)
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    rendered = generate(spec, source_label_for_path(spec_path))

    outputs = args.output or DEFAULT_OUTPUTS
    stale: list[Path] = []
    for output in outputs:
        path = output if output.is_absolute() else (Path.cwd() / output)
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != rendered:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding='utf-8', newline='\n')
            print(f'wrote {source_label_for_path(path)}')

    if stale:
        for path in stale:
            label = source_label_for_path(path)
            print(f'{label} is stale; run backend/scripts/generate_ts_openapi_types.py', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
