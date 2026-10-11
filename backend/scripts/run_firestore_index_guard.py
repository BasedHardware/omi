#!/usr/bin/env python3
"""Run only the hermetic Firestore index guard for canonical release checks."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from select_backend_unit_tests import BACKEND_DIR, FIRESTORE_INDEX_GUARD_TESTS

GUIDE = '.github/agent-docs/firestore-queries-and-indexes.md'


def main() -> int:
    started = time.monotonic()
    state = BACKEND_DIR.parent / '.agent-brief' / 'firestore-index-guard'
    try:
        state.mkdir(parents=True, exist_ok=True)
        version = (BACKEND_DIR / '.python-version').read_text().strip()
        venv = state / f'venv-{version}'
        python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            subprocess.run(['uv', 'venv', '--python', version, str(venv)], check=True)
        subprocess.run(
            ['uv', 'pip', 'sync', '--python', str(python), str(BACKEND_DIR / 'firestore-guard-requirements.txt')],
            check=True,
        )
        missing = [test for test in FIRESTORE_INDEX_GUARD_TESTS if not (BACKEND_DIR / test).is_file()]
        if missing:
            raise ValueError(f'missing guard tests: {missing}')
        test_list = state / 'tests.txt'
        test_list.write_text('\n'.join(FIRESTORE_INDEX_GUARD_TESTS) + '\n', encoding='utf-8')
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(
            f'FAIL: Firestore index guard environment setup failed: {exc}. '
            f'Restore uv/Python and the pinned guard requirements, then rerun. '
            f'No release proof is issued; do not skip this check. See {GUIDE}.',
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env.update(
        PYTHON=str(python),
        BACKEND_UNIT_TEST_FILE_LIST=str(test_list),
        BACKEND_PYTEST_FILE_ISOLATION='1',
        BACKEND_PYTEST_PARALLEL_SESSION='0',
        BACKEND_PYTEST_WORKERS='2',
        # Include the digest-pinned skip/covered-by sentinel even though the
        # general backend PR lane marks it slow. It is part of this guard.
        BACKEND_PYTEST_MARK_EXPR='not integration',
        # This release check gates index correctness, not machine-dependent CPU
        # speed. Keep advisory timings; the CI inventory budgets the cold run.
        BACKEND_FAST_UNIT_WARN_SECONDS='0.1',
        BACKEND_FAST_UNIT_FAIL_SECONDS='inf',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        PYTEST_PLUGINS='pytest_asyncio.plugin',
        PYTEST_ADDOPTS='',
    )
    result = subprocess.run(['bash', 'test.sh'], cwd=BACKEND_DIR, env=env, check=False)
    elapsed = time.monotonic() - started
    if result.returncode:
        print(
            'FAIL: Firestore index guard did not pass. Declare the required index in '
            'backend/database/firestore_index_registry.py and regenerate firestore.indexes.json '
            'in the same PR; update the runtime driver/caller witness for a changed query. '
            f'See {GUIDE}. If pytest reports an import/collection error, repair the guard '
            'environment instead; no release proof is issued.',
            file=sys.stderr,
        )
        return 1
    print(
        f'Firestore index guard passed ({len(FIRESTORE_INDEX_GUARD_TESTS)} files; cold setup + tests {elapsed:.2f}s).'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
