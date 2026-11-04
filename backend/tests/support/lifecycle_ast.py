"""Pure, conservative lifecycle payload inventory and entry-deadline probes.

This is source analysis, not whole-program execution or a liveness simulator.
Every literal payload site is retained, including duplicates in one function;
response/query maps are intentionally included in the reviewed inventory.
"""

import ast
from dataclasses import dataclass
from functools import lru_cache


@lru_cache(maxsize=64)
def parsed(source):
    return ast.parse(source)


FIELDS = frozenset(
    {
        'status',
        'state',
        'stage',
        'projection_state',
        'record_audio_closed',
        'record_upload_sessions',
        'record_upload_failed',
        'record_audio_partial',
        'summary_first_pending_at',
        'summary_due_at',
        'summary_completed_at',
        'finalization_status',
        'wrap_up_requested_at',
        'composed_fingerprint',
        'recorded_merged_into',
        'sync_bridge_pending',
    }
)
UNKNOWN = object()


def fields_for(module):
    fields = set(FIELDS) - {'state', 'stage'}
    if (
        module.startswith(('utils/batch_pipeline/', 'database/batch_pipeline_'))
        or module == 'database/record_partial.py'
    ):
        fields.add('state')
    if module in {'utils/fair_use.py', 'database/fair_use.py'}:
        fields.add('stage')
    return fields


def literal_key(node, constants):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return constants.get(node.id, set())
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == 'bridge_pending' and node.attr == 'FIELD':
            return {'sync_bridge_pending'}
    return set()


@lru_cache(maxsize=64)
def constant_names(tree):
    def strings(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.IfExp):
            return strings(node.body) | strings(node.orelse)
        if isinstance(node, ast.Attribute) and node.attr == 'value' and isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == 'ConversationStatus':
                return {node.value.attr}
        return set()

    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and strings(node.value):
                    result.setdefault(target.id, set()).update(strings(node.value))
    return result


def payload_sites(source):
    """(qualified owner, field, value expression, sibling keys), one per site."""
    tree = parsed(source)
    constants = constant_names(tree)
    found = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = visit_ClassDef
        visit_AsyncFunctionDef = visit_ClassDef

        def add(self, key, value, siblings):
            expression = ast.unparse(value) if value is not None else '<unknown>'
            aliases = (
                sorted(
                    {
                        (node.id, tuple(sorted(constants[node.id])))
                        for node in ast.walk(value)
                        if isinstance(node, ast.Name) and node.id in constants
                    }
                )
                if value is not None
                else []
            )
            if aliases:
                expression += f'; literal aliases={aliases!r}'
            for field in sorted(literal_key(key, constants) & FIELDS):
                found.append(
                    (
                        '.'.join(self.stack) or '<module>',
                        field,
                        expression,
                        tuple(sorted(siblings)),
                    )
                )

        def visit_Dict(self, node):
            siblings = set().union(*(literal_key(key, constants) for key in node.keys))
            for key, value in zip(node.keys, node.values):
                self.add(key, value, siblings)
            self.generic_visit(node)

        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    self.add(target.slice, node.value, literal_key(target.slice, constants))
                elif isinstance(target, ast.Attribute) and target.attr in FIELDS:
                    self.add(ast.Constant(target.attr), node.value, {target.attr})
            self.generic_visit(node)

        def visit_Call(self, node):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            )
            if name in {'dict', 'update', 'set', 'setdefault'}:
                siblings = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
                for keyword in node.keywords:
                    self.add(ast.Constant(keyword.arg), keyword.value, siblings)
                if name == 'setdefault' and len(node.args) >= 2:
                    self.add(node.args[0], node.args[1], literal_key(node.args[0], constants))
            self.generic_visit(node)

    Visitor().visit(tree)
    return sorted(found)


def builders(sites):
    found = {}
    for owner, field, _value, _siblings in sites:
        found.setdefault(field, set()).add(owner)
    return {field: sorted(owners) for field, owners in found.items()}


@lru_cache(maxsize=512)
def function_node(source, qualified):
    node = parsed(source)
    for part in qualified.split('.'):
        node = next(
            (
                child
                for child in node.body
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == part
            ),
            None,
        )
        if node is None:
            return None
    return node


