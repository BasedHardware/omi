#!/usr/bin/env python3
"""Generate Omi Integration API SDKs from integration-public OpenAPI.

Repo-owned codegen (same spirit as generate_ts_openapi_types.py). Emits thin
HTTP clients for TypeScript, Go, Python, Rust, and C++ so the public Integration
API has one source of truth: docs/api-reference/integration-public-openapi.json.

Usage:
  python backend/scripts/generate_integration_sdks.py
  python backend/scripts/generate_integration_sdks.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = ROOT_DIR / 'docs' / 'api-reference' / 'integration-public-openapi.json'
SDK_ROOT = ROOT_DIR / 'sdks' / 'integration'
DEFAULT_BASE_URL = 'https://api.omi.me'

HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head'}

# Stable, ergonomic method names. Keys are OpenAPI operationIds.
METHOD_NAMES: dict[str, str] = {
    'send_app_notification_to_user_v1_integrations_notification_post': 'send_notification_v1',
    'get_conversations_via_integration_v2_integrations__app_id__conversations_get': 'list_conversations',
    'get_memories_via_integration_v2_integrations__app_id__memories_get': 'list_memories',
    'send_notification_via_integration_v2_integrations__app_id__notification_post': 'send_notification',
    'search_conversations_via_integration_v2_integrations__app_id__search_conversations_post': 'search_conversations',
    'get_tasks_via_integration_v2_integrations__app_id__tasks_get': 'list_tasks',
    'create_conversation_via_integration_v2_integrations__app_id__user_conversations_post': 'create_conversation',
    'create_memories_via_integration_v2_integrations__app_id__user_memories_post': 'create_memories',
}


class GeneratorError(RuntimeError):
    pass


def load_spec(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise GeneratorError(f'missing OpenAPI spec: {path}') from exc
    except json.JSONDecodeError as exc:
        raise GeneratorError(f'invalid OpenAPI JSON at {path}: {exc}') from exc


def ref_name(ref: str | None) -> str | None:
    if not ref or not isinstance(ref, str):
        return None
    prefix = '#/components/schemas/'
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return None


def schema_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return 'any'
    if '$ref' in schema:
        return ref_name(schema['$ref']) or 'any'
    if 'anyOf' in schema:
        non_null = [s for s in schema['anyOf'] if not (isinstance(s, dict) and s.get('type') == 'null')]
        if len(non_null) == 1 and isinstance(non_null[0], dict):
            return schema_type(non_null[0])
        return 'any'
    t = schema.get('type')
    if isinstance(t, list):
        non_null = [x for x in t if x != 'null']
        t = non_null[0] if non_null else 'any'
    if t == 'array':
        items = schema.get('items') or {}
        return f'array<{schema_type(items) if isinstance(items, dict) else "any"}>'
    if t in {'string', 'integer', 'number', 'boolean', 'object'}:
        return t
    if schema.get('enum'):
        return 'string'
    return 'any'


def operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, methods in (spec.get('paths') or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            op_id = op.get('operationId') or f'{method}_{path}'
            name = METHOD_NAMES.get(op_id)
            if not name:
                # Fallback: last meaningful path segment + method
                slug = re.sub(r'[{}]', '', path.strip('/').split('/')[-1])
                name = f'{method.lower()}_{slug}'
            params: list[dict[str, Any]] = []
            for pr in op.get('parameters') or []:
                if not isinstance(pr, dict):
                    continue
                if pr.get('in') == 'header' and str(pr.get('name', '')).lower() == 'authorization':
                    continue
                schema = pr.get('schema') if isinstance(pr.get('schema'), dict) else {}
                params.append(
                    {
                        'name': pr.get('name'),
                        'in': pr.get('in'),
                        'required': bool(pr.get('required')),
                        'type': schema_type(schema),
                        'default': schema.get('default') if isinstance(schema, dict) else None,
                    }
                )
            body_ref = None
            body_type = None
            rb = op.get('requestBody')
            if isinstance(rb, dict):
                content = (rb.get('content') or {}).get('application/json') or {}
                schema = content.get('schema') if isinstance(content, dict) else None
                if isinstance(schema, dict):
                    body_ref = ref_name(schema.get('$ref'))
                    body_type = schema_type(schema)
            success_ref = None
            for code in ('200', '201'):
                resp = (op.get('responses') or {}).get(code)
                if not isinstance(resp, dict):
                    continue
                if '$ref' in resp:
                    # response component; treat as any JSON
                    success_ref = None
                    break
                content = (resp.get('content') or {}).get('application/json') or {}
                schema = content.get('schema') if isinstance(content, dict) else None
                if isinstance(schema, dict):
                    success_ref = ref_name(schema.get('$ref')) or None
                    break
            out.append(
                {
                    'name': name,
                    'op_id': op_id,
                    'method': method.upper(),
                    'path': path,
                    'summary': op.get('summary') or '',
                    'params': params,
                    'body_ref': body_ref,
                    'body_type': body_type,
                    'success_ref': success_ref,
                    'has_app_id_path': '{app_id}' in path,
                }
            )
    out.sort(key=lambda item: (item['path'], item['method']))
    return out


def spec_fingerprint(spec_path: Path) -> str:
    digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()[:16]
    return digest


def collect_schemas(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = (spec.get('components') or {}).get('schemas') or {}
    return {name: schema for name, schema in raw.items() if isinstance(schema, dict)}


def _schema_props(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    props = schema.get('properties') or {}
    required = list(schema.get('required') or [])
    return props if isinstance(props, dict) else {}, required


def _unwrap_nullable(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if schema.get('nullable') is True:
        return schema, True
    any_of = schema.get('anyOf')
    if isinstance(any_of, list):
        non_null = [s for s in any_of if not (isinstance(s, dict) and s.get('type') == 'null')]
        has_null = len(non_null) != len(any_of)
        if len(non_null) == 1 and isinstance(non_null[0], dict):
            return non_null[0], has_null
    t = schema.get('type')
    if isinstance(t, list) and 'null' in t:
        non_null = [x for x in t if x != 'null']
        next_schema = dict(schema)
        if len(non_null) == 1:
            next_schema['type'] = non_null[0]
        elif non_null:
            next_schema['type'] = non_null
        else:
            next_schema.pop('type', None)
        return next_schema, True
    return schema, False


def ts_type_expr(schema: dict[str, Any] | None, schemas: dict[str, dict[str, Any]]) -> str:
    if not schema:
        return 'unknown'
    if '$ref' in schema:
        name = ref_name(schema['$ref'])
        return name or 'unknown'
    schema, optional = _unwrap_nullable(schema)
    if '$ref' in schema:
        name = ref_name(schema['$ref']) or 'unknown'
        return f'{name} | null' if optional else name
    t = schema.get('type')
    if isinstance(t, list):
        t = next((x for x in t if x != 'null'), 'unknown')
    enum = schema.get('enum')
    if enum and all(isinstance(x, str) for x in enum):
        expr = ' | '.join(json.dumps(x) for x in enum)
        return f'({expr}) | null' if optional else expr
    if t == 'string':
        base = 'string'
    elif t == 'integer' or t == 'number':
        base = 'number'
    elif t == 'boolean':
        base = 'boolean'
    elif t == 'array':
        items = schema.get('items') if isinstance(schema.get('items'), dict) else {}
        base = f'Array<{ts_type_expr(items, schemas)}>'
    elif t == 'object' or schema.get('properties') or schema.get('additionalProperties') is not None:
        if schema.get('additionalProperties') and not schema.get('properties'):
            base = 'Record<string, unknown>'
        else:
            # inline object rare; use Record
            base = 'Record<string, unknown>'
    else:
        base = 'unknown'
    return f'{base} | null' if optional else base


def py_type_expr(schema: dict[str, Any] | None, schemas: dict[str, dict[str, Any]]) -> str:
    if not schema:
        return 'Any'
    if '$ref' in schema:
        name = ref_name(schema['$ref'])
        return name or 'Any'
    schema, optional = _unwrap_nullable(schema)
    if '$ref' in schema:
        name = ref_name(schema['$ref']) or 'Any'
        return f'{name} | None' if optional else name
    t = schema.get('type')
    if isinstance(t, list):
        t = next((x for x in t if x != 'null'), None)
    if schema.get('enum') and all(isinstance(x, str) for x in schema['enum']):
        # use Literal
        lits = ', '.join(repr(x) for x in schema['enum'])
        base = f'Literal[{lits}]'
    elif t == 'string':
        base = 'str'
    elif t == 'integer':
        base = 'int'
    elif t == 'number':
        base = 'float'
    elif t == 'boolean':
        base = 'bool'
    elif t == 'array':
        items = schema.get('items') if isinstance(schema.get('items'), dict) else {}
        base = f'list[{py_type_expr(items, schemas)}]'
    elif t == 'object' or schema.get('additionalProperties') is not None or schema.get('properties'):
        base = 'dict[str, Any]'
    else:
        base = 'Any'
    return f'{base} | None' if optional else base


def go_type_expr(schema: dict[str, Any] | None, schemas: dict[str, dict[str, Any]], for_field: bool = True) -> str:
    if not schema:
        return 'any'
    if '$ref' in schema:
        name = ref_name(schema['$ref'])
        return name or 'any'
    schema, optional = _unwrap_nullable(schema)
    if '$ref' in schema:
        name = ref_name(schema['$ref']) or 'any'
        return f'*{name}' if optional and for_field else name
    t = schema.get('type')
    if isinstance(t, list):
        t = next((x for x in t if x != 'null'), None)
    if t == 'string':
        base = 'string'
    elif t == 'integer':
        base = 'int'
    elif t == 'number':
        base = 'float64'
    elif t == 'boolean':
        base = 'bool'
    elif t == 'array':
        items = schema.get('items') if isinstance(schema.get('items'), dict) else {}
        base = f'[]{go_type_expr(items, schemas, for_field=False)}'
    elif t == 'object' or schema.get('additionalProperties') is not None or schema.get('properties'):
        base = 'map[string]any'
    else:
        base = 'any'
    if optional and for_field and base not in {'map[string]any'} and not base.startswith('[]'):
        return f'*{base}'
    return base


def dart_type_expr(schema: dict[str, Any] | None, schemas: dict[str, dict[str, Any]]) -> str:
    if not schema:
        return 'Object?'
    if '$ref' in schema:
        name = ref_name(schema['$ref'])
        return name or 'Object?'
    schema, optional = _unwrap_nullable(schema)
    if '$ref' in schema:
        name = ref_name(schema['$ref']) or 'Object'
        return f'{name}?' if optional else name
    t = schema.get('type')
    if isinstance(t, list):
        t = next((x for x in t if x != 'null'), None)
    if t == 'string':
        base = 'String'
    elif t == 'integer':
        base = 'int'
    elif t == 'number':
        base = 'double'
    elif t == 'boolean':
        base = 'bool'
    elif t == 'array':
        items = schema.get('items') if isinstance(schema.get('items'), dict) else {}
        item_t = dart_type_expr(items, schemas).rstrip('?')
        base = f'List<{item_t}>'
    elif t == 'object' or schema.get('additionalProperties') is not None or schema.get('properties'):
        base = 'Map<String, dynamic>'
    else:
        base = 'Object'
    return f'{base}?' if optional else base


def gen_ts_types(schemas: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for name, schema in sorted(schemas.items()):
        if schema.get('enum') and schema.get('type') == 'string':
            vals = ' | '.join(json.dumps(v) for v in schema['enum'])
            lines.append(f'export type {name} = {vals};')
            lines.append('')
            continue
        props, required = _schema_props(schema)
        if schema.get('type') == 'object' or props:
            lines.append(f'export interface {name} {{')
            for prop, ps in props.items():
                if not isinstance(ps, dict):
                    continue
                opt = prop not in required
                # also nullable fields optional-ish
                te = ts_type_expr(ps, schemas)
                q = '?' if opt else ''
                lines.append(f'  {json.dumps(prop)[1:-1] if not prop.isidentifier() else prop}{q}: {te};')
            lines.append('}')
            lines.append('')
        else:
            lines.append(f'export type {name} = Record<string, unknown>;')
            lines.append('')
    return '\n'.join(lines)


def gen_py_types(schemas: dict[str, dict[str, Any]]) -> str:
    lines = [
        'from __future__ import annotations',
        '',
        'from typing import Any, Literal, NotRequired, TypedDict',
        '',
    ]
    # enums first
    for name, schema in sorted(schemas.items()):
        if schema.get('enum') and schema.get('type') == 'string':
            lits = ', '.join(repr(v) for v in schema['enum'])
            lines.append(f'{name} = Literal[{lits}]')
            lines.append('')
    for name, schema in sorted(schemas.items()):
        if schema.get('enum') and schema.get('type') == 'string':
            continue
        props, required = _schema_props(schema)
        lines.append(f'class {name}(TypedDict):')
        if not props:
            lines.append('    pass')
            lines.append('')
            continue
        for prop, ps in props.items():
            if not isinstance(ps, dict):
                continue
            te = py_type_expr(ps, schemas)
            if prop in required:
                lines.append(f'    {prop}: {te}')
            else:
                lines.append(f'    {prop}: NotRequired[{te}]')
        lines.append('')
    return '\n'.join(lines) + '\n'


def gen_go_types(schemas: dict[str, dict[str, Any]]) -> str:
    lines = ['package omiintegration', '', 'import "time"', '']
    # drop unused time if no date-time - use string for date-time always
    lines = ['package omiintegration', '']
    for name, schema in sorted(schemas.items()):
        if schema.get('enum') and schema.get('type') == 'string':
            lines.append(f'// {name} is an OpenAPI string enum.')
            lines.append(f'type {name} string')
            lines.append('')
            lines.append('const (')
            for v in schema['enum']:
                const = to_go_export(str(v).replace('-', '_'))
                lines.append(f'\t{name}{const} {name} = {json.dumps(v)}')
            lines.append(')')
            lines.append('')
            continue
        props, required = _schema_props(schema)
        lines.append(f'// {name} is generated from the Integration OpenAPI schema.')
        lines.append(f'type {name} struct {{')
        if not props:
            lines.append('\t// empty response object')
        for prop, ps in props.items():
            if not isinstance(ps, dict):
                continue
            field = to_go_export(prop)
            te = go_type_expr(ps, schemas)
            omit = ',omitempty' if prop not in required else ''
            lines.append(f'\t{field} {te} `json:"{prop}{omit}"`')
        lines.append('}')
        lines.append('')
    return '\n'.join(lines) + '\n'


def gen_dart_types(schemas: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for name, schema in sorted(schemas.items()):
        if schema.get('enum') and schema.get('type') == 'string':
            lines.append(f'typedef {name} = String;')
            lines.append('')
            continue
        props, required = _schema_props(schema)
        lines.append(f'class {name} {{')
        if not props:
            lines.append(f'  const {name}();')
            lines.append(f'  factory {name}.fromJson(Map<String, dynamic> json) => const {name}();')
            lines.append(f'  Map<String, dynamic> toJson() => const <String, dynamic>{{}};')
            lines.append('}')
            lines.append('')
            continue
        fields = []
        for prop, ps in props.items():
            if not isinstance(ps, dict):
                continue
            te = dart_type_expr(ps, schemas)
            # Non-required OpenAPI fields are optional named params → must be nullable in Dart.
            if prop not in required and not te.endswith('?'):
                te = f'{te}?'
            field = to_camel(prop) if '_' in prop else prop
            fields.append((prop, field, te, prop in required))
            lines.append(f'  final {te} {field};')
        lines.append('')
        ctor_args = ', '.join(
            (f'required this.{field}' if req and not te.endswith('?') else f'this.{field}')
            for _, field, te, req in fields
        )
        lines.append(f'  const {name}({{{ctor_args}}});')
        lines.append('')
        lines.append(f'  factory {name}.fromJson(Map<String, dynamic> json) {{')
        lines.append(f'    return {name}(')
        for prop, field, te, req in fields:
            is_list = te.startswith('List<') or te.startswith('List<')
            raw_list = te.startswith('List<')
            if raw_list:
                list_type = te[:-1] if te.endswith('?') else te
                assert list_type.startswith('List<') and list_type.endswith('>')
                inner = list_type[len('List<') : -1]
                # strip outer nullable on list type: List<Foo>?
                list_nullable = False
                # te is like List<Foo> or List<Foo>? — we forced ? only on whole type earlier
                if te.endswith('>?'):
                    # shouldn't happen with our construction
                    pass
                inner_base = inner.rstrip('?')
                if inner_base in schemas and not (
                    (schemas.get(inner_base) or {}).get('enum')
                    and (schemas.get(inner_base) or {}).get('type') == 'string'
                ):
                    mapped = f"(json[{json.dumps(prop)}] as List<dynamic>?)?.map((e) => {inner_base}.fromJson(e as Map<String, dynamic>)).toList()"
                else:
                    mapped = f"(json[{json.dumps(prop)}] as List<dynamic>?)?.map((e) => e as {inner_base}).toList()"
                if prop in required:
                    lines.append(f"      {field}: {mapped} ?? const [],")
                else:
                    lines.append(f"      {field}: {mapped},")
            elif te.rstrip('?') in schemas:
                base = te.rstrip('?')
                base_schema = schemas.get(base) or {}
                if base_schema.get('enum') and base_schema.get('type') == 'string':
                    # enum typedefs are strings
                    lines.append(f"      {field}: json[{json.dumps(prop)}] as {te},")
                elif prop in required and not te.endswith('?'):
                    lines.append(f"      {field}: {base}.fromJson(json[{json.dumps(prop)}] as Map<String, dynamic>),")
                else:
                    lines.append(
                        f"      {field}: json[{json.dumps(prop)}] == null ? null : {base}.fromJson(json[{json.dumps(prop)}] as Map<String, dynamic>),"
                    )
            else:
                cast = te.rstrip('?')
                if cast == 'Map<String, dynamic>':
                    expr = f"(json[{json.dumps(prop)}] as Map?)?.cast<String, dynamic>()"
                    if prop in required and not te.endswith('?'):
                        lines.append(f"      {field}: {expr} ?? const {{}},")
                    else:
                        lines.append(f"      {field}: {expr},")
                elif cast in {'String', 'int', 'double', 'bool', 'Object'}:
                    lines.append(f"      {field}: json[{json.dumps(prop)}] as {te},")
                else:
                    # enum typedefs etc.
                    lines.append(f"      {field}: json[{json.dumps(prop)}] as {te},")
        lines.append('    );')
        lines.append('  }')
        lines.append('}')
        lines.append('')
    return '\n'.join(lines)


def header_comment(lang: str, spec_path: Path) -> str:
    rel = spec_path.relative_to(ROOT_DIR).as_posix()
    common = (
        f'AUTO-GENERATED by backend/scripts/generate_integration_sdks.py from {rel}.\n'
        f'Do not edit by hand. Re-run the generator after OpenAPI changes.\n'
        f'Spec sha256[0:16]={spec_fingerprint(spec_path)}\n'
    )
    if lang == 'ts':
        return '/**\n * ' + '\n * '.join(common.strip().splitlines()) + '\n */\n'
    if lang in {'go', 'rust', 'cpp'}:
        return ''.join(f'// {line}\n' for line in common.strip().splitlines()) + '\n'
    if lang == 'py':
        return '"""\n' + common + '"""\n\n'
    return common


def to_camel(name: str) -> str:
    parts = name.split('_')
    return parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def to_pascal(name: str) -> str:
    return ''.join(p[:1].upper() + p[1:] for p in name.split('_') if p)


def to_go_export(name: str) -> str:
    return to_pascal(name)


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


def gen_typescript(ops: list[dict[str, Any]], schemas: dict[str, dict[str, Any]], spec_path: Path) -> dict[str, str]:
    lines: list[str] = [header_comment('ts', spec_path)]
    lines.append(gen_ts_types(schemas))
    lines.append("""export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { [key: string]: Json | undefined };

