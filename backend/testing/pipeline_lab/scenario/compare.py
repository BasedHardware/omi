"""``python -m testing.pipeline_lab scenario compare``: the same scenarios on several arms, against a baseline.

An *arm* is ``{name, ref, overlay, env}``: product code from ``ref`` (omitted or null = this working tree), and
on top of each scenario's own env an optional lab overlay file (``{name, env, serving, gates, model_config}``,
``stack/overlay.py``) and then ``env``. Arms may share a ref and differ only by overlay or env (a threshold
sweep), or differ by ref (the two-ref form below). Every arm is compared with the baseline arm::

    scenario compare BASE [HEAD|--worktree]          two arms: base = BASE, head = HEAD or this tree
    scenario compare --arms FILE [--baseline NAME]   FILE: [arm, ...] or {"baseline": NAME, "arms": [...]}
    scenario compare --arm SPEC --arm SPEC ...       SPEC: an arm as JSON, or NAME[@REF]

Writes (``DIR`` = ``--keep``, else a fresh private directory)::

    DIR/<arm>/        the run layout of scenario/verdict.py for each arm (the two-ref form: base/ and head/)
    DIR/compare.json  outcomes and conversation differences per arm, metrics, the harness report (SCHEMA)
    DIR/.arms/        each arm's effective overlay (0600; omitted for an arm with neither overlay nor env)

A ref runs in the lab's pinned worktree for that commit (``worktrees.ensure_worktree``, never fetched) with
**this checkout's** lab package vendored in and this checkout's venv (the dependency locks must match). So
every arm runs the invoking checkout's harness, scenario files and budgets: ``compare.json`` ``harness`` says
whether each arm's own ref carries a different harness, so an assertion weakened on one side cannot make both
sides silently green.

Metrics: each registered extractor (``scenario/metrics.py``) reads each arm's directory; the report gives a
per-arm table and each arm's delta against the baseline. Metrics are reported, never judged.

Exit 0 when no arm differs from the baseline, 1 when an outcome or a conversation differs, 2 when an arm
errored, a metric extractor failed, or the arms could not be set up.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab import worktrees
from testing.pipeline_lab.orchestrator import redact_overlay
from testing.pipeline_lab.scenario import metrics as metric_registry, stack, verdict as verdicts
from testing.pipeline_lab.scenario.spec import ScenarioError, load_scenario
from testing.pipeline_lab.stack.overlay import Overlay
from testing.pipeline_lab.store import private_write_text

SCHEMA = 2
# The conversation fields compare reads (no handle: it is a random id).
COMPARED = ('recordings', 'visible', 'hidden_reason', 'words', 'manual_end')
ARM_KEYS = ('name', 'ref', 'overlay', 'env')
_ARM_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
ARMS_DIR = '.arms'
# The harness every arm runs (vendored from the invoking checkout), and how its changed paths are grouped.
HARNESS = 'backend/testing/pipeline_lab'
HARNESS_GROUPS = (
    ('scenarios', 'scenario/scenarios/'),  # expect rows and budgets
    ('fixtures', 'scenario/fixtures/'),
    ('code', ''),  # checks, budget counting, verdicts, the runner, ...
)
LEGACY = ('base', 'head')


def committed_scenarios() -> list[str]:
    return sorted(path.stem for path in stack.SCENARIO_DIR.glob('*.json'))


# ---- arms ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmSpec:
    """One arm: ``ref`` None runs this working tree; ``overlay`` is a lab overlay file; ``env`` wins over it."""

    name: str
    ref: Optional[str] = None
    overlay: Optional[Path] = None
    env: Mapping[str, str] = field(default_factory=dict)

    def effective_overlay(self) -> Optional[dict[str, Any]]:
        """The overlay mapping the arm's scenario processes apply (``scenario/run.py --arm-overlay``), or None."""
        if self.overlay is None and not self.env:
            return None
        try:
            base = Overlay.load(self.overlay) if self.overlay is not None else Overlay()
            merged = Overlay.from_mapping({**base.to_mapping(), 'env': {**base.env, **self.env}, 'name': self.name})
        except (OSError, ValueError) as error:
            raise ScenarioError(f'arm {self.name}: overlay: {error}') from None
        return merged.to_mapping()

    def describe(self) -> dict[str, Any]:
        """What compare.json records of the arm's configuration: env with secret-shaped values redacted, the
        overlay file's name and digest and the names it sets (never its values: it may carry allow-lists)."""
        out: dict[str, Any] = {'env': redact_overlay({'env': dict(self.env)}).get('env', {}), 'overlay': None}
        if self.overlay is not None:
            overlay = Overlay.load(self.overlay)
            out['overlay'] = {
                'file': self.overlay.name,
                'digest': overlay.digest(),
                'env_keys': sorted(overlay.env),
                'serving': sorted(overlay.serving),
                'gates': sorted(overlay.gates),
                'model_config': sorted(overlay.model_config),
            }
        return out


