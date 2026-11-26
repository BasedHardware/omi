"""``python -m testing.pipeline_lab scenario compare <base-ref> [<head-ref>|--worktree]``.

Runs the same scenarios (from this checkout) against two backend trees on one shared stack and writes::

    DIR/base/      the run layout of scenario/verdict.py, product code from <base-ref>
    DIR/head/      the same for <head-ref>, or this working tree (the default, or --worktree)
    DIR/compare.json

A ref runs in the lab's pinned worktree for that commit (``worktrees.ensure_worktree``, never fetched) with
this checkout's lab package vendored in and this checkout's venv (the dependency locks must match). Exit 0
when nothing differs, 1 when an outcome or a conversation differs, 2 when either side errored.
"""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.scenario import stack, verdict as verdicts

SCHEMA = 1
# The conversation fields compare reads (no handle: it is a random id).
COMPARED = ('recordings', 'visible', 'hidden_reason', 'words', 'manual_end')


def committed_scenarios() -> list[str]:
    return sorted(path.stem for path in stack.SCENARIO_DIR.glob('*.json'))


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


def _side(repo: Path, ref: Optional[str], vendor_root: Path) -> tuple[Optional[stack.Arm], dict[str, Any]]:
    """The arm for ``ref`` (``None`` = this working tree) and its run.json identity."""
    from testing.pipeline_lab import worktrees

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
) -> int:
    from testing.pipeline_lab.scenario.spec import load_scenario

    paths = [stack.resolve(name) for name in (names or committed_scenarios())]
    for path in paths:
        load_scenario(path)
    root = stack.output_root(keep, prefix='plab-compare-')
    repo = stack.BACKEND.parent
    started = time.perf_counter()
    with ExitStack() as cleanup:
        vendors = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-lab-arm-')))
        (vendors / 'base').mkdir()
        (vendors / 'head').mkdir()
        base_arm, base_id = _side(repo, base_ref, vendors / 'base')
        head_arm, head_id = _side(repo, head_ref, vendors / 'head')
        peers = cleanup.enter_context(stack.local_stack(root))
        sides = {}
        for side, arm, identity in (('base', base_arm, base_id), ('head', head_arm, head_id)):
            sides[side] = stack.run_set(
                paths, root / side, peers, timeout=timeout, clock=clock, jobs=jobs, arm=arm, identity=identity
            )
            if not as_json:
                summary = ', '.join(f'{r["name"]}={r["outcome"]}' for r in sides[side].verdict['scenarios'])
                print(f'== {side} ({identity.get("ref")} {str(identity.get("sha") or "")[:12]}): {summary}', flush=True)
    outcomes = {
        row['name']: (
            row['outcome'],
            next(r['outcome'] for r in sides['head'].verdict['scenarios'] if r['name'] == row['name']),
        )
        for row in sides['base'].verdict['scenarios']
    }
    first = {side: {name: rs[0] for name, rs in done.results.items()} for side, done in sides.items()}
    rows = compare_results(first['base'], first['head'], outcomes)
    errored = any(o == 'error' for pair in outcomes.values() for o in pair)
    differs = any(row['differs'] for row in rows)
    report = {
        'schema': SCHEMA,
        'base': {k: base_id.get(k) for k in ('ref', 'sha', 'backend_tree', 'dirty')},
        'head': {k: head_id.get(k) for k in ('ref', 'sha', 'backend_tree', 'dirty')},
        'differs': differs,
        'errored': errored,
        'seconds': round(time.perf_counter() - started, 1),
        'scenarios': rows,
    }
    verdicts.write_json(root / 'compare.json', report)
    if as_json:
        print(json.dumps(report))
    else:
        for row in rows:
            mark = 'DIFFERS' if row['differs'] else 'same'
            print(f'  {mark:<8}{row["name"]}: base {row["base"]}, head {row["head"]}')
            for conv in row['conversations']:
                print(f'          conversation {conv["key"]}: {", ".join(conv["fields"])}')
        print(f'== compare in {report["seconds"]:.1f} s: {"differs" if differs else "no difference"}; output: {root}')
    if errored:
        return 2
    return 1 if differs else 0
