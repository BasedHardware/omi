"""What "the same result" means for a replay, and the comparison that checks it.

    python -m testing.pipeline_lab.determinism RUN_DIR_A RUN_DIR_B [RUN_DIR ...]

A replay's **semantic artifacts** are the files in its run directory that describe what the product
did: the conversations it built, their boundaries, visibility, notes (action items, memories), the
notifications it sent, the v3 event timeline on the replay's clock, task scheduling and the day
stages. Everything in :data:`ARTIFACTS`, minus the fields in :data:`WALL_CLOCK_FIELDS` and
:data:`VOLATILE_FIELDS`, is semantic; two runs of the same inputs must agree on all of it.

This module is the one place that definition lives. Each artifact names the fields it drops and why:

- :data:`WALL_CLOCK_FIELDS` are measurements of the host, not product outputs: real-time windows
  (``real_now``), durations (``seconds``, ``timings``, ``ms``), cache bookkeeping (``stored_at``,
  ``cache_hit``) and the orchestrator's real-time stamps.
- :data:`VOLATILE_FIELDS` are identifiers drawn from a random source on purpose: the LLM proxy's call
  ids (``secrets.token_hex``) and the run id. They are replaced by a count or dropped.
- Random UUIDs (version 4) the product mints, such as notification and daily-summary ids, are renamed
  ``uuid4#1``, ``uuid4#2``, ... in first-seen order, so references between files still have to match.
  Name-based ids (UUID v5, such as v3 conversation ids) are kept as they are.

Everything else, product timestamps included (``created_at``, ``finished_at``, event ``at``), stays:
under the simulated clock (``stack/clock.py``) those are the replay's own instants and must repeat.

:func:`compare_runs` returns the differences as JSON paths. Callers print paths, never values: the
values of an owner replay are owner data (lab ``AGENTS.md``, Privacy). ``scenario run --repeat`` calls
:func:`compare_runs` with :data:`SCENARIO_ARTIFACTS` on each repeat's directory (``scenario/verdict.py``).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Iterator, Mapping, Optional, Sequence

# Dropped at any depth in every artifact: host measurements, never product inputs.
WALL_CLOCK_FIELDS: frozenset[str] = frozenset(
    {
        'seconds',  # v3 event / chain conversation / driver durations (time.monotonic)
        'barrier_seconds',
        'export_seconds',
        'timings',  # per-phase durations (time.perf_counter)
        'window',  # chain driver real_now() window per conversation
        'stored_at',  # stage cache write time (store.py)
        'ms',  # LLM proxy call latency
        'cache_hit',  # the second run of a day hits the proxy cache; the answer is the same
        'late_monotonic_reads',  # clock diagnostic (stack/clock.py); its warning line is compared
    }
)

# Dropped (or replaced) at any depth: identifiers drawn from a random source by the lab itself.
VOLATILE_FIELDS: Mapping[str, str] = {
    'llm_call_ids': 'count',  # proxy call ids are secrets.token_hex: compare how many, not which
    'run_id': 'drop',
}


@dataclass(frozen=True)
class Artifact:
    """One semantic artifact: a file (or glob) under the run directory and how to read it."""

    pattern: str
    drop: frozenset[str] = frozenset()  # extra fields dropped at any depth in this artifact only
    unordered: bool = False  # JSONL rows written by concurrent workers: compare as a multiset
    optional: bool = True  # absent from both runs is fine; present in only one is a difference


ARTIFACTS: tuple[Artifact, ...] = (
    Artifact('conversations/*.json', optional=False),
    Artifact('chain.json'),
    Artifact('v3_driver.json'),
    Artifact('v3_recordings.json'),
    Artifact('v3_tasks.jsonl'),
    Artifact('notifications.jsonl', unordered=True),
    Artifact('sinks_telemetry.jsonl', unordered=True),
    Artifact('day.json'),
    Artifact('baseline.json'),
    # Prompt and answer per call. ``at`` is the proxy's real receive time; ``id`` is random; spend is
    # bookkeeping (a cache hit on the second run costs nothing and records what the first one paid).
    Artifact('llm_calls.jsonl', drop=frozenset({'at', 'id', 'usd', 'recorded_usd'}), unordered=True),
    # Orchestrator decisions are stamped with real time (``utc_iso``); the decision itself is semantic.
    Artifact('decisions.jsonl', drop=frozenset({'at'}), unordered=True),
)

# A scenario run directory (``scenario run --repeat``, ``scenario/verdict.py``): the same rules applied to
# the files one scenario run writes, so a repeat and a day replay agree on what "the same" means.
SCENARIO_ARTIFACTS: tuple[Artifact, ...] = (
    # ``log`` is the path of this run's own error log (it names the run directory), not a product output.
    Artifact('result.json', drop=frozenset({'log'}), optional=False),
    # The product's Home route bodies (scenario/home.py). ``updated_at`` is the Firestore document's
    # ``update_time`` (database/conversations.py ``document_data_with_revision``): the emulator's real wall
    # clock at the write, not the lab clock, so it differs on every run (seen with --repeat 3, 2026-11-25).
    Artifact('home.json', drop=frozenset({'updated_at'})),
    Artifact('v3_tasks.jsonl'),
    Artifact('notifications.jsonl', unordered=True),
    Artifact('sinks_telemetry.jsonl', unordered=True),
    Artifact('decisions.jsonl', drop=frozenset({'at'}), unordered=True),
)

_UUID4 = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b')


@dataclass
class Difference:
    artifact: str
    path: str
    kind: str  # changed | only_a | only_b | missing_file

    def __str__(self) -> str:
        return f'{self.artifact} {self.path} ({self.kind})'


@dataclass
class Comparison:
    differences: list[Difference] = field(default_factory=list)
    compared: list[str] = field(default_factory=list)

    @property
    def same(self) -> bool:
        return not self.differences

    def as_dict(self, limit: int = 200) -> dict[str, Any]:
        """Paths only: safe to print for an owner replay."""
        return {
            'same': self.same,
            'compared': self.compared,
            'differences': len(self.differences),
            'paths': [str(d) for d in self.differences[:limit]],
        }


class _Renamer:
    """Rename random UUIDs to ordinals in first-seen order, across all artifacts of one run."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def __call__(self, text: str) -> str:
        def one(match: re.Match[str]) -> str:
            value = match.group(0)
            if value not in self.names:
                self.names[value] = f'uuid4#{len(self.names) + 1}'
            return self.names[value]

        return _UUID4.sub(one, text)


