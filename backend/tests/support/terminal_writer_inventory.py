"""Offline AST ratchet for terminal conversation and finalization-job writers.

Like lifecycle_ast, this inventories payload builders as well as storage sites.
It follows local aliases, mutations and module-local patch helpers, without
importing serving code. Dynamic conversation payloads and status claims are
conservatively included: source analysis cannot prove their runtime value.
"""

import ast
import os
import re
from functools import lru_cache
from pathlib import Path

TERMINAL_STATUSES = {'conversation': {'completed', 'failed'}, 'finalization': {'completed', 'dead_letter'}}
TERMINAL_WRITER_OWNERS = {
    'conversation': 'utils/conversations/lifecycle.py + database/conversations.py:claim_conversation_status',
    'finalization': 'database/conversation_finalization_jobs.py',
}


def terminal_writer_sites(source, module):
    """Return machine -> (file, qualified function) sites; line numbers are not identity."""
    tree = ast.parse(source)
    nodes, parents, pending = [], {}, [tree]
    while pending:
        node = pending.pop()
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            parents[child] = node
            pending.append(child)
    definitions = {node.name: node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    found = {machine: set() for machine in TERMINAL_STATUSES}

    def owner(node):
        names = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return '.'.join(reversed(names)) or '<module>'

    def scope(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return tree

    def local_nodes(root):
        yield root
        for child in ast.iter_child_nodes(root):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield from local_nodes(child)

    scopes = {}

    def bindings(node):
        root = scope(node)
        if root not in scopes:
            result = {}
            # Include enclosing bindings for nested transaction callbacks.
            if root is not tree:
                result.update({name: list(values) for name, values in bindings(root).items()})
            for item in local_nodes(root):
                if isinstance(item, (ast.Assign, ast.AnnAssign)):
                    for target in item.targets if isinstance(item, ast.Assign) else [item.target]:
                        if isinstance(target, ast.Name):
                            result.setdefault(target.id, []).append(item.value)
                        elif isinstance(target, (ast.Subscript, ast.Attribute)) and isinstance(target.value, ast.Name):
                            result.setdefault(target.value.id, []).append(item)
                elif isinstance(item, ast.For):
                    targets = item.target.elts if isinstance(item.target, ast.Tuple) else [item.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            result.setdefault(target.id, []).append(item.iter)
                elif isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute):
                    if (
                        item.func.attr in {'update', 'setdefault'}
                        and len(item.args) <= 1
                        and isinstance(item.func.value, ast.Name)
                    ):
                        result.setdefault(item.func.value.id, []).append(item)
            scopes[root] = result
        return scopes[root]

    @lru_cache(maxsize=None)
    def expand(root):
        """Finite def/use closure, including mutations and local patch helpers."""
        seen = set()

        def visit(node):
            if node is None or node in seen:
                return
            seen.add(node)
            if isinstance(node, ast.Name):
                for value in bindings(node).get(node.id, ()):
                    visit(value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if key is None:  # **payload preserves its top-level status.
                        visit(value)
            elif isinstance(node, ast.DictComp):
                if isinstance(node.value, ast.Subscript):
                    visit(node.value.value)
            elif isinstance(node, ast.IfExp):
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
                if name in definitions:
                    for item in local_nodes(definitions[name]):
                        if isinstance(item, ast.Return):
                            visit(item.value)
                if name in {'model_dump', 'dict', 'copy'} and isinstance(node.func, ast.Attribute):
                    visit(node.func.value)
                # Patch/copy wrappers pass a whole payload. Do not follow reads
                # (get/to_dict) or individual field values back to the full row.
                if name not in {'get', 'to_dict', 'where', 'stream'}:
                    for arg in node.args:
                        visit(arg)

        visit(root)
        return tuple(seen)

    @lru_cache(maxsize=None)
    def machine_for(target):
        seen = set()
        evidence = []

        def visit(node):
            if node in seen:
                return
            seen.add(node)
            if isinstance(node, ast.Name):
                evidence.append(node.id)
                for value in bindings(node).get(node.id, ()):
                    visit(value)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                evidence.append(node.value)
            elif isinstance(node, ast.Call):
                evidence.append(ast.unparse(node.func))
                for arg in node.args:
                    visit(arg)
                if isinstance(node.func, ast.Attribute):
                    visit(node.func.value)
                elif isinstance(node.func, ast.Name) and node.func.id in definitions:
                    for item in local_nodes(definitions[node.func.id]):
                        if isinstance(item, ast.Return) and item.value is not None:
                            visit(item.value)
            elif isinstance(node, (ast.List, ast.Tuple, ast.ListComp)):
                for child in ast.iter_child_nodes(node):
                    visit(child)
            elif isinstance(node, ast.comprehension):
                visit(node.iter)
            elif isinstance(node, ast.Attribute):
                evidence.append(node.attr)
                visit(node.value)

        visit(target)
        evidence = ' '.join(evidence).lower()
        if 'finalization_job' in evidence or (
            'job_ref' in evidence and module == 'database/conversation_finalization_jobs.py'
        ):
            return 'finalization'
        if 'conversation' in evidence:
            return 'conversation'
        return None

    @lru_cache(maxsize=None)
    def strings(node, seen=frozenset()):
        if node is None or node in seen:
            return set()
        seen = seen | {node}
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name):
            return set().union(*(strings(value, seen) for value in bindings(node).get(node.id, ())))
        if isinstance(node, ast.IfExp):
            return strings(node.body, seen) | strings(node.orelse, seen)
        if isinstance(node, ast.Attribute):
            if node.attr == 'value':
                return strings(node.value, seen)
            if isinstance(node.value, ast.Name) and node.value.id == 'ConversationStatus':
                return {node.attr}
        return set()

    def pairs(node):
        if isinstance(node, ast.Dict):
            return list(zip(node.keys, node.values))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            result = []
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Subscript):
                    result.append((target.slice, node.value))
                elif isinstance(target, ast.Attribute):
                    result.append((ast.Constant(target.attr), node.value))
            return result
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
            if name in {'dict', 'update', 'set', 'merge', 'setdefault', 'Conversation'}:
                result = [(ast.Constant(k.arg), k.value) for k in node.keywords if k.arg]
                if name == 'setdefault' and len(node.args) >= 2:
                    result.append((node.args[0], node.args[1]))
                return result
        return []

    def add(machine, node):
        found[machine].add((module, owner(node)))

    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
        if name == 'claim_conversation_status':
            claimed = next((k.value for k in node.keywords if k.arg == 'claimed_status'), None)
            if claimed is None and len(node.args) >= 4:
                claimed = node.args[3]
            values = strings(claimed)
            if not values or values & TERMINAL_STATUSES['conversation']:
                add('conversation', node)
            continue
        seams = {
            'create_completed_conversation',
            'persist_processed_conversation',
            'persist_imported_conversation',
            'ingest_sync_conversation',
            'update_conversation',
            'upsert_conversation_with_lifecycle',
            'persist_processing_result_with_lifecycle',
            'create_conversation_if_absent_with_lifecycle',
        }
        seam = name in seams or (
            name == 'run_blocking' and any(isinstance(arg, ast.Attribute) and arg.attr in seams for arg in node.args)
        )
        if seam and node.args:
            expanded = expand(node.args[-1])
            for item in expanded:
                if any(
                    'status' in strings(key) and strings(value) & TERMINAL_STATUSES['conversation']
                    for key, value in pairs(item)
                ):
                    add('conversation', item)
            continue
        if name not in {'update', 'set', 'merge', 'create', 'add'}:
            continue
        # transaction.update(ref, payload) and ref.update(payload), including
        # batch writes. Local mapping updates are followed from their real sink.
        if len(node.args) >= 2:
            target, payload = node.args[:2]
        elif len(node.args) == 1 and isinstance(node.func, ast.Attribute):
            target, payload = node.func.value, node.args[0]
        elif isinstance(node.func, ast.Attribute) and node.keywords:
            target = node.func.value
            payload = node
        else:
            continue
        machine = machine_for(target)
        if machine is None:
            continue
        expanded = expand(payload)
        terminal = [
            item
            for item in expanded
            if any(
                'status' in strings(key) and strings(value) & TERMINAL_STATUSES[machine] for key, value in pairs(item)
            )
        ]
        # Opaque full conversation payloads can contain a terminal status even
        # when it was supplied by another module. Inventory their storage seam.
        opaque = machine == 'conversation' and (
            any(isinstance(item, ast.Name) and item.id in {'conversation_data', 'claimed_status'} for item in expanded)
            or any('status' in strings(key) and not strings(value) for item in expanded for key, value in pairs(item))
        )
        imported_patch = any(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == 'dead_letter_conversation_updates'
            for item in expanded
        )
        if terminal or opaque or imported_patch:
            add(machine, node)
            for item in terminal:
                add(machine, item)

    for definition in definitions.values():
        if any(arg.arg == 'conversation_ref' for arg in definition.args.args):
            for item in local_nodes(definition):
                if isinstance(item, ast.Return):
                    for patch in expand(item.value):
                        if any(
                            'status' in strings(key) and strings(value) & TERMINAL_STATUSES['conversation']
                            for key, value in pairs(patch)
                        ):
                            add('conversation', patch)

    # Conversation models/payloads carry their status through helper seams in
    # other modules; inventory the enum write at construction, never enum reads.
    for node in nodes:
        for key, value in pairs(node):
            if 'status' in strings(key) and strings(value) & TERMINAL_STATUSES['conversation']:
                if any(isinstance(item, ast.Name) and item.id == 'ConversationStatus' for item in ast.walk(value)):
                    add('conversation', node)
    return found


def scan_terminal_writers(backend):
    found = {machine: set() for machine in TERMINAL_STATUSES}
    for directory, children, files in os.walk(backend):
        children[:] = sorted(
            name
            for name in children
            if not name.startswith('.') and name not in {'tests', 'testing', '__pycache__', 'node_modules'}
        )
        for name in sorted(files):
            if not name.endswith('.py') or name.startswith('test_') or name.endswith('_test.py'):
                continue
            path = Path(directory) / name
            source = path.read_text()
            if not re.search(
                r'''(?:['"](?:completed|failed|dead_letter)['"]|ConversationStatus\.(?:completed|failed)|claim_conversation_status|conversation_data)''',
                source,
            ):
                continue
            if not re.search(r'''(?:['"]status['"]|status\s*=|\.status\s*=|claim_conversation_status)''', source):
                continue
            for machine, sites in terminal_writer_sites(source, path.relative_to(backend).as_posix()).items():
                found[machine].update(sites)
    return found


def assert_terminal_writers(actual, known):
    for machine, owner in TERMINAL_WRITER_OWNERS.items():
        expected = set(known[machine])
        new, stale = actual[machine] - expected, expected - actual[machine]
        assert not new and not stale, (
            f'TERMINAL-WRITER-OWNER ({machine}): intended owner {owner}; '
            f'new writers={sorted(new)}; stale allowlist entries={sorted(stale)}. '
            'Route new terminal writes through the owner; remove retired exceptions explicitly.'
        )
