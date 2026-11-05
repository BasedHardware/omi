#!/usr/bin/env python3
"""Generate Kotlin (kotlinx.serialization) DTOs from the Omi app-client OpenAPI spec.

Mirrors backend/scripts/generate_swift_openapi_types.py so that the
Android wire DTOs carry the SAME type names, property names, enum case names
and optionality as the Swift `OmiAPI` namespace in omi-native. Hand-ported
Swift code (`dto.category?.rawValue`, `dto.subjectAttribution == ._unknown`,
`OmiAPI.MemoryDB`) therefore translates mechanically.

The schema selection (TARGET_SCHEMAS, PRESENCE_AWARE_PATCH_SCHEMAS, transitive
$ref collection) and the type/optionality mapping are loaded from the Swift
generator itself, so the two outputs cannot drift apart. Only the rendering
is Kotlin specific. Client methods are not generated (DTOs only).

Usage:
  python3 Tools/api/generate_kotlin_openapi_types.py            # write
  python3 Tools/api/generate_kotlin_openapi_types.py --check    # exit 1 if stale

Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ANDROID_ROOT = Path(__file__).resolve().parents[2]
# Inside the Omi repository the backend is two levels up and the iOS app next to this one (`../ios`);
# in separate checkouts they are the repos omi-fresh and omi-native in ~/CODING.
UPSTREAM_ROOT = ANDROID_ROOT.parents[1] if (ANDROID_ROOT.parents[1] / 'backend').is_dir() else Path.home() / 'CODING' / 'omi-fresh'
IOS_ROOT = ANDROID_ROOT.parent / 'ios' if (ANDROID_ROOT.parent / 'ios').is_dir() else Path.home() / 'CODING' / 'omi-native'
DEFAULT_SWIFT_GENERATOR = Path(
    os.environ.get('OMI_SWIFT_GENERATOR', str(UPSTREAM_ROOT / 'backend' / 'scripts' / 'generate_swift_openapi_types.py'))
)
DEFAULT_OUTPUT = (
    ANDROID_ROOT / 'network' / 'src' / 'main' / 'kotlin' / 'com' / 'friend' / 'ios' / 'network' / 'generated' / 'OmiApi.kt'
)
PACKAGE = 'com.friend.ios.network.generated'
# omi-native's backend patches carry a spec half (docs/backend-patches/*.openapi.json); both apps'
# generators read the spec through it, so a field a patch adds is generated on iOS and Android alike.
BACKEND_PATCHES = Path(os.environ.get('OMI_BACKEND_PATCHES', str(IOS_ROOT / 'Tools' / 'api' / 'backend_patches.py')))

# Kotlin hard keywords. Identifiers that collide are emitted in backticks so the
# Kotlin name stays identical to the Swift name.
KOTLIN_HARD_KEYWORDS = {
    'as', 'break', 'class', 'continue', 'do', 'else', 'false', 'for', 'fun', 'if', 'in',
    'interface', 'is', 'null', 'object', 'package', 'return', 'super', 'this', 'throw',
    'true', 'try', 'typealias', 'typeof', 'val', 'var', 'when', 'while',
}

SWIFT_TO_KOTLIN_SCALARS = {
    'String': 'String',
    'Int': 'Int',
    'Double': 'Double',
    'Bool': 'Boolean',
    'OmiAnyCodable': 'OmiAnyCodable',
}

# Swift-side special unions. Their Kotlin variant classes use the Swift case
# names with an upper-case first letter (Swift `.taskCreate(x)` -> Kotlin
# `CandidateCreate.TaskCreate(value = x)`).
CANDIDATE_CREATE_ARMS = (
    # (variant, payload type, subject_kind, proposed_action)
    ('TaskCreate', 'TaskCreateCandidate', 'task', 'create'),
    ('TaskUpdate', 'TaskUpdateCandidate', 'task', 'update'),
    ('TaskComplete', 'TaskCompleteCandidate', 'task', 'complete'),
    ('TaskCancel', 'TaskCancelCandidate', 'task', 'cancel'),
    ('TaskSupersede', 'TaskSupersedeCandidate', 'task', 'supersede'),
    ('WorkstreamCreate', 'WorkstreamCreateCandidate', 'workstream', 'create'),
)


def load_swift_generator(path: Path) -> ModuleType:
    """Import the Swift generator by file path. It has no import-time side effects
    (main() is guarded), so exec_module is safe and avoids copying its lists."""
    if not path.is_file():
        raise SystemExit(f'Swift generator not found: {path} (set --swift-generator or OMI_SWIFT_GENERATOR)')
    spec = importlib.util.spec_from_file_location('omi_swift_openapi_generator', path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ('TARGET_SCHEMAS', 'PRESENCE_AWARE_PATCH_SCHEMAS', '_collect_deps', '_swift_type',
                 '_swift_type_name', '_swift_prop_name', 'SWIFT_RESERVED'):
        if not hasattr(module, attr):
            raise SystemExit(f'{path} no longer exposes {attr}; update generate_kotlin_openapi_types.py')
    return module


# Modifier and soft keywords are legal identifiers in most positions but can be
# misparsed (e.g. an enum entry `external(...)`), so they are escaped too.
KOTLIN_SOFT_AND_MODIFIER_KEYWORDS = {
    'abstract', 'actual', 'annotation', 'by', 'catch', 'companion', 'const', 'constructor',
    'crossinline', 'data', 'delegate', 'dynamic', 'enum', 'expect', 'external', 'field', 'file',
    'final', 'finally', 'get', 'import', 'infix', 'init', 'inline', 'inner', 'internal',
    'lateinit', 'noinline', 'open', 'operator', 'out', 'override', 'param', 'private',
    'property', 'protected', 'public', 'receiver', 'reified', 'sealed', 'set', 'setparam',
    'suspend', 'tailrec', 'value', 'vararg', 'where',
}


def kt_ident(name: str) -> str:
    if name in KOTLIN_HARD_KEYWORDS or name in KOTLIN_SOFT_AND_MODIFIER_KEYWORDS:
        return f'`{name}`'
    return name


def kt_string(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'


def swift_type_to_kotlin(expr: str) -> str:
    """Translate a Swift type expression from the Swift generator (`[X]`,
    `[String: X]`, scalars, generated names) into Kotlin."""
    expr = expr.strip()
    if expr.startswith('[') and expr.endswith(']'):
        inner = expr[1:-1]
        depth = 0
        for i, ch in enumerate(inner):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
            elif ch == ':' and depth == 0:
                key = swift_type_to_kotlin(inner[:i])
                value = swift_type_to_kotlin(inner[i + 1:])
                return f'Map<{key}, {value}>'
        return f'List<{swift_type_to_kotlin(inner)}>'
    return SWIFT_TO_KOTLIN_SCALARS.get(expr, expr)


def swift_enum_case_name(sw: ModuleType, value: str) -> str:
    """Exactly the Swift generator's enum case naming (see _render_enum)."""
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', value):
        return value if value not in sw.SWIFT_RESERVED else value + '_'
    return re.sub(r'[^A-Za-z0-9_]', '_', value)


