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
    'conversation': 'utils/conversations/lifecycle.py + database/conversations.py:claim_conversation_status_in_txn',
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
    aliases = {
        alias.asname: alias.name
        for node in nodes
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname
    }
    cas_aliases = {'claim_conversation_status'} | {
        name for name, original in aliases.items() if original == 'claim_conversation_status'
    }
    cas_aliases.update(
        target.id
        for node in nodes
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        and node.value.id == 'claim_conversation_status'
        for target in node.targets
        if isinstance(target, ast.Name)
    )
    enum_names = {'ConversationStatus'}
    module_names = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == 'ConversationStatus':
                    enum_names.add(alias.asname or alias.name)
                else:
                    module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module_names.add(alias.asname or alias.name)

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
                if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
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
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                visit(node.left)
                visit(node.right)
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
    def machine_for(target, seen=frozenset()):
        if target in seen:
            return None
        seen = seen | {target}
        if isinstance(target, ast.Name):
            values = [
                value
                for value in bindings(target).get(target.id, ())
                if not isinstance(value, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                and not (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and value.func.attr in {'update', 'setdefault'}
                )
            ]
            if values:
                return next((machine for value in values if (machine := machine_for(value, seen))), None)
            if target.id == 'conversation_ref':
                return 'conversation'
            if target.id in {'job_ref', 'jobs_collection'} and module == 'database/conversation_finalization_jobs.py':
                return 'finalization'
        elif isinstance(target, ast.Call):
            if isinstance(target.func, ast.Attribute):
                if target.func.attr == 'collection' and target.args:
                    collections = strings(target.args[0])
                    if 'conversations' in collections or ast.unparse(target.args[0]) == 'conversations_collection':
                        return 'conversation'
                    if 'conversation_finalization_jobs' in collections:
                        return 'finalization'
                    # The nearest collection owns the document. A photos,
                    # receipts or frame child is not a conversation document.
                    return None
                if target.func.attr == 'document':
                    return machine_for(target.func.value, seen)
                if 'conversation_ref' in target.func.attr:
                    return 'conversation'
            elif isinstance(target.func, ast.Name):
                if target.func.id in definitions:
                    return next(
                        (
                            machine
                            for item in local_nodes(definitions[target.func.id])
                            if isinstance(item, ast.Return)
                            and item.value is not None
                            and (machine := machine_for(item.value, seen))
                        ),
                        None,
                    )
                if 'conversation_ref' in target.func.id:
                    return 'conversation'
                if target.func.id == '_job_ref' and module == 'database/conversation_finalization_jobs.py':
                    return 'finalization'
                if target.func.id == 'zip':
                    return next((machine for item in target.args if (machine := machine_for(item, seen))), None)
        elif isinstance(target, ast.IfExp):
            return machine_for(target.body, seen) or machine_for(target.orelse, seen)
        elif isinstance(target, (ast.List, ast.Tuple)):
            return next((machine for item in target.elts if (machine := machine_for(item, seen))), None)
        elif isinstance(target, ast.ListComp):
            return machine_for(target.elt, seen)
        elif isinstance(target, ast.Subscript):
            return machine_for(target.value, seen)
        return None

    def dotted_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f'{parent}.{node.attr}' if parent else None
        return None

    def conversation_status_class(node, seen=frozenset()):
        if node is None or node in seen:
            return False
        seen = seen | {node}
        name = dotted_name(node)
        if name in enum_names:
            return True
        if isinstance(node, ast.Attribute) and node.attr == 'ConversationStatus':
            parent = dotted_name(node.value)
            if parent and any(parent == name or parent.startswith(f'{name}.') for name in module_names):
                return True
        if isinstance(node, ast.Name):
            return any(conversation_status_class(value, seen) for value in bindings(node).get(node.id, ()))
        return False

    @lru_cache(maxsize=None)
    def enum_values(node, seen=frozenset()):
        """Resolve enum imports, qualification, member lookup and .value without IO."""
        if node is None or node in seen:
            return set()
        seen = seen | {node}
        if isinstance(node, ast.Attribute):
            if node.attr == 'value':
                return enum_values(node.value, seen)
            if conversation_status_class(node.value):
                return {node.attr}
        if isinstance(node, ast.Subscript) and conversation_status_class(node.value):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                return {node.slice.value}
        if isinstance(node, ast.Name):
            return set().union(*(enum_values(value, seen) for value in bindings(node).get(node.id, ())))
        if isinstance(node, ast.IfExp):
            return enum_values(node.body, seen) | enum_values(node.orelse, seen)
        return set()

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
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            return enum_values(node)
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
        if name in cas_aliases:
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
        if seam and (node.args or node.keywords):
            expanded = set()
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                expanded.update(expand(argument))
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
        # Full-document creates/sets and dynamic plan payloads can carry status
        # from a different module. A dictionary comprehension with unknown keys
        # can restore status too. Keep those seams conservative.
        whole_document = name in {'set', 'create', 'add'} and isinstance(payload, (ast.Name, ast.Attribute, ast.Call))
        opaque = opaque or (
            machine == 'conversation'
            and (
                whole_document
                or any(isinstance(item, ast.Attribute) and item.attr == 'payload' for item in expanded)
                or any(isinstance(item, ast.DictComp) for item in expanded)
            )
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
        is_claim_core = definition.name == 'claim_conversation_status_in_txn'
        if is_claim_core or any(arg.arg == 'conversation_ref' for arg in definition.args.args):
            for item in local_nodes(definition):
                if isinstance(item, ast.Return):
                    for patch in expand(item.value):
                        if any(
                            'status' in strings(key)
                            and (
                                strings(value) & TERMINAL_STATUSES['conversation']
                                or (is_claim_core and not strings(value))
                            )
                            for key, value in pairs(patch)
                        ):
                            add('conversation', patch)

    # Conversation models/payloads carry their status through helper seams in
    # other modules; inventory the enum write at construction, never enum reads.
    for node in nodes:
        for key, value in pairs(node):
            if 'status' in strings(key) and strings(value) & TERMINAL_STATUSES['conversation']:
                if enum_values(value) & TERMINAL_STATUSES['conversation']:
                    add('conversation', node)
    return found


def terminal_candidate_modules(backend):
    """Cheap source prefilter shared by the full scan and per-file CI checks."""
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
            conversation_storage = 'conversations' in source and re.search(r'\.(?:set|create|update|merge)\(', source)
            # Do not prefilter on terminal value spelling: import aliases and
            # module qualification can hide every enum member literal. Select
            # status payload syntax first, then resolve values in the AST.
            if not conversation_storage and not re.search(
                r'''(?:['"]status['"]|status\s*=|\.status\s*=|claim_conversation_status)''', source
            ):
                continue
            yield path.relative_to(backend).as_posix()


def scan_terminal_writers(backend):
    found = {machine: set() for machine in TERMINAL_STATUSES}
    for module in terminal_candidate_modules(backend):
        for machine, sites in terminal_writer_sites((backend / module).read_text(), module).items():
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
