#!/usr/bin/env python3
"""Inventory Firestore compound-query coverage and enforce its no-regression ratchet.

This AST-only tool deliberately inventories query *shapes*, rather than source
``where`` call counts.  Serving code is the enforcement scope; tests,
migrations, and operational scripts are reported separately and never inflate
serving coverage.  New serving compound chains must either use a registered
query spec or be an existing, baselined shape while the incremental migration
is in progress.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from database.firestore_index_registry import QUERY_SPECS  # noqa: E402

BASELINE_PATH = BACKEND_ROOT / 'scripts' / 'firestore_query_coverage_baseline.json'
WAIVERS_PATH = BACKEND_ROOT / 'scripts' / 'firestore_query_coverage_waivers.json'
QUERY_SPEC_SOURCE = Path('backend/database/firestore_index_registry.py')
NON_SERVING_SEGMENTS = {'tests', 'scripts', 'migrations', 'migration'}


def _canonical_source(path: PurePath) -> str:
    return path.as_posix()


@dataclass(frozen=True)
class QueryComponent:
    field_path: str
    operator: str
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {'field': self.field_path, 'operator': self.operator, 'kind': self.kind}


@dataclass
class QueryState:
    collection_group: str | None
    query_scope: str
    components: list[QueryComponent] = field(default_factory=list)
    supported: bool = True
    line: int = 0

    def clone(self) -> 'QueryState':
        return copy.deepcopy(self)


@dataclass(frozen=True)
class QueryShape:
    source: str
    symbol: str
    line: int
    collection_group: str | None
    query_scope: str
    components: tuple[QueryComponent, ...]
    classification: str
    registered_spec: str | None
    non_serving_scope: str | None

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            {
                'source': self.source,
                'symbol': self.symbol,
                'collection_group': self.collection_group,
                'query_scope': self.query_scope,
                'components': [component.as_dict() for component in self.components],
            },
            sort_keys=True,
            separators=(',', ':'),
        )
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        return {
            'id': self.fingerprint,
            'source': self.source,
            'symbol': self.symbol,
            'line': self.line,
            'collection_group': self.collection_group,
            'query_scope': self.query_scope,
            'fields': [component.as_dict() for component in self.components],
            'classification': self.classification,
            'registered_spec': self.registered_spec,
            'non_serving_scope': self.non_serving_scope,
        }


def _literal_string(node: ast.AST | None, constants: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _direction(node: ast.AST | None, constants: Mapping[str, str]) -> str | None:
    literal = _literal_string(node, constants)
    if literal is not None:
        return literal.upper()
    if isinstance(node, ast.Attribute) and node.attr in {'ASCENDING', 'DESCENDING'}:
        return node.attr
    return None


class FunctionQueryAnalyzer:
    def __init__(
        self,
        *,
        source: str,
        symbol: str,
        constants: Mapping[str, str],
        non_serving_scope: str | None,
        registered_signatures: Mapping[tuple[str, str, tuple[tuple[str, str], ...]], str],
        waiver_ids: set[str],
    ) -> None:
        self.source = source
        self.symbol = symbol
        self.constants = constants
        self.non_serving_scope = non_serving_scope
        self.registered_signatures = registered_signatures
        self.waiver_ids = waiver_ids
        self.states: dict[str, QueryState] = {}
        self.shapes: dict[str, QueryShape] = {}

    def analyze(self, statements: Iterable[ast.stmt]) -> list[QueryShape]:
        self._analyze_block(statements)
        return sorted(self.shapes.values(), key=lambda shape: (shape.source, shape.line, shape.fingerprint))

    def _analyze_block(self, statements: Iterable[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                value = statement.value
                state = self._parse_expression(value) if value is not None else None
                if state is not None:
                    for target in self._assignment_targets(statement):
                        self.states[target] = state.clone()
                    self._record(state)
                continue
            if isinstance(statement, ast.Expr):
                self._record(self._parse_expression(statement.value))
                continue
            if isinstance(statement, ast.Return):
                self._record(self._parse_expression(statement.value))
                continue
            if isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                self._analyze_nested(statement)

    def _analyze_nested(self, statement: ast.stmt) -> None:
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._record(self._parse_expression(statement.iter))
        blocks: list[list[ast.stmt]] = []
        for name in ('body', 'orelse', 'finalbody'):
            value = getattr(statement, name, None)
            if isinstance(value, list):
                blocks.append(value)
        if isinstance(statement, ast.Try):
            blocks.extend(handler.body for handler in statement.handlers)
        original = self.states
        for block in blocks:
            self.states = copy.deepcopy(original)
            self._analyze_block(block)
        self.states = original

    @staticmethod
    def _assignment_targets(statement: ast.Assign | ast.AnnAssign) -> list[str]:
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        return [target.id for target in targets if isinstance(target, ast.Name)]

    def _parse_expression(self, node: ast.AST | None) -> QueryState | None:
        if isinstance(node, ast.Name):
            state = self.states.get(node.id)
            return state.clone() if state is not None else None
        if not isinstance(node, ast.Call):
            return None
        if not isinstance(node.func, ast.Attribute):
            for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                nested = self._parse_expression(argument)
                if nested is not None:
                    return nested
            return None

        method = node.func.attr
        if method in {'collection', 'collection_group'}:
            collection_group = _literal_string(node.args[0] if node.args else None, self.constants)
            return QueryState(
                collection_group=collection_group,
                query_scope='COLLECTION_GROUP' if method == 'collection_group' else 'COLLECTION',
                supported=collection_group is not None,
                line=node.lineno,
            )

        state = self._parse_expression(node.func.value)
        if state is None:
            return None
        state.line = node.lineno
        if method == 'where':
            component = self._where_component(node)
            state.components.append(component)
            state.supported = state.supported and component.field_path != '?' and component.operator != '?'
        elif method == 'order_by':
            component = self._order_component(node)
            state.components.append(component)
            state.supported = state.supported and component.field_path != '?' and component.operator != '?'
        elif method in {'limit', 'offset', 'select', 'stream', 'get', 'count'}:
            pass
        else:
            return state
        return state

    def _where_component(self, node: ast.Call) -> QueryComponent:
        if len(node.args) >= 2:
            field_path = _literal_string(node.args[0], self.constants) or '?'
            operator = _literal_string(node.args[1], self.constants) or '?'
            return QueryComponent(field_path, operator, 'filter')
        for keyword in node.keywords:
            if keyword.arg != 'filter' or not isinstance(keyword.value, ast.Call):
                continue
            if len(keyword.value.args) >= 2:
                field_path = _literal_string(keyword.value.args[0], self.constants) or '?'
                operator = _literal_string(keyword.value.args[1], self.constants) or '?'
                return QueryComponent(field_path, operator, 'filter')
        return QueryComponent('?', '?', 'filter')

    def _order_component(self, node: ast.Call) -> QueryComponent:
        field_path = _literal_string(node.args[0] if node.args else None, self.constants) or '?'
        direction = 'ASCENDING'
        for keyword in node.keywords:
            if keyword.arg == 'direction':
                direction = _direction(keyword.value, self.constants) or '?'
        return QueryComponent(field_path, direction, 'order')

    def _record(self, state: QueryState | None) -> None:
        if state is None or len(state.components) < 2:
            return
        registered_spec = None
        if state.supported and state.collection_group is not None:
            signature = (
                state.collection_group,
                state.query_scope,
                tuple((component.field_path, component.operator) for component in state.components),
            )
            registered_spec = self.registered_signatures.get(signature)
        if self.non_serving_scope is not None:
            classification = 'non_serving'
        elif not state.supported or state.collection_group is None:
            classification = 'unsupported'
        elif registered_spec is not None:
            classification = 'registered'
        else:
            classification = 'raw_unregistered'
        shape = QueryShape(
            source=self.source,
            symbol=self.symbol,
            line=state.line,
            collection_group=state.collection_group,
            query_scope=state.query_scope,
            components=tuple(state.components),
            classification=classification,
            registered_spec=registered_spec,
            non_serving_scope=self.non_serving_scope,
        )
        if classification == 'raw_unregistered' and shape.fingerprint in self.waiver_ids:
            shape = QueryShape(
                source=shape.source,
                symbol=shape.symbol,
                line=shape.line,
                collection_group=shape.collection_group,
                query_scope=shape.query_scope,
                components=shape.components,
                classification='waived',
                registered_spec=None,
                non_serving_scope=None,
            )
        previous = self.shapes.get(shape.fingerprint)
        if previous is None or shape.line < previous.line:
            self.shapes[shape.fingerprint] = shape


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name):
            value = _literal_string(statement.value, constants)
            if value is not None:
                constants[target.id] = value
    return constants


def _non_serving_scope(relative: Path) -> str | None:
    segments = set(relative.parts)
    if 'tests' in segments:
        return 'tests'
    if 'migrations' in segments or 'migration' in segments:
        return 'migrations'
    if 'scripts' in segments:
        return 'scripts'
    return None


def _registered_signatures() -> dict[tuple[str, str, tuple[tuple[str, str], ...]], str]:
    return {spec.query_signature: spec.identifier for spec in QUERY_SPECS}


def _load_waivers(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError(f'{path.relative_to(ROOT)} must contain a list')
    waiver_ids: set[str] = set()
    today = date.today()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError('Firestore query waiver must be an object')
        identifier = item.get('query_id')
        owner = item.get('owner')
        expires_on = item.get('expires_on')
        if not all(isinstance(value, str) and value for value in (identifier, owner, expires_on)):
            raise ValueError('Firestore query waiver requires query_id, owner, and expires_on')
        try:
            expiry = date.fromisoformat(expires_on)
        except ValueError as exc:
            raise ValueError(f'Firestore query waiver {identifier} has invalid expires_on') from exc
        if expiry < today:
            raise ValueError(f'Firestore query waiver {identifier} expired on {expires_on}')
        waiver_ids.add(identifier)
    return waiver_ids


def inventory(*, waiver_ids: set[str]) -> list[QueryShape]:
    registered_signatures = _registered_signatures()
    shapes: dict[str, QueryShape] = {}
    for path in sorted(BACKEND_ROOT.rglob('*.py')):
        backend_relative = path.relative_to(BACKEND_ROOT)
        relative = path.relative_to(ROOT)
        if relative == QUERY_SPEC_SOURCE or any(
            part.startswith('.') or part in {'venv', '__pycache__'} for part in backend_relative.parts
        ):
            continue
        source = _canonical_source(relative)
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=source)
        constants = _module_constants(tree)
        non_serving_scope = _non_serving_scope(relative)
        module_analyzer = FunctionQueryAnalyzer(
            source=source,
            symbol='<module>',
            constants=constants,
            non_serving_scope=non_serving_scope,
            registered_signatures=registered_signatures,
            waiver_ids=waiver_ids,
        )
        for shape in module_analyzer.analyze(tree.body):
            shapes[shape.fingerprint] = shape
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            analyzer = FunctionQueryAnalyzer(
                source=source,
                symbol=node.name,
                constants=constants,
                non_serving_scope=non_serving_scope,
                registered_signatures=registered_signatures,
                waiver_ids=waiver_ids,
            )
            for shape in analyzer.analyze(node.body):
                shapes[shape.fingerprint] = shape
    registry_source = (ROOT / QUERY_SPEC_SOURCE).read_text(encoding='utf-8').splitlines()
    for spec in QUERY_SPECS:
        line = next(
            (index for index, text in enumerate(registry_source, start=1) if f"identifier='{spec.identifier}'" in text),
            0,
        )
        shape = QueryShape(
            source=_canonical_source(QUERY_SPEC_SOURCE),
            symbol=spec.identifier,
            line=line,
            collection_group=spec.collection_group,
            query_scope=spec.query_scope,
            components=tuple(
                QueryComponent(query_filter.field_path, query_filter.operator, 'filter')
                for query_filter in spec.filters
            ),
            classification='registered',
            registered_spec=spec.identifier,
            non_serving_scope=None,
        )
        shapes[shape.fingerprint] = shape
    return sorted(shapes.values(), key=lambda shape: (shape.source, shape.line, shape.fingerprint))


def report_for(shapes: Iterable[QueryShape]) -> dict[str, Any]:
    entries = list(shapes)
    serving = [shape for shape in entries if shape.non_serving_scope is None]
    non_serving = [shape for shape in entries if shape.non_serving_scope is not None]
    counts = {
        'serving': {
            classification: sum(shape.classification == classification for shape in serving)
            for classification in ('registered', 'raw_unregistered', 'waived', 'unsupported')
        },
        'non_serving': {
            scope: sum(shape.non_serving_scope == scope for shape in non_serving)
            for scope in ('tests', 'migrations', 'scripts')
        },
    }
    counts['serving']['eligible'] = sum(
        counts['serving'][classification]
        for classification in ('registered', 'raw_unregistered', 'waived', 'unsupported')
    )
    zero_debt = counts['serving']['eligible'] == counts['serving']['registered']
    return {
        'schema_version': 1,
        'counts': counts,
        'zero_debt': zero_debt,
        'queries': [shape.as_dict() for shape in entries],
    }


def baseline_for(report: Mapping[str, Any]) -> dict[str, Any]:
    serving = report['counts']['serving']
    return {
        'schema_version': 1,
        'eligible_serving': serving['eligible'],
        'registered_serving': serving['registered'],
        'raw_unregistered': sorted(
            query['id'] for query in report['queries'] if query['classification'] == 'raw_unregistered'
        ),
        'unsupported': sorted(query['id'] for query in report['queries'] if query['classification'] == 'unsupported'),
    }


def check_ratchet(report: Mapping[str, Any], baseline: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if baseline.get('schema_version') != 1:
        return ['Firestore query coverage baseline has an unsupported schema version']
    current = baseline_for(report)
    current_raw = set(current['raw_unregistered'])
    baseline_raw = set(baseline.get('raw_unregistered', []))
    new_raw = sorted(current_raw - baseline_raw)
    if new_raw:
        errors.append(f'new unregistered serving compound query shape(s): {", ".join(new_raw)}')
    current_unsupported = set(current['unsupported'])
    baseline_unsupported = set(baseline.get('unsupported', []))
    new_unsupported = sorted(current_unsupported - baseline_unsupported)
    if new_unsupported:
        errors.append(f'new unsupported serving compound query shape(s): {", ".join(new_unsupported)}')
    baseline_registered = int(baseline.get('registered_serving', 0))
    baseline_eligible = int(baseline.get('eligible_serving', 0))
    if current['registered_serving'] < baseline_registered:
        errors.append('registered serving-query coverage count decreased')
    if current['registered_serving'] * max(baseline_eligible, 1) < baseline_registered * max(
        current['eligible_serving'], 1
    ):
        errors.append('registered serving-query coverage percentage decreased')
    return errors


def _render_human(report: Mapping[str, Any]) -> str:
    serving = report['counts']['serving']
    non_serving = report['counts']['non_serving']
    lines = [
        'Firestore serving query coverage:',
        '  registered={registered} raw_unregistered={raw_unregistered} waived={waived} unsupported={unsupported} eligible={eligible}'.format(
            **serving
        ),
        '  non_serving: tests={tests} migrations={migrations} scripts={scripts}'.format(**non_serving),
        f"  zero_debt={'yes' if report['zero_debt'] else 'no'}",
    ]
    for query in report['queries']:
        fields = ', '.join(f"{field['field']} {field['operator']}" for field in query['fields'])
        lines.append(
            f"  {query['classification']}: {query['source']}:{query['line']} {query['collection_group'] or '?'} [{fields}]"
        )
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=('report', 'json', 'baseline'), default='report')
    parser.add_argument('--baseline', type=Path, default=BASELINE_PATH)
    parser.add_argument('--waivers', type=Path, default=WAIVERS_PATH)
    parser.add_argument('--check-ratchet', action='store_true')
    args = parser.parse_args()
    try:
        report = report_for(inventory(waiver_ids=_load_waivers(args.waivers.resolve())))
        if args.check_ratchet:
            baseline = json.loads(args.baseline.resolve().read_text(encoding='utf-8'))
            errors = check_ratchet(report, baseline)
            if errors:
                for error in errors:
                    print(f'ERROR: {error}', file=sys.stderr)
                return 1
    except (OSError, SyntaxError, ValueError, json.JSONDecodeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    if args.format == 'json':
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == 'baseline':
        print(json.dumps(baseline_for(report), indent=2, sort_keys=True))
    else:
        print(_render_human(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