class KotlinRenderer:
    def __init__(self, sw: ModuleType, schemas: dict[str, Any]):
        self.sw = sw
        self.schemas = schemas
        self.struct_count = 0
        self.patch_count = 0
        self.enum_count = 0

    # --- fields -------------------------------------------------------------
    def fields(self, schema: dict[str, Any], force_required: bool = False) -> list[tuple[str, str, str, bool]]:
        props = schema.get('properties') or {}
        required = set(schema.get('required') or [])
        out = []
        for wire_name, prop_schema in sorted(props.items()):
            swift_expr, optional = self.sw._swift_type(prop_schema, required=force_required or wire_name in required)
            out.append((self.sw._swift_prop_name(wire_name), wire_name, swift_type_to_kotlin(swift_expr), optional))
        return out

    # --- enums --------------------------------------------------------------
    def render_enum(self, name: str, schema: dict[str, Any]) -> str:
        self.enum_count += 1
        lines = [
            f'@Serializable(with = {name}.Serializer::class)',
            f'enum class {name}(override val rawValue: String) : OmiRawEnum {{',
        ]
        for value in schema.get('enum') or []:
            case = kt_ident(swift_enum_case_name(self.sw, value))
            lines.append(f'    @SerialName({kt_string(value)}) {case}({kt_string(value)}),')
        lines.append('    @SerialName("__unknown__") _unknown("__unknown__");')
        lines.append('')
        lines.append(
            f'    object Serializer : OmiRawEnumSerializer<{name}>'
            f'("{PACKAGE}.OmiAPI.{name}", {name}.entries, {name}._unknown)'
        )
        lines.append('}')
        return '\n'.join(lines) + '\n'

    # --- plain structs ------------------------------------------------------
    def render_struct(self, name: str, schema: dict[str, Any]) -> str:
        self.struct_count += 1
        fields = self.fields(schema)
        lines: list[str] = []
        if name == 'CandidateRecord':
            # task_change is decoded according to proposed_action/subject_kind,
            # exactly like the Swift init(from:). The transforming serializer tags
            # the payload before the plugin-generated serializer sees it.
            lines.append('@KeepGeneratedSerializer')
            lines.append('@Serializable(with = CandidateRecord.Serializer::class)')
        else:
            lines.append('@Serializable')
        if not fields:
            lines.append(f'class {name}')
            return '\n'.join(lines) + '\n'
        lines.append(f'data class {name}(')
        for kt_name, wire_name, kt_type, optional in fields:
            decl = f'    @SerialName({kt_string(wire_name)}) val {kt_ident(kt_name)}: {kt_type}'
            decl += '? = null,' if optional else ','
            lines.append(decl)
        if name == 'CandidateRecord':
            lines.append(') {')
            lines.append('    object Serializer : JsonTransformingSerializer<CandidateRecord>(CandidateRecord.generatedSerializer()) {')
            lines.append('        override fun transformDeserialize(element: JsonElement): JsonElement =')
            lines.append('            CandidateTaskChange.tagInRecord(element)')
            lines.append('    }')
            lines.append('}')
        else:
            lines.append(')')
        return '\n'.join(lines) + '\n'

    # --- tri-state patch structs --------------------------------------------
    def render_patch_struct(self, name: str, schema: dict[str, Any]) -> str:
        self.patch_count += 1
        fields = self.fields(schema, force_required=True)
        lines = ['@Serializable', f'data class {name}(']
        for kt_name, wire_name, kt_type, _ in fields:
            lines.append(
                f'    @SerialName({kt_string(wire_name)}) @EncodeDefault(EncodeDefault.Mode.NEVER) '
                f'val {kt_ident(kt_name)}: OmiPatchField<{kt_type}> = OmiPatchField.Omitted,'
            )
        lines.append(')')
        return '\n'.join(lines) + '\n'


