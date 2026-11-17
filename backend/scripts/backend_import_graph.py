"""Static import graph for backend unit-test selection.

The selector uses this to replace "run the whole suite" with "run the tests
that can import the changed module" for Python sources that no hand-written
contract covers. The graph is deliberately conservative where it is cheap to
be and narrow only where the evidence allows:

* Edges come from module-level code: top-level statements, class bodies and
  module-level ``if``/``try``/``with`` blocks, including ``TYPE_CHECKING``
  blocks. These run at import time, so the closure over them is the set of
  modules a test loads just by importing.
* Imports inside a function body ("lazy" imports) are not followed
  transitively; following them makes nearly every test reach nearly every
  module (2026-11-17 measurement: 3,054 of 3,075 tests). Instead, modules
  that lazily import the changed module are added as one extra starting
  point, and the module-level closure is taken from there.
* ``import a.b.c`` and ``from a.b import c`` also depend on the packages
  ``a`` and ``a.b``, whose ``__init__`` runs first. Relative imports are
  resolved against the importing module's package.
* A test file also depends on every ``conftest.py`` in its ancestor
  directories, because pytest imports them before the test.
* ``importlib.import_module`` and ``__import__`` calls with a literal name
  are edges. A module or data file is also reached by any module whose
  source names its file (``runpy.run_path``, ``subprocess`` script paths,
  fixtures), so scripts run without an import are still selected.

Dependencies this graph cannot see (``importlib``, string-based loading,
data files read at runtime, tests that scan the source tree) are why callers
must keep a full-suite fallback for non-Python inputs, unparseable or deleted
modules, and a scheduled full run.
"""

from __future__ import annotations

import ast
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

TEST_TREE_PREFIXES = ('tests/', 'testing/', 'scripts/jobstore_operator/tests/')
# Python source scans: ratchets and inventories that read whole source trees
# instead of importing what they check (``UTILS_DIR.rglob('*.py')``, an
# ``os.walk`` filtered to ``.py``). Directory listings of fixtures do not count.
TREE_SCAN_PATTERN = re.compile(
    rb"""\.r?glob\(\s*['"][^'"]*\.py['"]"""  # Path.glob/rglob('*.py' | '**/*.py')
    rb"""|glob\.glob\([^)]*\.py"""
    rb"""|['"]--glob['"]\s*,\s*['"][^'"]*\.py['"]"""  # rg --glob '*.py' subprocess scans
    rb"""|\.rglob\(\s*['"]\*['"]\s*\)[\s\S]{0,300}?\.py['"]"""  # rglob('*') filtered to .py
    rb"""|os\.walk\([^)]*\)[\s\S]{0,400}?\.py['"]"""
    rb"""|iterdir\(\)[\s\S]{0,200}?(?:\.suffix\s*==\s*['"]\.py|endswith\(\s*['"]\.py)"""
)

SKIP_DIR_NAMES = frozenset({'.venv', 'venv', 'node_modules', '__pycache__', '.git', '.mypy_cache', '.pytest_cache'})


def module_name_for(relative_path: str) -> Optional[str]:
    """``database/x.py`` -> ``database.x``; package ``__init__`` -> package name."""
    if not relative_path.endswith('.py'):
        return None
    parts = relative_path[:-3].split('/')
    if parts[-1] == '__init__':
        parts = parts[:-1]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return '.'.join(parts)


