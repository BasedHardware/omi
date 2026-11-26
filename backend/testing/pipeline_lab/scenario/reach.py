"""Which backend files each committed scenario runs, measured, for ``affected`` (stdlib only).

    python -m testing.pipeline_lab scenario run --trace-calls --keep DIR     # every committed scenario
    python -m testing.pipeline_lab scenario reach DIR                        # writes scenario/reach.json

``--trace-calls`` makes each scenario process record every backend file in which a function (not a module
body) was called between the lab environment being up and the final snapshot (``called_files.json`` in the
scenario's directory). Module bodies are left out on purpose: the runner preimports most of the product, so
"imported" would name every file for every scenario. ``scenario reach`` keeps the union over repeats and
writes ``reach.json`` beside the scenarios: the files every scenario calls once, under ``common``, and each
scenario's extras under ``scenarios``.

``affected`` names a scenario for a changed ``.py`` file when the scenario's measured reach holds it. A
committed scenario missing from ``reach.json`` is treated conservatively: any backend ``.py`` file the
scenario runner's import closure reaches names it. Re-measure after adding a scenario or when the product
path a scenario takes changes (``affected`` lists the measured ref; ``test_pipeline_lab_affected`` fails when
``reach.json`` names a file that no longer exists).

Paths only, no values: the trace records file names, and every scenario is synthetic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
from typing import Any, Callable, Mapping, Optional

REACH_FILE = Path(__file__).resolve().parent / 'reach.json'
CALLED_FILE = 'called_files.json'
BACKEND = Path(__file__).resolve().parents[3]
SKIP_PREFIXES = ('tests/', '.venv/')


class CallTrace:
    """Backend files (``backend/...``) with a function called while installed; every thread, new ones too."""

    def __init__(self, backend: Path = BACKEND):
        self.prefix = str(backend) + '/'
        self.files: set[str] = set()
        self._codes: set[Any] = set()

    def _profile(self, frame: Any, event: str, arg: Any) -> None:
        if event != 'call':
            return
        code = frame.f_code
        if code in self._codes:
            return
        self._codes.add(code)
        name = code.co_filename
        if code.co_name == '<module>' or not name.startswith(self.prefix):
            return
        rel = name[len(self.prefix) :]
        if not rel.startswith(SKIP_PREFIXES):
            self.files.add('backend/' + rel)

    def start(self) -> 'CallTrace':
        sys.setprofile(self._profile)
        threading.setprofile(self._profile)
        return self

    def stop(self) -> list[str]:
        sys.setprofile(None)
        threading.setprofile(None)  # type: ignore[arg-type]
        return sorted(self.files)


def _called(folder: Path) -> Optional[set[str]]:
    """The union of ``called_files.json`` over a scenario folder and its ``repeat-*`` folders."""
    found: Optional[set[str]] = None
    for path in [folder / CALLED_FILE, *sorted(folder.glob(f'repeat-*/{CALLED_FILE}'))]:
        if path.is_file():
            found = (found or set()) | set(json.loads(path.read_text()))
    return found


def build_reach(run_dir: Path, identity: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """``reach.json``'s content from a ``scenario run --trace-calls`` directory."""
    run_dir = Path(run_dir)
    per: dict[str, set[str]] = {}
    for folder in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        called = _called(folder)
        if called is not None:
            per[folder.name] = called
    if not per:
        raise ValueError(f'{run_dir}: no {CALLED_FILE}; run `scenario run --trace-calls --keep {run_dir}` first')
    common = set.intersection(*per.values())
    run = {}
    if (run_dir / 'run.json').is_file():
        run = json.loads((run_dir / 'run.json').read_text())
    identity = identity or {}
    return {
        'schema': 1,
        'measured_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'ref': identity.get('sha') or run.get('sha'),
        'dirty': run.get('dirty'),
        'how': 'scenario run --trace-calls, then scenario reach (scenario/reach.py)',
        'common': sorted(common),
        'scenarios': {name: sorted(files - common) for name, files in sorted(per.items())},
    }


def write_reach(run_dir: Path, out: Path = REACH_FILE) -> dict[str, Any]:
    value = build_reach(run_dir)
    out.write_text(json.dumps(value, indent=1) + '\n')
    return {
        'written': str(out),
        'scenarios': {k: len(value['common']) + len(v) for k, v in value['scenarios'].items()},
        'common': len(value['common']),
    }


def load_reach(read: Callable[[str], Optional[str]], rel: str) -> dict[str, set[str]]:
    """``{scenario: files}`` from a ``reach.json`` read through ``read(rel)`` (the working tree or a git ref)."""
    text = read(rel)
    if not text:
        return {}
    value = json.loads(text)
    common = set(value.get('common') or ())
    return {name: common | set(files) for name, files in (value.get('scenarios') or {}).items()}