export class OmiIntegrationError extends Error {
  readonly status: number;
  readonly body: Json | string | null;

  constructor(status: number, body: Json | string | null, message?: string) {
    super(message ?? `Omi Integration API error: HTTP ${status}`);
    this.name = 'OmiIntegrationError';
    this.status = status;
    this.body = body;
  }
}

export interface ClientOptions {
  apiKey: string;
  appId: string;
  baseUrl?: string;
  fetch?: typeof fetch;
}

export class OmiIntegrationClient {
  readonly apiKey: string;
  readonly appId: string;
  readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ClientOptions) {
    if (!options.apiKey) throw new Error('apiKey is required');
    if (!options.appId) throw new Error('appId is required');
    this.apiKey = options.apiKey;
    this.appId = options.appId;
    this.baseUrl = (options.baseUrl ?? 'https://api.omi.me').replace(/\\/$/, '');
    this.fetchImpl = options.fetch ?? fetch;
  }

  private async request(
    method: string,
    path: string,
    query?: Record<string, unknown>,
    body?: unknown,
  ): Promise<Json> {
    const url = new URL(this.baseUrl + path);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value === undefined || value === null) continue;
        if (Array.isArray(value)) {
          for (const item of value) url.searchParams.append(key, String(item));
        } else {
          url.searchParams.set(key, String(value));
        }
      }
    }
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: 'application/json',
    };
    let payload: string | undefined;
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    const response = await this.fetchImpl(url, { method, headers, body: payload });
    const text = await response.text();
    let parsed: Json | string | null = null;
    if (text) {
      try {
        parsed = JSON.parse(text) as Json;
      } catch {
        parsed = text;
      }
    }
    if (!response.ok) {
      throw new OmiIntegrationError(response.status, parsed);
    }
    return (parsed ?? null) as Json;
  }