def _parent_packages(name: str) -> Iterable[str]:
    parts = name.split('.')
    for index in range(1, len(parts) + 1):
        yield '.'.join(parts[:index])


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, module: str, is_package: bool):
        self.module = module
        self.package = module if is_package else module.rpartition('.')[0]
        self.depth = 0  # function nesting depth
        self.module_level: Set[str] = set()
        self.lazy: Set[str] = set()

    def _add(self, names: Iterable[str]) -> None:
        target = self.lazy if self.depth else self.module_level
        for name in names:
            target.update(_parent_packages(name))

    def _function(self, node: ast.AST) -> None:
        # Decorators and default values run at definition time, i.e. import time.
        for child in getattr(node, 'decorator_list', []):
            self.visit(child)
        args = getattr(node, 'args', None)
        if args is not None:
            for default in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
                self.visit(default)
        self.depth += 1
        for child in getattr(node, 'body', []):
            self.visit(child)
        self.depth -= 1

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        # importlib.import_module('pkg.mod') / import_module(...) / __import__(...)
        # with a literal absolute name is an ordinary import edge.
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
        if name in {'import_module', '__import__'} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and not first.value.startswith('.'):
                self._add([first.value])
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self._add(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            base_parts = self.package.split('.') if self.package else []
            if node.level > 1:
                base_parts = base_parts[: len(base_parts) - (node.level - 1)]
            base = '.'.join(part for part in base_parts + ([node.module] if node.module else []) if part)
        else:
            base = node.module or ''
        if not base:
            names = [alias.name for alias in node.names if alias.name != '*']
            self._add(names)
            return
        self._add([base] + [f'{base}.{alias.name}' for alias in node.names if alias.name != '*'])


@dataclass
class ImportGraph:
    backend_dir: Path
    modules: Dict[str, str] = field(default_factory=dict)  # module -> backend-relative path
    path_modules: Dict[str, str] = field(default_factory=dict)  # backend-relative path -> module
    importers: Dict[str, Set[str]] = field(default_factory=dict)  # module -> module-level importers
    lazy_importers: Dict[str, Set[str]] = field(default_factory=dict)  # module -> function-level importers
    unparseable: Set[str] = field(default_factory=set)  # backend-relative paths
    _sources: Optional[Dict[str, bytes]] = field(default=None, repr=False)
    _tree_scan_modules: Optional[Set[str]] = field(default=None, repr=False)
    _tree_scan_tests: Dict[tuple, Set[str]] = field(default_factory=dict, repr=False)

    def module_for_path(self, relative_path: str) -> Optional[str]:
        return self.path_modules.get(relative_path)

    def dependent_modules(self, module: str) -> Set[str]:
        """Modules that load ``module`` when imported, plus one lazy hop."""
        start = {module} | self.lazy_importers.get(module, set())
        seen = set(start)
        stack = list(start)
        while stack:
            current = stack.pop()
            for importer in self.importers.get(current, ()):
                if importer not in seen:
                    seen.add(importer)
                    stack.append(importer)
        return seen

    def referencing_modules(self, relative_path: str) -> Set[str]:
        """Modules whose source names a data file (its file name appears in the text).

        Non-Python inputs (fixtures, manifests, deploy YAML) are read at
        runtime by modules that name them. Matching by file name over-selects
        for common names, which is safe; a file read only through a directory
        scan or glob matches nothing, and callers must then fall back to the
        full suite.
        """
        name = relative_path.rsplit('/', 1)[-1].encode('utf-8')
        if not name:
            return set()
        return {module for module, text in self._module_sources().items() if name in text}

    def _module_sources(self) -> Dict[str, bytes]:
        if self._sources is None:
            self._sources = {}
            for module, path in self.modules.items():
                try:
                    self._sources[module] = (self.backend_dir / path).read_bytes()
                except OSError:
                    continue
        return self._sources

    def is_test_tree_module(self, module: str) -> bool:
        return self.modules.get(module, '').startswith(TEST_TREE_PREFIXES)

    def tree_scan_tests(self, tests: Iterable[str]) -> Set[str]:
        """Tests that scan source directories, directly or through a test-tree helper.

        A changed module can break such a test without either importing the
        other, so callers add these for every Python change the graph resolves.
        """
        key = tuple(sorted(tests))
        if key not in self._tree_scan_tests:
            selected: Set[str] = set()
            for module in self.tree_scan_modules():
                selected |= self._tests_reaching(self.dependent_modules(module), key)
            self._tree_scan_tests[key] = selected
        return set(self._tree_scan_tests[key])

    def tree_scan_modules(self) -> Set[str]:
        if self._tree_scan_modules is None:
            self._tree_scan_modules = {
                module
                for module, text in self._module_sources().items()
                if self.is_test_tree_module(module) and TREE_SCAN_PATTERN.search(text)
            }
        return self._tree_scan_modules

    def warm(self) -> 'ImportGraph':
        """Do the one-time work (source read, scanner detection) up front."""
        self.tree_scan_modules()
        return self

    def dependent_tests(self, relative_path: str, tests: Iterable[str]) -> Set[str]:
        """Backend-relative test files that can load ``relative_path``.

        Tests whose import closure reaches the module, plus tests that reach
        any module naming the file (for data files that is the only route).
        Empty means no dependency was found; callers must then fall back to
        the full suite rather than run nothing.
        """
        module = self.module_for_path(relative_path)
        dependents = self.dependent_modules(module) if module is not None else set()
        # Name references: test code that names the file (load_module_fresh,
        # spec_from_file_location, runpy, subprocess, fixtures) always counts.
        # Production code that names it counts only for data files and for
        # modules nothing imports (scripts, jobs, entry points); a library
        # module's file name also appears in path tables, which is noise.
        unimported = module is None or not (self.importers.get(module) or self.lazy_importers.get(module))
        for referencing in self.referencing_modules(relative_path):
            if referencing != module and (unimported or self.is_test_tree_module(referencing)):
                dependents |= self.dependent_modules(referencing)
        if not dependents:
            return set()
        return self._tests_reaching(dependents, tests)

    def _tests_reaching(self, dependents: Set[str], tests: Iterable[str]) -> Set[str]:
        conftest_dirs = []
        for dependent in dependents:
            path = self.modules.get(dependent, '')
            if path == 'conftest.py' or path.endswith('/conftest.py'):
                conftest_dirs.append(path[: -len('conftest.py')])
        selected = set()
        for test in tests:
            test_module = self.path_modules.get(test)
            if test_module is not None and test_module in dependents:
                selected.add(test)
            elif any(test.startswith(directory) for directory in conftest_dirs):
                selected.add(test)
        return selected


def _scan_file(item: tuple[str, str, str, bool]) -> tuple[str, str, Optional[Set[str]], Optional[Set[str]]]:
    full_path, relative, module, is_package = item
    try:
        with open(full_path, 'rb') as handle:
            tree = ast.parse(handle.read(), filename=relative)
    except (SyntaxError, ValueError, OSError):
        return relative, module, None, None
    collector = _ImportCollector(module, is_package=is_package)
    collector.visit(tree)
    return relative, module, collector.module_level, collector.lazy - collector.module_level


def build_import_graph(
    backend_dir: Path, *, workers: Optional[int] = None, min_parallel_files: int = 200
) -> ImportGraph:
    """Parse every backend module once. Parsing ~6,200 files is CPU-bound, so
    it fans out across processes (BACKEND_IMPORT_GRAPH_WORKERS overrides)."""
    graph = ImportGraph(backend_dir=backend_dir)
    items: list[tuple[str, str, str, bool]] = []
    for root, dirs, files in os.walk(backend_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIR_NAMES and not d.startswith('.'))
        for filename in sorted(files):
            if not filename.endswith('.py'):
                continue
            full_path = os.path.join(root, filename)
            relative = Path(full_path).relative_to(backend_dir).as_posix()
            module = module_name_for(relative)
            if module is None:
                continue
            graph.modules[module] = relative
            graph.path_modules[relative] = module
            items.append((full_path, relative, module, filename == '__init__.py'))
    if workers is None:
        workers = int(os.environ.get('BACKEND_IMPORT_GRAPH_WORKERS', '0') or 0) or min(8, os.cpu_count() or 1)
    results = None
    if workers > 1 and len(items) > min_parallel_files:
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_scan_file, items, chunksize=64))
        except Exception:  # noqa: BLE001 - a broken pool (spawn without an importable __main__) must not fail selection
            results = None
    if results is None:
        results = [_scan_file(item) for item in items]
    for relative, module, module_level, lazy in results:
        if module_level is None or lazy is None:
            graph.unparseable.add(relative)
            continue
        for target in module_level:
            if target in graph.modules and target != module:
                graph.importers.setdefault(target, set()).add(module)
        for target in lazy:
            if target in graph.modules and target != module:
                graph.lazy_importers.setdefault(target, set()).add(module)
    return graph


_GRAPH_CACHE: Dict[str, ImportGraph] = {}


def cached_import_graph(backend_dir: Path) -> ImportGraph:
    """One graph per backend directory per process.

    The cache lives here, not in the selector, because tests and tools load the
    selector afresh (runpy, spec_from_file_location) while this module stays
    imported once, so each fresh selector reuses the same parse.
    """
    key = str(Path(backend_dir).resolve())
    if key not in _GRAPH_CACHE:
        _GRAPH_CACHE[key] = build_import_graph(Path(backend_dir))
    return _GRAPH_CACHE[key]
