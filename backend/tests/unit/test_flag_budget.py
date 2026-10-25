"""Flag budget: the transcription pipeline's env surface may not grow unowned (ADR 0006).

The pipeline-architecture review (2026-10-25, section 07) found 308 pipeline env
names and 52 default-off gates, accumulated without owners or expiry. This test
inventories every literal env name read (``os.getenv`` / ``os.environ``; module
constants resolved, via ``config.policy.guard.env_reads``) under ``SCOPE`` and
compares it to ``config/flag_budget.json``.

Each allowlist entry is one of:

- ``{"seeded": "2026-10-25"}``: present when the budget was set;
- ``{"replaces": "OLD_NAME"}``: takes the slot of a name removed from the
  surface in the same change (the budget holds);
- ``{"owner": ..., "review_by": "YYYY-MM-DD"}``: an explicit exception above the
  budget. It fails once ``review_by`` has passed: renew it or delete the flag.

A name that leaves the surface moves to the append-only ``retired`` ledger as
``{"on": "YYYY-MM-DD", "replaced_by": "NEW" | null}``. A replacement is valid
only when the retired entry names it, so a slot given up in an earlier change
(``replaced_by: null``) cannot be reclaimed later. ``budget`` must equal the
number of seeded + replacement entries, so a removal without a replacement
lowers the budget in the same change, and it can never exceed ``SEED_BUDGET``. Names read only through helpers (``serving_for``, kill-switch
registry lookups) or computed at runtime are not counted; the batch-stage env
ratchet covers dynamic reads under ``utils/batch_pipeline``.

Print today's inventory::

    cd backend && python tests/unit/test_flag_budget.py
"""

from __future__ import annotations

import datetime
import functools
import json
import sys
from pathlib import Path

import pytest

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.policy.guard import env_reads

BACKEND_DIR = Path(__file__).resolve().parents[2]
BUDGET_PATH = BACKEND_DIR / 'config' / 'flag_budget.json'
SEED_BUDGET = 170  # 2026-10-25 seed; lower it when the surface shrinks, never raise it.

SCOPE = (
    'utils/batch_pipeline/**/*.py',
    'diarizer/batch_pipeline*.py',
    'config/batch_pipeline*.py',
    'utils/sync/**/*.py',
    'utils/stt/**/*.py',
    'config/policy/**/*.py',
    'config/prerecorded_*.py',
    'config/live_stt_*.py',
    'config/transcription_final_pass.py',
)


@functools.lru_cache(maxsize=None)
def _scan_pattern(backend: Path, pattern: str) -> tuple[tuple[str, str], ...]:
    """(name, file) pairs for one scope pattern; cached so the per-pattern tests pay the parse once."""
    pairs = set()
    for path in backend.glob(pattern):
        source = path.read_text(encoding='utf-8')
        # Every env read names getenv or environ somewhere (aliases included); skip the parse otherwise.
        if 'getenv' not in source and 'environ' not in source:
            continue
        relative = path.relative_to(backend).as_posix()
        pairs.update((name, relative) for name in env_reads(source) if isinstance(name, str))
    return tuple(sorted(pairs))


def scan(backend: Path = BACKEND_DIR, patterns: tuple[str, ...] = SCOPE) -> dict[str, list[str]]:
    """Map each literal env name read in scope to the files that read it."""
    found: dict[str, set[str]] = {}
    for pattern in patterns:
        for name, relative in _scan_pattern(backend, pattern):
            found.setdefault(name, set()).add(relative)
    return {name: sorted(paths) for name, paths in sorted(found.items())}


def unlisted(read: dict[str, list[str]], names: dict[str, dict]) -> list[str]:
    return [
        f'{name} (read in {", ".join(read[name])}) is not in config/flag_budget.json: remove another name and '
        f'add {{"replaces": "<OLD>"}}, or add {{"owner": ..., "review_by": "YYYY-MM-DD"}}'
        for name in sorted(set(read) - set(names))
    ]


