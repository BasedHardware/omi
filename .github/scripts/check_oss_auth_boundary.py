#!/usr/bin/env python3
"""Keep the auth boundary sealed: utils/auth/ is the only door to Firebase Auth (WP3).

Outside ``backend/utils/auth/`` (and the documented exceptions below) no module may touch the Firebase
**auth** surface — ``import firebase_admin.auth`` / ``from firebase_admin.auth import ...`` /
``from firebase_admin import auth`` / a ``<firebase_admin-alias>.auth`` attribute access (e.g.
``firebase_admin.auth.verify_id_token(...)`` after a plain ``import firebase_admin``, or
``fb.auth.verify_id_token(...)`` after ``import firebase_admin as fb``). Callers reach
authentication through the neutral port (``utils.auth.get_auth_provider()`` → verify_token /
get_user_profile / …), so the backend stays swappable (Firebase | OIDC/Keycloak).

Deliberately NOT forbidden: ``firebase_admin.initialize_app`` (process bootstrap), ``firebase_admin.
messaging`` (push, ADR-0011), ``firebase_admin.firestore`` (that's the Firestore guard's job).

Deliberately NOT DETECTED, and the reason matters more than the list: ``getattr(firebase_admin, 'auth')``,
``sys.modules['firebase_admin'].auth`` and a package smuggled through a container (``{'fb':
firebase_admin}['fb'].auth``). Nothing in the tree writes them, product code has no reason to, and
chasing every dynamic shape turns a precise guard into a false-positive machine. What IS covered is the
one realistic escape: a module handing the package out via ``return firebase_admin`` (see ast.Return
below), because the codebase already uses a lazy-accessor idiom one small step away from it. The
consumer side of that shape (``someone_elses_accessor().auth``) stays undetectable by construction —
attribute tracking works on names, not on call results. This is
the auth analogue of the Firestore/object-store/vector boundary guards; without it an upstream merge
could silently reintroduce a raw Firebase-auth call (ADR-0029/0030). Ratchets against a baseline (WP3
target: empty). Companion of ADR-0034/0004.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/auth_boundary_baseline.json')

# Paths (relative to the scan root, i.e. backend/) exempt from the boundary:
#  - utils/auth/ : the boundary itself (the port + its firebase/oidc adapters).
#  - tests/, testing/ : the test suites (they inject the in-memory FakeAuthProvider / stub firebase).
#  - scripts/    : one-off operational tooling (ADR-0023).
#  - agent-proxy/, pusher/ : separately deployed services with their own firebase app (ADR-0023).
# NOTE: migrations/ is intentionally NOT excluded — a re-added migration that touches Firebase auth
# directly must fail this boundary too (the upstream migrations reach auth only via the port; verified 0).
EXCLUDED_PREFIXES = ('utils/auth/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/', 'pusher/')

# Build scratch, which is not source and must never be scanned. CI creates `backend/.openapi-venv`
# (the OpenAPI export's env) and `backend/.venv` in EARLIER STEPS OF THE SAME JOB, so by the time this
# guard runs they are sitting in the tree — and a dependency shipping a Python-2 file (`aenum/_py2.py`)
# made `ast.parse` raise SyntaxError and took the whole check down. Measured on CI, not theorised: the
# same crash reproduces locally the moment a venv exists, and deleting it is treating the symptom.
NOT_SOURCE_DIRS = frozenset({'.venv', '.openapi-venv', 'node_modules', '__pycache__', '.pytest_cache', '_temp'})

# EXCEPT the ones the runtime actually imports. ADR-0023's premise — "scripts/ is not deployed runtime" —
# is FALSE for two modules (BACKLOG L12): main.py imports scripts/reconcile_mongo_indexes.py and calls it at
# boot, and utils/memory/canonical_short_term_maintenance_cron.py imports run_enrichment from
# scripts/enrich_historical_memory_graph.py. Excluding the whole directory therefore left runtime code
# unscanned. These two are scanned; tests/unit/test_runtime_reachable_scripts.py RECOMPUTES the set from the
# source, so the tuple cannot drift away from reality.
RUNTIME_REACHABLE_SCRIPTS = (
    'scripts/enrich_historical_memory_graph.py',
    'scripts/reconcile_mongo_indexes.py',
)


# ``ast.Match`` / the pattern nodes exist only on Python 3.10+; a file using ``match`` cannot parse on
# an older interpreter anyway, so the pattern handling is reached only where these attributes exist.
_AST_MATCH = getattr(ast, 'Match', None)


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return module == 'firebase_admin.auth' or module.startswith('firebase_admin.auth.')


def _is_dynimport_callable(value: ast.AST) -> bool:
    """True if ``value`` is a reference to the dynamic-import *callable itself* (not a call of it):
    ``importlib.import_module``, a bare ``import_module`` (from ``from importlib import import_module``)
    or ``__import__``. Used to track ``im = importlib.import_module`` aliases."""
    if isinstance(value, ast.Attribute):
        return value.attr == 'import_module' and isinstance(value.value, ast.Name) and value.value.id == 'importlib'
    if isinstance(value, ast.Name):
        return value.id in ('import_module', '__import__')
    return False


def _collect_dynimport_aliases(tree: ast.AST) -> frozenset[str]:
    """Names bound to the dynamic-import callable, e.g. ``im = importlib.import_module``. Without this
    ``im('firebase_admin.auth')`` would dodge the dynamic-import check (only the literal
    ``import_module`` / ``__import__`` receivers were recognised)."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_dynimport_callable(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
    return frozenset(aliases)


