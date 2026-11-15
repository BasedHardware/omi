"""Offline inventory of literal batch-state writes; no production imports or IO.

This is a bounded AST check, not Python data-flow analysis. It follows local
payload names, dict spreads, updates and subscript assignments into buffered
put/patch writes as well as direct Firestore set/update/create payloads.
Computed keys, helper-returned payloads and external storage/queue contracts
still require the PR's explicit reader/version review.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
REGISTRY = BACKEND / 'deploy/state_readers.yaml'


def literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def written_fields(source: str) -> dict[str, set[str]]:
    """Return table -> literal top-level fields. '?' means a raw reference/helper."""
    tree = ast.parse(source)
    result = defaultdict(set)
    constants = {
        n.targets[0].id: literal(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    }
    # Analyze each lexical function separately: an unrelated local `job` must
    # not turn logging/diagnostic dictionaries into persisted job fields.
    scopes = [tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))]
    for scope in scopes:
        nodes = []

        def visit(node):
            if node is not scope and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return
            nodes.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(scope)
        assignments = defaultdict(list)
        mutations = defaultdict(list)
        calls = [n for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and node.value is not None:
                        assignments[target.id].append(node.value)
                    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                        key = literal(target.slice)
                        if key:
                            mutations[target.value.id].append({key})
        for call in calls:
            if isinstance(call.func.value, ast.Name):
                if call.func.attr == 'update':
                    mutations[call.func.value.id].append(call)
                elif call.func.attr == 'setdefault' and call.args and literal(call.args[0]):
                    mutations[call.func.value.id].append({literal(call.args[0])})

        def keys(node, seen=frozenset()):
            if isinstance(node, set):
                return node
            if isinstance(node, ast.Dict):
                found = {literal(k) for k in node.keys if literal(k)}
                for key, value in zip(node.keys, node.values):
                    if key is None:
                        found |= keys(value, seen)
                return found
            if isinstance(node, ast.Name) and node.id not in seen:
                return set().union(
                    *(keys(value, seen | {node.id}) for value in assignments[node.id] + mutations[node.id])
                )
            if isinstance(node, ast.BoolOp):
                return set().union(*(keys(value, seen) for value in node.values))
            if isinstance(node, ast.Call):
                # Only dict/update keywords are payload fields, never RPC options.
                if (isinstance(node.func, ast.Name) and node.func.id == 'dict') or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == 'update'
                ):
                    return {k.arg for k in node.keywords if k.arg} | set().union(*(keys(a, seen) for a in node.args))
            return set()

        persisted = set()
        for call in calls:
            if call.func.attr in {'put', 'patch'} and len(call.args) >= 3:
                table = literal(call.args[0]) or constants.get(getattr(call.args[0], 'id', ''))
                if table:
                    result[table] |= keys(call.args[2])
                    if isinstance(call.args[2], ast.Name):
                        persisted.add(call.args[2].id)
        for call in calls:
            if call.func.attr not in {'set', 'update', 'create'}:
                continue
            receiver = call.func.value
            # Local in-memory dictionaries are covered at their put() sink.
            # Parameter updates (e.g. retry_policy's job) remain checked.
            if isinstance(receiver, ast.Name) and receiver.id in assignments:
                if receiver.id not in persisted and any(
                    isinstance(a, (ast.Dict, ast.ListComp, ast.DictComp)) for a in assignments[receiver.id]
                ):
                    continue
                if receiver.id in persisted:
                    continue
            payload = call.args[-1] if call.args else None
            fields = keys(payload)
            if (
                call.func.attr == 'update'
                and isinstance(receiver, ast.Name)
                and receiver.id in {'job', 'queue', 'owner', 'gpu', 'control'}
            ):
                fields |= {k.arg for k in call.keywords if k.arg}
            result['?'] |= fields
    return {table: fields for table, fields in result.items() if fields}


def source_paths():
    return sorted(
        [*(BACKEND / 'utils/batch_pipeline').rglob('*.py'), *(BACKEND / 'database').glob('batch_pipeline*.py')]
    )


def runtime_roster():
    """Use the existing runtime manifest and the cross-service Helm roster."""
    manifest = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text())
    tree = ast.parse((BACKEND / 'scripts/cross_service_contract.py').read_text())
    charts = next(
        n.value
        for n in tree.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == 'HELM_CHARTS'
    )
    services = {f'helm/{literal(row.elts[0])}' for row in charts.elts}
    for env in manifest['environments'].values():
        services |= {f'cloud_run/{name}' for name in env['cloud_run']['services']}
        services |= {f'job/{name}' for name in env['cloud_run']['jobs']}
        services |= {f'gke/{name}' for name in env['gke'] if name != 'config_map'}
        services.add('desktop_backend')
    return services


def validate(registry, roster):
    errors = []
    for state, entry in registry['states'].items():
        readers, writers = entry.get('readers', {}), entry.get('writers', [])
        if not readers:
            errors.append(f'{state}: no readers')
        if not writers:
            errors.append(f'{state}: no writers')
        for service in set(readers) | set(writers):
            if service not in roster:
                errors.append(f'{state}: unknown deployable {service}')
        for service, version in readers.items():
            if not isinstance(version, str) or not version.strip():
                errors.append(f'{state}: reader {service} needs a minimum version/contract')
        switch = entry.get('kill_switch', {})
        service = switch.get('service')
        if service not in set(readers) | set(writers):
            errors.append(f'{state}: kill switch service {service} is not a reader or writer')
        if not switch.get('flag'):
            errors.append(f'{state}: kill switch needs a flag')
    return errors


def coverage_errors(registry, paths):
    registered = {name.rsplit('.', 1)[-1] for name in registry['states']}
    errors = []
    for path in paths:
        fields = set().union(*written_fields(path.read_text()).values())
        errors.extend(f'{path.name}: unregistered written field {field}' for field in sorted(fields - registered))
    return errors


def main():
    registry = yaml.safe_load(REGISTRY.read_text())
    errors = validate(registry, runtime_roster()) + coverage_errors(registry, source_paths())
    if errors:
        raise SystemExit('\n'.join(errors))
    print('State readers registry: all literal writes and deployables covered')


if __name__ == '__main__':
    main()