def problems(read: dict[str, list[str]], data: dict, today: datetime.date) -> list[str]:
    names: dict[str, dict] = data['names']
    retired: dict[str, dict] = data.get('retired', {})
    out = unlisted(read, names)
    for name in sorted(set(names) - set(read)):
        out.append(
            f'{name} is no longer read in scope: move it to "retired" as {{"on": "YYYY-MM-DD", "replaced_by": null}} '
            f'and lower "budget", or name its replacement, in the same change'
        )
    for old, entry in sorted(retired.items()):
        if old in names or old in read:
            out.append(f'{old} is retired but still on the surface')
        new = entry.get('replaced_by')
        if new is not None and names.get(new, {}).get('replaces') != old and new not in retired:
            out.append(f'retired {old} names replacement {new}, which has no {{"replaces": "{old}"}} entry')
    slots = 0
    for name, entry in sorted(names.items()):
        if 'seeded' in entry:
            slots += 1
        elif 'replaces' in entry:
            slots += 1
            old = entry['replaces']
            if old in names or old in read:
                out.append(f'{name} replaces {old}, which is still on the surface')
            elif retired.get(old, {}).get('replaced_by') != name:
                out.append(
                    f'{name} replaces {old}, but "retired" does not record {old} as replaced_by {name}; '
                    f'a slot can only transfer in the change that removes the old name'
                )
        else:
            owner = str(entry.get('owner', '')).strip()
            try:
                review_by = datetime.date.fromisoformat(entry.get('review_by', ''))
            except (TypeError, ValueError):
                review_by = None
            if not owner or review_by is None:
                out.append(f'{name} is above the budget and needs an "owner" and a "review_by" date')
            elif review_by < today:
                out.append(f'{name} passed review_by {review_by} ({owner}): renew it with a reason or delete the flag')
    budget = data['budget']
    if budget > SEED_BUDGET:
        out.append(f'budget {budget} exceeds the seeded budget {SEED_BUDGET}; new names need an owner and review_by')
    if slots != budget:
        out.append(f'budget is {budget} but {slots} seeded/replacement entries remain; set "budget" to {slots}')
    return out


def _load() -> dict:
    return json.loads(BUDGET_PATH.read_text(encoding='utf-8'))


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


@pytest.mark.parametrize('pattern', SCOPE)
def test_scoped_env_reads_are_in_the_budget(pattern):
    found = unlisted(scan(patterns=(pattern,)), _load()['names'])
    assert not found, 'Flag budget (backend/docs/adr/0006-pipeline-flag-budget.md):\n' + '\n'.join(found)


def test_pipeline_env_surface_holds_its_budget():
    # Runs after the per-pattern tests, so scan() reuses their cached parses.
    found = problems(scan(), _load(), _today())
    assert not found, 'Flag budget (backend/docs/adr/0006-pipeline-flag-budget.md):\n' + '\n'.join(found)


def test_budget_file_declares_scope_and_count():
    data = _load()
    assert tuple(data['scope']) == SCOPE
    assert data['count'] == len(data['names'])
    assert isinstance(data['retired'], dict)


def _data(retired=None, **names):
    slots = sum(1 for entry in names.values() if 'seeded' in entry or 'replaces' in entry)
    return {'budget': slots, 'names': names, 'retired': retired or {}}


SEEDED = {'seeded': '2026-10-25'}
TODAY = datetime.date(2026, 10, 25)


def test_new_name_fails_unless_owned_or_swapped():
    read = {'A': ['x.py'], 'ZZ_FAKE': ['y.py']}
    assert any(p.startswith('ZZ_FAKE ') for p in problems(read, _data(A=SEEDED), TODAY))
    owned = {'owner': 'batch record lane', 'review_by': '2026-11-15'}
    assert problems(read, _data(A=SEEDED, ZZ_FAKE=owned), TODAY) == []
    swapped = {'ZZ_FAKE': ['y.py']}
    ledger = {'A': {'on': '2026-10-26', 'replaced_by': 'ZZ_FAKE'}}
    assert problems(swapped, _data(retired=ledger, ZZ_FAKE={'replaces': 'A'}), TODAY) == []


