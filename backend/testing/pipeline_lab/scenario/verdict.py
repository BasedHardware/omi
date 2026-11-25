"""The run directory a ``scenario run`` writes, and the verdict and determinism helpers (pure, stdlib only).

Layout (a contract other tools read; ``schema`` bumps on any incompatible change)::

    DIR/run.json        {"schema": 1, "backend_tree", "ref", "started_at", "seconds", "scenarios": [...], "isolation": {...}}
    DIR/verdict.json    {"schema": 1, "outcome": "passed|failed|error", "scenarios": [{"name", "outcome", "seconds",
                         "checks": [{"label", "passed", "expected", "actual", "at"}], "stand_ins", "error"}]}
    DIR/<name>/scenario.json   the scenario file as run
    DIR/<name>/result.json     what ``scenario/run.py`` writes
    DIR/<name>/home.json       written by the Home hook (``run.write_home_snapshot``), not here
    DIR/<name>/v3_tasks.jsonl, decisions.jsonl
    DIR/<name>/repeat-<k>/...  repeats 2..N of ``--repeat N`` (repeat 1 is DIR/<name>/ itself)

Wall-clock values live only in ``run.json`` and the ``seconds`` fields (and ``result.json``'s ``timings``),
so everything else is comparable between runs.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.scenario.checks import OUTCOMES, actual_of, expected_of

SCHEMA = 1
# result.json fields that measure wall time or name a path of this run; dropped before repeats are compared.
WALL_CLOCK_FIELDS = ('seconds', 'timings', 'log')
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
        'error': result.get('error'),
    }


def verdict(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {'schema': SCHEMA, 'outcome': overall_outcome([r['outcome'] for r in rows]), 'scenarios': list(rows)}


# ---- determinism ----------------------------------------------------------------------------------


def _handles(result: Mapping[str, Any]) -> list[str]:
    seen: list[str] = []
    snapshots = [result.get('conversations') or []]
    snapshots += [c.get('conversations') or [] for _, c in sorted((result.get('checkpoints') or {}).items())]
    for snapshot in snapshots:
        for conv in snapshot:
            handle = conv.get('handle')
            if handle and handle not in seen:
                seen.append(handle)
    return seen


def comparable(result: Mapping[str, Any]) -> str:
    """``result.json`` as canonical text with wall-clock fields removed and conversation handles (prefixes
    of random document ids) renamed ``conv1``, ``conv2``, ... in order of first appearance."""
    text = json.dumps({k: v for k, v in result.items() if k not in WALL_CLOCK_FIELDS}, sort_keys=True, default=str)
    for number, handle in enumerate(_handles(result), start=1):
        text = re.sub(rf'\b{re.escape(handle)}\b', f'conv{number}', text)
    return text


def repeat_differences(results: Sequence[Mapping[str, Any]]) -> list[str]:
    """Top-level ``result.json`` keys whose comparable value differs between any repeat and the first."""
    if len(results) < 2:
        return []
    parsed = [json.loads(comparable(r)) for r in results]
    first = parsed[0]
    keys = sorted({k for p in parsed for k in p})
    return [k for k in keys if any(p.get(k) != first.get(k) for p in parsed[1:])]


# ---- files ----------------------------------------------------------------------------------------


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=False, default=str) + '\n')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())