def canonical(value: Any, *, drop: Iterable[str] = (), rename: Optional[_Renamer] = None) -> Any:
    """``value`` with wall-clock and volatile fields removed and random UUIDs renamed.

    ``drop`` adds to :data:`WALL_CLOCK_FIELDS`. Dict keys are visited sorted, so renaming is stable.
    """
    dropped = WALL_CLOCK_FIELDS | frozenset(drop)
    rename = rename or _Renamer()

    def walk(node: Any) -> Any:
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for key in sorted(node, key=str):
                if key in dropped:
                    continue
                volatile = VOLATILE_FIELDS.get(key)
                if volatile == 'drop':
                    continue
                if volatile == 'count':
                    out[rename(str(key))] = len(node[key] or [])
                    continue
                out[rename(str(key))] = walk(node[key])
            return out
        if isinstance(node, (list, tuple)):
            return [walk(item) for item in node]
        if isinstance(node, str):
            return rename(node)
        return node

    return walk(value)


def semantic_diff(a: Any, b: Any, path: str = '$') -> Iterator[tuple[str, str]]:
    """Yield ``(json_path, kind)`` for every place two canonical values differ."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        for key in sorted(set(a) | set(b), key=str):
            child = f'{path}.{key}'
            if key not in b:
                yield child, 'only_a'
            elif key not in a:
                yield child, 'only_b'
            else:
                yield from semantic_diff(a[key], b[key], child)
        return
    if isinstance(a, list) and isinstance(b, list):
        for index in range(max(len(a), len(b))):
            child = f'{path}[{index}]'
            if index >= len(b):
                yield child, 'only_a'
            elif index >= len(a):
                yield child, 'only_b'
            else:
                yield from semantic_diff(a[index], b[index], child)
        return
    if a != b:
        yield path, 'changed'


def _read(path: Path) -> Any:
    if path.suffix == '.jsonl':
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    return json.loads(path.read_text(encoding='utf-8'))


def _id_blind_key(row: Any) -> str:
    return _UUID4.sub('<uuid4>', json.dumps(row, sort_keys=True, default=str))


def load_semantic(run_dir: Path, artifacts: Sequence[Artifact] = ARTIFACTS) -> dict[str, Any]:
    """Every semantic artifact of one run directory, canonical, keyed by its relative path."""
    run_dir = Path(run_dir)
    rename = _Renamer()
    out: dict[str, Any] = {}
    for artifact in artifacts:
        for path in sorted(run_dir.glob(artifact.pattern)):
            raw = _read(path)
            if artifact.unordered and isinstance(raw, list):
                # Order rows with their random ids masked first, so the ordinal each id gets does not depend on
                # write order (two runs writing the same rows in a different order compare equal).
                raw = sorted(raw, key=_id_blind_key)
            value = canonical(raw, drop=artifact.drop, rename=rename)
            if artifact.unordered and isinstance(value, list):
                value = sorted(value, key=lambda row: json.dumps(row, sort_keys=True))
            out[str(path.relative_to(run_dir))] = value
    return out


def compare_runs(a: Path, b: Path, artifacts: Sequence[Artifact] = ARTIFACTS) -> Comparison:
    left, right = load_semantic(a, artifacts), load_semantic(b, artifacts)
    result = Comparison(compared=sorted(set(left) | set(right)))
    for name in result.compared:
        if name not in right:
            result.differences.append(Difference(name, '$', 'only_a'))
        elif name not in left:
            result.differences.append(Difference(name, '$', 'only_b'))
        else:
            result.differences.extend(Difference(name, p, k) for p, k in semantic_diff(left[name], right[name]))
    for artifact in artifacts:
        if not artifact.optional and not any(n for n in result.compared if Path(n).match(artifact.pattern)):
            result.differences.append(Difference(artifact.pattern, '$', 'missing_file'))
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.determinism')
    parser.add_argument('runs', nargs='+', help='two or more run directories; each is compared with the first')
    parser.add_argument('--limit', type=int, default=200, help='paths to print per pair')
    args = parser.parse_args(argv)
    if len(args.runs) < 2:
        parser.error('give at least two run directories')
    first = Path(args.runs[0])
    report = {str(other): compare_runs(first, Path(other)).as_dict(args.limit) for other in args.runs[1:]}
    print(json.dumps({'reference': str(first), 'pairs': report}, indent=1))
    return 0 if all(r['same'] for r in report.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
