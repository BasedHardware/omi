#!/usr/bin/env python3
"""Keep the object-storage boundary sealed: utils/object_store/ is the only door (WP6).

Outside ``backend/utils/object_store/`` (and the documented exceptions below) no module may:
  * import the raw client — ``google.cloud.storage`` (or ``from google.cloud import storage``); or
  * run a raw blob/bucket op — ``.upload_from_string`` / ``.upload_from_filename`` /
    ``.upload_from_file`` / ``.download_as_bytes`` / ``.download_to_filename`` / ``.copy_blob`` /
    ``.delete_blob`` / ``.delete_blobs`` / ``.make_public`` / ``.list_blobs`` /
    ``.generate_signed_url`` method call, or a raw ``Blob.delete()`` (receiver/type-aware, since a
    bare ``.delete`` name collides — see ``_is_raw_blob_delete``).

Callers reach object storage through the neutral port (``utils.object_store.get_object_store()`` →
``put`` / ``get_bytes`` / ``presign_get`` / ``public_url`` / …), so the backend stays swappable
(GCS | S3-compatible). This is the object-store analogue of the Firestore persistence-boundary
guard; without it an upstream merge could silently reintroduce raw GCS in an auto-merged region or a
new file (ADR-0029/0030 — D14).

Ratchets against a baseline (WP6 target: empty). Companion of ADR-0032/0004.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/object_store_boundary_baseline.json')

# Paths (relative to the scan root, i.e. backend/) exempt from the boundary:
#  - utils/object_store/ : the boundary itself (the port + its gcs/s3 adapters).
#  - tests/, testing/    : the test suites (they inject the in-memory FakeObjectStore).
#  - scripts/            : one-off operational tooling, not deployed runtime (intentional — ADR-0023).
#  - agent-proxy/        : a separately deployed service (intentional — ADR-0023).
#  - migrations/         : removed in WP1; kept here so a re-added dir does not silently slip in.
EXCLUDED_PREFIXES = ('utils/object_store/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/', 'migrations/')

# Distinctive google-cloud-storage blob/bucket method names (no stdlib / domain collisions). The raw
# client import is forbidden on its own; these catch a client handed across a module boundary.
_FORBIDDEN_OP_METHODS = frozenset(
    {
        'upload_from_string',
        'upload_from_filename',
        'upload_from_file',
        'download_as_bytes',
        'download_to_filename',
        'copy_blob',
        'delete_blob',
        'delete_blobs',
        'make_public',
        'list_blobs',
        'generate_signed_url',
    }
)


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return module == 'google.cloud.storage' or module.startswith('google.cloud.storage')


def _looks_like_blob_name(name: str) -> bool:
    # A receiver identifier that denotes a GCS Blob object: exactly ``blob`` or a ``*_blob`` suffix.
    return name == 'blob' or name.endswith('_blob')


# GCS Blob instance methods whose bare names collide everywhere (a handed Blob could bypass the port
# through any of them), so they are only flagged when the receiver looks like a Blob — see below.
_RAW_BLOB_METHODS = frozenset({'delete', 'open', 'exists', 'patch'})


def _is_raw_blob_method(node: ast.Call) -> bool:
    """A raw GCS Blob instance method (delete/open/exists/patch) — receiver/type-aware, because these
    names collide everywhere.

    Caught: ``bucket.blob(key).<m>()`` / ``bucket.get_blob(key).<m>()`` (the receiver is a GCS blob
    factory call) and a Blob handed across a module boundary, ``blob.<m>()`` / ``x._blob.<m>()``
    (receiver named ``blob`` / ``*_blob``). The blessed port form ``get_object_store().<m>(...)`` is
    NOT flagged (its receiver is neither).
    """
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _RAW_BLOB_METHODS):
        return False
    receiver = func.value
    # ``<...>.blob(...).<m>()`` / ``<...>.get_blob(...).<m>()`` — receiver is a blob factory call.
    if (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Attribute)
        and receiver.func.attr in ('blob', 'get_blob')
    ):
        return True
    # ``blob.<m>()`` / ``self._blob.<m>()`` — receiver identifier looks like a Blob.
    if isinstance(receiver, ast.Name):
        return _looks_like_blob_name(receiver.id)
    if isinstance(receiver, ast.Attribute):
        return _looks_like_blob_name(receiver.attr)
    return False


def _is_s3_client_construction(node: ast.Call) -> bool:
    """A raw S3 client/resource: ``<x>.client('s3')`` / ``<x>.resource('s3')`` for ANY receiver.

    Keyed on the ``'s3'`` service name (not a blanket boto3 ban) so unrelated AWS clients (sqs/sns/…)
    are not false positives. The receiver is intentionally unconstrained — not just the literal
    ``boto3`` — so an aliased ``import boto3 as b3``, a ``boto3.Session().client('s3')``, and a
    ``session.client('s3')`` variable are all caught, closing the previous alias/Session bypass
    (cubic review PR 10887). The service name is read from the first positional arg or the
    ``service_name=`` keyword."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in ('client', 'resource')):
        return False
    arg = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == 'service_name'), None)
    return isinstance(arg, ast.Constant) and arg.value == 's3'


def _forbidden_dynamic_import(node: ast.Call, is_forbidden) -> bool:
    """A literal dynamic import of a forbidden module: ``importlib.import_module('X')``,
    ``import_module('X')`` (bare, from ``from importlib import import_module``) or ``__import__('X')``.

    The attribute form is restricted to ``importlib.import_module`` so an unrelated helper method named
    ``import_module`` is not a false positive. The module name is taken from the first positional
    argument or, if absent, the ``name=`` keyword — so a keyword-form call cannot dodge the check."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if not (func.attr == 'import_module' and isinstance(func.value, ast.Name) and func.value.id == 'importlib'):
            return False
    elif isinstance(func, ast.Name):
        if func.id not in ('import_module', '__import__'):
            return False
    else:
        return False
    arg = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == 'name'), None)
    return isinstance(arg, ast.Constant) and isinstance(arg.value, str) and is_forbidden(arg.value)


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            if _is_forbidden_import_module(alias.name):
                self.count += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        # ``from google.cloud.storage import X``.
        if _is_forbidden_import_module(node.module):
            self.count += 1
        # ``from google.cloud import storage``.
        elif node.module == 'google.cloud':
            if any(alias.name == 'storage' for alias in node.names):
                self.count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_OP_METHODS:
            self.count += 1
        elif _is_raw_blob_method(node):
            self.count += 1
        elif _is_s3_client_construction(node):
            self.count += 1
        elif _forbidden_dynamic_import(node, _is_forbidden_import_module):
            self.count += 1
        self.generic_visit(node)


def count_boundary_violations(source: str, filename: str = '<unknown>') -> int:
    visitor = _BoundaryVisitor()
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.count


def collect_counts(repository_root: Path, scan_root: Path) -> dict[str, int]:
    root = repository_root / scan_root
    counts: dict[str, int] = {}
    for path in sorted(root.rglob('*.py')):
        rel_to_scan = path.relative_to(root).as_posix()
        if any(rel_to_scan.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
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
    print('FAIL: object-store boundary breached — go through the utils.object_store port')
    print('(get_object_store().put / get_bytes / presign_get / public_url), not the raw GCS client.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
