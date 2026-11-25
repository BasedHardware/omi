"""The run directory a ``scenario run`` writes, and the verdict and determinism helpers (pure, stdlib only).

Layout (a contract other tools read; ``schema`` bumps on any incompatible change)::

    DIR/run.json        {"schema": 1, "backend_tree", "ref", "started_at", "seconds", "scenarios": [...], "isolation": {...}}
    DIR/verdict.json    {"schema": 1, "outcome": "passed|failed|error", "scenarios": [{"name", "outcome", "seconds",
                         "checks": [{"label", "passed", "expected", "actual", "at"}], "stand_ins", "error"}]}
    DIR/<name>/scenario.json   the scenario file as run
    DIR/<name>/result.json     what ``scenario/run.py`` writes
    DIR/<name>/home.json       written by ``scenario/home.HomeRecorder.write_home_snapshot``, not here
    DIR/<name>/v3_tasks.jsonl, decisions.jsonl
    DIR/<name>/repeat-<k>/...  repeats 2..N of ``--repeat N`` (repeat 1 is DIR/<name>/ itself)

Repeats are compared by ``determinism.compare_runs`` over ``determinism.SCENARIO_ARTIFACTS`` (result.json,
home.json, v3_tasks.jsonl, ...): one allowlist of wall-clock fields for repeats and day replays alike.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.scenario.checks import OUTCOMES, actual_of, expected_of

SCHEMA = 1
OVERALL = {0: 'passed', 1: 'failed', 2: 'error'}


def overall_outcome(outcomes: Sequence[str]) -> str:
    return OVERALL[max((OUTCOMES.get(o, 2) for o in outcomes), default=0)]


def exit_code(outcomes: Sequence[str]) -> int:
    return max((OUTCOMES.get(o, 2) for o in outcomes), default=0)


def _snapshot_for(result: Mapping[str, Any], index: int, at: Optional[float]) -> list[Mapping[str, Any]]:
    if at is None:
        return list(result.get('conversations') or [])
    seen = (result.get('checkpoints') or {}).get(str(index))
    return list(seen['conversations']) if seen else []


def scenario_verdict(name: str, result: Mapping[str, Any], scenario: Any = None) -> dict[str, Any]:
    """One ``verdict.json`` scenario row from a ``result.json`` and the scenario it ran (``spec.Scenario``)."""
    checks = []
    rows = list(result.get('checks') or [])
    if scenario is not None and len(rows) == len(scenario.checks):
        for index, (check, row) in enumerate(zip(scenario.checks, rows)):
            snapshot = _snapshot_for(result, index, check.at)
            checks.append(
                {
                    'label': check.label or row.get('check'),
                    'passed': bool(row.get('ok')),
                    'expected': expected_of(check),
                    'actual': actual_of(check, snapshot, result.get('finish_target')),
                    'at': check.at,
                }
            )
    else:  # an error before the checks ran, or no scenario object: what result.json says
        checks = [
            {'label': row.get('check'), 'passed': bool(row.get('ok')), 'expected': {}, 'actual': {}, 'at': None}
            for row in rows
        ]
    return {
        'name': name,
        'outcome': str(result.get('outcome') or 'error'),
        'seconds': result.get('seconds', 0),
        'checks': checks,
        'stand_ins': sorted((result.get('stand_ins') or {}).keys()),
        'transcripts': transcript_sources(result),
        'error': result.get('error'),
    }


def verdict(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {'schema': SCHEMA, 'outcome': overall_outcome([r['outcome'] for r in rows]), 'scenarios': list(rows)}


# ---- determinism ----------------------------------------------------------------------------------

REPEAT_DIFFERENCE_LIMIT = 50


def repeat_differences(run_dirs: Sequence[Path], limit: int = REPEAT_DIFFERENCE_LIMIT) -> list[str]:
    """``<artifact> <json path>`` for each place a repeat's directory differs from the first's (paths only,
    no values), by ``determinism.compare_runs`` over ``determinism.SCENARIO_ARTIFACTS``."""
    from testing.pipeline_lab.determinism import SCENARIO_ARTIFACTS, compare_runs

    out: list[str] = []
    for other in run_dirs[1:]:
        for difference in compare_runs(Path(run_dirs[0]), Path(other), SCENARIO_ARTIFACTS).differences:
            text = f'{difference.artifact} {difference.path}'
            if text not in out:
                out.append(text)
    return out[:limit]


def transcript_sources(result: Mapping[str, Any]) -> dict[str, str]:
    """Each recording's transcript source: ``scripted`` (speech lines in the scenario) or the cassette's
    ``synthetic`` / ``local`` / ``vendor`` for an ``audio_file`` recording (``scenario/audio.py``)."""
    audio = {row.get('label'): row.get('source') for row in (result.get('audio') or {}).get('recordings') or []}
    out = {}
    for row in result.get('recordings') or []:
        label = row.get('label')
        out[str(label)] = str(row.get('stt') or audio.get(label) or 'scripted')
    return out


# ---- files ----------------------------------------------------------------------------------------


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=False, default=str) + '\n')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())