def _forbidden_dynamic_import(node: ast.Call, is_forbidden, extra_names: frozenset[str] = frozenset()) -> bool:
    """A literal dynamic import of a forbidden module: ``importlib.import_module('X')``,
    ``import_module('X')`` (bare, from ``from importlib import import_module``), ``__import__('X')`` or
    an aliased callable ``im('X')`` (``im = importlib.import_module``; ``extra_names``).

    The attribute form is restricted to ``importlib.import_module`` so an unrelated helper method named
    ``import_module`` is not a false positive. The module name is taken from the first positional
    argument or, if absent, the ``name=`` keyword — so a keyword-form call cannot dodge the check."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if not (func.attr == 'import_module' and isinstance(func.value, ast.Name) and func.value.id == 'importlib'):
            return False
    elif isinstance(func, ast.Name):
        if func.id not in ('import_module', '__import__') and func.id not in extra_names:
            return False
    else:
        return False
    arg = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == 'name'), None)
    return isinstance(arg, ast.Constant) and isinstance(arg.value, str) and is_forbidden(arg.value)


class _Count:
    __slots__ = ('n', 'dynimport')

    def __init__(self) -> None:
        self.n = 0
        self.dynimport: frozenset[str] = frozenset()


def _scan_expr(node: ast.AST, aliases: set[str], count: _Count) -> None:
    """Count auth-surface accesses inside a single expression: a ``<alias>.auth`` attribute (where
    ``alias`` is currently bound to ``firebase_admin`` in this scope) or a literal dynamic import of
    ``firebase_admin.auth``. Expressions never open a statement scope, so a plain walk is safe here —
    only *statements* rebind names, and scope/order tracking happens in ``_scan_stmt``."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
            # Walrus ``(fb := firebase_admin)``: the only expression form that *binds* a name. Propagate
            # or clear the package alias so a later ``fb.auth`` in this scope is seen (statements share
            # this mutable ``aliases`` set). Non-walrus expressions never rebind, so a plain walk is safe.
            if isinstance(sub.value, ast.Name) and sub.value.id in aliases:
                aliases.add(sub.target.id)
            else:
                aliases.discard(sub.target.id)
        elif isinstance(sub, ast.Attribute):
            if sub.attr == 'auth' and isinstance(sub.value, ast.Name) and sub.value.id in aliases:
                count.n += 1
        elif isinstance(sub, ast.Call) and _forbidden_dynamic_import(sub, _is_forbidden_import_module, count.dynimport):
            count.n += 1