HEADER = '''// Generated, do not edit.
// Generated by Tools/api/generate_kotlin_openapi_types.py from {spec_label}
// (schema selection and type mapping come from {swift_label}).
// Kotlin wire DTOs mirroring the Swift `OmiAPI` namespace in omi-native: same
// type names, property names, enum case names and optionality. Dates stay
// String (parse with BackendDate). Decode with `OmiJson`.
@file:OptIn(ExperimentalSerializationApi::class)
@file:Suppress(
    "ktlint",
    "EnumEntryName",
    "ClassName",
    "PropertyName",
    "unused",
    "RedundantVisibilityModifier",
)

package {package}

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.KeepGeneratedSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.buildClassSerialDescriptor
import kotlinx.serialization.descriptors.nullable
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonTransformingSerializer
import kotlinx.serialization.json.contentOrNull

/** Opaque backend JSON value (Swift `OmiAnyCodable`). */
typealias OmiAnyCodable = JsonElement

/**
 * Namespace for generated backend REST wire DTOs (Swift `enum OmiAPI`).
 * Domain models adapt from `OmiAPI.*` types.
 */
object OmiAPI {

'''

CANDIDATE_TASK_CHANGE = '''/**
 * Swift `CandidateTaskChange`: `.create(TaskCreatePayload)` / `.change(TaskChangePayload)`.
 * Standalone decoding tries TaskCreatePayload first, then TaskChangePayload. Inside
 * CandidateRecord the arm is chosen from proposed_action/subject_kind (see tagInRecord).
 */
@Serializable(with = CandidateTaskChange.Serializer::class)
sealed class CandidateTaskChange {
    data class Create(val value: TaskCreatePayload) : CandidateTaskChange()
    data class Change(val value: TaskChangePayload) : CandidateTaskChange()

    object Serializer : KSerializer<CandidateTaskChange> {
        override val descriptor: SerialDescriptor = buildClassSerialDescriptor("$PACKAGE.OmiAPI.CandidateTaskChange")

        override fun deserialize(decoder: Decoder): CandidateTaskChange {
            val json = (decoder as? JsonDecoder)
                ?: throw SerializationException("CandidateTaskChange can only be decoded from JSON")
            val element = json.decodeJsonElement()
            val obj = element as? JsonObject
            val variant = (obj?.get(VARIANT_KEY) as? JsonPrimitive)?.contentOrNull
            if (obj != null && variant != null) {
                val payload = obj[VALUE_KEY] ?: JsonNull
                return when (variant) {
                    "create" -> Create(json.json.decodeFromJsonElement(TaskCreatePayload.serializer(), payload))
                    else -> Change(json.json.decodeFromJsonElement(TaskChangePayload.serializer(), payload))
                }
            }
            return try {
                Create(json.json.decodeFromJsonElement(TaskCreatePayload.serializer(), element))
            } catch (e: IllegalArgumentException) {
                // SerializationException (incl. missing required fields) is an
                // IllegalArgumentException: fall back like Swift's `try?`.
                Change(json.json.decodeFromJsonElement(TaskChangePayload.serializer(), element))
            }
        }

        override fun serialize(encoder: Encoder, value: CandidateTaskChange) {
            when (value) {
                is Create -> encoder.encodeSerializableValue(TaskCreatePayload.serializer(), value.value)
                is Change -> encoder.encodeSerializableValue(TaskChangePayload.serializer(), value.value)
            }
        }
    }

    companion object {
        private const val VARIANT_KEY = "__omi_task_change_variant"
        private const val VALUE_KEY = "__omi_task_change_value"

        /**
         * Mirrors the Swift CandidateRecord init(from:): task_change decodes as
         * `.create` when proposed_action == create and subject_kind == task, as
         * `.change` for update/complete/cancel/supersede, and as null otherwise.
         */
        fun tagInRecord(element: JsonElement): JsonElement {
            val record = element as? JsonObject ?: return element
            val taskChange = record["task_change"]
            if (taskChange == null || taskChange is JsonNull) return element
            val action = (record["proposed_action"] as? JsonPrimitive)?.contentOrNull
            val subjectKind = (record["subject_kind"] as? JsonPrimitive)?.contentOrNull
            val variant = when {
                action == "create" && subjectKind == "task" -> "create"
                action == "update" || action == "complete" || action == "cancel" || action == "supersede" -> "change"
                else -> null
            }
            val tagged: JsonElement = if (variant == null) {
                JsonNull
            } else {
                JsonObject(mapOf(VARIANT_KEY to JsonPrimitive(variant), VALUE_KEY to taskChange))
            }
            return JsonObject(record + ("task_change" to tagged))
        }
    }
}

'''


