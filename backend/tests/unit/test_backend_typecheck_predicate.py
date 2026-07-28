from __future__ import annotations

from pathlib import Path
import subprocess

PREDICATE = Path(__file__).resolve().parents[2] / 'scripts' / 'needs-typecheck.sh'


def _needs_typecheck(paths: list[str]) -> bool:
    result = subprocess.run(
        ['bash', str(PREDICATE)],
        input=''.join(f'{path}\n' for path in paths),
        text=True,
        check=False,
        capture_output=True,
    )
    assert result.returncode in {0, 1}, result.stderr
    return result.returncode == 0


def test_typecheck_predicate_accepts_every_typed_boundary_input():
    for path in (
        'backend/routers/users.py',
        'backend/pyrightconfig.json',
        'backend/scripts/typecheck.sh',
        'backend/scripts/needs-typecheck.sh',
        'backend/requirements.txt',
        'backend/pylock.toml',
        '.github/workflows/backend-unit-tests.yml',
        'scripts/pre-push',
    ):
        assert _needs_typecheck([path]), path


def test_typecheck_predicate_skips_unrelated_changed_paths():
    assert not _needs_typecheck(['docs/doc/developer/Contribution.mdx'])
    assert not _needs_typecheck(['backend/docs/test_isolation.md'])
