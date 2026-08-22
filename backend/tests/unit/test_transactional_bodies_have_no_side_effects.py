"""The precondition poison-and-defer rests on, made mechanical (ADR-0091, BACKLOG L53).

When a write inside a transaction hits a Mongo write conflict, the facade no longer raises: it records
the conflict, lets the body run on to the end with every further store operation inert, and re-raises at
``_commit`` — the one place google's ``@transactional`` decorator retries. The body therefore runs at
least twice, and the losing run's store writes are all discarded.

That is only safe while a transactional body does **nothing but touch the store**. A body that sent an
email, enqueued a vector write, posted a notification or bumped a counter would do it on a run whose
writes land nowhere, and then do it again on the replay: one request, two side effects, one of them for
a decision that was thrown away.

When the design was chosen this was measured across the tree — 155 transactional bodies, none with a
side effect outside the store. A measurement in a commit message rots; this is the same measurement as a
test, so the day someone adds the first one, the design's precondition fails loudly here instead of
quietly in production.

It is a STATIC check (an AST scan), not behavioural coverage, and says so: it cannot see a side effect
reached through an indirection it does not name. What it does catch is the direct, obvious form, which
is how such a call actually arrives.
"""

from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]

# Names whose appearance inside a transactional body means "this reaches something other than the store".
# Kept as whole-word identifiers rather than substrings: `email` as a FIELD name is not a side effect,
# and an earlier draft of this scan flagged four bodies for exactly that reason before being tightened.
SIDE_EFFECT_CALLS = frozenset(
    {
        'record_fallback',
        'send_notification',
        'send_email',
        'publish_message',
        'upsert_vector',
        'upsert_vectors',
        'delete_vector',
        'delete_vectors',
        'post',
        'put_object',
        'delete_object',
        'enqueue_task',
        'create_task',
    }
)
SIDE_EFFECT_MODULES = frozenset({'requests', 'httpx', 'urllib', 'smtplib', 'boto3'})

SKIP_DIRS = ('tests', 'testing', 'scripts', '__pycache__', '_temp')


def _transactional_bodies():
    """Every function that runs inside a transaction: decorated with a `transactional`, or taking one."""
    for path in sorted(BACKEND.rglob('*.py')):
        relative = path.relative_to(BACKEND)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorated = any('transactional' in ast.dump(d) for d in node.decorator_list)
            takes_one = bool(node.args.args) and node.args.args[0].arg == 'transaction'
            if decorated or takes_one:
                yield relative, node


def _offending_calls(node):
    found = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        function = inner.func
        if isinstance(function, ast.Name) and function.id in SIDE_EFFECT_CALLS:
            found.append(function.id)
        elif isinstance(function, ast.Attribute):
            if function.attr in SIDE_EFFECT_CALLS:
                root = function.value
                while isinstance(root, ast.Attribute):
                    root = root.value
                # `transaction.post(...)` is not a thing, but `client.post(...)` is; only flag when the
                # receiver is not the transaction or a document reference.
                if not (isinstance(root, ast.Name) and root.id in {'transaction', 'ref', 'doc_ref'}):
                    found.append(f'{getattr(root, "id", "?")}.{function.attr}')
            if isinstance(function.value, ast.Name) and function.value.id in SIDE_EFFECT_MODULES:
                found.append(f'{function.value.id}.{function.attr}')
    return sorted(set(found))


def test_the_scan_finds_the_transactional_bodies_it_claims_to():
    """A scan that matched nothing would pass vacuously forever."""
    bodies = list(_transactional_bodies())

    assert len(bodies) > 100, f'only {len(bodies)} transactional bodies found — the pattern or the tree moved'


def test_no_transactional_body_reaches_outside_the_store():
    offenders = []
    for relative, node in _transactional_bodies():
        found = _offending_calls(node)
        if found:
            offenders.append(f'{relative}:{node.lineno} {node.name}() -> {found}')

    assert not offenders, (
        'a transactional body reaches something other than the store, which poison-and-defer '
        '(ADR-0091) cannot replay safely — the losing run would do it too:\n  ' + '\n  '.join(offenders)
    )