def _scan_scope(statements: list[ast.stmt], inherited: set[str], count: _Count) -> None:
    """Walk one lexical scope's statements *in order*, tracking which names are bound to the
    ``firebase_admin`` package. Seeded from a snapshot of the enclosing scope so a nested function
    still sees a module-level ``import firebase_admin as fb``; a local rebind (``fb = build_client()``)
    then drops ``fb`` for the rest of *this* scope, so a legitimate ``fb.auth`` on an unrelated object
    is not a false positive. Compound statements (if/for/while/with/try/match) share this same scope."""
    aliases = set(inherited)
    for stmt in statements:
        _scan_stmt(stmt, aliases, count)


def _scan_pattern(
    pattern: ast.AST | None,
    aliases: set[str],
    subject_is_alias: bool,
    case_aliases: set[str],
    count: _Count,
) -> None:
    """Scan one match ``case`` pattern. Python forbids calls in patterns, so the only auth surface a
    pattern can reach is a ``MatchValue`` value pattern (``case fb.auth.X:``) — scanned as an
    expression. A top-level ``MatchAs`` capture (``case obj`` / ``case _ as obj``) of a
    firebase-aliased *subject* rebinds the captured name to the package alias for this case's
    guard/body; captures nested inside a sequence/mapping/class pattern bind sub-values, not the
    subject, so the alias does not propagate into them."""
    if pattern is None:
        return
    if isinstance(pattern, ast.MatchValue):
        _scan_expr(pattern.value, aliases, count)
    elif isinstance(pattern, ast.MatchAs):
        # ``<inner> as name`` — both the inner capture chain and ``name`` bind the same subject value.
        _scan_pattern(pattern.pattern, aliases, subject_is_alias, case_aliases, count)
        if pattern.name is not None:
            if subject_is_alias:
                case_aliases.add(pattern.name)
            else:
                case_aliases.discard(pattern.name)
    elif isinstance(pattern, ast.MatchOr):  # each alternative matches the same subject
        for alt in pattern.patterns:
            _scan_pattern(alt, aliases, subject_is_alias, case_aliases, count)
    elif isinstance(pattern, ast.MatchSequence):
        for sub in pattern.patterns:
            _scan_pattern(sub, aliases, False, case_aliases, count)
    elif isinstance(pattern, ast.MatchMapping):
        for sub in pattern.patterns:
            _scan_pattern(sub, aliases, False, case_aliases, count)
    elif isinstance(pattern, ast.MatchClass):
        for sub in [*pattern.patterns, *pattern.kwd_patterns]:
            _scan_pattern(sub, aliases, False, case_aliases, count)
    # MatchSingleton / MatchStar: no nested pattern or value to scan.


def _bind_target(target: ast.expr, value: ast.expr | None, aliases: set[str], count: _Count) -> None:
    """Propagate/clear the firebase_admin package alias from an assignment's RHS onto one target.
    A plain ``fb2 = fb`` binds when the RHS name is a live alias; a ``fb = <non-alias>`` clears it.
    Tuple/list unpacking (``a, fb = 1, firebase_admin``) matches element-wise against a same-length
    tuple/list RHS so ``fb`` still becomes an alias; any other target shape (subscript/attribute) or a
    non-decomposable RHS just clears its Name targets and scans the target expression."""
    if isinstance(target, ast.Name):
        if isinstance(value, ast.Name) and value.id in aliases:
            aliases.add(target.id)
        else:
            aliases.discard(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        elts = value.elts if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts) else None
        for i, elt in enumerate(target.elts):
            _bind_target(elt, elts[i] if elts is not None else None, aliases, count)
    else:
        _scan_expr(target, aliases, count)