""")

    for op in ops:
        method_name = to_camel(op['name'])
        path_expr_parts: list[str] = []
        # build path with app_id substitution
        path = op['path']
        if '{app_id}' in path:
            path_js = path.replace('{app_id}', '${this.appId}')
            path_expr = f'`{path_js}`'
        else:
            path_expr = json.dumps(path)

        path_params = [p for p in op['params'] if p['in'] == 'path' and p['name'] != 'app_id']
        query_params = [p for p in op['params'] if p['in'] == 'query']
        args: list[str] = []
        # required query/path first
        for p in path_params:
            args.append(f"{to_camel(p['name'])}: string")
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]
        for p in required_q:
            ts_t = (
                'string'
                if p['type'] in {'string', 'any'}
                else (
                    'number'
                    if p['type'] in {'integer', 'number'}
                    else ('boolean' if p['type'] == 'boolean' else 'unknown')
                )
            )
            if p['type'].startswith('array'):
                ts_t = 'string[]'
            args.append(f"{to_camel(p['name'])}: {ts_t}")
        if op['body_type']:
            args.append(f'body: {op["body_ref"] or "Record<string, unknown>"}')
        if optional_q:
            fields = []
            for p in optional_q:
                ts_t = (
                    'string'
                    if p['type'] in {'string', 'any', None} or p['type'] is None
                    else (
                        'number'
                        if p['type'] in {'integer', 'number'}
                        else (
                            'boolean'
                            if p['type'] == 'boolean'
                            else ('string[]' if str(p['type']).startswith('array') else 'unknown')
                        )
                    )
                )
                fields.append(f"{to_camel(p['name'])}?: {ts_t}")
            args.append(f"options: {{ {'; '.join(fields)} }} = {{}}")

        lines.append(f'  /** {op["summary"]} */')
        ret_t = op.get('success_ref') or 'Json'
        lines.append(f'  async {method_name}({", ".join(args)}): Promise<{ret_t}> {{')
        # query object
        if query_params:
            lines.append('    const query: Record<string, unknown> = {};')
            for p in required_q:
                lines.append(f'    query[{json.dumps(p["name"])}] = {to_camel(p["name"])};')
            for p in optional_q:
                lines.append(
                    f'    if (options.{to_camel(p["name"])} !== undefined) query[{json.dumps(p["name"])}] = options.{to_camel(p["name"])};'
                )
            query_arg = 'query'
        else:
            query_arg = 'undefined'
        body_arg = 'body' if op['body_type'] else 'undefined'
        ret_t = op.get('success_ref') or 'Json'
        lines.append(
            f'    return (await this.request({json.dumps(op["method"])}, {path_expr}, {query_arg}, {body_arg})) as unknown as {ret_t};'
        )
        lines.append('  }')
        lines.append('')

    lines.append('}\n')
    lines.append('export default OmiIntegrationClient;\n')

    package_json = {
        'name': '@basedhardware/omi-integration',
        'version': '0.1.0',
        'description': 'Omi Integration API client (OpenAPI-generated)',
        'type': 'module',
        'main': './src/client.ts',
        'types': './src/client.ts',
        'exports': {
            '.': './src/client.ts',
        },
        'files': ['src', 'README.md'],
        'license': 'MIT',
        'repository': {
            'type': 'git',
            'url': 'https://github.com/BasedHardware/omi.git',
            'directory': 'sdks/integration/typescript',
        },
        'keywords': ['omi', 'integration', 'openapi', 'sdk'],
        'scripts': {
            'typecheck': 'tsc --noEmit -p tsconfig.json',
        },
    }
    tsconfig = {
        'compilerOptions': {
            'target': 'ES2022',
            'module': 'ES2022',
            'moduleResolution': 'bundler',
            'strict': True,
            'skipLibCheck': True,
            'noEmit': True,
            'lib': ['ES2022', 'DOM'],
        },
        'include': ['src/**/*.ts'],
    }
    return {
        'src/client.ts': ''.join(
            line + '\n' if not line.endswith('\n') else line for line in '\n'.join(lines).splitlines(True)
        ),
        'package.json': json.dumps(package_json, indent=2) + '\n',
        'tsconfig.json': json.dumps(tsconfig, indent=2) + '\n',
    }


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def gen_go(ops: list[dict[str, Any]], schemas: dict[str, dict[str, Any]], spec_path: Path) -> dict[str, str]:
    lines: list[str] = [header_comment('go', spec_path)]
    lines.append("""package omiintegration