def parse_arm(raw: Any, *, base_dir: Path) -> ArmSpec:
    """An arm from JSON (``{"name", "ref"?, "overlay"?, "env"?}``; overlay relative to ``base_dir``)."""
    if not isinstance(raw, Mapping):
        raise ScenarioError(f'arm {raw!r}: an object with {", ".join(ARM_KEYS)}')
    unknown = sorted(set(raw) - set(ARM_KEYS))
    if unknown:
        raise ScenarioError(f'arm {raw.get("name")!r}: unknown keys {unknown} (allowed: {", ".join(ARM_KEYS)})')
    name = raw.get('name')
    if not isinstance(name, str) or not _ARM_NAME.match(name):
        raise ScenarioError(f'arm name {name!r}: letters, digits, "_" and "-", at most 64, not starting with "-"')
    ref = raw.get('ref')
    if ref is not None and (not isinstance(ref, str) or not ref.strip() or ref.startswith('-')):
        raise ScenarioError(f'arm {name}: ref must be a branch, tag or sha (or null for this working tree)')
    overlay = raw.get('overlay')
    if overlay is not None and (not isinstance(overlay, str) or not overlay):
        raise ScenarioError(f'arm {name}: overlay must be a file path')
    env = raw.get('env') or {}
    if not isinstance(env, Mapping) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ScenarioError(f'arm {name}: env must be an object of string values')
    path = None
    if overlay is not None:
        path = Path(overlay).expanduser()
        path = (path if path.is_absolute() else base_dir / path).resolve()
        if not path.is_file():
            raise ScenarioError(f'arm {name}: overlay {overlay} is not a file')
    arm = ArmSpec(name=name, ref=ref, overlay=path, env=dict(env))
    arm.effective_overlay()  # validate now, before any stack or worktree
    return arm


def parse_arm_spec(text: str) -> ArmSpec:
    """``--arm``: an arm as JSON, or the shorthand ``NAME[@REF]``."""
    text = text.strip()
    if text.startswith('{'):
        try:
            raw = json.loads(text)
        except ValueError as error:
            raise ScenarioError(f'--arm {text!r}: not JSON ({error})') from None
        return parse_arm(raw, base_dir=Path.cwd())
    name, at, ref = text.partition('@')
    return parse_arm({'name': name, 'ref': ref if at else None}, base_dir=Path.cwd())


def load_arms(path: str) -> tuple[list[ArmSpec], Optional[str]]:
    """``--arms FILE``: ``[arm, ...]`` or ``{"baseline": NAME, "arms": [...]}``; overlays relative to FILE."""
    file = Path(path).expanduser().resolve()
    try:
        raw = json.loads(file.read_text())
    except (OSError, ValueError) as error:
        raise ScenarioError(f'--arms {path}: {error}') from None
    baseline = None
    if isinstance(raw, Mapping):
        unknown = sorted(set(raw) - {'baseline', 'arms'})
        if unknown:
            raise ScenarioError(f'--arms {path}: unknown keys {unknown} (allowed: baseline, arms)')
        baseline = raw.get('baseline')
        if baseline is not None and not isinstance(baseline, str):
            raise ScenarioError(f'--arms {path}: baseline must be an arm name')
        raw = raw.get('arms')
    if not isinstance(raw, list):
        raise ScenarioError(f'--arms {path}: a list of arms, or {{"baseline", "arms"}}')
    return [parse_arm(row, base_dir=file.parent) for row in raw], baseline


