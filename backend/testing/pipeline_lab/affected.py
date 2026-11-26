"""Which lab stages and scenarios a change can influence (``python -m testing.pipeline_lab affected``).

    python -m testing.pipeline_lab affected                 # merge-base(origin/main, HEAD) .. working tree
    python -m testing.pipeline_lab affected BASE..HEAD      # two refs
    python -m testing.pipeline_lab affected --json

Each changed path gets the earliest stage it can influence, by three rules in order:

1. **Import closure.** ``STAGE_ROOTS`` names, per stage, the lab modules its driver runs. The
   static import closure of those roots (every ``import`` in the file, lazy ones included, plus
   any string literal that names a backend module, which covers ``PRODUCT_MODULES`` preimport
   lists and ``run_module`` targets) is the set of backend files the stage can reach. A changed
   file reached by a stage maps to the earliest such stage; a row of ``REFINE`` may move it later
   when the file is known to act only there.
2. **Explicit table.** ``PATH_TABLE`` maps files the closure cannot see (lock files, overlays'
   source yaml, viewers, scoring, docs, tests) to a stage, to ``ALL`` or to no stage.
3. **Conservative default.** Any other path under ``backend/`` means "run everything"
   (earliest stage ``ingest``). Paths outside ``backend/`` cannot reach the lab: no stage.

Scenarios (``scenario/scenarios/*.json``) a path names, first match wins:

1. ``SCENARIO_TABLE``: the scenario file itself; audio fixtures and the cassette code (the scenarios with an
   ``audio_file``); the scenario harness and the scenario view (every scenario); the product areas every
   scenario exercises by design: the conversations v3 runtime, Finish, fast finish, visibility, the Home
   routes, the manual-finish hook, and the production profile (every scenario); dependency locks.
2. **Measured reach.** ``scenario/reach.json`` lists, per committed scenario, the backend files in which a
   function ran during that scenario (``scenario run --trace-calls``, ``scenario/reach.py``). A changed
   ``.py`` file names the scenarios whose reach holds it. A committed scenario missing from ``reach.json``
   is named for any file in the static import closure of ``SCENARIO_ROOTS`` (conservative).
3. Lab code in the closure of ``SCENARIO_ROOTS`` and not measured (imported by the runner, e.g. a parent
   process module): every scenario. Anything else: none.

The closure is computed on the head side (the working tree, or the head ref read from git);
a path that exists only on the base side is looked up in the base closure too.

``self_check()`` fails when a stage in ``contracts.STAGES`` has no ``STAGE_ROOTS`` entry or a
root does not resolve to a file; every ``affected`` call runs it first.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from testing.pipeline_lab.contracts import STAGES, stage_index

ALL = '*'  # PATH_TABLE value: every stage (same as the default for unmapped backend paths)
LAB = 'testing.pipeline_lab'

_LANES = (f'{LAB}.timeline.build', f'{LAB}.registry', f'{LAB}.store')
_CHAIN = (f'{LAB}.chain.plugin', f'{LAB}.chain.entry', f'{LAB}.v3.entry')
STAGE_ROOTS: dict[str, tuple[str, ...]] = {
    'ingest': _LANES,
    'transcribe': (*_LANES, f'{LAB}.lanes.plugin', f'{LAB}.lanes.__main__'),
    'boundaries': _LANES,
    'speakers': _LANES,
    'discard': _CHAIN,
    'notes': _CHAIN,
    'memories': _CHAIN,
    'tasks': _CHAIN,
    'notifications': _CHAIN,
    'goals': _CHAIN,
    'daily_summary': (*_CHAIN, f'{LAB}.day.run'),
    'chat_index': (*_CHAIN, f'{LAB}.day.outputs'),
}
# Stages whose drivers call a few product functions through modules that import most of the product
# at load time (``utils/sync/pipeline.py``). For these, the import closure is followed inside the lab
# only, and the product files the stage can influence are these globs: the modules whose functions
# the drivers call, as measured: ``test_pipeline_lab_affected`` traces a record + sync replay of a
# synthetic day and fails when a product function outside the scope runs. Branches the synthetic day
# does not take (vendor errors, other providers) can call more; widen the globs when they show up.
# Stages not listed use their full import closure.
_INGEST_SCOPE = ('backend/utils/stt/local_vad.py',)
PRODUCT_SCOPE: dict[str, tuple[str, ...]] = {
    'ingest': _INGEST_SCOPE,
    'transcribe': (
        'backend/utils/stt/*',
        'backend/utils/sync/*',
        'backend/utils/batch_pipeline/*',
        'backend/diarizer/*',
        'backend/config/batch_*.py',
        'backend/config/policy/batch.py',
        'backend/config/prerecorded_language.py',
        'backend/config/refactor_modes.py',
        'backend/config/refactor_switches.py',
        'backend/config/stt_*.py',
        'backend/config/live_stt_gpu_fleet.py',
        'backend/models/speaker_label_provenance.py',
        'backend/models/transcript_segment.py',
        'backend/utils/conversations/final_pass_assignment.py',
        'backend/utils/observability/sync_phases.py',
        'backend/utils/request_validation.py',
    ),
    'boundaries': _INGEST_SCOPE,
    'speakers': _INGEST_SCOPE,
}
# Every stage's code includes these (dependency locks).
SHARED_CODE = ('backend/pylock*.toml', 'backend/requirements*.txt', 'backend/pyproject.toml')
LAB_PREFIX = 'backend/testing/'
SCENARIO_ROOTS = (f'{LAB}.scenario.run', f'{LAB}.scenario.ops', f'{LAB}.scenario.stack', f'{LAB}.scenario.checks')
SCENARIO_DIR = 'backend/testing/pipeline_lab/scenario/scenarios'
SCENARIO_REACH = 'backend/testing/pipeline_lab/scenario/reach.json'
_SCN = 'backend/testing/pipeline_lab/scenario'
# (glob, selector, reason). Selectors: 'self' (the scenario file), 'uses' (scenarios whose JSON names the file),
# 'audio' (scenarios with an audio_file), 'all', None (none). First match wins.
SCENARIO_TABLE: tuple[tuple[str, Optional[str], str], ...] = (
    (f'{SCENARIO_DIR}/*.json', 'self', 'the scenario file'),
    (f'{_SCN}/fixtures/audio/*', 'uses', 'audio fixture: the scenarios whose audio_file names it'),
    (f'{_SCN}/fixtures/*', 'audio', 'audio fixtures and committed STT cassettes'),
    (f'{_SCN}/audio.py', 'audio', 'audio_file words'),
    ('backend/testing/pipeline_lab/cassette/*', 'audio', 'STT cassettes: audio_file words'),
    ('backend/testing/pipeline_lab/lanes/batch.py', 'audio', 'batch lane: audio_file words'),
    ('backend/testing/pipeline_lab/lanes/sync.py', 'audio', 'sync lane: audio_file words'),
    (SCENARIO_REACH, None, "the scenarios' measured reach"),
    (f'{_SCN}/*.md', None, 'documentation'),
    (f'{_SCN}/*', 'all', 'scenario harness'),
    ('backend/testing/pipeline_lab/inspector/scenario_view.py', 'all', 'scenario view'),
    ('backend/testing/pipeline_lab/inspector/server.py', 'all', 'scenario view server'),
    ('backend/testing/pipeline_lab/inspector/reader.py', 'all', 'scenario view server'),
    ('backend/testing/pipeline_lab/inspector/static/scenario.*', 'all', 'scenario view page'),
    ('backend/utils/conversations/v3/*', 'all', 'conversations v3 runtime, Finish, fast finish, visibility'),
    ('backend/database/conversations_v3*.py', 'all', 'conversations v3 storage'),
    ('backend/config/conversations_v3*.py', 'all', 'conversations v3 admission and switches'),
    ('backend/routers/conversations.py', 'all', 'Home routes (scenario/home.py)'),
    ('backend/utils/batch_pipeline/live.py', 'all', 'manual-finish hook (scenario admission)'),
    ('backend/deploy/runtime_env.yaml', 'all', 'the production profile scenarios run under'),
    ('backend/pylock*.toml', 'all', 'dependencies'),
    ('backend/requirements*.txt', 'all', 'dependencies'),
    ('backend/pyproject.toml', 'all', 'dependencies and tool config'),
)

# Moves a closure hit to a later stage: the file is reached by the chain process, but only the
# named stage executes it. Keep this to files whose only callers are that stage.
REFINE: tuple[tuple[str, str, str], ...] = (
    ('backend/testing/pipeline_lab/day/*', 'daily_summary', 'day stages run after every conversation'),
    ('backend/testing/pipeline_lab/baseline/build.py', 'chat_index', 'baseline view, written after the day'),
)

# (glob, stage | ALL | None, reason). First match wins. None: cannot change any stage's output.
PATH_TABLE: tuple[tuple[str, Optional[str], str], ...] = (
    ('backend/testing/pipeline_lab/orchestrator.py', ALL, 'walks every stage'),
    ('backend/testing/pipeline_lab/keys.py', ALL, 'stage cache keys'),
    ('backend/testing/pipeline_lab/store.py', ALL, 'run store'),
    ('backend/testing/pipeline_lab/registry.py', ALL, 'stage registry'),
    ('backend/testing/pipeline_lab/contracts.py', ALL, 'store contract'),
    ('backend/testing/pipeline_lab/cli.py', ALL, 'run command'),
    ('backend/testing/pipeline_lab/lanes/plugin.py', 'ingest', 'ingest, boundaries and speakers drivers'),
    ('backend/testing/pipeline_lab/__main__.py', ALL, 'run command'),
    ('backend/testing/pipeline_lab/worktrees.py', ALL, 'pinned arms'),
    ('backend/testing/pipeline_lab/ledger.py', ALL, 'spend cap'),
    ('backend/testing/pipeline_lab/llm_proxy/*', 'discard', 'LLM calls start in the chain'),
    ('backend/testing/pipeline_lab/cassette/*', 'transcribe', 'STT cassettes'),
    ('backend/testing/pipeline_lab/timeline/*', 'ingest', 'day timeline'),
    ('backend/testing/pipeline_lab/seed/*', 'discard', 'start state seeded by the chain; corpus add-day'),
    ('backend/testing/pipeline_lab/affected.py', None, 'this map'),
    ('backend/testing/pipeline_lab/inspector/*', None, 'viewer: reads run files'),
    ('backend/testing/pipeline_lab/ideal/*', None, 'scoring against the ideal'),
    ('backend/testing/pipeline_lab/baseline/compare.py', None, 'run comparison'),
    ('backend/testing/pipeline_lab/sample.py', None, 'synthetic sample run'),
    ('backend/testing/pipeline_lab/scenario/*', None, 'scenario harness (see scenarios)'),
    ('backend/testing/pipeline_lab/*.md', None, 'documentation'),
    ('backend/pylock*.toml', ALL, 'dependencies'),
    ('backend/requirements*.txt', ALL, 'dependencies'),
    ('backend/pyproject.toml', ALL, 'dependencies and tool config'),
    ('backend/deploy/runtime_env.yaml', 'discard', 'production env: the overlay the chain runs with'),
    ('backend/tests/*', None, 'tests (run the changed test file)'),
    ('backend/*.md', None, 'documentation'),
    ('backend/docs/*', None, 'documentation'),
    ('backend/charts/*', None, 'deploy charts'),
    ('backend/Dockerfile*', None, 'container images'),
)


@dataclass
class PathResult:
    path: str
    stage: Optional[str]  # earliest stage, or None
    rule: str  # closure | table | default | outside
    reason: str
    scenarios: list[str] = field(default_factory=list)
    scenario_reason: str = ''

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


# ---- sources: the working tree or a git ref -------------------------------------------


class Source:
    """Backend files on one side of the diff: ``exists(rel)`` and ``read(rel)``, rel from the repo root."""

    def exists(self, rel: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self, rel: str) -> Optional[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def matching(self, patterns: Iterable[str]) -> set[str]:  # pragma: no cover - interface
        raise NotImplementedError


class DiskSource(Source):
    def __init__(self, repo: Path):
        self.repo = Path(repo)
        self._files: Optional[set[str]] = None

    def exists(self, rel: str) -> bool:
        return (self.repo / rel).is_file()

    def read(self, rel: str) -> Optional[str]:
        try:
            return (self.repo / rel).read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None

    def matching(self, patterns: Iterable[str]) -> set[str]:
        if self._files is None:
            listing = _git(self.repo, 'ls-files', '--cached', '--others', '--exclude-standard', '--', 'backend')
            self._files = {rel for rel in listing.splitlines() if (self.repo / rel).is_file()}
        patterns = tuple(patterns)
        return {rel for rel in self._files if any(fnmatch.fnmatch(rel, p) for p in patterns)}


class GitSource(Source):
    def __init__(self, repo: Path, ref: str):
        self.repo, self.ref = Path(repo), ref
        listing = _git(self.repo, 'ls-tree', '-r', '--name-only', ref, '--', 'backend')
        self.files = set(listing.splitlines())

    def exists(self, rel: str) -> bool:
        return rel in self.files

    def read(self, rel: str) -> Optional[str]:
        if rel not in self.files:
            return None
        return _git(self.repo, 'show', f'{self.ref}:{rel}')

    def matching(self, patterns: Iterable[str]) -> set[str]:
        patterns = tuple(patterns)
        return {rel for rel in self.files if any(fnmatch.fnmatch(rel, p) for p in patterns)}


def _git(repo: Path, *args: str) -> str:
    from testing.pipeline_lab.worktrees import git_binary

    result = subprocess.run([git_binary(), '-C', str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError(f'git {args[0]} failed: {result.stderr.strip()[:200]}')
    return result.stdout


# ---- static import closure -------------------------------------------------------------


def _module_file(source: Source, module: str) -> Optional[str]:
    base = 'backend/' + module.replace('.', '/')
    for candidate in (base + '.py', base + '/__init__.py'):
        if source.exists(candidate):
            return candidate
    return None


def _package_of(rel: str) -> str:
    parts = rel[len('backend/') :].split('/')
    if parts[-1] == '__init__.py':
        return '.'.join(parts[:-1])
    return '.'.join(parts[:-1])


def _imports(source: Source, rel: str, text: str) -> set[str]:
    """Module names a file can load: imports anywhere in it, and dotted strings naming modules."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    package = _package_of(rel)
    for node in _walk_runtime(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split('.') if package else []
                parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                base = '.'.join(p for p in [*parts, node.module or ''] if p)
            else:
                base = node.module or ''
            if base:
                names.add(base)
            names.update(f'{base}.{alias.name}' if base else alias.name for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _DOTTED.fullmatch(node.value):
            names.add(node.value)
    return names


_DOTTED = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+')


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING') or (
        isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING'
    )


def _walk_runtime(tree: ast.AST) -> Iterable[ast.AST]:
    """``ast.walk`` minus ``if TYPE_CHECKING:`` bodies (never executed)."""
    stack = [tree]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            stack.extend(node.orelse)
            continue
        stack.extend(ast.iter_child_nodes(node))


def closure(
    source: Source,
    roots: Iterable[str],
    memo: Optional[dict[str, set[str]]] = None,
    follow: Optional[Callable[[str], bool]] = None,
) -> set[str]:
    """Repo-relative backend files reachable from ``roots`` (module names), parents' ``__init__`` included.

    ``memo`` caches each file's parsed imports across calls on the same source.
    """
    memo = {} if memo is None else memo
    seen: set[str] = set()
    queue = list(roots)
    visited_modules: set[str] = set()
    while queue:
        module = queue.pop()
        if module in visited_modules:
            continue
        visited_modules.add(module)
        parts = module.split('.')
        for depth in range(1, len(parts) + 1):  # importing a.b.c runs a/__init__ and a/b/__init__
            rel = _module_file(source, '.'.join(parts[:depth]))
            if rel is None or rel in seen or (follow is not None and not follow(rel)):
                continue
            seen.add(rel)
            if rel not in memo:
                text = source.read(rel)
                memo[rel] = _imports(source, rel, text) if text is not None else set()
            queue.extend(memo[rel])
    return seen


# ---- the map ------------------------------------------------------------------------------


def self_check(repo: Optional[Path] = None) -> list[str]:
    """Problems with the map: a contract stage without roots, or a root that names no file."""
    problems = [f'stage {stage} has no STAGE_ROOTS entry' for stage in STAGES if stage not in STAGE_ROOTS]
    problems += [f'STAGE_ROOTS names unknown stage {stage}' for stage in STAGE_ROOTS if stage not in STAGES]
    problems += [f'REFINE names unknown stage {stage}' for _, stage, _ in REFINE if stage not in STAGES]
    problems += [
        f'PATH_TABLE names unknown stage {stage}' for _, stage, _ in PATH_TABLE if stage not in (None, ALL, *STAGES)
    ]
    if repo is not None:
        disk = DiskSource(repo)
        for stage, roots in STAGE_ROOTS.items():
            problems += [f'{stage}: root {root} names no file' for root in roots if _module_file(disk, root) is None]
        problems += [
            f'scenario root {root} names no file' for root in SCENARIO_ROOTS if _module_file(disk, root) is None
        ]
    return problems


class StageMap:
    def __init__(self, source: Source, base: Optional[Source] = None):
        self.source, self.base = source, base
        self._closures: dict[tuple[int, tuple[str, ...]], set[str]] = {}
        self._memo: dict[int, dict[str, set[str]]] = {}

    def _closure(self, side: Source, roots: tuple[str, ...]) -> set[str]:
        slot = (id(side), roots)
        if slot not in self._closures:
            memo = self._memo.setdefault(id(side), {})
            self._closures[slot] = set().union(*(self._root_closure(side, root, memo) for root in roots))
        return self._closures[slot]

    def _root_closure(self, side: Source, root: str, memo: dict[str, set[str]], lab_only: bool = False) -> set[str]:
        slot = (id(side), (root, 'lab' if lab_only else 'all'))
        if slot not in self._closures:
            follow = (lambda rel: rel.startswith(LAB_PREFIX)) if lab_only else None
            self._closures[slot] = closure(side, [root], memo if not lab_only else {}, follow)
        return self._closures[slot]

    def lab_closure(self, side: Source, roots: tuple[str, ...]) -> set[str]:
        memo = self._memo.setdefault(id(side), {})
        return set().union(*(self._root_closure(side, root, memo, lab_only=True) for root in roots))

    def in_reach(self, side: Source, stage: str, rel: str) -> bool:
        """Whether ``rel`` is code ``stage`` runs: its import closure, or for a scoped stage its lab
        closure plus the ``PRODUCT_SCOPE`` globs."""
        scope = PRODUCT_SCOPE.get(stage)
        if scope is None:
            return rel in self._closure(side, STAGE_ROOTS[stage])
        if rel.startswith(LAB_PREFIX):
            return rel in self.lab_closure(side, STAGE_ROOTS[stage])
        return any(fnmatch.fnmatch(rel, pattern) for pattern in scope)

    def reach(self, stage: str) -> set[str]:
        """Every head-side file ``stage`` runs, shared dependency locks included (the stage's code key)."""
        scope = PRODUCT_SCOPE.get(stage)
        if scope is None:
            files = set(self._closure(self.source, STAGE_ROOTS[stage]))
        else:
            files = self.lab_closure(self.source, STAGE_ROOTS[stage]) | self.source.matching(scope)
        return files | self.source.matching(SHARED_CODE)

    def earliest_reach(self, rel: str) -> Optional[str]:
        """The first stage that runs ``rel`` (head side, then base side for files the head removed)."""
        sides = [self.source] + ([self.base] if self.base is not None and not self.source.exists(rel) else [])
        return next((stage for stage in STAGES if any(self.in_reach(side, stage, rel) for side in sides)), None)

    def _sides(self, rel: str) -> list[Source]:
        return [self.source] + ([self.base] if self.base is not None and not self.source.exists(rel) else [])

    def in_scenarios(self, rel: str) -> bool:
        """``rel`` is in the static import closure of the scenario runner (head side, or base for a removal)."""
        return any(rel in self._closure(side, SCENARIO_ROOTS) for side in self._sides(rel))

    def world(self) -> 'ScenarioWorld':
        if getattr(self, '_world', None) is None:
            self._world = ScenarioWorld.read(self.source)
        return self._world

    def scenarios_for(self, rel: str) -> tuple[list[str], str]:
        """(scenarios worth running for a change to ``rel``, why); see the module docstring."""
        world = self.world()
        names = world.names
        for pattern, selector, why in SCENARIO_TABLE:
            if not fnmatch.fnmatch(rel, pattern):
                continue
            if selector == 'self':
                return ([Path(rel).stem] if Path(rel).stem in names else []), why
            if selector == 'uses':
                return [n for n in names if Path(rel).name in world.texts.get(n, '')], why
            if selector == 'audio':
                return [n for n in names if n in world.audio], why
            if selector == 'all':
                return list(names), why
            return [], why
        if not rel.startswith('backend/') or not rel.endswith('.py'):
            return [], ''
        measured = [n for n in names if rel in world.reach.get(n, ())]
        unmeasured = [n for n in names if n not in world.reach]
        static = self.in_scenarios(rel)
        if rel.startswith(LAB_PREFIX) and static and not measured:
            return list(names), 'lab code the scenario runner imports'
        found = sorted(set(measured) | (set(unmeasured) if static else set()))
        if not found:
            return [], ('imported by the scenario runner; no committed scenario calls it' if static else '')
        why = f'measured: called in {len(measured)} of {len(names)} scenarios'
        if static and unmeasured:
            why += f'; {len(unmeasured)} not measured yet (scenario reach)'
        return found, why

    def classify(self, rel: str, scenario_names: list[str]) -> PathResult:
        result = self._classify(rel)
        result.scenarios, result.scenario_reason = self.scenarios_for(rel)
        return result

    def _classify(self, rel: str) -> PathResult:
        scenarios: list[str] = []
        if not rel.startswith('backend/'):
            return PathResult(rel, None, 'outside', 'outside backend/: the lab cannot reach it', scenarios)
        candidates: list[tuple[str, str, str]] = []  # (stage, rule, reason); the earliest wins
        reached = self.earliest_reach(rel) if rel.endswith('.py') else None
        if reached:
            stage = reached
            how = 'product scope' if PRODUCT_SCOPE.get(stage) and not rel.startswith(LAB_PREFIX) else 'import closure'
            reason = f'{how} of {stage}'
            for pattern, later, why in REFINE:
                if fnmatch.fnmatch(rel, pattern) and stage_index(later) > stage_index(stage):
                    stage, reason = later, f'{how}, refined: {why}'
                    break
            candidates.append((stage, 'closure', reason))
        for pattern, stage, why in PATH_TABLE:
            if fnmatch.fnmatch(rel, pattern):
                if stage is not None:
                    candidates.append((STAGES[0] if stage == ALL else stage, 'table', why))
                elif not candidates:
                    return PathResult(rel, None, 'table', why, scenarios)
                break
        if candidates:
            stage, rule, reason = min(candidates, key=lambda c: stage_index(c[0]))
            return PathResult(rel, stage, rule, reason, scenarios)
        if any(fnmatch.fnmatch(rel, pattern) for pattern, selector, _ in SCENARIO_TABLE if selector):
            return PathResult(rel, None, 'table', 'scenario input only (no day-replay stage runs it)', scenarios)
        if rel.endswith('.py') and self.in_scenarios(rel):
            return PathResult(rel, None, 'table', 'scenario runner only (no day-replay stage imports it)', scenarios)
        return PathResult(rel, STAGES[0], 'default', 'unmapped backend path: run everything', scenarios)


@dataclass
class ScenarioWorld:
    """The committed scenarios on one side: names, file texts, which use ``audio_file``, measured reach."""

    names: list[str]
    texts: dict[str, str]
    audio: set[str]
    reach: dict[str, set[str]]

    @classmethod
    def read(cls, source: Source) -> 'ScenarioWorld':
        from testing.pipeline_lab.scenario.reach import load_reach

        files = sorted(source.matching([f'{SCENARIO_DIR}/*.json']))
        texts = {Path(f).stem: source.read(f) or '' for f in files}
        audio = {name for name, text in texts.items() if '"audio_file"' in text}
        return cls(sorted(texts), texts, audio, load_reach(source.read, SCENARIO_REACH))


def scenario_names(source: Source, repo: Path) -> list[str]:
    if isinstance(source, GitSource):
        files = [f for f in source.files if f.startswith(SCENARIO_DIR + '/') and f.endswith('.json')]
    else:
        files = [str(p.relative_to(repo)) for p in (repo / SCENARIO_DIR).glob('*.json')]
    return sorted(Path(f).stem for f in files)


# ---- changed paths and the report --------------------------------------------------------------


def changed_paths(repo: Path, spec: Optional[str]) -> tuple[str, Optional[str], list[str]]:
    """(base, head or None for the working tree, repo-relative paths) for ``BASE..HEAD`` or the default."""
    if spec and '..' in spec:
        base, head = spec.split('..', 1)
        base, head = base.rstrip('.') or 'HEAD', head.lstrip('.') or 'HEAD'
        names = _git(repo, 'diff', '--name-only', '--no-renames', base, head)
        return base, head, sorted(set(names.splitlines()))
    base = spec or _git(repo, 'merge-base', 'origin/main', 'HEAD').strip()
    names = set(_git(repo, 'diff', '--name-only', '--no-renames', base).splitlines())
    names |= set(_git(repo, 'ls-files', '--others', '--exclude-standard').splitlines())
    return base, None, sorted(n for n in names if n)


def unit_of(stage: str) -> tuple[str, ...]:
    """The stages that execute together with ``stage`` (the chain composite), from the registry's view."""
    from testing.pipeline_lab.chain.plugin import CHAIN_STAGES

    return tuple(CHAIN_STAGES) if stage in CHAIN_STAGES else (stage,)


def affected(
    repo: Path,
    spec: Optional[str] = None,
    *,
    paths: Optional[list[str]] = None,
    stage_map: Optional['StageMap'] = None,
) -> dict[str, Any]:
    """The report for ``BASE..HEAD`` (or ``paths`` given directly, classified on the working tree)."""
    problems = self_check(repo)
    if problems:
        raise ValueError('affected map self-check failed: ' + '; '.join(problems))
    if paths is None:
        base, head, paths = changed_paths(repo, spec)
    else:
        base, head = spec or 'given', None
    if stage_map is None:
        source: Source = GitSource(repo, head) if head else DiskSource(repo)
        base_source: Optional[Source] = None
        if base != 'given':
            try:
                base_source = GitSource(repo, base)
            except ValueError:
                base_source = None
        stage_map = StageMap(source, base_source)
    names = scenario_names(stage_map.source, repo)
    results = [stage_map.classify(rel, names) for rel in paths]
    stages = [r.stage for r in results if r.stage]
    earliest = min(stages, key=stage_index) if stages else None
    rerun = list(STAGES[stage_index(unit_of(earliest)[0]) :]) if earliest else []
    scenarios = sorted({s for r in results for s in r.scenarios})
    commands = []
    if earliest:
        start = unit_of(earliest)[0]
        commands.append(
            'python -m testing.pipeline_lab run --day DAY --ref HEAD --in-place'
            + ('' if start == STAGES[0] else f' --from-stage {start}')
        )
    if scenarios:
        commands.append('python -m testing.pipeline_lab scenario run ' + ' '.join(scenarios))
    units = []
    for stage in rerun:
        unit = unit_of(stage)
        if len(unit) > 1 and unit[0] == stage:
            units.append({'unit': 'chain', 'stages': list(unit), 'why': 'one process_conversation per conversation'})
    return {
        'base': base,
        'head': head or 'working tree',
        'changed': len(paths),
        'earliest_stage': earliest,
        'rerun_stages': rerun,
        'units': units,
        'scenarios': scenarios,
        'commands': commands,
        'paths': [r.to_json() for r in results],
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [f'affected {report["base"][:12]}..{report["head"]}: {report["changed"]} changed paths']
    width = max([len(p['path']) for p in report['paths']] + [10])
    for row in report['paths']:
        stage = row['stage'] or '-'
        extra = f'  scenarios: {len(row["scenarios"])} ({row["scenario_reason"]})' if row['scenarios'] else ''
        lines.append(f'  {row["path"]:<{width}}  {stage:<13} {row["rule"]}: {row["reason"]}{extra}')
    if report['earliest_stage']:
        lines.append(f'earliest stage: {report["earliest_stage"]}; re-run: {", ".join(report["rerun_stages"])}')
        for unit in report['units']:
            lines.append(f'  unit {unit["unit"]}: {"..".join((unit["stages"][0], unit["stages"][-1]))} run together')
    else:
        lines.append('earliest stage: none (no lab stage can see these changes)')
    lines.append('scenarios: ' + (', '.join(report['scenarios']) if report['scenarios'] else 'none'))
    lines.extend(f'run: {command}' for command in report['commands'])
    return '\n'.join(lines)


# ---- code keys for the stage cache ----------------------------------------------------------------


_ENV_NAME = re.compile(r"""['"]([A-Z][A-Z0-9]*_[A-Z0-9_]+)['"]""")


def _disk_state(path: Path) -> str:
    """What a dirty path holds now, for code keys: content and the executable bit for a file, the target for a
    symlink, a content hash of every file for a directory git lists whole (a nested repository or submodule
    work tree), else ``deleted``. Mode-only edits and symlink retargets change the state."""
    import hashlib

    try:
        info = path.lstat()
    except FileNotFoundError:
        return 'deleted'
    if stat.S_ISLNK(info.st_mode):
        return 'symlink:' + os.readlink(path)
    if stat.S_ISREG(info.st_mode):
        digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        return digest + (':x' if info.st_mode & 0o111 else '')
    if stat.S_ISDIR(info.st_mode):
        digest = hashlib.sha256()
        for item in sorted(path.rglob('*')):
            relative = item.relative_to(path)
            if '.git' in relative.parts or not item.is_file() or item.is_symlink():
                continue
            digest.update(relative.as_posix().encode() + b'\0' + _disk_state(item).encode() + b'\0')
        return 'dir:' + digest.hexdigest()
    return 'special'


class CodeState:
    """The backend code a run executes: blob ids at ``HEAD`` with uncommitted edits folded in.

    ``tree_key()`` stands in for the backend tree hash in stage keys (it equals the git tree hash
    when the checkout is clean); ``stage_key(stages)`` hashes only the files those stages run.
    """

    def __init__(self, repo: Path):
        import hashlib

        self.repo = Path(repo)
        self.tree = _git(self.repo, 'rev-parse', 'HEAD:backend').strip()
        self.blobs: dict[str, str] = {}
        for line in _git(self.repo, 'ls-tree', '-r', 'HEAD', '--', 'backend').splitlines():
            meta, _, rel = line.partition('\t')
            self.blobs[rel] = meta.split()[2]
        self.dirty: dict[str, str] = {}
        status = _git(self.repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--', 'backend')
        entries = status.split('\0')
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if len(entry) < 4:
                continue
            code, rel = entry[:2], entry[3:]
            paths = [rel]
            if 'R' in code or 'C' in code:
                # -z puts a rename's or copy's source path next (index or worktree column). A rename's source is
                # gone and a copy's may be edited: record its disk state too, or "rename A to B" keys the same as
                # "add B beside an unchanged A".
                if index < len(entries) and entries[index]:
                    paths.append(entries[index])
                index += 1
            for name in paths:
                self.dirty[name.rstrip('/')] = _disk_state(self.repo / name)
        self.blobs.update(self.dirty)
        self._map: Optional[StageMap] = None

    def tree_key(self) -> str:
        if not self.dirty:
            return self.tree
        from testing.pipeline_lab.keys import hash_json

        return 'dirty:' + hash_json({'tree': self.tree, 'dirty': self.dirty})

    def ambient_env(self, stages: Iterable[str], overlay: Iterable[str] = ()) -> str:
        """Hash of the ambient env values the code ``stages`` run can read, for a stage that runs with the
        operator's env (the ``transcribe`` replay; the chain clears its env, ``stack/env.py``).

        Every upper-case quoted name in those files counts, whatever helper reads it. A name the overlay sets is
        keyed through the overlay; a credential-shaped one is removed before the stage runs, so reads as absent."""
        from testing.pipeline_lab.keys import hash_json
        from testing.pipeline_lab.stack.runtime_env import SECRETISH
        from testing.pipeline_lab.worktrees import _SCRUB_EXACT, _SCRUB_SUFFIXES

        if self._map is None:
            self._map = StageMap(DiskSource(self.repo))
        names: set[str] = set()
        for stage in stages:
            for rel in self._map.reach(stage):
                if rel.endswith('.py'):
                    names.update(_ENV_NAME.findall(self._map.source.read(rel) or ''))
        skip = set(overlay)
        values = {
            name: os.environ[name]
            for name in sorted(names - skip)
            if name in os.environ
            and not (name in _SCRUB_EXACT or name.endswith(_SCRUB_SUFFIXES) or SECRETISH.search(name))
        }
        return 'env:' + hash_json(values)

    def stage_key(self, stages: Iterable[str]) -> str:
        from testing.pipeline_lab.keys import hash_json

        if self._map is None:
            self._map = StageMap(DiskSource(self.repo))
        files: set[str] = set()
        for stage in stages:
            files |= self._map.reach(stage)
        return 'reach:' + hash_json({rel: self.blobs.get(rel, 'missing') for rel in sorted(files)})