def value(node, bindings):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return bindings.get(node.id, UNKNOWN)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        result = value(node.operand, bindings)
        return not result if result is not UNKNOWN else UNKNOWN
    if isinstance(node, ast.IfExp):
        condition = value(node.test, bindings)
        return value(node.body if condition else node.orelse, bindings) if condition is not UNKNOWN else UNKNOWN
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        items = [value(item, bindings) for item in node.elts]
        return items if all(item is not UNKNOWN for item in items) else UNKNOWN
    if isinstance(node, ast.BoolOp):
        items = [value(item, bindings) for item in node.values]
        if isinstance(node.op, ast.And):
            if any(item is not UNKNOWN and not item for item in items):
                return False
            return True if all(item is not UNKNOWN for item in items) else UNKNOWN
        if isinstance(node.op, ast.Or):
            if any(item is not UNKNOWN and item for item in items):
                return True
            return False if all(item is not UNKNOWN for item in items) else UNKNOWN
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = value(node.left, bindings), value(node.comparators[0], bindings)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        if isinstance(node.ops[0], ast.Eq):
            return left == right
        if isinstance(node.ops[0], ast.NotEq):
            return left != right
        if isinstance(node.ops[0], ast.Is):
            return left is right
        if isinstance(node.ops[0], ast.IsNot):
            return left is not right
        if isinstance(node.ops[0], ast.In):
            return left in right
        if isinstance(node.ops[0], ast.NotIn):
            return left not in right
    if isinstance(node, ast.Attribute) and node.attr == 'value' and isinstance(node.value, ast.Attribute):
        if isinstance(node.value.value, ast.Name) and node.value.value.id == 'ConversationStatus':
            return node.value.attr
    return UNKNOWN


@dataclass(frozen=True)
class EntryPath:
    module: str
    function: str
    field: str
    state: str | None = None
    bindings: tuple[tuple[str, object], ...] = ()
    inplace: bool = False