def legacy_arms(base_ref: str, head_ref: Optional[str]) -> list[ArmSpec]:
    """``compare BASE [HEAD|--worktree]``: arm ``base`` at BASE, arm ``head`` at HEAD or this working tree."""
    return [parse_arm({'name': 'base', 'ref': base_ref}, base_dir=Path.cwd()), ArmSpec('head', head_ref)]


def check_arms(arms: Sequence[ArmSpec], baseline: Optional[str]) -> str:
    """Validate the set; return the baseline arm's name (default: the first arm)."""
    if len(arms) < 2:
        raise ScenarioError('compare needs at least two arms')
    names = [arm.name for arm in arms]
    duplicate = sorted({n for n in names if names.count(n) > 1})
    if duplicate:
        raise ScenarioError(f'arm names must be unique: {duplicate}')
    baseline = baseline or names[0]
    if baseline not in names:
        raise ScenarioError(f'baseline {baseline!r} is not an arm ({", ".join(names)})')
    return baseline


# ---- conversation and outcome differences ----------------------------------------------------------


def _keyed(conversations: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Live conversations keyed by their recording labels (``B+C``); repeats of a key get ``#2``, ``#3``."""
    out: dict[str, dict[str, Any]] = {}
    rows = [c for c in conversations if not c.get('deleted')]
    rows.sort(key=lambda c: ('+'.join(sorted(c.get('recordings') or [])), str(c.get('started_at') or '')))
    for conv in rows:
        key = '+'.join(sorted(conv.get('recordings') or [])) or '-'
        name, n = key, 1
        while name in out:
            n += 1
            name = f'{key}#{n}'
        out[name] = {k: conv.get(k) for k in COMPARED}
    return out


def diff_conversations(base: Sequence[Mapping[str, Any]], head: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per conversation that is missing on a side or differs in a compared field."""
    left, right = _keyed(base), _keyed(head)
    rows = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if a == b:
            continue
        fields = sorted(k for k in COMPARED if (a or {}).get(k) != (b or {}).get(k)) if a and b else ['present']
        rows.append({'key': key, 'base': a, 'head': b, 'fields': fields})
    return rows


def compare_results(
    base: Mapping[str, Mapping[str, Any]], head: Mapping[str, Mapping[str, Any]], outcomes: Mapping[str, tuple]
) -> list[dict[str, Any]]:
    """Per scenario: each side's outcome and the conversations that differ (final state)."""
    rows = []
    for name in sorted(set(base) | set(head)):
        a, b = base.get(name) or {}, head.get(name) or {}
        base_outcome, head_outcome = outcomes.get(name, (a.get('outcome'), b.get('outcome')))
        conversations = diff_conversations(a.get('conversations') or [], b.get('conversations') or [])
        rows.append(
            {
                'name': name,
                'base': base_outcome,
                'head': head_outcome,
                'differs': base_outcome != head_outcome or bool(conversations),
                'conversations': conversations,
            }
        )
    return rows


def compare_arms(
    results: Mapping[str, Mapping[str, Mapping[str, Any]]],
    outcomes: Mapping[str, Mapping[str, str]],
    order: Sequence[str],
    baseline: str,
) -> list[dict[str, Any]]:
    """Per scenario, every non-baseline arm against the baseline. ``results[arm][scenario]`` is the first
    repeat's result.json, ``outcomes[arm][scenario]`` the verdict outcome. Each row also keeps the two-arm
    fields (``base``, ``head``, ``conversations``: the baseline against the first other arm)."""
    others = [arm for arm in order if arm != baseline]
    names = sorted({name for arm in order for name in (results.get(arm) or {})})
    rows = []
    for name in names:
        by_arm = {}
        for arm in others:
            row = compare_results(
                {name: results[baseline].get(name) or {}},
                {name: results[arm].get(name) or {}},
                {name: (outcomes[baseline].get(name), outcomes[arm].get(name))},
            )[0]
            by_arm[arm] = {'outcome': row['head'], 'differs': row['differs'], 'conversations': row['conversations']}
        first = by_arm[others[0]]
        rows.append(
            {
                'name': name,
                'base': outcomes[baseline].get(name),
                'head': first['outcome'],
                'differs': any(entry['differs'] for entry in by_arm.values()),
                'conversations': first['conversations'],
                'outcomes': {arm: outcomes[arm].get(name) for arm in order},
                'arms': by_arm,
            }
        )
    return rows


# ---- the harness every arm ran -------------------------------------------------------------------------


def _group(relative: str) -> str:
    return next(name for name, prefix in HARNESS_GROUPS if relative.startswith(prefix))


def harness_report(
    repo: Path, identities: Mapping[str, Mapping[str, Any]], order: Sequence[str], baseline: str
) -> dict[str, Any]:
    """Whether each arm's own ref carries the harness that ran (this checkout's ``backend/testing/pipeline_lab``,
    working tree included), and which harness files differ, by group (``scenarios``: expect rows and budgets)."""
    note = (
        "every arm ran the invoking checkout's harness (backend/testing/pipeline_lab: checks, budgets, scenario "
        'files); an arm whose own ref has a different harness was judged by assertions that ref does not carry'
    )
    try:
        head = worktrees.git(repo, 'rev-parse', 'HEAD')
        ran = {
            'source': 'invoking checkout',
            'sha': head,
            'tree': worktrees.git(repo, 'rev-parse', f'HEAD:{HARNESS}'),
            'dirty': bool(worktrees.git(repo, 'status', '--porcelain', '--', HARNESS)),
        }
        untracked = [
            p
            for p in worktrees.git(repo, 'ls-files', '--others', '--exclude-standard', '--', HARNESS).splitlines()
            if p
        ]
        arms: dict[str, dict[str, Any]] = {}
        for name in order:
            sha = identities[name].get('sha') if identities[name].get('ref_given') else None
            if sha is None:  # this working tree: the harness that ran, by definition
                arms[name] = {
                    'ref': None,
                    'sha': head,
                    'tree': ran['tree'] + ('+modified' if ran['dirty'] else ''),
                    'same_as_ran': True,
                    'changed': {},
                }
                continue
            changed_paths = worktrees.git(repo, 'diff', '--name-only', sha, '--', HARNESS).splitlines()
            changed: dict[str, list[str]] = {}
            for path in sorted({p for p in changed_paths + untracked if p}):
                relative = path[len(HARNESS) + 1 :] if path.startswith(HARNESS + '/') else path
                changed.setdefault(_group(relative), []).append(relative)
            arms[name] = {
                'ref': identities[name].get('ref'),
                'sha': sha,
                'tree': worktrees.git(repo, 'rev-parse', f'{sha}:{HARNESS}', check=False) or None,
                'same_as_ran': not changed,
                'changed': changed,
            }
    except worktrees.WorktreeError as error:
        return {'path': HARNESS, 'error': str(error), 'drift': None, 'note': note}
    for row in arms.values():
        row['same_as_baseline'] = row['tree'] == arms[baseline]['tree']
    return {
        'path': HARNESS,
        'ran': ran,
        'arms': arms,
        # Product code from more than one commit (a modified working tree counts as its own).
        'refs_differ': len({(row['sha'], row['ref'] is None and ran['dirty']) for row in arms.values()}) > 1,
        'drift': any(not row['same_as_ran'] for row in arms.values()),
        'note': note,
    }


def harness_lines(report: Mapping[str, Any]) -> list[str]:
    """The human lines of the harness report (``harness_report``)."""
    if report.get('error'):
        return [f'  WARNING: harness check failed ({report["error"]}); {report["note"]}']
    ran = report['ran']
    lines = [
        f"  harness: every arm ran this checkout's {report['path']} (tree {str(ran['tree'])[:10]}"
        f"{', modified' if ran['dirty'] else ''})"
    ]
    for name, row in report['arms'].items():
        if row['same_as_ran']:
            continue
        counts = ', '.join(f'{len(paths)} {group}' for group, paths in row['changed'].items())
        lines.append(
            f'  WARNING: arm {name} ({row["ref"]}) carries a different harness than the one that ran: {counts} '
            f'file(s) differ'
        )
        for group, paths in row['changed'].items():
            shown = ', '.join(paths[:8]) + (', ...' if len(paths) > 8 else '')
            lines.append(f'           {group}: {shown}')
    if report['drift']:
        lines.append(f'           {report["note"]}')
    return lines


# ---- metrics ---------------------------------------------------------------------------------------


def load_metrics(names: Optional[Sequence[str]]) -> list[str]:
    """Import the metric modules (before any arm runs: a broken one fails the command, exit 2)."""
    try:
        modules = metric_registry.load_metric_modules()
    except metric_registry.MetricError as error:
        raise ScenarioError(str(error)) from None
    missing = sorted(set(names or ()) - set(metric_registry.registered()))
    if missing:
        raise ScenarioError(
            f'--metric {", ".join(missing)}: not registered ({", ".join(metric_registry.registered())})'
        )
    return modules


def arm_metrics(
    roots: Mapping[str, Path],
    order: Sequence[str],
    baseline: str,
    names: Optional[Sequence[str]],
    modules: Sequence[str] = (),
) -> dict[str, Any]:
    """``{"extractors", "modules", "keys", "values": {arm: {key: v}}, "deltas": {arm: {key: d}},
    "errors": {arm: {metric: error}}}``."""
    chosen = list(names) if names else list(metric_registry.registered())
    values, errors = {}, {}
    for arm in order:
        values[arm], arm_errors = metric_registry.extract(roots[arm], chosen)
        if arm_errors:
            errors[arm] = arm_errors
    keys, deltas = metric_registry.table(values, baseline)
    return {
        'extractors': chosen,
        'modules': list(modules),
        'keys': keys,
        'values': values,
        'deltas': deltas,
        'errors': errors,
    }


def _cell(value: Any) -> str:
    if value is None:
        return '-'
    if isinstance(value, float):
        return f'{value:g}'
    return str(value)


def _delta_cell(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ('+' if value > 0 else '') + _cell(value)
    return _cell(value)


def metric_lines(report: Mapping[str, Any], order: Sequence[str], baseline: str) -> list[str]:
    """A per-arm table of the keys where some arm differs from the baseline (the rest are counted)."""
    values, deltas = report['values'], report['deltas']
    moved = [k for k in report['keys'] if any(values[a].get(k) != values[baseline].get(k) for a in order)]
    lines = [
        f'  metrics ({", ".join(report["extractors"]) or "none"}): {len(moved)} of {len(report["keys"])} key(s) '
        f'differ from baseline {baseline}'
    ]
    if moved:
        header = ['key'] + [f'{a} (baseline)' if a == baseline else a for a in order]
        rows = [header]
        for key in moved:
            row = [key]
            for arm in order:
                cell = _cell(values[arm].get(key))
                if arm != baseline:
                    cell += f' ({_delta_cell(deltas[arm].get(key))})'
                row.append(cell)
            rows.append(row)
        widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
        for row in rows:
            lines.append('    ' + '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    for arm, errs in report['errors'].items():
        for name, error in errs.items():
            lines.append(f'  ERROR: metric {name} on arm {arm}: {error}')
    return lines


# ---- the command ------------------------------------------------------------------------------------


def _side(repo: Path, ref: Optional[str], vendor_root: Path) -> tuple[Optional[stack.Arm], dict[str, Any]]:
    """The arm for ``ref`` (``None`` = this working tree) and its run.json identity."""
    if ref is None:
        return None, stack.backend_identity()
    tree = worktrees.ensure_worktree(repo, ref)
    worktrees.check_lockfile(stack.BACKEND, tree.backend)
    vendor = worktrees.vendor_lab(vendor_root)
    identity = {
        'backend_tree': tree.backend_tree,
        'ref': ref,
        'sha': tree.sha,
        'dirty': False,
        'worktree': str(tree.path),
    }
    return stack.Arm(backend=tree.backend, vendor=vendor), identity


def compare_refs(
    base_ref: str,
    head_ref: Optional[str],
    *,
    names: Optional[Sequence[str]],
    keep: Optional[str],
    timeout: float,
    jobs: int = 1,
    clock: str = 'frozen',
    as_json: bool = False,
    metric_names: Optional[Sequence[str]] = None,
) -> int:
    """The two-ref form: arms ``base`` (BASE) and ``head`` (HEAD, or this working tree)."""
    return compare_arm_set(
        legacy_arms(base_ref, head_ref),
        'base',
        names=names,
        keep=keep,
        timeout=timeout,
        jobs=jobs,
        clock=clock,
        as_json=as_json,
        metric_names=metric_names,
    )


def compare_arm_set(
    arms: Sequence[ArmSpec],
    baseline: Optional[str],
    *,
    names: Optional[Sequence[str]],
    keep: Optional[str],
    timeout: float,
    jobs: int = 1,
    clock: str = 'frozen',
    as_json: bool = False,
    metric_names: Optional[Sequence[str]] = None,
) -> int:
    baseline = check_arms(arms, baseline)
    order = [arm.name for arm in arms]
    paths = [stack.resolve(name) for name in (names or committed_scenarios())]
    for path in paths:
        load_scenario(path)
    modules = load_metrics(metric_names)
    root = stack.output_root(keep, prefix='plab-compare-')
    repo = stack.BACKEND.parent
    started = time.perf_counter()
    identities: dict[str, dict[str, Any]] = {}
    done: dict[str, Any] = {}
    with ExitStack() as cleanup:
        vendors = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-lab-arm-')))
        sides = []
        for arm in arms:
            (vendors / arm.name).mkdir()
            side, identity = _side(repo, arm.ref, vendors / arm.name)
            identities[arm.name] = {**identity, 'ref_given': arm.ref is not None}
            run_args = ['--stt', 'replay']
            overlay = arm.effective_overlay()
            if overlay is not None:
                overlay_dir = stack._private(root / ARMS_DIR, 'arm overlays')
                overlay_path = overlay_dir / f'{arm.name}.json'
                private_write_text(overlay_path, json.dumps(overlay, indent=1, sort_keys=True) + '\n')
                run_args += ['--arm-overlay', str(overlay_path)]
            sides.append((arm, side, identity, run_args))
        peers = cleanup.enter_context(stack.local_stack(root))
        for arm, side, identity, run_args in sides:
            done[arm.name] = stack.run_set(
                paths,
                root / arm.name,
                peers,
                timeout=timeout,
                clock=clock,
                jobs=jobs,
                arm=side,
                identity=identity,
                stt_args=run_args,
            )
            if not as_json:
                summary = ', '.join(f'{r["name"]}={r["outcome"]}' for r in done[arm.name].verdict['scenarios'])
                where = f'{identity.get("ref")} {str(identity.get("sha") or "")[:12]}'
                print(f'== {arm.name} ({where}): {summary}', flush=True)
    outcomes = {arm: {r['name']: r['outcome'] for r in done[arm].verdict['scenarios']} for arm in order}
    results = {arm: {name: rs[0] for name, rs in done[arm].results.items()} for arm in order}
    rows = compare_arms(results, outcomes, order, baseline)
    harness = harness_report(repo, identities, order, baseline)
    metrics = arm_metrics({arm: root / arm for arm in order}, order, baseline, metric_names, modules)
    errored = any(o == 'error' for by_name in outcomes.values() for o in by_name.values()) or bool(metrics['errors'])
    differs = any(row['differs'] for row in rows)
    first_other = next(arm for arm in order if arm != baseline)
    fields = ('ref', 'sha', 'backend_tree', 'dirty')
    report = {
        'schema': SCHEMA,
        'baseline': baseline,
        'arms': [
            {'name': arm.name, **{k: identities[arm.name].get(k) for k in fields}, **arm.describe()} for arm in arms
        ],
        # The two-arm fields (schema 1, and the web view): the baseline and the first other arm.
        'base': {k: identities[baseline].get(k) for k in fields},
        'head': {k: identities[first_other].get(k) for k in fields},
        'differs': differs,
        'errored': errored,
        'seconds': round(time.perf_counter() - started, 1),
        'scenarios': rows,
        'metrics': metrics,
        'harness': harness,
    }
    verdicts.write_json(root / 'compare.json', report)
    if as_json:
        print(json.dumps(report, default=str))
    else:
        for row in rows:
            mark = 'DIFFERS' if row['differs'] else 'same'
            shown = ', '.join(f'{arm} {row["outcomes"][arm]}' for arm in order)
            print(f'  {mark:<8}{row["name"]}: {shown}')
            for arm, entry in row['arms'].items():
                for conv in entry['conversations']:
                    print(f'          {arm} vs {baseline}: conversation {conv["key"]}: {", ".join(conv["fields"])}')
        for line in metric_lines(metrics, order, baseline) + harness_lines(harness):
            print(line)
        verdict_text = 'differs' if differs else 'no difference'
        print(f'== compare of {len(order)} arms in {report["seconds"]:.1f} s: {verdict_text}; output: {root}')
    if errored:
        return 2
    return 1 if differs else 0
