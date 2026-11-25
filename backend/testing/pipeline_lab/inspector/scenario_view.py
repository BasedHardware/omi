"""``python -m testing.pipeline_lab scenario view <run-dir> [--port N]``: a read-only page for one scenario run.

Stateless: everything on the page comes from the run directory, so copying the directory to another machine
and running ``view`` there gives the same page. No emulator, database, corpus or registry. Standard library
only; the page has no external assets and makes no request beyond this server. Loopback only, with the
day-replay inspector's access policy (``inspector/server.py``), and it never writes.

A run directory is either

- a run: ``run.json`` and ``verdict.json`` (optional) and one directory per scenario holding ``result.json``,
  ``home.json`` and ``scenario.json`` (each optional; the page says which is missing), or
- a compare run: ``base/`` and ``head/``, each a run as above, and ``compare.json`` (optional), or
- one scenario's directory (``result.json`` at its root).

Routes (JSON unless noted):
    GET /api/run                      layout, run.json, verdict.json, compare.json, scenarios with outcomes
    GET /api/scenarios/<name>         {sides: {"run"|"base"|"head": {result, home, scenario, missing}}}
    GET /, /static/<file>             the page (scenario.html, scenario.css, scenario.js)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Optional

from http.server import ThreadingHTTPServer

from testing.pipeline_lab.inspector.reader import BadRequest, NotFound
from testing.pipeline_lab.inspector.server import STATIC_DIR, InspectorHandler, _is_loopback

PAGE = 'scenario.html'
SCENARIO_FILES = ('result.json', 'home.json', 'scenario.json')
RUN_FILES = ('run.json', 'verdict.json')
SIDES = ('base', 'head')
SINGLE = 'run'
MAX_JSON_BYTES = 32 * 1024 * 1024
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
# Failures first: the rail and the default selection read this order.
OUTCOME_ORDER = {'error': 0, 'failed': 1, 'xpass': 2, 'unknown': 3, 'xfail': 4, 'passed': 5}


def _read_json(path: Path) -> tuple[Any, Optional[str]]:
    """``(value, problem)``; ``problem`` is None when the file was read, else why not."""
    if not path.is_file():
        return None, 'missing'
    if path.stat().st_size > MAX_JSON_BYTES:
        return None, 'too large'
    try:
        return json.loads(path.read_text(encoding='utf-8')), None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f'unreadable ({type(error).__name__})'


class RunDir:
    """Read-only view of one run directory; every path it opens resolves inside ``root``."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotFound(f'{root} is not a directory')

    # ---- layout

    @property
    def kind(self) -> str:
        if all((self.root / side).is_dir() for side in SIDES):
            return 'compare'
        if (self.root / 'result.json').is_file() or (self.root / 'home.json').is_file():
            return 'scenario'
        return 'run'

    def sides(self) -> tuple[str, ...]:
        return SIDES if self.kind == 'compare' else (SINGLE,)

    def _side_root(self, side: str) -> Path:
        if side not in self.sides():
            raise BadRequest(f'unknown side {side!r}')
        return self.root / side if side in SIDES else self.root

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise BadRequest('path outside the run directory')
        return resolved

    def scenario_dir(self, side: str, name: str) -> Path:
        if not _NAME.match(name):
            raise BadRequest('bad scenario name')
        base = self._side_root(side)
        if self.kind == 'scenario':
            if name != self.single_name():
                raise NotFound(f'no scenario {name!r}')
            return self._inside(base)
        return self._inside(base / name)

    def single_name(self) -> str:
        result, _ = _read_json(self.root / 'result.json')
        name = result.get('scenario') if isinstance(result, dict) else None
        return str(name) if isinstance(name, str) and _NAME.match(name) else self.root.name

    def scenario_names(self, side: str) -> list[str]:
        if self.kind == 'scenario':
            return [self.single_name()]
        base = self._side_root(side)
        names = []
        for child in sorted(base.iterdir()) if base.is_dir() else []:
            if child.is_dir() and _NAME.match(child.name) and any((child / f).is_file() for f in SCENARIO_FILES):
                try:
                    self._inside(child)
                except BadRequest:
                    continue  # a link out of the run directory is not part of the run
                names.append(child.name)
        return names

    # ---- reads

    def run_files(self, side: str) -> dict[str, Any]:
        base = self._side_root(side)
        out: dict[str, Any] = {'missing': []}
        for name in RUN_FILES:
            value, problem = _read_json(self._inside(base / name)) if (base / name).exists() else (None, 'missing')
            out[name.split('.')[0]] = value
            if problem:
                out['missing'].append({'file': name, 'problem': problem})
        return out

    def scenario_bundle(self, side: str, name: str) -> dict[str, Any]:
        folder = self.scenario_dir(side, name)
        if not folder.is_dir():
            raise NotFound(f'no scenario {name!r} in {side}')
        bundle: dict[str, Any] = {'dir': str(folder), 'missing': []}
        for file in SCENARIO_FILES:
            path = folder / file
            value, problem = _read_json(self._inside(path)) if path.exists() else (None, 'missing')
            bundle[file.split('.')[0]] = value
            if problem:
                bundle['missing'].append({'file': file, 'problem': problem})
        return bundle

    def outcome(self, side: str, name: str, verdict: Any) -> str:
        found = _verdict_outcome(verdict, name)
        if found:
            return found
        try:
            folder = self.scenario_dir(side, name)
        except (BadRequest, NotFound):
            return 'unknown'
        result, _ = _read_json(folder / 'result.json')
        value = result.get('outcome') if isinstance(result, dict) else None
        return str(value) if value in OUTCOME_ORDER else 'unknown'

    def overview(self) -> dict[str, Any]:
        kind = self.kind
        out: dict[str, Any] = {'kind': kind, 'root': str(self.root), 'sides': {}, 'missing': []}
        if kind == 'compare':
            value, problem = _read_json(self.root / 'compare.json')
            out['compare'] = value
            if problem:
                out['missing'].append({'file': 'compare.json', 'problem': problem})
        names: list[str] = []
        for side in self.sides():
            files = self.run_files(side) if kind != 'scenario' else {'run': None, 'verdict': None, 'missing': []}
            side_names = self.scenario_names(side)
            outcomes = {n: self.outcome(side, n, files.get('verdict')) for n in side_names}
            out['sides'][side] = {**files, 'outcomes': outcomes}
            names += [n for n in side_names if n not in names]
        primary = 'head' if kind == 'compare' else SINGLE

        def rank(name: str) -> tuple[int, str]:
            outcome = out['sides'][primary]['outcomes'].get(name, 'unknown')
            return OUTCOME_ORDER.get(outcome, 3), name

        out['scenarios'] = sorted(names, key=rank)
        return out

    def scenario(self, name: str) -> dict[str, Any]:
        sides = {}
        for side in self.sides():
            try:
                sides[side] = self.scenario_bundle(side, name)
            except NotFound:
                sides[side] = None
        if not any(sides.values()):
            raise NotFound(f'no scenario {name!r}')
        return {'name': name, 'sides': sides}