@lru_cache(maxsize=512)
def entry_deadline_sites(source, entry, deadline):
    """Audit each matching entry payload; never borrow a sibling path's stamp.

    Later mutations count only on the same mapping, before its first storage
    handoff, and on guards proved by the entry's bindings/dominating path.
    Unknown conditional mutations cannot prove a deadline. Opaque delegation
    must have its own declared entry path instead of receiving a free pass.
    """
    root = function_node(source, entry.function)
    if root is None:
        return []
    constants = constant_names(parsed(source))
    bindings = dict(entry.bindings)
    parents = {child: parent for parent in ast.walk(root) for child in ast.iter_child_nodes(parent)}

    def guards(node):
        result = []
        while node in parents:
            parent = parents[node]
            if isinstance(parent, ast.If):
                result.append((parent, node in parent.body))
            node = parent
        return result

    def possible(node):
        return all(
            value(parent.test, bindings) is UNKNOWN or bool(value(parent.test, bindings)) == branch
            for parent, branch in guards(node)
        )

    def guaranteed(node, start):
        existing = {(id(parent), branch) for parent, branch in guards(start)}
        for parent, branch in guards(node):
            if (id(parent), branch) in existing:
                continue
            evaluated = value(parent.test, bindings)
            if evaluated is UNKNOWN or bool(evaluated) != branch:
                return False
        return True

    def resolved(item, site, seen=frozenset()):
        if isinstance(item, ast.Name) and item.id not in seen:
            for previous in sorted(nodes, key=lambda node: getattr(node, 'lineno', 0), reverse=True):
                if not isinstance(previous, (ast.Assign, ast.AnnAssign)) or previous.lineno >= site.lineno:
                    continue
                targets = previous.targets if isinstance(previous, ast.Assign) else [previous.target]
                if any(isinstance(target, ast.Name) and target.id == item.id for target in targets) and guaranteed(
                    previous, site
                ):
                    return resolved(previous.value, previous, seen | {item.id})
        return value(item, bindings)

    def nonempty_fields(pairs, site):
        return {
            field for key, item in pairs for field in literal_key(key, constants) if resolved(item, site) is not None
        }

    candidates = []
    mutations = []

    def local_nodes(node):
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield from local_nodes(child)

    nodes = list(local_nodes(root))

    def matches(item, site):
        if entry.state is None:
            return True
        resolved = value(item, bindings)
        if resolved != entry.state:
            return False
        if isinstance(item, ast.Name):
            for previous in sorted(nodes, key=lambda node: getattr(node, 'lineno', 0), reverse=True):
                if not isinstance(previous, (ast.Assign, ast.AnnAssign)) or previous.lineno >= site.lineno:
                    continue
                targets = previous.targets if isinstance(previous, ast.Assign) else [previous.target]
                if any(isinstance(target, ast.Name) and target.id == item.id for target in targets) and guaranteed(
                    previous, site
                ):
                    assigned = value(previous.value, bindings)
                    return assigned is UNKNOWN or assigned == resolved
        return True

    for node in nodes:
        pairs = []
        mapping = None
        if isinstance(node, ast.Dict):
            pairs = list(zip(node.keys, node.values))
            parent = parents.get(node)
            if isinstance(parent, (ast.Assign, ast.AnnAssign)):
                targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                mapping = targets[0].id if len(targets) == 1 and isinstance(targets[0], ast.Name) else None
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'update':
                pairs = [(ast.Constant(keyword.arg), keyword.value) for keyword in node.keywords if keyword.arg]
                if len(node.args) == 1 and isinstance(node.args[0], ast.Dict):
                    pairs.extend(zip(node.args[0].keys, node.args[0].values))
                mapping = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            elif node.func.attr == 'setdefault' and len(node.args) >= 2:
                pairs = [(node.args[0], node.args[1])]
                mapping = node.func.value.id if isinstance(node.func.value, ast.Name) else None
        if pairs:
            for key, item in pairs:
                if entry.field in literal_key(key, constants) and matches(item, node):
                    candidates.append((node, mapping, nonempty_fields(pairs, node)))
            if mapping:
                nonempty = nonempty_fields(pairs, node)
                written = set().union(*(literal_key(key, constants) for key, _item in pairs))
                mutations.append((node, mapping, nonempty, written - nonempty))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    written = literal_key(target.slice, constants)
                    fields = written if resolved(node.value, node) is not None else set()
                    mutations.append((node, target.value.id, fields, written - fields))
                    if entry.field in fields and matches(node.value, node):
                        fields = (
                            nonempty_fields(zip(node.value.keys, node.value.values), node)
                            if isinstance(node.value, ast.Dict)
                            else fields
                        )
                        candidates.append((node, target.value.id, set(fields)))
        if isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    mutations.append((node, target.value.id, set(), literal_key(target.slice, constants)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'pop' and isinstance(node.func.value, ast.Name) and node.args:
                mutations.append((node, node.func.value.id, set(), literal_key(node.args[0], constants)))
    result = []
    sinks = {'update', 'set', 'put', 'patch', 'update_fair_use_state', 'update_fair_use_state_if_unchanged'}
    for node, mapping, fields in candidates:
        if not possible(node):
            continue
        stop = root.end_lineno + 1
        handoff = entry.inplace
        if mapping is None:
            parent = parents.get(node)
            handoff = handoff or (
                isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and parent.func.attr in sinks
            )
        if mapping:
            for later in nodes:
                if isinstance(later, ast.Call) and isinstance(later.func, ast.Attribute) and later.func.attr in sinks:
                    if later.lineno > node.lineno and any(
                        isinstance(arg, ast.Name) and arg.id == mapping for arg in later.args
                    ):
                        stop = min(stop, later.lineno)
                        handoff = True
            for later, target, extra, cleared in sorted(mutations, key=lambda mutation: mutation[0].lineno):
                if target == mapping and node.lineno < later.lineno < stop and possible(later):
                    fields.difference_update(cleared)
                    if guaranteed(later, node):
                        fields.update(extra)
        if handoff:
            result.append((node.lineno, deadline in fields))
    return result
