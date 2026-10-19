"""Ratchet: importers of the legacy sync modules scheduled for retirement.

Why: workstream C of the backend target architecture retires legacy sync
transcription (the per-owner backfill sequencer, legacy redrive/dead letters,
the legacy fresh-lane budget, pre-STT WAL trims and the legacy empty-ASR
recovery) once the batch record lane serves 100% of owners. Each deletion PR
must be able to see every dependant it has to cut. This test freezes today's
import edges into those modules so the set can only shrink.

Scope (exact):

- Retiring modules: ``RETIRING_MODULES`` below, the class (a) rows of plan C
  section 2. Shared sync infrastructure that batch imports (assignment, ledger,
  bridge, stage, lineage, ...), enrichment (``reprocess``, custody, scan) and the
  cap-hold family are class (b) and deliberately absent.
- Importers: every ``*.py`` under ``backend/`` except ``tests/``, the legacy
  sync package itself (``utils/sync/``), ``routers/sync.py`` (both are deleted or
  rehomed with the modules) and the retiring modules themselves. ``testing/``
  (hermetic harness) and ``scripts/`` (operator tools) are in scope: a
  dependant there blocks deletion just as a runtime caller does.
- Edges: ``import a.b``, ``from a import b``, ``from a.b import c`` and
  package-relative forms, at any nesting depth (function-local imports count),
  plus ``importlib.import_module('<literal>')``. An edge is keyed by
  (backend-relative importer path, retiring module), never by line number.

The test fails when an edge appears (call the batch pipeline or shared
infrastructure instead; an edge that must exist goes into the baseline with a
reviewed ``why``) and when a baseline edge has disappeared (delete it so the
baseline stays tight). Deletion PRs C10/C11 take a module's edge list to zero.

Regenerate after deleting edges (keeps existing ``why`` strings; new edges get
the unreviewed placeholder, which a reviewer must replace)::

    cd backend && python tests/unit/test_sync_legacy_import_ratchet.py --write
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
# Direct ``--write`` invocation (``python tests/unit/test_sync_legacy_import_ratchet.py``)
# runs without backend/ on sys.path; bootstrap like scripts/select_backend_unit_tests.py.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.support.sync_legacy_ratchet_scope import (  # noqa: E402
    EXCLUDED_FILES as SCOPE_EXCLUDED_FILES,
    EXCLUDED_PARTS as SCOPE_EXCLUDED_PARTS,
    EXCLUDED_PREFIXES as SCOPE_EXCLUDED_PREFIXES,
    EXCLUDED_TOP_DIRS as SCOPE_EXCLUDED_TOP_DIRS,
    is_sync_legacy_ratchet_path,
)

BASELINE_PATH = BACKEND_DIR / 'tests' / 'unit' / 'fixtures' / 'sync_legacy_import_baseline.json'
UNREVIEWED = 'UNREVIEWED: justify this new dependant on retiring legacy sync code'

# module -> plan C deletion PR. Plan: omi-knowledge-base
# projects/backend-target-architecture/plan-c-legacy-consolidation.md, section 2.
RETIRING_MODULES: dict[str, str] = {
    'utils.sync.pipeline': 'C11',
    'utils.sync.uid_sequencer': 'C10',
    'database.sync_backfill_sequencer': 'C10',
    'utils.sync.owner_prefetch': 'C10',
    'utils.sync.staged_prefetch': 'C10',
    'utils.sync.backfill_cutover': 'C10',
    'utils.sync.backfill_order': 'C10',
    'database.sync_redrive': 'C10',
    'database.sync_dead_letters': 'C10',
    'utils.sync.redrive_policy': 'C10',
    'utils.sync.completed_status': 'C10',
    'utils.sync.legacy_fresh': 'C9/C11',
    'utils.sync.wal_audio_coverage': 'C11',
    'utils.sync.wal_audio_coverage_metrics': 'C11',
    'utils.sync.safety_wal_coverage': 'C11',
    'utils.sync.safety_wal_metrics': 'C11',
    'utils.sync.empty_recovery': 'C11',
    'utils.sync.empty_recovery_intent': 'C11',
    'database.sync_empty_recovery': 'C11',
}

EXCLUDED_TOP_DIRS = SCOPE_EXCLUDED_TOP_DIRS
# Local environments and caches (``.venv``, ``.openapi-venv``, ...) are not first-party code.
EXCLUDED_PARTS = SCOPE_EXCLUDED_PARTS
EXCLUDED_PREFIXES = SCOPE_EXCLUDED_PREFIXES
EXCLUDED_FILES = SCOPE_EXCLUDED_FILES


def _module_path(module: str) -> str:
    return module.replace('.', '/') + '.py'


def _module_name(relative: str) -> str:
    parts = relative[: -len('.py')].split('/')
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def _in_scope(relative: str) -> bool:
    parts = relative.split('/')
    if parts[0] in EXCLUDED_TOP_DIRS or any(part.startswith('.') or part in EXCLUDED_PARTS for part in parts):
        return False
    if relative.startswith(EXCLUDED_PREFIXES) or relative in EXCLUDED_FILES:
        return False
    return _module_name(relative) not in RETIRING_MODULES


def _resolve_from(node: ast.ImportFrom, importer: str) -> str | None:
    if not node.level:
        return node.module
    package = _module_name(importer).split('.')
    if not importer.endswith('__init__.py'):
        package = package[:-1]
    if node.level > 1:
        package = package[: len(package) - (node.level - 1)]
    return '.'.join([*package, *([node.module] if node.module else [])]) or None


def _retiring(candidate: str | None) -> str | None:
    if not candidate:
        return None
    for module in RETIRING_MODULES:
        if candidate == module or candidate.startswith(module + '.'):
            return module
    return None


def imported_retiring_modules(source: str, importer: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=importer)):
        if isinstance(node, ast.Import):
            found.update(m for m in (_retiring(alias.name) for alias in node.names) if m)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, importer)
            module = _retiring(base)
            if module:
                found.add(module)
                continue
            for alias in node.names:
                module = _retiring(f'{base}.{alias.name}' if base else alias.name)
                if module:
                    found.add(module)
        elif isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module')
            or (isinstance(node.func, ast.Name) and node.func.id == 'import_module')
        ):
            name_arg = next(
                (keyword.value for keyword in node.keywords if keyword.arg == 'name'),
                node.args[0] if node.args else None,
            )
            if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                module = _retiring(name_arg.value)
                if module:
                    found.add(module)
    return found


def current_edges() -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {module: set() for module in RETIRING_MODULES}
    for root, dirs, files in os.walk(BACKEND_DIR):
        # Prune environments/caches before descending; _in_scope stays the authority.
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in EXCLUDED_PARTS)
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            path = Path(root) / name
            relative = path.relative_to(BACKEND_DIR).as_posix()
            if not _in_scope(relative):
                continue
            for module in imported_retiring_modules(path.read_text(encoding='utf-8'), relative):
                edges[module].add(relative)
    return edges


def load_baseline() -> dict[str, dict[str, str]]:
    data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    return {module: dict(entry.get('importers', {})) for module, entry in data['modules'].items()}


def write_baseline() -> None:
    previous = load_baseline() if BASELINE_PATH.exists() else {}
    edges = current_edges()
    data = {
        'description': (
            'Frozen importers of legacy sync modules scheduled for retirement (plan C class (a)). '
            'May only shrink. Owned by tests/unit/test_sync_legacy_import_ratchet.py.'
        ),
        'modules': {
            module: {
                'retire_in': RETIRING_MODULES[module],
                'importers': {
                    importer: previous.get(module, {}).get(importer, UNREVIEWED) for importer in sorted(edges[module])
                },
            }
            for module in sorted(RETIRING_MODULES)
        },
    }
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + '\n', encoding='utf-8')


def test_retiring_modules_exist():
    missing = [m for m in RETIRING_MODULES if not (BACKEND_DIR / _module_path(m)).is_file()]
    assert not missing, (
        f'retired legacy sync modules {missing} no longer exist: remove them from RETIRING_MODULES '
        'and the baseline (their importer lists must already be empty)'
    )


def test_baseline_covers_exactly_the_retiring_modules():
    assert sorted(load_baseline()) == sorted(RETIRING_MODULES)


def test_baseline_edges_are_reviewed():
    unreviewed = [
        f'{importer} -> {module}'
        for module, importers in load_baseline().items()
        for importer, why in importers.items()
        if not why.strip() or why.startswith('UNREVIEWED')
    ]
    assert not unreviewed, f'baseline edges need a reviewed "why": {unreviewed}'


@pytest.fixture(scope='module')
def edges() -> dict[str, set[str]]:
    # Parse the tree once per module, outside the per-test call budget.
    return current_edges()


def test_no_new_importers_of_retiring_legacy_sync_modules(edges):
    baseline = load_baseline()
    added = sorted(
        f'{importer} -> {module}'
        for module, importers in edges.items()
        for importer in importers - set(baseline.get(module, {}))
    )
    assert not added, (
        'New dependants on legacy sync modules scheduled for deletion (plan C). Use the batch pipeline or '
        f'shared sync infrastructure instead: {added}'
    )


def test_baseline_only_shrinks_stale_edges_are_removed(edges):
    stale = sorted(
        f'{importer} -> {module}'
        for module, importers in load_baseline().items()
        for importer in set(importers) - edges.get(module, set())
    )
    assert not stale, (
        'These baseline edges no longer exist; remove them so the ratchet stays tight '
        f'(python tests/unit/test_sync_legacy_import_ratchet.py --write): {stale}'
    )


@pytest.mark.parametrize(
    ('source', 'importer', 'expected'),
    [
        ('import utils.sync.pipeline', 'utils/x.py', {'utils.sync.pipeline'}),
        ('import utils.sync.pipeline as legacy', 'utils/x.py', {'utils.sync.pipeline'}),
        ('from utils.sync import pipeline, reprocess', 'utils/x.py', {'utils.sync.pipeline'}),
        ('from utils.sync.uid_sequencer import sweep', 'utils/x.py', {'utils.sync.uid_sequencer'}),
        ('def f():\n    from database import sync_redrive\n', 'services/x.py', {'database.sync_redrive'}),
        ('from .sync_dead_letters import x', 'database/other.py', {'database.sync_dead_letters'}),
        ('from . import sync_empty_recovery', 'database/other.py', {'database.sync_empty_recovery'}),
        ('importlib.import_module("utils.sync.legacy_fresh")', 'utils/x.py', {'utils.sync.legacy_fresh'}),
        ('importlib.import_module(name="utils.sync.legacy_fresh")', 'utils/x.py', {'utils.sync.legacy_fresh'}),
        ('importlib.import_module(name=name_variable)', 'utils/x.py', set()),
        ('from utils.sync import reprocess, assignment', 'utils/x.py', set()),
        ('from utils.sync.pipeline_v2 import x', 'utils/x.py', set()),
        ('import database.sync_ledger', 'utils/x.py', set()),
    ],
)
def test_import_detection(source, importer, expected):
    assert imported_retiring_modules(source, importer) == expected


@pytest.mark.parametrize(
    ('relative', 'scoped'),
    [
        ('utils/batch_pipeline/enrichment.py', True),
        ('testing/pipeline_sim/x.py', True),
        ('utils/sync/reprocess.py', False),
        ('routers/sync.py', False),
        ('database/sync_redrive.py', False),
        ('tests/unit/test_x.py', False),
        ('.openapi-venv/lib/python3.11/site-packages/aenum/_py2.py', False),
        ('venv/lib/x.py', False),
    ],
)
def test_importer_scope(relative, scoped):
    assert _in_scope(relative) is scoped


@pytest.mark.parametrize(
    ('path', 'selects'),
    [
        # Any importer in the ratchet's scope selects the ratchet, even when
        # its AREA_TESTS mapping has no test_sync_* glob (utils/apps).
        ('backend/utils/apps/app_loader.py', True),
        ('backend/utils/other/storage.py', True),
        ('backend/database/sync_jobs.py', True),
        ('backend/testing/pipeline_sim/sim.py', True),
        ('backend/scripts/repair_sync_redrive.py', True),
        ('backend/main.py', True),
        # The ratchet's own excluded scopes stay narrow.
        ('backend/tests/unit/test_x.py', False),
        ('backend/utils/sync/pipeline.py', False),
        ('backend/routers/sync.py', False),
        # Not Python source: cannot add an import edge.
        ('backend/utils/apps/README.md', False),
    ],
)
def test_ratchet_selects_for_every_scoped_importer(path, selects):
    assert is_sync_legacy_ratchet_path(path) is selects


def test_selection_scope_is_the_ratchet_scope():
    """The selector predicate must be a superset of the ratchet's importer
    scope: every ``_in_scope`` path must select the ratchet, and the shared
    exclusion constants cannot drift apart."""
    assert SCOPE_EXCLUDED_TOP_DIRS == {'tests'}
    assert SCOPE_EXCLUDED_PREFIXES == ('utils/sync/',)
    assert SCOPE_EXCLUDED_FILES == {'routers/sync.py'}
    for relative in _all_source_paths():
        if _in_scope(relative):
            assert is_sync_legacy_ratchet_path(relative), relative


def _all_source_paths():
    for root, dirs, files in os.walk(BACKEND_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in EXCLUDED_PARTS)
        for name in sorted(files):
            if name.endswith('.py'):
                yield Path(root, name).relative_to(BACKEND_DIR).as_posix()


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        write_baseline()
        print(f'wrote {BASELINE_PATH.relative_to(BACKEND_DIR)}')
    else:
        raise SystemExit('usage: python tests/unit/test_sync_legacy_import_ratchet.py --write')
