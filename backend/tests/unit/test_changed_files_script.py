import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CHANGED_FILES = ROOT / 'scripts/changed-files'


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


def _find_git_bash(git_exec_path: Path) -> Path:
    for parent in git_exec_path.parents:
        for relative_path in ('bin/bash.exe', 'usr/bin/bash.exe'):
            candidate = parent / relative_path
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f'Git Bash was not found above {git_exec_path}')


def _bash() -> str:
    if os.name != 'nt':
        return 'bash'
    return str(_find_git_bash(Path(_git(ROOT, '--exec-path'))))


def _commit(repo: Path, message: str) -> str:
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', message], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    return _git(repo, 'rev-parse', 'HEAD')


def test_changed_files_reports_delete_rename_and_file_type_change(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'ci@example.com'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'CI'], cwd=repo, check=True)

    risky = repo / 'desktop/macos/Backend-Rust/src/risky.rs'
    risky.parent.mkdir(parents=True)
    risky.write_text('pub fn risky() {}\n')
    deleted = repo / 'backend/routers/deleted.py'
    deleted.parent.mkdir(parents=True)
    deleted.write_text('VALUE = 1\n')
    changed_type = repo / 'backend/routers/changed_type.py'
    changed_type.write_text('target.py\n')
    base = _commit(repo, 'base')

    renamed = repo / 'docs/risky.rs'
    renamed.parent.mkdir()
    risky.rename(renamed)
    deleted.unlink()
    changed_type.unlink()
    changed_type.symlink_to('target.py')
    head = _commit(repo, 'move delete and change type')

    changed = set(subprocess.check_output([_bash(), str(CHANGED_FILES), base, head], cwd=repo, text=True).splitlines())

    assert changed == {
        'backend/routers/deleted.py',
        'backend/routers/changed_type.py',
        'desktop/macos/Backend-Rust/src/risky.rs',
        'docs/risky.rs',
    }


def test_changed_files_helper_is_not_hidden_by_repository_ignore_rules():
    result = subprocess.run(
        ['git', 'check-ignore', '--no-index', '--quiet', 'scripts/changed-files'],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 1


def test_git_bash_resolution_uses_the_git_installation(tmp_path):
    git_root = tmp_path / 'Git'
    git_exec_path = git_root / 'mingw64/libexec/git-core'
    git_exec_path.mkdir(parents=True)
    git_bash = git_root / 'bin/bash.exe'
    git_bash.parent.mkdir()
    git_bash.touch()

    assert _find_git_bash(git_exec_path) == git_bash