def render_candidate_create() -> str:
    lines = [
        '/**',
        ' * Swift `CandidateCreate`: strict request union discriminated by',
        ' * (subject_kind, proposed_action). Unknown combinations fail to decode, as in Swift.',
        ' */',
        '@Serializable(with = CandidateCreate.Serializer::class)',
        'sealed class CandidateCreate {',
    ]
    for variant, payload, _, _ in CANDIDATE_CREATE_ARMS:
        lines.append(f'    data class {variant}(val value: {payload}) : CandidateCreate()')
    lines += [
        '',
        '    object Serializer : KSerializer<CandidateCreate> {',
        '        override val descriptor: SerialDescriptor = buildClassSerialDescriptor("$PACKAGE.OmiAPI.CandidateCreate")',
        '',
        '        override fun deserialize(decoder: Decoder): CandidateCreate {',
        '            val json = (decoder as? JsonDecoder)',
        '                ?: throw SerializationException("CandidateCreate can only be decoded from JSON")',
        '            val element = json.decodeJsonElement()',
        '            val obj = element as? JsonObject ?: throw SerializationException("CandidateCreate must be a JSON object")',
        '            val subjectKind = (obj["subject_kind"] as? JsonPrimitive)?.contentOrNull',
        '                ?: throw SerializationException("CandidateCreate is missing subject_kind")',
        '            val proposedAction = (obj["proposed_action"] as? JsonPrimitive)?.contentOrNull',
        '                ?: throw SerializationException("CandidateCreate is missing proposed_action")',
        '            return when (subjectKind to proposedAction) {',
    ]
    for variant, payload, kind, action in CANDIDATE_CREATE_ARMS:
        lines.append(
            f'                "{kind}" to "{action}" -> '
            f'{variant}(json.json.decodeFromJsonElement({payload}.serializer(), element))'
        )
    lines += [
        '                else -> throw SerializationException("Unsupported Candidate discriminator")',
        '            }',
        '        }',
        '',
        '        override fun serialize(encoder: Encoder, value: CandidateCreate) {',
        '            when (value) {',
    ]
    for variant, payload, _, _ in CANDIDATE_CREATE_ARMS:
        lines.append(f'                is {variant} -> encoder.encodeSerializableValue({payload}.serializer(), value.value)')
    lines += [
        '            }',
        '        }',
        '    }',
        '}',
        '',
    ]
    return '\n'.join(lines) + '\n'