def _scan_stmt(stmt: ast.stmt, aliases: set[str], count: _Count) -> None:
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            if _is_forbidden_import_module(alias.name):
                count.n += 1
            if alias.name == 'firebase_admin' or alias.name.startswith('firebase_admin.'):
                aliases.add(alias.asname or alias.name.split('.', 1)[0])
            elif alias.asname:
                # A non-firebase import shadowing a name that was an alias clears it.
                aliases.discard(alias.asname)
        return

    if isinstance(stmt, ast.ImportFrom):
        # ``from firebase_admin.auth import X``.
        if _is_forbidden_import_module(stmt.module):
            count.n += 1
        # ``from firebase_admin import auth``.
        elif stmt.module == 'firebase_admin' and any(a.name == 'auth' for a in stmt.names):
            count.n += 1
        # ``from firebase_admin import X`` binds the *submodule* firebase_admin.X, not the package, so
        # ``X.auth`` is never firebase_admin.auth — such a name must not become a package alias. A
        # from-import that reuses an alias name shadows it.
        for a in stmt.names:
            aliases.discard(a.asname or a.name)
        return

    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Decorators / default values / base classes are evaluated in the *enclosing* scope.
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.arguments):
                for default in [*child.defaults, *(d for d in child.kw_defaults if d is not None)]:
                    _scan_expr(default, aliases, count)
            elif isinstance(child, ast.expr):
                _scan_expr(child, aliases, count)
        if isinstance(stmt, ast.ClassDef):
            # Class attributes are class-local names, NOT bare names inside the methods (which reach
            # them via self/ClassName). So a class-level attribute must neither shadow nor become a
            # bare alias for the methods: seed each nested def/class from the ENCLOSING aliases, while
            # class-level statements mutate only a class-local set.
            enclosing = set(aliases)
            class_local = set(aliases)
            for body_stmt in stmt.body:
                if isinstance(body_stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _scan_stmt(body_stmt, set(enclosing), count)
                else:
                    _scan_stmt(body_stmt, class_local, count)
        else:
            _scan_scope(stmt.body, aliases, count)  # body opens a fresh scope seeded from this snapshot
        aliases.discard(stmt.name)  # the def/class name is a non-alias binding in this scope
        return

    if isinstance(stmt, ast.Return):
        # Handing the firebase_admin PACKAGE out of a module outside the boundary. The lazy-accessor
        # idiom is already in the codebase (utils/auth/adapters/firebase.py returns the `auth` MODULE,
        # which this guard catches on its import), and a variant returning the package instead was the
        # one realistic shape the guard could not see: `def _fb(): return firebase_admin` makes every
        # later `_fb().auth` invisible, because the attribute is then on a Call, not on a tracked Name.
        # Returning the package has no legitimate use outside utils/auth/, so this cannot false-positive.
        if stmt.value is not None:
            if isinstance(stmt.value, ast.Name) and stmt.value.id in aliases:
                count.n += 1
            _scan_expr(stmt.value, aliases, count)
        return

    if isinstance(stmt, ast.Assign):
        _scan_expr(stmt.value, aliases, count)
        for target in stmt.targets:
            _bind_target(target, stmt.value, aliases, count)
        return

    if isinstance(stmt, ast.AnnAssign):
        if stmt.value is not None:
            _scan_expr(stmt.value, aliases, count)
        if isinstance(stmt.target, ast.Name):
            if stmt.value is not None and isinstance(stmt.value, ast.Name) and stmt.value.id in aliases:
                aliases.add(stmt.target.id)
            elif stmt.value is not None:
                aliases.discard(stmt.target.id)
        _scan_expr(stmt.annotation, aliases, count)
        return

    if isinstance(stmt, ast.If):
        # Branch-sensitive: a rebind inside one branch must NOT clear the alias for the sibling
        # branch or for statements after the if. Scan each branch on its own copy, then keep an
        # alias if it survives on EITHER path (union) so a later access on the not-rebound path stays
        # visible.
        _scan_expr(stmt.test, aliases, count)
        branch = set(aliases)
        for s in stmt.body:
            _scan_stmt(s, branch, count)
        other = set(aliases)
        for s in stmt.orelse:
            _scan_stmt(s, other, count)
        aliases.clear()
        aliases.update(branch | other)
        return

    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
        # A loop body may run zero or more times: union the not-entered (original), body, and else
        # states so a conditional rebind inside the loop cannot hide a later alias access.
        before = set(aliases)
        if isinstance(stmt, ast.While):
            _scan_expr(stmt.test, aliases, count)
        else:
            _scan_expr(stmt.iter, aliases, count)
            if isinstance(stmt.target, ast.Name):
                aliases.discard(stmt.target.id)  # the loop variable rebinds this name to an element
            else:
                _scan_expr(stmt.target, aliases, count)
        body_aliases = set(aliases)
        for s in stmt.body:
            _scan_stmt(s, body_aliases, count)
        else_aliases = set(aliases)
        for s in stmt.orelse:
            _scan_stmt(s, else_aliases, count)
        aliases.clear()
        aliases.update(before | body_aliases | else_aliases)
        return

    if _AST_MATCH is not None and isinstance(stmt, _AST_MATCH):
        # ``match <subject>: case <pattern> [if <guard>]: <body>``. Each case is branch-like — a
        # capture binds only in that case's guard/body — so scan every case on its own alias copy.
        # Beyond the already-covered guard/body: the *pattern* itself can reach the auth surface via a
        # ``MatchValue`` value pattern (``case fb.auth.X:``), and a top-level ``MatchAs`` capture of a
        # firebase-aliased subject (``match fb: case obj:``) rebinds the captured name to the alias.
        _scan_expr(stmt.subject, aliases, count)
        subject_is_alias = isinstance(stmt.subject, ast.Name) and stmt.subject.id in aliases
        for case in stmt.cases:
            case_aliases = set(aliases)
            _scan_pattern(case.pattern, aliases, subject_is_alias, case_aliases, count)
            if case.guard is not None:
                _scan_expr(case.guard, case_aliases, count)
            _scan_scope(case.body, case_aliases, count)
        return

    # Generic statement (Expr / Return / AugAssign / With / Try / match / …): scan its expression
    # children here and recurse into any sub-statement bodies as the *same* scope, in order, so alias
    # rebinds inside a linear block are seen by later statements.
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.stmt):
            _scan_stmt(child, aliases, count)
        elif isinstance(child, ast.excepthandler):
            if child.type is not None:
                _scan_expr(child.type, aliases, count)
            _scan_scope(child.body, aliases, count)
        elif isinstance(child, ast.withitem):
            # ``with fb.auth...() as X``: the context expression was previously missed (withitem is
            # neither an ast.stmt nor an ast.expr). Scan it, and propagate/clear the alias onto X.
            _scan_expr(child.context_expr, aliases, count)
            if isinstance(child.optional_vars, ast.Name):
                if isinstance(child.context_expr, ast.Name) and child.context_expr.id in aliases:
                    aliases.add(child.optional_vars.id)
                else:
                    aliases.discard(child.optional_vars.id)
        elif isinstance(child, ast.expr):
            _scan_expr(child, aliases, count)


