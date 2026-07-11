#!/usr/bin/env python3
"""Reject app-client OpenAPI changes that break already released clients.

Compatibility is directional:

* requests described by the base contract must still be accepted by the head;
* responses described by the head must remain decodable by the base contract.

The checker intentionally has no third-party dependencies so it can run before the
OpenAPI export environment is installed.  Local JSON references are resolved while
walking operations, including recursive schemas.  New operations, optional request
fields, and response fields are additive and therefore allowed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = ROOT / 'docs/api-reference/app-client-openapi.json'
HTTP_METHODS = frozenset({'get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'})
Schema = dict[str, Any]
Direction = Literal['request', 'response']


class OpenAPICompatibilityError(RuntimeError):
    """The contracts cannot be compared safely."""


@dataclass(frozen=True, order=True)
class CompatibilityIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f'{self.path}: {self.message}'


class LocalReferenceResolver:
    def __init__(self, document: Schema, *, label: str):
        self.document = document
        self.label = label

    def resolve(self, value: object) -> object:
        current = value
        followed: set[str] = set()
        while isinstance(current, dict) and '$ref' in current:
            ref = current.get('$ref')
            if not isinstance(ref, str) or not ref.startswith('#/'):
                raise OpenAPICompatibilityError(f'{self.label}: only local $ref values are supported; found {ref!r}')
            if ref in followed:
                # A direct reference loop has no concrete schema to compare.
                raise OpenAPICompatibilityError(f'{self.label}: cyclic $ref chain at {ref}')
            followed.add(ref)
            target: object = self.document
            for encoded_part in ref[2:].split('/'):
                part = encoded_part.replace('~1', '/').replace('~0', '~')
                if not isinstance(target, dict) or part not in target:
                    raise OpenAPICompatibilityError(f'{self.label}: unresolved local $ref {ref}')
                target = target[part]
            siblings = {key: item for key, item in current.items() if key != '$ref'}
            if siblings:
                if not isinstance(target, dict):
                    raise OpenAPICompatibilityError(f'{self.label}: $ref {ref} does not resolve to an object')
                current = {**target, **siblings}
            else:
                current = target
        return current


class CompatibilityChecker:
    def __init__(self, base: Schema, head: Schema):
        self.base = base
        self.head = head
        self.base_refs = LocalReferenceResolver(base, label='base contract')
        self.head_refs = LocalReferenceResolver(head, label='head contract')
        self.issues: list[CompatibilityIssue] = []

    def check(self) -> list[CompatibilityIssue]:
        base_paths = _mapping(self.base.get('paths'))
        head_paths = _mapping(self.head.get('paths'))
        for route in sorted(base_paths):
            base_path_item = _mapping(self.base_refs.resolve(base_paths[route]))
            head_raw = head_paths.get(route)
            if head_raw is None:
                self._issue(f'paths.{route}', 'released endpoint was removed')
                continue
            head_path_item = _mapping(self.head_refs.resolve(head_raw))
            for method in sorted(HTTP_METHODS.intersection(base_path_item)):
                operation_path = f'paths.{route}.{method}'
                if method not in head_path_item:
                    self._issue(operation_path, 'released operation was removed')
                    continue
                base_operation = _mapping(self.base_refs.resolve(base_path_item[method]))
                head_operation = _mapping(self.head_refs.resolve(head_path_item[method]))
                self._check_security(base_operation, head_operation, operation_path)
                self._check_parameters(
                    base_path_item,
                    base_operation,
                    head_path_item,
                    head_operation,
                    operation_path,
                )
                self._check_request_body(base_operation, head_operation, operation_path)
                self._check_responses(base_operation, head_operation, operation_path)
        return sorted(set(self.issues))

    def _issue(self, path: str, message: str) -> None:
        self.issues.append(CompatibilityIssue(path, message))

    def _check_security(self, base_op: Schema, head_op: Schema, path: str) -> None:
        if 'security' not in head_op:
            return
        base_security = base_op.get('security')
        head_security = head_op.get('security')
        if base_security is None:
            # Global security is deliberately not inferred here: exported app-client
            # operations carry their effective requirement when it matters.
            if head_security:
                self._issue(f'{path}.security', 'operation now requires authentication')
            return
        if not isinstance(base_security, list) or not isinstance(head_security, list):
            self._issue(f'{path}.security', 'security requirements changed to an unsupported shape')
            return

        base_alternatives = _security_alternatives(base_security)
        head_alternatives = _security_alternatives(head_security)
        for old_alternative in base_alternatives:
            if not any(
                _security_alternative_is_no_stricter(new_alternative, old_alternative)
                for new_alternative in head_alternatives
            ):
                self._issue(f'{path}.security', 'a released authentication alternative is no longer accepted')
                return

    def _parameters(
        self, path_item: Schema, operation: Schema, resolver: LocalReferenceResolver
    ) -> dict[tuple[str, str], Schema]:
        result: dict[tuple[str, str], Schema] = {}
        for raw in [*_list(path_item.get('parameters')), *_list(operation.get('parameters'))]:
            parameter = _mapping(resolver.resolve(raw))
            name = parameter.get('name')
            location = parameter.get('in')
            if isinstance(name, str) and isinstance(location, str):
                result[(location, name)] = parameter
        return result

    def _check_parameters(
        self,
        base_path_item: Schema,
        base_op: Schema,
        head_path_item: Schema,
        head_op: Schema,
        path: str,
    ) -> None:
        base_parameters = self._parameters(base_path_item, base_op, self.base_refs)
        head_parameters = self._parameters(head_path_item, head_op, self.head_refs)
        for identity in sorted(base_parameters):
            location, name = identity
            parameter_path = f'{path}.parameters.{location}.{name}'
            if identity not in head_parameters:
                self._issue(parameter_path, 'released request parameter was removed or moved')
                continue
            old = base_parameters[identity]
            new = head_parameters[identity]
            if not old.get('required', False) and new.get('required', False):
                self._issue(parameter_path, 'optional request parameter became required')
            self._check_parameter_content(old, new, parameter_path)

        for identity in sorted(set(head_parameters) - set(base_parameters)):
            location, name = identity
            if head_parameters[identity].get('required', False):
                self._issue(
                    f'{path}.parameters.{location}.{name}', 'new required request parameter rejects released clients'
                )

    def _check_parameter_content(self, old: Schema, new: Schema, path: str) -> None:
        if 'schema' in old:
            if 'schema' not in new:
                self._issue(f'{path}.schema', 'parameter schema was removed')
            else:
                self._compare_schema(old['schema'], new['schema'], 'request', f'{path}.schema', set())
            return
        old_content = _mapping(old.get('content'))
        new_content = _mapping(new.get('content'))
        for media_type in sorted(old_content):
            media_path = f'{path}.content.{media_type}'
            if media_type not in new_content:
                self._issue(media_path, 'released parameter media type was removed')
                continue
            self._compare_schema(
                _mapping(old_content[media_type]).get('schema', {}),
                _mapping(new_content[media_type]).get('schema', {}),
                'request',
                f'{media_path}.schema',
                set(),
            )

    def _check_request_body(self, base_op: Schema, head_op: Schema, path: str) -> None:
        old_raw = base_op.get('requestBody')
        new_raw = head_op.get('requestBody')
        body_path = f'{path}.requestBody'
        if old_raw is None:
            if new_raw is not None:
                new = _mapping(self.head_refs.resolve(new_raw))
                if new.get('required', False):
                    self._issue(body_path, 'new required request body rejects released clients')
            return
        if new_raw is None:
            self._issue(body_path, 'released request body was removed')
            return
        old = _mapping(self.base_refs.resolve(old_raw))
        new = _mapping(self.head_refs.resolve(new_raw))
        if not old.get('required', False) and new.get('required', False):
            self._issue(body_path, 'optional request body became required')
        old_content = _mapping(old.get('content'))
        new_content = _mapping(new.get('content'))
        for media_type in sorted(old_content):
            media_path = f'{body_path}.content.{media_type}'
            if media_type not in new_content:
                self._issue(media_path, 'released request media type was removed')
                continue
            self._compare_schema(
                _mapping(old_content[media_type]).get('schema', {}),
                _mapping(new_content[media_type]).get('schema', {}),
                'request',
                f'{media_path}.schema',
                set(),
            )

    def _check_responses(self, base_op: Schema, head_op: Schema, path: str) -> None:
        old_responses = _mapping(base_op.get('responses'))
        new_responses = _mapping(head_op.get('responses'))
        new_successes = sorted(status for status in new_responses if _is_success_status(status))

        for status in new_successes:
            response_path = f'{path}.responses.{status}'
            old_match = _matching_response_key(old_responses, str(status), include_default=True)
            if old_match is None:
                self._issue(response_path, 'new success response status is not modeled by the released client')
                continue
            self._compare_response_content(
                old_responses[old_match],
                new_responses[status],
                response_path,
            )

        if 'default' in new_responses:
            default_path = f'{path}.responses.default'
            if 'default' not in old_responses:
                self._issue(default_path, 'new default response is not modeled by the released client')
            else:
                self._compare_response_content(
                    old_responses['default'],
                    new_responses['default'],
                    default_path,
                )

    def _compare_response_content(self, old_raw: object, new_raw: object, path: str) -> None:
        old = _mapping(self.base_refs.resolve(old_raw))
        new = _mapping(self.head_refs.resolve(new_raw))
        old_content = _mapping(old.get('content'))
        new_content = _mapping(new.get('content'))
        for media_type in sorted(new_content):
            media_path = f'{path}.content.{media_type}'
            if media_type not in old_content:
                self._issue(media_path, 'new success response media type is not modeled by the released client')
                continue
            old_schema = _mapping(old_content[media_type]).get('schema')
            new_schema = _mapping(new_content[media_type]).get('schema')
            if old_schema is not None and new_schema is None:
                self._issue(f'{media_path}.schema', 'success response body schema was removed')
            elif old_schema is not None and new_schema is not None:
                self._compare_schema(old_schema, new_schema, 'response', f'{media_path}.schema', set())

    def _compare_schema(
        self,
        old_raw: object,
        new_raw: object,
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        old = _mapping(self.base_refs.resolve(old_raw))
        new = _mapping(self.head_refs.resolve(new_raw))
        pair = (id(old), id(new), direction)
        if pair in seen:
            return
        seen.add(pair)

        self._compare_compositions(old, new, direction, path, seen)
        if any(key in old or key in new for key in ('oneOf', 'anyOf')):
            # Union membership was compared branch-by-branch above.  Treating the
            # union wrapper as an unconstrained scalar as well would incorrectly
            # reject compatible broadening such as string -> string|null requests.
            return
        self._compare_types(old, new, direction, path)
        self._compare_values(old, new, direction, path)
        self._compare_constraints(old, new, direction, path)
        self._compare_objects(old, new, direction, path, seen)
        self._compare_arrays(old, new, direction, path, seen)

    def _compare_compositions(
        self,
        old: Schema,
        new: Schema,
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        old_union = next((key for key in ('oneOf', 'anyOf') if key in old), None)
        new_union = next((key for key in ('oneOf', 'anyOf') if key in new), None)
        if old_union or new_union:
            if old_union is not None and new_union is not None and old_union != new_union:
                self._issue(path, f'{direction} union kind changed from {old_union or "none"} to {new_union or "none"}')
            else:
                old_branches = _list(old.get(old_union)) if old_union is not None else [old]
                new_branches = _list(new.get(new_union)) if new_union is not None else [new]
                self._compare_union(
                    old_branches,
                    new_branches,
                    direction,
                    f'{path}.{old_union or new_union}',
                    seen,
                )

        if 'allOf' in old or 'allOf' in new:
            old_all = _list(old.get('allOf'))
            new_all = _list(new.get('allOf'))
            if len(old_all) != len(new_all):
                self._issue(
                    f'{path}.allOf',
                    'composed schema branch count changed; compatibility cannot be proven safely',
                )
            else:
                for index, (old_branch, new_branch) in enumerate(zip(old_all, new_all)):
                    self._compare_schema(old_branch, new_branch, direction, f'{path}.allOf[{index}]', seen)

        if old.get('not') != new.get('not') and ('not' in old or 'not' in new):
            self._issue(f'{path}.not', 'negated schema changed; compatibility cannot be proven safely')

    def _compare_union(
        self,
        old_branches: list[Any],
        new_branches: list[Any],
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        source = old_branches if direction == 'request' else new_branches
        candidates = new_branches if direction == 'request' else old_branches
        for index, branch in enumerate(source):
            compatible = False
            for candidate in candidates:
                before = len(self.issues)
                branch_seen = set(seen)
                if direction == 'request':
                    self._compare_schema(branch, candidate, direction, path, branch_seen)
                else:
                    self._compare_schema(candidate, branch, direction, path, branch_seen)
                if len(self.issues) == before:
                    compatible = True
                    break
                del self.issues[before:]
            if not compatible:
                subject = 'released request' if direction == 'request' else 'new response'
                self._issue(f'{path}[{index}]', f'{subject} union branch has no compatible counterpart')

    def _compare_types(self, old: Schema, new: Schema, direction: Direction, path: str) -> None:
        old_types = _schema_types(old)
        new_types = _schema_types(new)
        source_types, accepted_types = (old_types, new_types) if direction == 'request' else (new_types, old_types)
        if accepted_types is None:
            return
        if source_types is None:
            self._issue(f'{path}.type', f'{direction} schema became more permissive than the released contract')
            return
        incompatible = sorted(
            source_type
            for source_type in source_types
            if not any(_type_is_subset(source_type, accepted) for accepted in accepted_types)
        )
        if incompatible:
            self._issue(f'{path}.type', f'{direction} no longer supports type(s): {", ".join(incompatible)}')

    def _compare_values(self, old: Schema, new: Schema, direction: Direction, path: str) -> None:
        old_values = _allowed_values(old)
        new_values = _allowed_values(new)
        source_values, accepted_values = (
            (old_values, new_values) if direction == 'request' else (new_values, old_values)
        )
        if accepted_values is None:
            return
        if source_values is None:
            self._issue(f'{path}.enum', f'{direction} values are no longer bounded by the released enum')
            return
        missing = [value for value in source_values if value not in accepted_values]
        if missing:
            verb = 'no longer accepted' if direction == 'request' else 'not decodable by released clients'
            self._issue(f'{path}.enum', f'value(s) {missing!r} are {verb}')

    def _compare_constraints(self, old: Schema, new: Schema, direction: Direction, path: str) -> None:
        lower_bounds = ('minimum', 'exclusiveMinimum', 'minLength', 'minItems', 'minProperties')
        upper_bounds = ('maximum', 'exclusiveMaximum', 'maxLength', 'maxItems', 'maxProperties')
        for key in lower_bounds:
            self._compare_bound(old, new, direction, path, key, lower=True)
        for key in upper_bounds:
            self._compare_bound(old, new, direction, path, key, lower=False)

        old_pattern, new_pattern = old.get('pattern'), new.get('pattern')
        if direction == 'request' and new_pattern is not None and new_pattern != old_pattern:
            self._issue(f'{path}.pattern', 'request pattern became narrower or changed')
        if direction == 'response' and old_pattern is not None and new_pattern != old_pattern:
            self._issue(f'{path}.pattern', 'response pattern no longer guarantees the released constraint')

        old_format, new_format = old.get('format'), new.get('format')
        if direction == 'request' and new_format is not None and new_format != old_format:
            self._issue(f'{path}.format', 'request format became narrower or changed')
        if direction == 'response' and old_format is not None and new_format != old_format:
            self._issue(f'{path}.format', 'response format no longer matches the released decoder')

    def _compare_bound(
        self,
        old: Schema,
        new: Schema,
        direction: Direction,
        path: str,
        key: str,
        *,
        lower: bool,
    ) -> None:
        old_value, new_value = old.get(key), new.get(key)
        if direction == 'request':
            breaks = new_value is not None and (
                old_value is None or (new_value > old_value if lower else new_value < old_value)
            )
        else:
            breaks = old_value is not None and (
                new_value is None or (new_value < old_value if lower else new_value > old_value)
            )
        if breaks:
            self._issue(f'{path}.{key}', f'{direction} constraint is incompatible with the released contract')

    def _compare_objects(
        self,
        old: Schema,
        new: Schema,
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        old_properties = _mapping(old.get('properties'))
        new_properties = _mapping(new.get('properties'))
        if (
            not old_properties
            and not new_properties
            and 'additionalProperties' not in old
            and 'additionalProperties' not in new
        ):
            return
        old_required = {item for item in _list(old.get('required')) if isinstance(item, str)}
        new_required = {item for item in _list(new.get('required')) if isinstance(item, str)}

        if direction == 'request':
            for name in sorted(old_properties):
                property_path = f'{path}.properties.{name}'
                if name not in new_properties:
                    self._issue(property_path, 'released request property was removed')
                else:
                    self._compare_schema(old_properties[name], new_properties[name], direction, property_path, seen)
            for name in sorted(new_required - old_required):
                self._issue(f'{path}.properties.{name}', 'new required request property rejects released clients')
        else:
            for name in sorted(set(old_properties).intersection(new_properties)):
                self._compare_schema(
                    old_properties[name],
                    new_properties[name],
                    direction,
                    f'{path}.properties.{name}',
                    seen,
                )
            # An allOf branch may declare a property required while a sibling branch
            # owns its schema.  Compare the guarantee where the property is defined;
            # treating the constraint-only branch as a removal makes identical
            # composed contracts fail their own compatibility check.
            for name in sorted(old_required.intersection(old_properties)):
                if name not in new_properties:
                    self._issue(f'{path}.properties.{name}', 'required released response property was removed')
                elif name not in new_required:
                    self._issue(
                        f'{path}.properties.{name}', 'required released response property is no longer guaranteed'
                    )

        self._compare_additional_properties(old, new, direction, path, seen)

    def _compare_additional_properties(
        self,
        old: Schema,
        new: Schema,
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        old_additional = old.get('additionalProperties', True)
        new_additional = new.get('additionalProperties', True)
        old_kind = _additional_properties_kind(old_additional)
        new_kind = _additional_properties_kind(new_additional)
        additional_path = f'{path}.additionalProperties'

        if direction == 'request':
            if old_kind == 'unconstrained' and new_kind != 'unconstrained':
                self._issue(additional_path, 'request additional properties became constrained')
            elif old_kind == 'schema' and new_kind == 'disallowed':
                self._issue(additional_path, 'request schema no longer accepts additional properties')
        else:
            if old_kind == 'disallowed' and new_kind != 'disallowed':
                self._issue(additional_path, 'response may now emit undeclared additional properties')
            elif old_kind == 'schema' and new_kind == 'unconstrained':
                self._issue(additional_path, 'response additional-property values became unconstrained')

        if old_kind == 'schema' and new_kind == 'schema':
            self._compare_schema(
                old_additional,
                new_additional,
                direction,
                additional_path,
                seen,
            )

    def _compare_arrays(
        self,
        old: Schema,
        new: Schema,
        direction: Direction,
        path: str,
        seen: set[tuple[int, int, Direction]],
    ) -> None:
        if 'items' not in old and 'items' not in new:
            return
        if 'items' not in old:
            if direction == 'request':
                self._issue(f'{path}.items', 'request array items became constrained')
            return
        if 'items' not in new:
            if direction == 'response':
                self._issue(f'{path}.items', 'response array items became unconstrained')
            return
        self._compare_schema(old['items'], new['items'], direction, f'{path}.items', seen)


def _mapping(value: object) -> Schema:
    return cast(Schema, value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _security_requirement(value: object) -> dict[str, frozenset[str]]:
    requirement = _mapping(value)
    return {name: frozenset(str(scope) for scope in _list(scopes)) for name, scopes in requirement.items()}


def _security_alternatives(raw: list[Any]) -> list[dict[str, frozenset[str]]]:
    # OpenAPI's empty security array explicitly disables authentication.  Model it
    # as one empty requirement so it participates in the same no-stricter relation.
    return [_security_requirement(item) for item in raw] or [{}]


def _security_alternative_is_no_stricter(
    new: dict[str, frozenset[str]],
    old: dict[str, frozenset[str]],
) -> bool:
    return all(scheme in old and scopes.issubset(old[scheme]) for scheme, scopes in new.items())


def _schema_types(schema: Schema) -> set[str] | None:
    raw = schema.get('type')
    if isinstance(raw, str):
        result = {raw}
    elif isinstance(raw, list):
        result = {str(item) for item in raw}
    elif 'properties' in schema or 'additionalProperties' in schema:
        result = {'object'}
    elif 'items' in schema:
        result = {'array'}
    else:
        return None
    if schema.get('nullable') is True:
        result.add('null')
    return result


def _type_is_subset(actual: str, accepted: str) -> bool:
    return actual == accepted or (actual == 'integer' and accepted == 'number')


def _allowed_values(schema: Schema) -> list[Any] | None:
    if 'const' in schema:
        return [schema['const']]
    enum = schema.get('enum')
    return list(enum) if isinstance(enum, list) else None


def _additional_properties_kind(value: object) -> Literal['disallowed', 'unconstrained', 'schema']:
    if value is False:
        return 'disallowed'
    if isinstance(value, dict):
        return 'schema'
    return 'unconstrained'


def _is_success_status(status: object) -> bool:
    text = str(status).upper()
    return text == '2XX' or (len(text) == 3 and text.startswith('2') and text[1:].isdigit())


def _matching_response_key(responses: Schema, status: str, *, include_default: bool) -> str | None:
    if status in responses:
        return status
    normalized = status.upper()
    if normalized != '2XX' and '2XX' in responses:
        return '2XX'
    if include_default and 'default' in responses:
        return 'default'
    return None


def compare_specs(base: Schema, head: Schema) -> list[CompatibilityIssue]:
    """Return deterministic, directional compatibility failures."""
    return CompatibilityChecker(base, head).check()


def load_spec(path: Path) -> Schema:
    try:
        loaded = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenAPICompatibilityError(f'cannot read OpenAPI contract {path}: {exc}') from exc
    if not isinstance(loaded, dict):
        raise OpenAPICompatibilityError(f'{path} must contain a JSON object')
    return cast(Schema, loaded)


def load_spec_from_merge_base(base_ref: str, spec_path: Path) -> tuple[Schema, str]:
    try:
        merge_base = subprocess.run(
            ['git', 'merge-base', 'HEAD', base_ref],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        relative = spec_path.resolve().relative_to(ROOT).as_posix()
        payload = subprocess.run(
            ['git', 'show', f'{merge_base}:{relative}'],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        loaded = json.loads(payload)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        raise OpenAPICompatibilityError(f'cannot load {spec_path} from merge-base with {base_ref}: {exc}') from exc
    if not isinstance(loaded, dict):
        raise OpenAPICompatibilityError(f'{spec_path} at {merge_base} must contain a JSON object')
    return cast(Schema, loaded), merge_base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--base-spec', type=Path, help='released/base app-client OpenAPI JSON')
    source.add_argument('--base-ref', help='git ref whose merge-base with HEAD contains the released contract')
    parser.add_argument('--head-spec', type=Path, default=DEFAULT_SPEC, help='candidate app-client OpenAPI JSON')
    args = parser.parse_args(argv)

    try:
        if args.base_ref:
            base, label = load_spec_from_merge_base(args.base_ref, args.head_spec)
            base_label = f'merge-base {label}'
        else:
            base = load_spec(args.base_spec)
            base_label = str(args.base_spec)
        head = load_spec(args.head_spec)
        issues = compare_specs(base, head)
    except OpenAPICompatibilityError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if issues:
        print(
            f'App-client OpenAPI compatibility failed: {len(issues)} breaking change(s) relative to {base_label}.',
            file=sys.stderr,
        )
        for issue in issues:
            print(f'  BREAKING {issue}', file=sys.stderr)
        print('Version the endpoint instead of breaking a released app-client contract.', file=sys.stderr)
        return 1

    print(f'App-client OpenAPI compatibility passed against {base_label}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