PATCH_FIELD = '''/**
 * Swift `OmiPatchField`: tri-state PATCH field. `Omitted` is never encoded (the key
 * is left out), `Null` encodes an explicit JSON null, `Value` encodes the value.
 * Decoding: absent key -> Omitted, null -> Null, anything else -> Value.
 */
@Serializable(with = OmiPatchFieldSerializer::class)
sealed interface OmiPatchField<out T> {
    data object Omitted : OmiPatchField<Nothing>
    data object Null : OmiPatchField<Nothing>
    data class Value<out T>(val value: T) : OmiPatchField<T>
}

class OmiPatchFieldSerializer<T>(private val valueSerializer: KSerializer<T>) : KSerializer<OmiPatchField<T>> {
    // Reported as nullable so OmiJson's coerceInputValues never turns an explicit
    // null into the Omitted default.
    override val descriptor: SerialDescriptor = valueSerializer.descriptor.nullable

    override fun deserialize(decoder: Decoder): OmiPatchField<T> {
        if (decoder is JsonDecoder) {
            val element = decoder.decodeJsonElement()
            return if (element is JsonNull) {
                OmiPatchField.Null
            } else {
                OmiPatchField.Value(decoder.json.decodeFromJsonElement(valueSerializer, element))
            }
        }
        return if (decoder.decodeNotNullMark()) {
            OmiPatchField.Value(decoder.decodeSerializableValue(valueSerializer))
        } else {
            decoder.decodeNull()
            OmiPatchField.Null
        }
    }

    override fun serialize(encoder: Encoder, value: OmiPatchField<T>) {
        when (value) {
            is OmiPatchField.Value -> {
                encoder.encodeNotNullMark()
                encoder.encodeSerializableValue(valueSerializer, value.value)
            }
            // Omitted is the @EncodeDefault(NEVER) default and never reaches here
            // through generated serializers; treat a stray one like Swift (nil).
            OmiPatchField.Null, OmiPatchField.Omitted -> encoder.encodeNull()
        }
    }
}

'''


def indent(block: str, prefix: str = '    ') -> str:
    return '\n'.join((prefix + line) if line else line for line in block.split('\n'))


