"""``python -m testing.pipeline_lab view PATH [--port N]``: one command for looking at lab results.

PATH decides the page (both are loopback-only and read-only, served by the inspector's server code):

- a scenario run directory (``verdict.json``, ``result.json``, or scenario folders holding ``result.json``)
  or a compare directory (``compare.json``, or ``base/`` and ``head/``): the scenario page, as
  ``scenario view PATH``;
- a lab store root (``runs/`` or ``corpus/``) or one day-replay run (``<root>/runs/<run id>/`` with
  ``run.json``): the day-replay inspector over that store, as the ``serve`` tool, opened on the run.

Anything else exits 2 naming what was looked for. ``scenario view`` and ``serve`` keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCENARIO_MARKERS = ('verdict.json', 'compare.json', 'result.json')
LOOKED_FOR = (
    'a scenario run directory (verdict.json, result.json, or <scenario>/result.json), a compare directory '
    '(compare.json, or base/ and head/), a lab store root (runs/ or corpus/), or a day-replay run '
    '(<root>/runs/<run id>/run.json)'
)


class NotAViewable(ValueError):
    """PATH is neither kind of result."""


@dataclass(frozen=True)
class Target:
    kind: str  # scenario | day
    path: Path  # the scenario directory, or the store root
    run_id: Optional[str] = None  # day: the run to open


def _scenario_dir(path: Path) -> bool:
    if any((path / marker).is_file() for marker in SCENARIO_MARKERS):
        return True
    if (path / 'base').is_dir() and (path / 'head').is_dir():
        return True
    return any(child.is_dir() and (child / 'result.json').is_file() for child in path.iterdir())


def detect(raw: str) -> Target:
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise NotAViewable(f'{raw}: not a directory; expected {LOOKED_FOR}')
    path = path.resolve()
    if _scenario_dir(path):
        return Target('scenario', path)
    if (path / 'runs').is_dir() or (path / 'corpus').is_dir():
        return Target('day', path)
    if (path / 'run.json').is_file() and path.parent.name == 'runs':
        return Target('day', path.parent.parent, path.name)
    raise NotAViewable(f'{raw}: nothing to view; looked for {LOOKED_FOR}')


def view(raw: str, *, port: int = 0, verdicts: Optional[str] = None) -> int:
    target = detect(raw)
    if target.kind == 'scenario':
        from testing.pipeline_lab.inspector import scenario_view

        return scenario_view.serve(str(target.path), port=port)
    from testing.pipeline_lab.inspector.server import main

    if target.run_id:
        print(f'Day replay run {target.run_id}: open #/run/{target.run_id} on the URL below', flush=True)
    argv = ['--root', str(target.path), '--port', str(port)]
    return main(argv + (['--verdicts', verdicts] if verdicts else []))