import (
\t"bytes"
\t"context"
\t"encoding/json"
\t"fmt"
\t"io"
\t"net/http"
\t"net/url"
\t"strings"
\t"time"
)

const DefaultBaseURL = "https://api.omi.me"

// Client talks to the Omi Integration API.
type Client struct {
\tAPIKey     string
\tAppID      string
\tBaseURL    string
\tHTTPClient *http.Client
}

// New creates a Client. apiKey and appID are required.
func New(apiKey, appID string) *Client {
\treturn &Client{
\t\tAPIKey:  apiKey,
\t\tAppID:   appID,
\t\tBaseURL: DefaultBaseURL,
\t\tHTTPClient: &http.Client{
\t\t\tTimeout: 30 * time.Second,
\t\t},
\t}
}

// APIError is a non-2xx Integration API response.
type APIError struct {
\tStatusCode int
\tBody       []byte
}

func (e *APIError) Error() string {
\treturn fmt.Sprintf("omi integration api: HTTP %d: %s", e.StatusCode, strings.TrimSpace(string(e.Body)))
}

func (c *Client) request(ctx context.Context, method, path string, query url.Values, body any) (json.RawMessage, error) {
\tif c.APIKey == "" {
\t\treturn nil, fmt.Errorf("omi integration: api key is required")
\t}
\tif c.AppID == "" {
\t\treturn nil, fmt.Errorf("omi integration: app id is required")
\t}
\tbase := c.BaseURL
\tif base == "" {
\t\tbase = DefaultBaseURL
\t}
\tbase = strings.TrimRight(base, "/")
\tu, err := url.Parse(base + path)
\tif err != nil {
\t\treturn nil, err
\t}
\tif query != nil {
\t\tu.RawQuery = query.Encode()
\t}
\tvar rdr io.Reader
\tif body != nil {
\t\tb, err := json.Marshal(body)
\t\tif err != nil {
\t\t\treturn nil, err
\t\t}
\t\trdr = bytes.NewReader(b)
\t}
\treq, err := http.NewRequestWithContext(ctx, method, u.String(), rdr)
\tif err != nil {
\t\treturn nil, err
\t}
\treq.Header.Set("Authorization", "Bearer "+c.APIKey)
\treq.Header.Set("Accept", "application/json")
\tif body != nil {
\t\treq.Header.Set("Content-Type", "application/json")
\t}
\thttpClient := c.HTTPClient
\tif httpClient == nil {
\t\thttpClient = http.DefaultClient
\t}
\tres, err := httpClient.Do(req)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer res.Body.Close()
\tdata, err := io.ReadAll(res.Body)
\tif err != nil {
\t\treturn nil, err
\t}
\tif res.StatusCode < 200 || res.StatusCode >= 300 {
\t\treturn nil, &APIError{StatusCode: res.StatusCode, Body: data}
\t}
\tif len(data) == 0 {
\t\treturn json.RawMessage("null"), nil
\t}
\treturn json.RawMessage(data), nil
}
""")

    for op in ops:
        export = to_go_export(op['name'])
        path = op['path'].replace('{app_id}', '"+c.AppID+"')
        path_lit = f'"{path}"' if '{app_id}' not in op['path'] else f'"{op["path"].replace("{app_id}", "")}"'
        # rebuild path properly
        if '{app_id}' in op['path']:
            parts = op['path'].split('{app_id}')
            path_expr = f'"{parts[0]}" + c.AppID + "{parts[1]}"'
        else:
            path_expr = json.dumps(op['path'])

        query_params = [p for p in op['params'] if p['in'] == 'query']
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]

        # options struct for optional query params
        opt_struct = None
        if optional_q:
            opt_struct = f'{export}Options'
            lines.append(f'// {opt_struct} holds optional query parameters for {export}.')
            lines.append(f'type {opt_struct} struct {{')
            for p in optional_q:
                field = to_go_export(p['name'])
                go_t = 'string'
                if p['type'] in {'integer', 'number'}:
                    go_t = '*int'
                elif p['type'] == 'boolean':
                    go_t = '*bool'
                elif str(p['type']).startswith('array'):
                    go_t = '[]string'
                else:
                    go_t = '*string' if not p['required'] else 'string'
                    if p['type'] in {'string', 'any', None}:
                        go_t = '*string'
                lines.append(f'\t{field} {go_t}')
            lines.append('}')
            lines.append('')

        args = ['ctx context.Context']
        for p in required_q:
            go_t = 'string'
            if p['type'] in {'integer', 'number'}:
                go_t = 'int'
            elif p['type'] == 'boolean':
                go_t = 'bool'
            elif str(p['type']).startswith('array'):
                go_t = '[]string'
            args.append(f'{to_camel(p["name"])} {go_t}')
        if op['body_type']:
            args.append('body any')
        if opt_struct:
            args.append(f'opts *{opt_struct}')

        lines.append(f'// {export} {op["summary"]}'.rstrip())
        lines.append(f'func (c *Client) {export}({", ".join(args)}) (json.RawMessage, error) {{')
        if query_params:
            lines.append('\tq := url.Values{}')
            for p in required_q:
                n = p['name']
                v = to_camel(n)
                if p['type'] in {'integer', 'number'}:
                    lines.append(f'\tq.Set({json.dumps(n)}, fmt.Sprintf("%d", {v}))')
                elif p['type'] == 'boolean':
                    lines.append(f'\tq.Set({json.dumps(n)}, fmt.Sprintf("%t", {v}))')
                elif str(p['type']).startswith('array'):
                    lines.append(f'\tfor _, item := range {v} {{ q.Add({json.dumps(n)}, item) }}')
                else:
                    lines.append(f'\tq.Set({json.dumps(n)}, {v})')
            if opt_struct:
                lines.append('\tif opts != nil {')
                for p in optional_q:
                    field = to_go_export(p['name'])
                    n = p['name']
                    if str(p['type']).startswith('array'):
                        lines.append(f'\t\tfor _, item := range opts.{field} {{ q.Add({json.dumps(n)}, item) }}')
                    elif p['type'] in {'integer', 'number'}:
                        lines.append(
                            f'\t\tif opts.{field} != nil {{ q.Set({json.dumps(n)}, fmt.Sprintf("%d", *opts.{field})) }}'
                        )
                    elif p['type'] == 'boolean':
                        lines.append(
                            f'\t\tif opts.{field} != nil {{ q.Set({json.dumps(n)}, fmt.Sprintf("%t", *opts.{field})) }}'
                        )
                    else:
                        lines.append(f'\t\tif opts.{field} != nil {{ q.Set({json.dumps(n)}, *opts.{field}) }}')
                lines.append('\t}')
            query_arg = 'q'
        else:
            query_arg = 'nil'
        body_arg = 'body' if op['body_type'] else 'nil'
        lines.append(f'\treturn c.request(ctx, {json.dumps(op["method"])}, {path_expr}, {query_arg}, {body_arg})')
        lines.append('}')
        lines.append('')

    go_mod = '''module github.com/BasedHardware/omi/sdks/integration/go

go 1.22
'''
    return {
        'omiintegration/client_gen.go': '\n'.join(lines) + '\n',
        'omiintegration/types_gen.go': header_comment('go', spec_path) + gen_go_types(schemas),
        'go.mod': go_mod,
    }


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def gen_python(ops: list[dict[str, Any]], schemas: dict[str, dict[str, Any]], spec_path: Path) -> dict[str, str]:
    lines: list[str] = [header_comment('py', spec_path)]
    lines.append('''from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

import httpx

from .models import *  # noqa: F403

JsonValue = Union[None, bool, int, float, str, list[Any], dict[str, Any]]

DEFAULT_BASE_URL = "https://api.omi.me"


class OmiIntegrationError(Exception):
    def __init__(self, status_code: int, body: Any, message: Optional[str] = None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"Omi Integration API error: HTTP {status_code}")


class OmiIntegrationClient:
    """Thin Integration API client. Auth: Authorization Bearer <integration api key>."""

    def __init__(
        self,
        api_key: str,
        app_id: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not app_id:
            raise ValueError("app_id is required")
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OmiIntegrationClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
    ) -> JsonValue:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        # Drop None values so optional query params stay optional.
        clean_params: Optional[dict[str, Any]] = None
        if params is not None:
            clean_params = {k: v for k, v in params.items() if v is not None}
        response = self._client.request(
            method,
            path,
            params=clean_params,
            json=json_body,
            headers=headers,
        )
        body: Any
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = response.text
        else:
            body = None
        if response.is_error:
            raise OmiIntegrationError(response.status_code, body)
        return body
''')

    for op in ops:
        path = op['path']
        if '{app_id}' in path:
            path_expr = "f\"" + path.replace('{app_id}', '{self.app_id}') + "\""
        else:
            path_expr = repr(path)
        query_params = [p for p in op['params'] if p['in'] == 'query']
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]

        args = ['self']
        for p in required_q:
            py_t = 'str'
            if p['type'] in {'integer'}:
                py_t = 'int'
            elif p['type'] == 'number':
                py_t = 'float'
            elif p['type'] == 'boolean':
                py_t = 'bool'
            elif str(p['type']).startswith('array'):
                py_t = 'Sequence[str]'
            args.append(f"{p['name']}: {py_t}")
        if op['body_type']:
            args.append(f'body: {op["body_ref"] or "Mapping[str, Any]"}')
        for p in optional_q:
            py_t = 'Optional[str]'
            if p['type'] in {'integer'}:
                py_t = 'Optional[int]'
            elif p['type'] == 'number':
                py_t = 'Optional[float]'
            elif p['type'] == 'boolean':
                py_t = 'Optional[bool]'
            elif str(p['type']).startswith('array'):
                py_t = 'Optional[Sequence[str]]'
            args.append(f"{p['name']}: {py_t} = None")

        ret = op.get('success_ref') or 'JsonValue'
        lines.append(f'    def {op["name"]}({", ".join(args)}) -> {ret}:')
        lines.append(f'        """{op["summary"]}"""')
        if query_params:
            lines.append('        params: MutableMapping[str, Any] = {}')
            for p in required_q:
                lines.append(f'        params[{p["name"]!r}] = {p["name"]}')
            for p in optional_q:
                lines.append(f'        if {p["name"]} is not None:')
                lines.append(f'            params[{p["name"]!r}] = {p["name"]}')
            params_arg = 'params=params'
        else:
            params_arg = 'params=None'
        body_arg = 'json_body=body' if op['body_type'] else 'json_body=None'
        lines.append(f'        return self._request({op["method"]!r}, {path_expr}, {params_arg}, {body_arg})')
        lines.append('')

    init_py = (
        header_comment('py', spec_path)
        + 'from .client import OmiIntegrationClient, OmiIntegrationError\n\n__all__ = ["OmiIntegrationClient", "OmiIntegrationError"]\n'
    )
    pyproject = '''[build-system]
requires = ["setuptools>=64.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "omi-integration"
version = "0.1.0"
description = "Omi Integration API client (OpenAPI-generated)"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = [
    "httpx>=0.27,<1.0",
]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Typing :: Typed",
]

[project.urls]
Homepage = "https://www.omi.me/"
Repository = "https://github.com/BasedHardware/omi"

[tool.setuptools.packages.find]
where = ["src"]
'''
    models_py = header_comment('py', spec_path) + gen_py_types(schemas)
    return {
        'src/omi_integration/__init__.py': init_py,
        'src/omi_integration/client.py': '\n'.join(lines) + '\n',
        'src/omi_integration/models.py': models_py,
        'src/omi_integration/py.typed': '',
        'pyproject.toml': pyproject,
    }


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------


def gen_rust(ops: list[dict[str, Any]], spec_path: Path) -> dict[str, str]:
    lines: list[str] = [header_comment('rust', spec_path)]
    lines.append('''use reqwest::blocking::Client as HttpClient;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use serde_json::Value;
use std::collections::HashMap;
use thiserror::Error;

pub const DEFAULT_BASE_URL: &str = "https://api.omi.me";

#[derive(Debug, Error)]
pub enum Error {
    #[error("api key is required")]
    MissingApiKey,
    #[error("app id is required")]
    MissingAppId,
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("omi integration api: HTTP {status}: {body}")]
    Api { status: u16, body: String },
}

#[derive(Debug, Clone)]
pub struct OmiIntegrationClient {
    api_key: String,
    app_id: String,
    base_url: String,
    http: HttpClient,
}

impl OmiIntegrationClient {
    pub fn new(api_key: impl Into<String>, app_id: impl Into<String>) -> Result<Self, Error> {
        let api_key = api_key.into();
        let app_id = app_id.into();
        if api_key.is_empty() {
            return Err(Error::MissingApiKey);
        }
        if app_id.is_empty() {
            return Err(Error::MissingAppId);
        }
        Ok(Self {
            api_key,
            app_id,
            base_url: DEFAULT_BASE_URL.to_string(),
            http: HttpClient::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()?,
        })
    }

    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into().trim_end_matches('/').to_string();
        self
    }

    fn request(
        &self,
        method: reqwest::Method,
        path: &str,
        query: &[(&str, String)],
        body: Option<&Value>,
    ) -> Result<Value, Error> {
        let url = format!("{}{}", self.base_url, path);
        let mut headers = HeaderMap::new();
        let auth = format!("Bearer {}", self.api_key);
        headers.insert(AUTHORIZATION, HeaderValue::from_str(&auth).map_err(|e| Error::Api { status: 0, body: e.to_string() })?);
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));

        let mut req = self.http.request(method, url).headers(headers);
        if !query.is_empty() {
            req = req.query(query);
        }
        if let Some(b) = body {
            req = req.json(b);
        }
        let response = req.send()?;
        let status = response.status();
        let text = response.text().unwrap_or_default();
        if !status.is_success() {
            return Err(Error::Api {
                status: status.as_u16(),
                body: text,
            });
        }
        if text.is_empty() {
            return Ok(Value::Null);
        }
        serde_json::from_str(&text).map_err(|e| Error::Api {
            status: status.as_u16(),
            body: e.to_string(),
        })
    }
''')

    for op in ops:
        fn = op['name']
        if '{app_id}' in op['path']:
            path_build = f'let path = "{op["path"]}".replace("{{app_id}}", &self.app_id);'
        else:
            path_build = f'let path = "{op["path"]}".to_string();'

        query_params = [p for p in op['params'] if p['in'] == 'query']
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]

        args = ['&self']
        for p in required_q:
            rust_t = '&str'
            if p['type'] in {'integer'}:
                rust_t = 'i64'
            elif p['type'] == 'number':
                rust_t = 'f64'
            elif p['type'] == 'boolean':
                rust_t = 'bool'
            elif str(p['type']).startswith('array'):
                rust_t = '&[String]'
            args.append(f'{p["name"]}: {rust_t}')
        if op['body_type']:
            args.append('body: &Value')
        for p in optional_q:
            rust_t = 'Option<&str>'
            if p['type'] in {'integer'}:
                rust_t = 'Option<i64>'
            elif p['type'] == 'number':
                rust_t = 'Option<f64>'
            elif p['type'] == 'boolean':
                rust_t = 'Option<bool>'
            elif str(p['type']).startswith('array'):
                rust_t = 'Option<&[String]>'
            args.append(f'{p["name"]}: {rust_t}')

        lines.append(f'    /// {op["summary"]}')
        lines.append(f'    pub fn {fn}({", ".join(args)}) -> Result<Value, Error> {{')
        lines.append(f'        {path_build}')
        if required_q or optional_q:
            lines.append('        let mut query: Vec<(&str, String)> = Vec::new();')
        else:
            lines.append('        let query: Vec<(&str, String)> = Vec::new();')
        for p in required_q:
            n = p['name']
            if p['type'] in {'integer', 'number'}:
                lines.append(f'        query.push(("{n}", {n}.to_string()));')
            elif p['type'] == 'boolean':
                lines.append(f'        query.push(("{n}", {n}.to_string()));')
            elif str(p['type']).startswith('array'):
                lines.append(f'        for item in {n} {{ query.push(("{n}", item.clone())); }}')
            else:
                lines.append(f'        query.push(("{n}", {n}.to_string()));')
        for p in optional_q:
            n = p['name']
            if str(p['type']).startswith('array'):
                lines.append(
                    f'        if let Some(values) = {n} {{ for item in values {{ query.push(("{n}", item.clone())); }} }}'
                )
            else:
                lines.append(f'        if let Some(value) = {n} {{ query.push(("{n}", value.to_string())); }}')
        method = {
            'GET': 'reqwest::Method::GET',
            'POST': 'reqwest::Method::POST',
            'PUT': 'reqwest::Method::PUT',
            'PATCH': 'reqwest::Method::PATCH',
            'DELETE': 'reqwest::Method::DELETE',
        }[op['method']]
        body_arg = 'Some(body)' if op['body_type'] else 'None'
        lines.append(f'        self.request({method}, &path, &query, {body_arg})')
        lines.append('    }')
        lines.append('')

    lines.append('}')
    # fix unused import warning
    rust_src = '\n'.join(lines) + '\n'
    rust_src = rust_src.replace('use std::collections::HashMap;\n', '')

    cargo = '''[package]
name = "omi-integration"
version = "0.1.0"
edition = "2021"
description = "Omi Integration API client (OpenAPI-generated)"
license = "MIT"
repository = "https://github.com/BasedHardware/omi"

[dependencies]
reqwest = { version = "0.12", default-features = false, features = ["blocking", "json", "rustls-tls"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
thiserror = "1"
'''
    lib_rs = header_comment('rust', spec_path) + 'mod client_gen;\npub use client_gen::*;\n'
    return {
        'src/client_gen.rs': rust_src,
        'src/lib.rs': lib_rs,
        'Cargo.toml': cargo,
    }


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


def gen_cpp(ops: list[dict[str, Any]], spec_path: Path) -> dict[str, str]:
    hdr = [header_comment('cpp', spec_path)]
    hdr.append('''#pragma once

#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace omi {
namespace integration {

struct JsonValue {
  // Opaque JSON text payload (object/array/scalar). Callers parse with their JSON lib.
  std::string raw;
};

class ApiError : public std::runtime_error {
 public:
  ApiError(int status, std::string body)
      : std::runtime_error("Omi Integration API error: HTTP " + std::to_string(status)),
        status_(status),
        body_(std::move(body)) {}
  int status() const { return status_; }
  const std::string& body() const { return body_; }

 private:
  int status_;
  std::string body_;
};

class Client {
 public:
  Client(std::string api_key, std::string app_id, std::string base_url = "https://api.omi.me");
  ~Client();

  Client(const Client&) = delete;
  Client& operator=(const Client&) = delete;

''')

    for op in ops:
        query_params = [p for p in op['params'] if p['in'] == 'query']
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]
        args: list[str] = []
        for p in required_q:
            if p['type'] in {'integer'}:
                args.append(f'int {p["name"]}')
            elif p['type'] == 'boolean':
                args.append(f'bool {p["name"]}')
            elif str(p['type']).startswith('array'):
                args.append(f'const std::vector<std::string>& {p["name"]}')
            else:
                args.append(f'const std::string& {p["name"]}')
        if op['body_type']:
            args.append('const std::string& json_body')
        for p in optional_q:
            if p['type'] in {'integer'}:
                args.append(f'std::optional<int> {p["name"]} = std::nullopt')
            elif p['type'] == 'boolean':
                args.append(f'std::optional<bool> {p["name"]} = std::nullopt')
            elif str(p['type']).startswith('array'):
                args.append(f'std::optional<std::vector<std::string>> {p["name"]} = std::nullopt')
            else:
                args.append(f'std::optional<std::string> {p["name"]} = std::nullopt')
        hdr.append(f'  // {op["summary"]}')
        hdr.append(f'  JsonValue {op["name"]}({", ".join(args)});')
        hdr.append('')

    hdr.append(''' private:
  JsonValue request(const std::string& method, const std::string& path,
                    const std::map<std::string, std::string>& query,
                    const std::string* json_body);

  std::string api_key_;
  std::string app_id_;
  std::string base_url_;
};

}  // namespace integration
}  // namespace omi
''')

    src = [header_comment('cpp', spec_path)]
    src.append('''#include "omi/integration/client.hpp"

#include <curl/curl.h>

#include <sstream>
#include <utility>

namespace omi {
namespace integration {
namespace {

size_t write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

std::string url_encode(CURL* curl, const std::string& value) {
  char* encoded = curl_easy_escape(curl, value.c_str(), static_cast<int>(value.size()));
  std::string result = encoded ? encoded : value;
  if (encoded) curl_free(encoded);
  return result;
}

}  // namespace

Client::Client(std::string api_key, std::string app_id, std::string base_url)
    : api_key_(std::move(api_key)), app_id_(std::move(app_id)), base_url_(std::move(base_url)) {
  if (api_key_.empty()) throw std::invalid_argument("api_key is required");
  if (app_id_.empty()) throw std::invalid_argument("app_id is required");
  while (!base_url_.empty() && base_url_.back() == '/') base_url_.pop_back();
  curl_global_init(CURL_GLOBAL_DEFAULT);
}

Client::~Client() { curl_global_cleanup(); }

JsonValue Client::request(const std::string& method, const std::string& path,
                          const std::map<std::string, std::string>& query,
                          const std::string* json_body) {
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("curl_easy_init failed");

  std::ostringstream url;
  url << base_url_ << path;
  bool first = true;
  for (const auto& [key, value] : query) {
    url << (first ? '?' : '&') << url_encode(curl, key) << '=' << url_encode(curl, value);
    first = false;
  }

  std::string response_body;
  struct curl_slist* headers = nullptr;
  const std::string auth = "Authorization: Bearer " + api_key_;
  headers = curl_slist_append(headers, auth.c_str());
  headers = curl_slist_append(headers, "Accept: application/json");
  if (json_body != nullptr) {
    headers = curl_slist_append(headers, "Content-Type: application/json");
  }

  curl_easy_setopt(curl, CURLOPT_URL, url.str().c_str());
  curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_body);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
  if (json_body != nullptr) {
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body->c_str());
  }

  const CURLcode rc = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);

  if (rc != CURLE_OK) {
    throw std::runtime_error(std::string("curl error: ") + curl_easy_strerror(rc));
  }
  if (status < 200 || status >= 300) {
    throw ApiError(static_cast<int>(status), response_body);
  }
  return JsonValue{response_body};
}
''')

    for op in ops:
        query_params = [p for p in op['params'] if p['in'] == 'query']
        required_q = [p for p in query_params if p['required']]
        optional_q = [p for p in query_params if not p['required']]
        args: list[str] = []
        for p in required_q:
            if p['type'] in {'integer'}:
                args.append(f'int {p["name"]}')
            elif p['type'] == 'boolean':
                args.append(f'bool {p["name"]}')
            elif str(p['type']).startswith('array'):
                args.append(f'const std::vector<std::string>& {p["name"]}')
            else:
                args.append(f'const std::string& {p["name"]}')
        if op['body_type']:
            args.append('const std::string& json_body')
        for p in optional_q:
            if p['type'] in {'integer'}:
                args.append(f'std::optional<int> {p["name"]}')
            elif p['type'] == 'boolean':
                args.append(f'std::optional<bool> {p["name"]}')
            elif str(p['type']).startswith('array'):
                args.append(f'std::optional<std::vector<std::string>> {p["name"]}')
            else:
                args.append(f'std::optional<std::string> {p["name"]}')

        if '{app_id}' in op['path']:
            path_expr = f'std::string("{op["path"]}").replace(path.find("{{app_id}}"), 8, app_id_)'
            # simpler:
            path_build = f'  std::string path = "{op["path"]}";\n  path.replace(path.find("{{app_id}}"), std::string("{{app_id}}").size(), app_id_);'
        else:
            path_build = f'  std::string path = "{op["path"]}";'

        src.append(f'JsonValue Client::{op["name"]}({", ".join(args)}) {{')
        src.append(path_build)
        src.append('  std::map<std::string, std::string> query;')
        for p in required_q:
            n = p['name']
            if p['type'] in {'integer'}:
                src.append(f'  query.emplace("{n}", std::to_string({n}));')
            elif p['type'] == 'boolean':
                src.append(f'  query.emplace("{n}", {n} ? "true" : "false");')
            elif str(p['type']).startswith('array'):
                src.append(f'  for (const auto& item : {n}) query.emplace("{n}", item);')
            else:
                src.append(f'  query.emplace("{n}", {n});')
        for p in optional_q:
            n = p['name']
            if p['type'] in {'integer'}:
                src.append(f'  if ({n}.has_value()) query.emplace("{n}", std::to_string(*{n}));')
            elif p['type'] == 'boolean':
                src.append(f'  if ({n}.has_value()) query.emplace("{n}", *{n} ? "true" : "false");')
            elif str(p['type']).startswith('array'):
                src.append(f'  if ({n}.has_value()) for (const auto& item : *{n}) query.emplace("{n}", item);')
            else:
                src.append(f'  if ({n}.has_value()) query.emplace("{n}", *{n});')
        body_arg = '&json_body' if op['body_type'] else 'nullptr'
        src.append(f'  return request("{op["method"]}", path, query, {body_arg});')
        src.append('}')
        src.append('')

    src.append('}  // namespace integration\n}  // namespace omi\n')

    cmake = '''cmake_minimum_required(VERSION 3.16)
project(omi_integration VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_library(omi_integration
  src/client.cpp
)
target_include_directories(omi_integration
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(omi_integration PUBLIC CURL::libcurl)

install(TARGETS omi_integration)
install(DIRECTORY include/ DESTINATION include)
'''
    return {
        'include/omi/integration/client.hpp': '\n'.join(hdr) + '\n',
        'src/client.cpp': '\n'.join(src) + '\n',
        'CMakeLists.txt': cmake,
    }


# ---------------------------------------------------------------------------
# Dart
# ---------------------------------------------------------------------------


def _dart_type(param: dict[str, Any], optional: bool) -> str:
    t = param.get("type")
    if str(t).startswith("array"):
        base = "List<String>"
    elif t == "integer":
        base = "int"
    elif t == "number":
        base = "double"
    elif t == "boolean":
        base = "bool"
    else:
        base = "String"
    if optional:
        return f"{base}?"
    return base


def gen_dart(ops: list[dict[str, Any]], schemas: dict[str, dict[str, Any]], spec_path: Path) -> dict[str, str]:
    lines: list[str] = [header_comment("cpp", spec_path)]
    lines.append("""import 'dart:convert';