def generate(sw: ModuleType, spec: dict[str, Any], spec_label: str, swift_label: str) -> tuple[str, KotlinRenderer]:
    schemas = spec.get('components', {}).get('schemas', {})
    targets = tuple(t for t in sw.TARGET_SCHEMAS if t in schemas)
    names = sw._collect_deps(schemas, targets)
    renderer = KotlinRenderer(sw, schemas)

    out = [HEADER.replace('{spec_label}', spec_label).replace('{swift_label}', swift_label).replace('{package}', PACKAGE)]
    out.append(indent(CANDIDATE_TASK_CHANGE.replace('$PACKAGE', PACKAGE)))
    out.append(indent(render_candidate_create().replace('$PACKAGE', PACKAGE)))
    out.append(indent(PATCH_FIELD))
    skipped: list[str] = []
    for name in names:
        schema = schemas[name]
        type_name = sw._swift_type_name(name)
        if schema.get('type') == 'string' and 'enum' in schema:
            block = renderer.render_enum(type_name, schema)
        elif schema.get('type') == 'object' or 'properties' in schema:
            if name in sw.PRESENCE_AWARE_PATCH_SCHEMAS:
                block = renderer.render_patch_struct(type_name, schema)
            else:
                block = renderer.render_struct(type_name, schema)
        else:
            # Same as Swift: non-object, non-enum schemas (CandidateCreate is
            # hand-rendered above; TaskCandidate is only reachable through it).
            skipped.append(name)
            continue
        out.append(indent(block) + '\n')
    out.append('}\n')
    text = ''.join(out)
    # Normalise: no trailing whitespace, single trailing newline.
    text = '\n'.join(line.rstrip() for line in text.split('\n')).rstrip('\n') + '\n'
    renderer.skipped = skipped  # type: ignore[attr-defined]
    return text, renderer


def label_for(path: Path, *roots: Path) -> str:
    for root in roots:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Generate Kotlin OmiAPI DTOs from the Omi OpenAPI spec.')
    p.add_argument('--swift-generator', type=Path, default=DEFAULT_SWIFT_GENERATOR,
                   help='path to backend/scripts/generate_swift_openapi_types.py')
    p.add_argument('--spec', type=Path, default=None,
                   help='OpenAPI spec (default: the Swift generator\'s DEFAULT_SPEC_PATH)')
    p.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    p.add_argument('--check', action='store_true', help='exit 1 if the generated file is stale')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    sw = load_swift_generator(args.swift_generator)
    spec_path: Path = args.spec or Path(sw.DEFAULT_SPEC_PATH)
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    patches_module = importlib.util.spec_from_file_location('omi_backend_patches', BACKEND_PATCHES)
    if patches_module is None or patches_module.loader is None:
        raise SystemExit(f'cannot load {BACKEND_PATCHES}')
    backend_patches = importlib.util.module_from_spec(patches_module)
    patches_module.loader.exec_module(backend_patches)
    spec, patches = backend_patches.apply(spec)
    swift_root = Path(sw.ROOT_DIR)
    generated, renderer = generate(
        sw,
        spec,
        spec_label=label_for(spec_path, swift_root) + ''.join(f' + docs/backend-patches/{p}' for p in patches),
        swift_label=label_for(args.swift_generator, swift_root),
    )

    if args.check:
        existing = args.out.read_text(encoding='utf-8') if args.out.exists() else ''
        if existing != generated:
            print(f'{label_for(args.out, ANDROID_ROOT)} is out of date. Run: python3 Tools/api/{Path(__file__).name}',
                  file=sys.stderr)
            return 1
        print(f'{label_for(args.out, ANDROID_ROOT)} is up to date')
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(generated, encoding='utf-8', newline='\n')
    print(
        f'wrote {label_for(args.out, ANDROID_ROOT)}: {renderer.struct_count} data classes, '
        f'{renderer.patch_count} tri-state patch classes, {renderer.enum_count} enums, '
        f'2 sealed unions; skipped (same as Swift): {", ".join(renderer.skipped) or "none"}'  # type: ignore[attr-defined]
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
