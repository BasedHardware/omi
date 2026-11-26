"""The run directory a ``scenario run`` writes, and the verdict and determinism helpers (pure, stdlib only).

Layout (a contract other tools read; ``schema`` bumps on any incompatible change)::

    DIR/run.json        {"schema": 1, "backend_tree", "ref", "started_at", "seconds", "scenarios": [...], "isolation": {...}}
    DIR/verdict.json    {"schema": 1, "outcome": "passed|failed|error", "scenarios": [{"name", "outcome", "seconds",
                         "checks": [{"label", "passed", "expected", "actual", "at"}], "stand_ins", "stand_in_notes",
                         "audio_steps", "ops", "ops_table", "budget", "error"}]}
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

from testing.pipeline_lab.scenario import budget as budgets, standins
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
    facts = {
        'ops': result.get('ops'),
        'fast_finish': result.get('fast_finish') or {},
        'finish_taps': result.get('finish_taps') or [],
        'paging': result.get('paging'),
    }
    if scenario is not None and len(rows) == len(scenario.checks):
        for index, (check, row) in enumerate(zip(scenario.checks, rows)):
            snapshot = _snapshot_for(result, index, check.at)
            checks.append(
                {
                    'label': check.label or row.get('check'),
                    'passed': bool(row.get('ok')),
                    'expected': expected_of(check),
                    'actual': actual_of(check, snapshot, result.get('finish_target'), facts),
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
        'stand_in_notes': [row['text'] for row in result.get('stand_in_notes') or standins.stand_in_notes(result)],
        'audio_steps': [row['text'] for row in result.get('audio_steps') or standins.audio_steps(result)],
        'transcripts': transcript_sources(result),
        'ops': ops_summary(result.get('ops')),
        'ops_table': budgets.table_rows(result.get('ops'), result.get('budget')),
        'budget': result.get('budget'),
        'error': result.get('error'),
    }


def ops_summary(ops: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """The verdict row's copy of ``result.json`` ``ops``: totals, per-collection splits, no-op sites."""
    if not ops:
        return None
    keep = (
        'reads', 'writes', 'deletes', 'noop_writes', 'by_collection', 'by_path', 'by_scope', 'noop_sites',
        'wall_clock_reads',
    )  # fmt: skip
    out = {k: ops.get(k) for k in keep if k in ops}
    out['vendor_calls'] = ops.get('vendor_calls')
    return out


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


# ---- summary (markdown, for a pull request or a CI job summary) -------------------------------------


def markdown_summary(run_dir: Path) -> str:
    """The verdict of a ``scenario run --keep DIR`` as markdown: overall outcome, one row per scenario,
    failed checks and repeat differences by label/path only (no transcript text), and how to view it."""
    run_dir = Path(run_dir)
    verdict_value = read_json(run_dir / 'verdict.json')
    run = read_json(run_dir / 'run.json') if (run_dir / 'run.json').is_file() else {}
    rows = verdict_value.get('scenarios') or []
    ref = run.get('sha') or run.get('ref') or 'unknown'
    head = (
        f'**Pipeline lab scenarios: {verdict_value.get("outcome")}** ({len(rows)} scenario(s) x{run.get("repeat", 1)}, '
        f'jobs {run.get("jobs", 1)}, stt {run.get("stt", "replay")}, {run.get("seconds", "?")} s, '
        f'ref `{str(ref)[:12]}`{" dirty" if run.get("dirty") else ""})'
    )
    lines = [
        head,
        '',
        '| scenario | outcome | checks | seconds | transcripts | reads | writes | no-op writes | stt | llm |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in rows:
        checks = row.get('checks') or []
        passed = sum(1 for check in checks if check.get('passed'))
        sources = ', '.join(sorted(set((row.get('transcripts') or {}).values()))) or '-'
        ops = row.get('ops') or {}
        vendor = ops.get('vendor_calls') or {}
        counts = ' | '.join(
            str(v if v is not None else '-')
            for v in (ops.get('reads'), ops.get('writes'), ops.get('noop_writes'), vendor.get('stt'), vendor.get('llm'))
        )
        lines.append(
            f'| {row["name"]} | {row["outcome"]} | {passed}/{len(checks)} | {row.get("seconds", 0)} | {sources} | '
            f'{counts} |'
        )
    for row in rows:
        failed = [str(check.get('label')) for check in row.get('checks') or [] if not check.get('passed')]
        if failed:
            lines.append(f'- {row["name"]}: failed checks: {", ".join(failed)}')
        if row.get('differences'):
            lines.append(f'- {row["name"]}: differs between repeats at: {", ".join(row["differences"][:10])}')
        if row.get('error'):
            lines.append(f'- {row["name"]}: error: {row["error"]}')
    lines += ['', f'View: `python -m testing.pipeline_lab view {run_dir}` (run from `backend/`).']
    return '\n'.join(lines) + '\n'