import 'package:http/http.dart' as http;

class OmiIntegrationException implements Exception {
  OmiIntegrationException(this.statusCode, this.body);
  final int statusCode;
  final Object? body;

  @override
  String toString() => 'OmiIntegrationException: HTTP $statusCode: $body';
}

/// Thin Integration API client. Auth: `Authorization: Bearer <key>`.
class OmiIntegrationClient {
  OmiIntegrationClient({
    required this.apiKey,
    required this.appId,
    this.baseUrl = 'https://api.omi.me',
    http.Client? httpClient,
  })  : _http = httpClient ?? http.Client(),
        _ownsClient = httpClient == null {
    if (apiKey.isEmpty) {
      throw ArgumentError.value(apiKey, 'apiKey', 'required');
    }
    if (appId.isEmpty) {
      throw ArgumentError.value(appId, 'appId', 'required');
    }
  }

  final String apiKey;
  final String appId;
  final String baseUrl;
  final http.Client _http;
  final bool _ownsClient;

  void close() {
    if (_ownsClient) {
      _http.close();
    }
  }

  Future<Object?> _request(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Object? body,
  }) async {
    final cleanedBase = baseUrl.replaceAll(RegExp(r'/+$'), '');
    final filteredQuery = <String, String>{};
    if (query != null) {
      for (final entry in query.entries) {
        if (entry.value == null) continue;
        filteredQuery[entry.key] = '${entry.value}';
      }
    }
    final uri = Uri.parse('$cleanedBase$path').replace(
      queryParameters: filteredQuery.isEmpty ? null : filteredQuery,
    );
    final headers = <String, String>{
      'Authorization': 'Bearer $apiKey',
      'Accept': 'application/json',
    };
    final encoded = body == null ? null : jsonEncode(body);
    if (encoded != null) {
      headers['Content-Type'] = 'application/json';
    }
    late final http.Response response;
    switch (method) {
      case 'GET':
        response = await _http.get(uri, headers: headers);
      case 'POST':
        response = await _http.post(uri, headers: headers, body: encoded);
      case 'PUT':
        response = await _http.put(uri, headers: headers, body: encoded);
      case 'PATCH':
        response = await _http.patch(uri, headers: headers, body: encoded);
      case 'DELETE':
        response = await _http.delete(uri, headers: headers, body: encoded);
      default:
        throw UnsupportedError('HTTP $method');
    }
    Object? parsed;
    if (response.body.isNotEmpty) {
      try {
        parsed = jsonDecode(response.body);
      } catch (_) {
        parsed = response.body;
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw OmiIntegrationException(response.statusCode, parsed);
    }
    return parsed;
  }
""")
    for op in ops:
        method_name = op["name"]  # snake_case is idiomatic Dart for private; public APIs often camelCase.
        dart_name = to_camel(op["name"])
        query_params = [p for p in op["params"] if p["in"] == "query"]
        required_q = [p for p in query_params if p["required"]]
        optional_q = [p for p in query_params if not p["required"]]

        args: list[str] = []
        for p in required_q:
            args.append(f"required {_dart_type(p, False)} {to_camel(p['name'])}")
        if op["body_type"]:
            args.append(f"required {op['body_ref'] or 'Map<String, dynamic>'} body")
        for p in optional_q:
            args.append(f"{_dart_type(p, True)} {to_camel(p['name'])}")

        lines.append(f"  /// {op['summary']}")
        if args:
            lines.append(f"  Future<Object?> {dart_name}({{")
            for a in args:
                lines.append(f"    {a},")
            lines.append("  }) async {")
        else:
            lines.append(f"  Future<Object?> {dart_name}() async {{")

        if "{app_id}" in op["path"]:
            path_expr = "'" + op["path"].replace("{app_id}", "$appId") + "'"
            # Use string interpolation carefully: path has no other $
            path_expr = '"' + op["path"].replace("{app_id}", "$appId") + '"'
        else:
            path_expr = json.dumps(op["path"])

        if query_params:
            lines.append("    final query = <String, dynamic>{")
            for p in required_q:
                lines.append(f"      {json.dumps(p['name'])}: {to_camel(p['name'])},")
            lines.append("    };")
            for p in optional_q:
                lines.append(
                    f"    if ({to_camel(p['name'])} != null) query[{json.dumps(p['name'])}] = {to_camel(p['name'])};"
                )
            query_arg = "query: query"
        else:
            query_arg = "query: null"
        body_arg = "body: body" if op["body_type"] else "body: null"
        lines.append(f"    return _request({json.dumps(op['method'])}, {path_expr}, {query_arg}, {body_arg});")
        lines.append("  }")
        lines.append("")

    lines.append("}")
    lines.append("")
    lines.append(gen_dart_types(schemas))

    pubspec = """name: omi_integration
description: Omi Integration API client (OpenAPI-generated)
version: 0.1.0
publish_to: none
environment:
  sdk: '>=3.0.0 <4.0.0'
dependencies:
  http: ^1.2.0
dev_dependencies:
  test: ^1.25.0
"""
    test = """import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi_integration/omi_integration.dart';
import 'package:test/test.dart';

void main() {
  test('sends bearer auth and app_id path', () async {
    late http.Request seen;
    final mock = MockClient((request) async {
      seen = request;
      return http.Response(jsonEncode({'memories': []}), 200);
    });
    final client = OmiIntegrationClient(
      apiKey: 'test-key',
      appId: 'app-123',
      httpClient: mock,
    );
    final body = await client.listMemories(uid: 'user-1', limit: 10);
    expect(body, isA<Map>());
    expect(seen.headers['Authorization'], 'Bearer test-key');
    expect(seen.url.path, '/v2/integrations/app-123/memories');
    expect(seen.url.queryParameters['uid'], 'user-1');
    client.close();
  });

  test('throws on non-2xx', () async {
    final mock = MockClient((request) async {
      return http.Response(jsonEncode({'detail': 'nope'}), 401);
    });
    final client = OmiIntegrationClient(
      apiKey: 'test-key',
      appId: 'app-123',
      httpClient: mock,
    );
    expect(
      () => client.listMemories(uid: 'user-1'),
      throwsA(isA<OmiIntegrationException>()),
    );
    client.close();
  });
}
"""
    return {
        "lib/omi_integration.dart": "\n".join(lines) + "\n",
        "pubspec.yaml": pubspec,
        "test/client_test.dart": test,
        "README.md": """# omi_integration (Dart)

OpenAPI-generated client for the Omi Integration API.

```dart
final client = OmiIntegrationClient(apiKey: apiKey, appId: appId);
final memories = await client.listMemories(uid: uid);
```

React Native / JS: use the TypeScript package under `../typescript` (same `fetch` API).

See the parent [README](../README.md).
""",
        ".gitignore": ".dart_tool/\n.packages\npubspec.lock\nbuild/\n",
    }


# ---------------------------------------------------------------------------
# Shared docs / scripts
# ---------------------------------------------------------------------------


def gen_readme(ops: list[dict[str, Any]]) -> str:
    methods = '\n'.join(f'| `{op["name"]}` | `{op["method"]}` | `{op["path"]}` | {op["summary"]} |' for op in ops)
    return f'''# Omi Integration API SDKs

OpenAPI-generated clients for the **Omi Integration API**.

- Spec: [`docs/api-reference/integration-public-openapi.json`](../../docs/api-reference/integration-public-openapi.json)
- Base URL: `https://api.omi.me`
- Auth: `Authorization: Bearer <integration_api_key>`
- Client config always includes your `app_id`

## Languages

| Lang | Path | Package |
|------|------|---------|
| TypeScript | [`typescript/`](typescript/) | `@basedhardware/omi-integration` |
| Go | [`go/`](go/) | `github.com/BasedHardware/omi/sdks/integration/go` |
| Python | [`python/`](python/) | `omi-integration` |
| Rust | [`rust/`](rust/) | `omi-integration` |
| C++ | [`cpp/`](cpp/) | CMake target `omi_integration` |
| Dart / Flutter | [`dart/`](dart/) | `omi_integration` |
| React Native | use [`typescript/`](typescript/) | same package — `fetch` works in RN |

## Regenerate

```bash
python backend/scripts/generate_integration_sdks.py
python backend/scripts/generate_integration_sdks.py --check   # CI
# or
sdks/integration/scripts/generate.sh
```

## Methods

| Method | HTTP | Path | Summary |
|--------|------|------|---------|
{methods}

## Use the OpenAPI spec yourself

Any OpenAPI generator can target the same spec:

```bash
# examples
openapi-generator-cli generate -i docs/api-reference/integration-public-openapi.json -g typescript-fetch -o /tmp/omi-ts
oapi-codegen -package omiintegration docs/api-reference/integration-public-openapi.json
```

## Quickstarts

### TypeScript

```ts
import {{ OmiIntegrationClient }} from '@basedhardware/omi-integration';

const client = new OmiIntegrationClient({{
  apiKey: process.env.OMI_INTEGRATION_API_KEY!,
  appId: process.env.OMI_APP_ID!,
}});

const memories = await client.listMemories(uid);
```

### Go

```go
client := omiintegration.New(os.Getenv("OMI_INTEGRATION_API_KEY"), os.Getenv("OMI_APP_ID"))
raw, err := client.ListMemories(ctx, uid, nil)
```

### Python

```python
from omi_integration import OmiIntegrationClient

with OmiIntegrationClient(api_key, app_id) as client:
    memories = client.list_memories(uid)
```

### Rust

```rust
let client = omi_integration::OmiIntegrationClient::new(api_key, app_id)?;
let memories = client.list_memories(uid, None, None)?;
```

### C++

```cpp
omi::integration::Client client(api_key, app_id);
auto memories = client.list_memories(uid);
```

### Dart / Flutter

```dart
final client = OmiIntegrationClient(apiKey: apiKey, appId: appId);
final memories = await client.listMemories(uid: uid);
```

### React Native

Use the TypeScript client (`@basedhardware/omi-integration`). No separate RN package —
global `fetch` is enough.
'''


def normalize_text(content: str) -> str:
    """Canonical file text: LF endings and exactly one trailing newline."""
    return content.replace('\r\n', '\n').rstrip('\n') + '\n'


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalize_text(content), encoding='utf-8')


def _format_dart_tree(root: Path) -> None:
    """Run dart format on generated Dart sources when the tool is available."""
    dart_dir = root / 'dart'
    if not dart_dir.exists():
        return
    import os
    import shutil
    import subprocess

    dart = None
    flutter_root = os.environ.get('FLUTTER_ROOT')
    if flutter_root:
        candidate = Path(flutter_root) / 'bin' / 'dart'
        if candidate.exists():
            dart = str(candidate)
    if dart is None:
        dart = shutil.which('dart')
    if not dart:
        return
    targets = [str(path) for path in dart_dir.rglob('*.dart') if path.is_file()]
    if not targets:
        return
    subprocess.run([dart, 'format', '--line-length', '120', *targets], check=False)


def generate_all(spec_path: Path) -> dict[str, str]:
    spec = load_spec(spec_path)
    ops = operations(spec)
    schemas = collect_schemas(spec)
    if not ops:
        raise GeneratorError(f'no operations found in {spec_path}')

    files: dict[str, str] = {}
    for rel, content in gen_typescript(ops, schemas, spec_path).items():
        files[f'typescript/{rel}'] = content
    for rel, content in gen_go(ops, schemas, spec_path).items():
        files[f'go/{rel}'] = content
    for rel, content in gen_python(ops, schemas, spec_path).items():
        files[f'python/{rel}'] = content
    for rel, content in gen_rust(ops, spec_path).items():
        files[f'rust/{rel}'] = content
    for rel, content in gen_cpp(ops, spec_path).items():
        files[f'cpp/{rel}'] = content
    for rel, content in gen_dart(ops, schemas, spec_path).items():
        files[f'dart/{rel}'] = content

    files['README.md'] = gen_readme(ops)
    files['python/README.md'] = """# omi-integration (Python)

OpenAPI-generated client for the Omi Integration API.

```bash
pip install -e sdks/integration/python
```

```python
from omi_integration import OmiIntegrationClient

with OmiIntegrationClient("YOUR_KEY", "YOUR_APP_ID") as client:
    print(client.list_memories("USER_UID"))
```

See the parent [README](../README.md) for all languages and regenerate instructions.
"""

    files['scripts/generate.sh'] = '''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec python3 "$ROOT/backend/scripts/generate_integration_sdks.py" "$@"
'''
    # Tiny hermetic tests live outside generated trees where practical.
    files['python/tests/test_client_auth.py'] = '''from __future__ import annotations

import json
from typing import Any

import httpx

from omi_integration import OmiIntegrationClient, OmiIntegrationError


def test_bearer_and_app_id_path() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"memories": []})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.omi.me")
    client = OmiIntegrationClient("test-key", "app-123", client=http)
    body = client.list_memories("user-1", limit=10)
    assert body == {"memories": []}
    assert seen["authorization"] == "Bearer test-key"
    assert "/v2/integrations/app-123/memories" in seen["url"]
    assert "uid=user-1" in seen["url"]
    client.close()


def test_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "nope"})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.omi.me")
    client = OmiIntegrationClient("test-key", "app-123", client=http)
    try:
        client.list_memories("user-1")
        assert False, "expected error"
    except OmiIntegrationError as exc:
        assert exc.status_code == 401
    finally:
        client.close()
'''
    return files


def check_dirty(files: dict[str, str], root: Path) -> list[str]:
    dirty: list[str] = []
    for rel, content in sorted(files.items()):
        path = root / rel
        if not path.exists():
            dirty.append(f'missing {rel}')
            continue
        existing = path.read_text(encoding='utf-8')
        if normalize_text(existing) != normalize_text(content):
            dirty.append(f'drift {rel}')
    return dirty


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=DEFAULT_SPEC)
    parser.add_argument('--check', action='store_true', help='fail if generated tree is stale')
    parser.add_argument('--out', type=Path, default=SDK_ROOT, help='output root (default sdks/integration)')
    args = parser.parse_args(argv)

    files = generate_all(args.spec.resolve())
    out_root = args.out

    if args.check:
        import shutil
        import subprocess
        import tempfile

        dirty = check_dirty(files, out_root)
        # Dart sources are post-processed with `dart format`; compare non-Dart
        # exactly, and require committed Dart to already be format-clean.
        dirty = [item for item in dirty if not item.split(' ', 1)[-1].startswith('dart/')]
        dart_dir = out_root / 'dart'
        dart_bin = None
        flutter_root = __import__('os').environ.get('FLUTTER_ROOT')
        if flutter_root:
            candidate = Path(flutter_root) / 'bin' / 'dart'
            if candidate.exists():
                dart_bin = str(candidate)
        if dart_bin is None:
            dart_bin = shutil.which('dart')
        if dart_dir.exists() and dart_bin:
            dart_files = [str(path) for path in dart_dir.rglob('*.dart') if path.is_file()]
            if dart_files:
                proc = subprocess.run(
                    [
                        dart_bin,
                        'format',
                        '--line-length',
                        '120',
                        '--set-exit-if-changed',
                        '--output',
                        'none',
                        *dart_files,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if proc.returncode != 0:
                    dirty.append('dart format drift (run generate_integration_sdks.py)')
        # Ensure generated non-dart files exist for every key
        for rel in files:
            if rel.startswith('dart/'):
                path = out_root / rel
                if not path.exists():
                    dirty.append(f'missing {rel}')
        if dirty:
            print('FAIL: integration SDKs are stale:', file=sys.stderr)
            for item in dirty:
                print(f'  - {item}', file=sys.stderr)
            print('Run: python backend/scripts/generate_integration_sdks.py', file=sys.stderr)
            return 1
        print(f'OK: {len(files)} integration SDK files match OpenAPI')
        return 0

    write_tree(out_root, files)
    _format_dart_tree(out_root)
    gen_sh = out_root / 'scripts' / 'generate.sh'
    if gen_sh.exists():
        gen_sh.chmod(gen_sh.stat().st_mode | 0o111)
    print(f'Wrote {len(files)} files under {out_root}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except GeneratorError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
