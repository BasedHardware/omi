"""`scripts/` is excluded from the boundary guards — except the modules the runtime imports (BACKLOG L12).

ADR-0023 excluded `backend/scripts/` from all four boundary guards on the premise that it is "one-off
operational tooling, not deployed runtime". Measured, that premise is FALSE for two of its 129 modules:

    scripts/enrich_historical_memory_graph.py  <- utils/memory/canonical_short_term_maintenance_cron.py
    scripts/reconcile_mongo_indexes.py         <- main.py   (called at boot)

So two runtime modules were unscanned by every boundary guard, and one of them builds a raw
`firestore.Client`. The guards now scan those two explicitly, via a `RUNTIME_REACHABLE_SCRIPTS` tuple.

A hand-written tuple is a fact about the import graph, and facts about the import graph rot. This
recomputes it from the source and requires the four guards to agree with reality — so a new
`from scripts.x import ...` in runtime code fails HERE, with the name of the importer, instead of quietly
widening the blind spot again.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPOSITORY = BACKEND.parent

GUARDS = (
    'check_oss_firestore_persistence_boundary.py',
    'check_oss_auth_boundary.py',
    'check_oss_vector_store_boundary.py',
    'check_oss_object_store_boundary.py',
)

# Directories that are not deployed runtime, so an import of `scripts.` from inside them does not make a
# script runtime-reachable. Mirrors the guards' own exclusions.
NOT_RUNTIME = ('scripts/', 'tests/', 'testing/', 'agent-proxy/')

# Build scratch, which is not source at all. The walk below said "computed from the source" and then
# read every .py under backend/ — including `backend/.venv`, which the CI job's own earlier step
# creates before this test runs. Scanning a virtualenv is both wrong (a dependency importing something
# named `scripts.` is not our runtime) and expensive: it took each of this file's six tests past the
# 1.00s fast-unit ceiling at ~7s of CPU apiece. Locally it stayed fast only because no venv was there.
NOT_SOURCE = ('.venv', '.openapi-venv', 'node_modules', '__pycache__', '.pytest_cache', '_temp')


@functools.lru_cache(maxsize=None)
def _runtime_reachable() -> dict[str, set[str]]:
    """{scripts/<module>.py: {importers}} computed from the source.

    Cached: the answer is a property of the tree, and every test in this file asks for it. Recomputing
    the walk six times was the other half of the cost. Callers only read the result.
    """
    reachable: dict[str, set[str]] = {}
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(NOT_RUNTIME) or any(part in NOT_SOURCE for part in path.parts):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for module in re.findall(r'(?:from|import)\s+scripts\.([A-Za-z_][A-Za-z0-9_]*)', text):
            reachable.setdefault(f'scripts/{module}.py', set()).add(relative)
    return reachable


def _declared(guard: str) -> tuple[str, ...]:
    text = (REPOSITORY / '.github' / 'scripts' / guard).read_text(encoding='utf-8')
    match = re.search(r'RUNTIME_REACHABLE_SCRIPTS = \(([^)]*)\)', text, re.S)
    assert match, f'{guard} no longer declares RUNTIME_REACHABLE_SCRIPTS'
    return tuple(sorted(re.findall(r"'([^']+)'", match.group(1))))


def test_the_reachable_set_is_what_the_source_says():
    reachable = _runtime_reachable()

    assert reachable, 'the scan found nothing — the pattern or the tree moved'
    assert sorted(reachable) == [
        'scripts/enrich_historical_memory_graph.py',
        'scripts/reconcile_mongo_indexes.py',
    ], f'the runtime import graph changed: {" · ".join(f"{k} <- {sorted(v)}" for k, v in sorted(reachable.items()))}'


@pytest.mark.parametrize('guard', GUARDS)
def test_every_boundary_guard_scans_exactly_those(guard):
    assert _declared(guard) == tuple(
        sorted(_runtime_reachable())
    ), f'{guard} scans a different set of scripts than the runtime actually imports'


def test_the_guards_still_exclude_the_rest_of_scripts():
    """The exception must stay an exception: 129 modules in there, and the other 127 really are CLI."""
    total = len(list((BACKEND / 'scripts').glob('*.py')))
    assert total > 100, 'sanity: scripts/ should still be a large directory of one-off tooling'
    assert len(_runtime_reachable()) < 5, 'if runtime imports many scripts, the exclusion is the wrong shape'