def _verdict_outcome(verdict: Any, name: str) -> Optional[str]:
    """A scenario's outcome from ``verdict.json``, for the shapes it may take: ``{"scenarios": [{"name"|
    "scenario", "outcome"}]}``, ``{"scenarios": {name: outcome | {"outcome"}}}`` or ``{name: outcome}``."""
    if not isinstance(verdict, dict):
        return None
    table = verdict.get('scenarios', verdict)
    value: Any = None
    if isinstance(table, list):
        for row in table:
            if isinstance(row, dict) and name in (row.get('name'), row.get('scenario')):
                value = row.get('outcome')
    elif isinstance(table, dict):
        value = table.get(name)
        if isinstance(value, dict):
            value = value.get('outcome')
    return str(value) if value in OUTCOME_ORDER else None


class ScenarioViewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        run: RunDir,
        *,
        allowed_hosts: Iterable[str] = (),
        allowed_logins: Iterable[str] = (),
        static_dir: Path = STATIC_DIR,
        quiet: bool = True,
    ):
        if not _is_loopback(address[0]):
            raise ValueError('the scenario view binds loopback only; use tailscale serve to reach it')
        self.run = run
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.allowed_logins = {login.strip().lower() for login in allowed_logins if login.strip()}
        self.static_dir = static_dir
        self.quiet = quiet
        super().__init__(address, ScenarioViewHandler)


class ScenarioViewHandler(InspectorHandler):
    """The inspector's plumbing and access policy, with the run directory's routes. Read-only."""

    server: ScenarioViewServer  # type: ignore[assignment]
    server_version = 'pipeline-lab-scenario-view'

    def _route_get(self, seg: list[str], query: dict[str, str]) -> None:
        run = self.server.run
        if not seg or seg == ['index.html']:
            return self._static(PAGE)
        if seg[0] == 'static' and len(seg) == 2:
            return self._static(seg[1])
        if seg == ['api', 'run']:
            return self._json(run.overview())
        if len(seg) == 3 and seg[:2] == ['api', 'scenarios']:
            return self._json(run.scenario(seg[2]))
        raise NotFound('not found')

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self.close_connection = True
        self._error(405, 'the scenario view is read-only')


def make_server(root: Path, *, host: str = '127.0.0.1', port: int = 0, quiet: bool = True) -> ScenarioViewServer:
    return ScenarioViewServer((host, port), RunDir(root), quiet=quiet)


def serve(root: str, *, port: int = 0, host: str = '127.0.0.1', verbose: bool = False) -> int:
    path = Path(root).expanduser()
    if not path.is_dir():
        raise NotFound(f'{root}: no such run directory')
    server = make_server(path, host=host, port=port, quiet=not verbose)
    bound_host, bound_port = server.server_address[:2]
    print(json.dumps({'url': f'http://{bound_host}:{bound_port}/', 'pid': os.getpid(), 'run_dir': str(path)}))
    print(f'Scenario view: http://{bound_host}:{bound_port}/  (Ctrl-C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
