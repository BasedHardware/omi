#!/usr/bin/env python3
"""Generate Dart wire DTOs from the app-client OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
DEFAULT_OUTPUT_DIR = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen'

SCHEMA_GROUPS = {
    'conversation': {
        'output': DEFAULT_OUTPUT_DIR / 'conversation_wire.g.dart',
        'schemas': (
            'Translation',
            'TranscriptSegment',
            'ActionItem',
            'AppResult',
            'PluginResult',
            'Event',
            'Structured',
            'Geolocation',
            'ConversationPhoto',
            'AudioFile',
            'CalendarEventLink',
            'Conversation',
        ),
    },
    'action_items_folders': {
        'output': DEFAULT_OUTPUT_DIR / 'action_items_folders_wire.g.dart',
        'schemas': (
            'ActionItemResponse',
            'ActionItemsResponse',
            'ActionItemsSearchResponse',
            'PendingSyncResponse',
            'Folder',
            'FolderMutationResponse',
            'BulkMoveConversationsResponse',
        ),
    },
    'api_keys': {
        'output': DEFAULT_OUTPUT_DIR / 'api_keys_wire.g.dart',
        'schemas': (
            'DevApiKey',
            'DevApiKeyCreated',
            'McpApiKey',
            'McpApiKeyCreated',
        ),
    },
    'agent': {
        'output': DEFAULT_OUTPUT_DIR / 'agent_wire.g.dart',
        'schemas': (
            'AgentVmInfo',
            'AgentKeepaliveResponse',
        ),
    },
    'phone_calls': {
        'output': DEFAULT_OUTPUT_DIR / 'phone_calls_wire.g.dart',
        'schemas': (
            'VerifyPhoneNumberResponse',
            'CheckVerificationResponse',
            'PhoneNumberResponse',
            'PhoneNumbersResponse',
            'PhoneMutationResponse',
            'TokenResponse',
        ),
    },
    'people': {
        'output': DEFAULT_OUTPUT_DIR / 'people_wire.g.dart',
        'schemas': ('Person',),
    },
    'imports_integrations': {
        'output': DEFAULT_OUTPUT_DIR / 'imports_integrations_wire.g.dart',
        'schemas': (
            'ImportJobResponse',
            'IntegrationResponse',
        ),
    },
    'wrapped_task_integrations': {
        'output': DEFAULT_OUTPUT_DIR / 'wrapped_task_integrations_wire.g.dart',
        'schemas': (
            'WrappedStatusResponse',
            'GenerateWrappedResponse',
            'TaskIntegrationsResponse',
            'DefaultTaskIntegrationResponse',
        ),
    },
    'subscription_usage': {
        'output': DEFAULT_OUTPUT_DIR / 'subscription_usage_wire.g.dart',
        'schemas': (
            'PlanLimits',
            'Subscription',
            'PricingOption',
            'SubscriptionPlan',
            'PhoneCallQuota',
            'UserSubscriptionResponse',
            'UsageStats',
            'UsageHistoryPoint',
            'UserUsageResponse',
        ),
    },
    'privacy': {
        'output': DEFAULT_OUTPUT_DIR / 'privacy_wire.g.dart',
        'schemas': (
            'MigrationRequest',
            'BatchMigrationRequest',
            'MigrationTargetRequest',
        ),
    },
    'announcements': {
        'output': DEFAULT_OUTPUT_DIR / 'announcements_wire.g.dart',
        'schemas': (
            'Targeting',
            'Display',
            'Announcement',
        ),
    },
}
ALIASES = {
    'Structured': {'action_items': ('actionItems',)},
    'Event': {'start': ('startsAt',)},
    'AppResult': {'app_id': ('appId',)},
    'Geolocation': {'google_place_id': ('googlePlaceId',), 'location_type': ('locationType',)},
}


@dataclass(frozen=True)
class DartType:
    name: str
    nullable: bool = False
    list_item: 'DartType | None' = None
    ref_schema: str | None = None
    is_date_time: bool = False
    is_map: bool = False

    @property
    def annotation(self) -> str:
        suffix = '?' if self.nullable else ''
        return f'{self.name}{suffix}'


@dataclass(frozen=True)
class Field:
    wire_name: str
    dart_name: str
    dart_type: DartType
    required: bool
    default: Any
    aliases: tuple[str, ...]


def snake_to_camel(value: str) -> str:
    parts = value.split('_')
    return parts[0] + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def generated_class_name(schema_name: str) -> str:
    return f'Generated{schema_name}'


def unwrap_nullable(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    any_of = schema.get('anyOf')
    if not isinstance(any_of, list):
        return schema, False
    non_null = [item for item in any_of if item.get('type') != 'null']
    if len(non_null) == 1 and len(non_null) != len(any_of):
        return non_null[0], True
    return schema, False


def dart_type_for(
    schema: dict[str, Any],
    required: bool,
    target_schemas: tuple[str, ...],
    all_schemas: dict[str, Any],
) -> DartType:
    unwrapped, nullable = unwrap_nullable(schema)
    nullable = nullable or not required
    ref = unwrapped.get('$ref')
    if isinstance(ref, str):
        schema_name = ref.rsplit('/', 1)[-1]
        if schema_name in target_schemas:
            return DartType(generated_class_name(schema_name), nullable=nullable, ref_schema=schema_name)
        ref_schema = all_schemas.get(schema_name, {})
        if ref_schema.get('type') == 'string':
            return DartType('String', nullable=nullable)
        raise ValueError(f'$ref target {schema_name} is not in selected Dart schema group')

    schema_type = unwrapped.get('type')
    if unwrapped.get('format') == 'date-time':
        return DartType('DateTime', nullable=nullable, is_date_time=True)
    if schema_type == 'array':
        item_type = dart_type_for(unwrapped.get('items', {'type': 'object'}), True, target_schemas, all_schemas)
        return DartType(f'List<{item_type.name}>', nullable=nullable, list_item=item_type)
    if schema_type == 'integer':
        return DartType('int', nullable=nullable)
    if schema_type == 'number':
        return DartType('double', nullable=nullable)
    if schema_type == 'boolean':
        return DartType('bool', nullable=nullable)
    if schema_type == 'object' or unwrapped.get('additionalProperties') is not None:
        return DartType('Map<String, dynamic>', nullable=nullable, is_map=True)
    return DartType('String', nullable=nullable)


def default_for(field: Field) -> str:
    if field.dart_type.ref_schema and isinstance(field.default, dict):
        return f'{field.dart_type.name}.fromJson(const {{}})'
    if field.default is not None:
        return dart_literal(field.default)
    if field.dart_type.list_item:
        return 'null' if field.dart_type.nullable else 'const []'
    if field.dart_type.name == 'String' and not field.dart_type.nullable:
        return "''"
    if field.dart_type.name == 'int' and not field.dart_type.nullable:
        return '0'
    if field.dart_type.name == 'double' and not field.dart_type.nullable:
        return '0.0'
    if field.dart_type.name == 'bool' and not field.dart_type.nullable:
        return 'false'
    if field.dart_type.is_date_time and not field.dart_type.nullable:
        return 'DateTime.fromMillisecondsSinceEpoch(0)'
    if field.dart_type.ref_schema and not field.dart_type.nullable:
        if field.dart_type.ref_schema == 'Structured':
            return 'GeneratedStructured.fromJson(const {})'
    return 'null'


def dart_literal(value: Any) -> str:
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if value is None:
        return 'null'
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return 'const []'
    return str(value)


def read_key_expr(field: Field) -> str:
    names = (field.wire_name,) + field.aliases
    quoted = ', '.join(json.dumps(name) for name in names)
    return f'_readAny(json, const [{quoted}])'


def read_expr(field: Field) -> str:
    value = read_key_expr(field)
    typ = field.dart_type
    default = default_for(field)
    has_schema_default = field.default is not None
    if typ.list_item:
        item = typ.list_item
        nullable_prefix = f'{value} == null ? null : ' if typ.nullable else ''
        if item.ref_schema:
            expr = f'{nullable_prefix}_readObjectList({value}, {item.name}.fromJson)'
            return (
                f'_required({expr}, {json.dumps(field.wire_name)})'
                if field.required and not has_schema_default
                else expr
            )
        if item.name == 'String':
            expr = f'{nullable_prefix}_readStringList({value})'
            return (
                f'_required({expr}, {json.dumps(field.wire_name)})'
                if field.required and not has_schema_default
                else expr
            )
        if item.name == 'double':
            expr = f'{nullable_prefix}_readDoubleList({value})'
            return (
                f'_required({expr}, {json.dumps(field.wire_name)})'
                if field.required and not has_schema_default
                else expr
            )
        if item.name == 'int':
            expr = f'{nullable_prefix}_readIntList({value})'
            return (
                f'_required({expr}, {json.dumps(field.wire_name)})'
                if field.required and not has_schema_default
                else expr
            )
        expr = f'{nullable_prefix}_readDynamicList({value})'
        return (
            f'_required({expr}, {json.dumps(field.wire_name)})' if field.required and not has_schema_default else expr
        )
    if typ.ref_schema:
        if typ.nullable:
            return f'_readObject({value}, {typ.name}.fromJson)'
        expr = f'_readObject({value}, {typ.name}.fromJson)'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    if typ.is_date_time:
        if typ.nullable:
            return f'_readDateTime({value})'
        expr = f'_readDateTime({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    if typ.is_map:
        if typ.nullable:
            return f'_readMap({value})'
        expr = f'_readMap({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? const {{}}'
    if typ.name == 'String':
        if typ.nullable and field.default is None:
            return f'_readString({value})'
        expr = f'_readString({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    if typ.name == 'int':
        if typ.nullable and field.default is None:
            return f'_readInt({value})'
        expr = f'_readInt({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    if typ.name == 'double':
        if typ.nullable and field.default is None:
            return f'_readDouble({value})'
        expr = f'_readDouble({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    if typ.name == 'bool':
        if typ.nullable and field.default is None:
            return f'_readBool({value})'
        expr = f'_readBool({value})'
        if field.required and not has_schema_default:
            return f'_required({expr}, {json.dumps(field.wire_name)})'
        return f'{expr} ?? {default}'
    return value


def to_json_expr(field: Field) -> str:
    name = field.dart_name
    typ = field.dart_type
    if typ.list_item:
        item = typ.list_item
        if item.ref_schema:
            if typ.nullable:
                return f'{name}?.map((value) => value.toJson()).toList()'
            return f'{name}.map((value) => value.toJson()).toList()'
        return name
    if typ.ref_schema:
        return f'{name}?.toJson()' if typ.nullable else f'{name}.toJson()'
    if typ.is_date_time:
        return f'{name}?.toUtc().toIso8601String()' if typ.nullable else f'{name}.toUtc().toIso8601String()'
    return name


def fields_for_schema(
    schema_name: str,
    schema: dict[str, Any],
    target_schemas: tuple[str, ...],
    all_schemas: dict[str, Any],
) -> list[Field]:
    required = set(schema.get('required', []))
    fields: list[Field] = []
    for wire_name, prop_schema in schema.get('properties', {}).items():
        is_required = wire_name in required or prop_schema.get('default') is not None
        fields.append(
            Field(
                wire_name=wire_name,
                dart_name=snake_to_camel(wire_name),
                dart_type=dart_type_for(prop_schema, is_required, target_schemas, all_schemas),
                required=is_required,
                default=prop_schema.get('default'),
                aliases=ALIASES.get(schema_name, {}).get(wire_name, ()),
            )
        )
    return fields


def emit_class(schema_name: str, fields: list[Field]) -> str:
    class_name = generated_class_name(schema_name)
    lines = [f'class {class_name} {{']
    for field in fields:
        lines.append(f'  final {field.dart_type.annotation} {field.dart_name};')
    lines.append('')
    lines.append(f'  const {class_name}({{')
    for field in fields:
        required = 'required ' if field.required or not field.dart_type.nullable else ''
        default = ''
        if not required and field.dart_type.list_item and not field.dart_type.nullable:
            default = ' = const []'
        lines.append(f'    {required}this.{field.dart_name}{default},')
    lines.append('  });')
    lines.append('')
    lines.append(f'  factory {class_name}.fromJson(Map<String, dynamic> json) {{')
    lines.append(f'    return {class_name}(')
    for field in fields:
        lines.append(f'      {field.dart_name}: {read_expr(field)},')
    lines.append('    );')
    lines.append('  }')
    lines.append('')
    lines.append('  Map<String, dynamic> toJson() {')
    lines.append('    return {')
    for field in fields:
        lines.append(f"      '{field.wire_name}': {to_json_expr(field)},")
    lines.append('    };')
    lines.append('  }')
    lines.append('}')
    return '\n'.join(lines)


def emit_helpers() -> str:
    return r'''
dynamic _readAny(Map<String, dynamic> json, List<String> names) {
  for (final name in names) {
    if (json.containsKey(name)) return json[name];
  }
  return null;
}

String? _readString(dynamic value) => value?.toString();

int? _readInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

double? _readDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

bool? _readBool(dynamic value) {
  if (value is bool) return value;
  if (value is String) return value.toLowerCase() == 'true';
  return null;
}

T _required<T>(T? value, String name) {
  if (value == null) {
    throw FormatException('Missing required field: $name');
  }
  return value;
}

DateTime? _readDateTime(dynamic value) {
  if (value == null) return null;
  if (value is int) return DateTime.fromMillisecondsSinceEpoch(value * 1000).toLocal();
  if (value is num) return DateTime.fromMillisecondsSinceEpoch((value * 1000).round()).toLocal();
  return DateTime.tryParse(value.toString())?.toLocal();
}

Map<String, dynamic>? _readMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
}

T? _readObject<T>(dynamic value, T Function(Map<String, dynamic>) fromJson) {
  final map = _readMap(value);
  return map == null ? null : fromJson(map);
}

List<T> _readObjectList<T>(dynamic value, T Function(Map<String, dynamic>) fromJson) {
  if (value is! List) return const [];
  return value.map(_readMap).whereType<Map<String, dynamic>>().map(fromJson).toList();
}

List<String> _readStringList(dynamic value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}

List<double> _readDoubleList(dynamic value) {
  if (value is! List) return const [];
  return value.map(_readDouble).whereType<double>().toList();
}

List<int> _readIntList(dynamic value) {
  if (value is! List) return const [];
  return value.map(_readInt).whereType<int>().toList();
}

List<dynamic> _readDynamicList(dynamic value) => value is List ? value : const [];
'''.strip()


def build_output(spec: dict[str, Any], group: str = 'conversation') -> str:
    if group not in SCHEMA_GROUPS:
        raise ValueError(f'unknown Dart generation group: {group}')
    target_schemas = SCHEMA_GROUPS[group]['schemas']
    schemas = spec.get('components', {}).get('schemas', {})
    missing = [name for name in target_schemas if name not in schemas]
    if missing:
        raise ValueError('missing OpenAPI schemas: ' + ', '.join(missing))

    chunks = [
        '// GENERATED CODE - DO NOT EDIT.',
        '// ignore_for_file: unused_element',
        f'// Generated by backend/scripts/generate_dart_models.py --group {group} from docs/api-reference/app-client-openapi.json.',
        '',
    ]
    for schema_name in target_schemas:
        chunks.append(
            emit_class(schema_name, fields_for_schema(schema_name, schemas[schema_name], target_schemas, schemas))
        )
        chunks.append('')
    chunks.append(emit_helpers())
    chunks.append('')
    return '\n'.join(chunks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate Dart app-client wire DTOs.')
    parser.add_argument('--spec', default=str(DEFAULT_SPEC_PATH), help='app-client OpenAPI spec path')
    parser.add_argument(
        '--group',
        choices=tuple(SCHEMA_GROUPS),
        default='conversation',
        help='schema group to generate',
    )
    parser.add_argument('--all', action='store_true', help='generate or check every schema group')
    parser.add_argument('--output', default=None, help='Dart output path; defaults to the selected group output')
    parser.add_argument('--check', action='store_true', help='fail if generated output is stale')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all and args.output:
        raise SystemExit('--output cannot be used with --all')

    spec = json.loads(Path(args.spec).read_text())
    groups = tuple(SCHEMA_GROUPS) if args.all else (args.group,)
    for group in groups:
        output_path = Path(args.output) if args.output else SCHEMA_GROUPS[group]['output']
        generated = build_output(spec, group)
        if args.check:
            if not output_path.exists() or output_path.read_text() != generated:
                raise SystemExit(f'{output_path} is stale; run backend/scripts/generate_dart_models.py --group {group}')
            print(f'{output_path} is up to date')
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated)
        print(f'wrote {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