def test_a_slot_retired_earlier_cannot_be_reclaimed():
    # Luna r1 P2: after A left with no replacement (budget lowered), a later change may not add
    # {"replaces": "A"} and raise the budget back.
    read = {'B': ['x.py'], 'NEW': ['y.py']}
    ledger = {'A': {'on': '2026-10-26', 'replaced_by': None}}
    found = problems(read, _data(retired=ledger, B=SEEDED, NEW={'replaces': 'A'}), TODAY)
    assert found == [
        'NEW replaces A, but "retired" does not record A as replaced_by NEW; '
        'a slot can only transfer in the change that removes the old name'
    ]
    unrecorded = problems(read, _data(B=SEEDED, NEW={'replaces': 'A'}), TODAY)
    assert unrecorded and 'does not record A' in unrecorded[0]


def test_retired_ledger_stays_consistent():
    read = {'A': ['x.py']}
    assert problems(read, _data(retired={'A': {'on': '2026-10-26', 'replaced_by': None}}, A=SEEDED), TODAY)[0] == (
        'A is retired but still on the surface'
    )
    dangling = problems({}, _data(retired={'A': {'on': '2026-10-26', 'replaced_by': 'GONE'}}), TODAY)
    assert dangling == ['retired A names replacement GONE, which has no {"replaces": "A"} entry']


def test_removal_must_lower_the_budget():
    data = {'budget': 2, 'names': {'A': SEEDED}}
    assert problems({'A': ['x.py']}, data, TODAY) == [
        'budget is 2 but 1 seeded/replacement entries remain; set "budget" to 1'
    ]
    stale = problems({}, _data(A=SEEDED), TODAY)
    assert stale[0].startswith('A is no longer read in scope')


def test_exception_needs_owner_and_unexpired_review_by():
    read = {'B': ['x.py']}
    assert problems(read, _data(B={'owner': 'sync lane'}), TODAY)
    assert problems(read, _data(B={'review_by': '2026-12-01'}), TODAY)
    expired = problems(read, _data(B={'owner': 'sync lane', 'review_by': '2026-10-24'}), TODAY)
    assert expired and 'passed review_by' in expired[0]


def test_replacement_must_name_a_removed_name():
    read = {'A': ['x.py'], 'B': ['y.py']}
    found = problems(read, {'budget': 2, 'names': {'A': SEEDED, 'B': {'replaces': 'A'}}}, TODAY)
    assert found == ['B replaces A, which is still on the surface']


def test_budget_cannot_be_raised_past_the_seed():
    names = {f'N{i}': SEEDED for i in range(SEED_BUDGET + 1)}
    read = {name: ['x.py'] for name in names}
    assert any('exceeds the seeded budget' in p for p in problems(read, _data(**names), TODAY))


def test_scanner_resolves_aliases_and_module_constants(tmp_path):
    module = tmp_path / 'utils' / 'sync' / 'probe.py'
    module.parent.mkdir(parents=True)
    module.write_text(
        'import os\n'
        'from os import environ as env\n'
        'FLAG = "ZZ_CONST"\n'
        'a = os.getenv("ZZ_FAKE")\n'
        'b = env.get(FLAG)\n'
        'c = os.environ["ZZ_SUBSCRIPT"]\n'
        'd = os.getenv(key="ZZ_KEYWORD")\n'
        'e = env.get(key="ZZ_KEYWORD_GET", default="")\n'
    )
    assert scan(tmp_path) == {
        'ZZ_CONST': ['utils/sync/probe.py'],
        'ZZ_FAKE': ['utils/sync/probe.py'],
        'ZZ_KEYWORD': ['utils/sync/probe.py'],
        'ZZ_KEYWORD_GET': ['utils/sync/probe.py'],
        'ZZ_SUBSCRIPT': ['utils/sync/probe.py'],
    }


def test_changed_file_ci_selects_the_budget_for_every_scoped_path():
    from scripts.select_backend_unit_tests import FLAG_BUDGET_PREFIXES

    for pattern in SCOPE:
        stem = 'backend/' + pattern.split('*', 1)[0]
        assert stem.startswith(FLAG_BUDGET_PREFIXES), pattern
    assert 'backend/config/flag_budget.json'.startswith(FLAG_BUDGET_PREFIXES)


if __name__ == '__main__':
    inventory = scan()
    for env_name, files in inventory.items():
        print(f'{env_name}\t{", ".join(files)}')
    print(f'{len(inventory)} names in scope', file=sys.stderr)