def count_boundary_violations(source: str, filename: str = '<unknown>') -> int:
    tree = ast.parse(source, filename=filename)
    count = _Count()
    count.dynimport = _collect_dynimport_aliases(tree)
    # ``firebase_admin`` is always recognised at module scope so a raw ``firebase_admin.auth`` is
    # caught even in a file that only imports the submodule directly.
    _scan_scope(tree.body, {'firebase_admin'}, count)
    return count.n


def collect_counts(repository_root: Path, scan_root: Path) -> dict[str, int]:
    root = repository_root / scan_root
    counts: dict[str, int] = {}
    for path in sorted(root.rglob('*.py')):
        if NOT_SOURCE_DIRS.intersection(path.parts):
            continue
        rel_to_scan = path.relative_to(root).as_posix()
        if rel_to_scan not in RUNTIME_REACHABLE_SCRIPTS and any(
            rel_to_scan.startswith(prefix) for prefix in EXCLUDED_PREFIXES
        ):
            continue
        count = count_boundary_violations(path.read_text(encoding='utf-8'), str(path))
        if count:
            counts[path.relative_to(repository_root).as_posix()] = count
    return counts


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of path-to-nonnegative-count entries: {path}')
    return payload


def violations(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    return [
        f'{path}: found {count}, baseline allows {baseline.get(path, 0)}'
        for path, count in sorted(counts.items())
        if count > baseline.get(path, 0)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--scan-root', type=Path, default=DEFAULT_SCAN_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--print-counts', action='store_true')
    args = parser.parse_args()

    repository_root = args.root.resolve()
    counts = collect_counts(repository_root, args.scan_root)
    if args.print_counts:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0

    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline
    errors = violations(counts, load_baseline(baseline_path))
    if not errors:
        return 0
    print('FAIL: auth boundary breached — go through the utils.auth port')
    print('(get_auth_provider().verify_token / get_user_profile), not firebase_admin.auth.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
