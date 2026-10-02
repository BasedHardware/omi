from pathlib import Path
import subprocess

from testing.shell import bash_command

ROOT = Path(__file__).resolve().parents[3]
CHANGED_FILES = ROOT / 'scripts/changed-files'


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


def _init_hermetic_repo(repo: Path) -> None:
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'ci@example.com'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'CI'], cwd=repo, check=True)
    # Hermetic to developer/system git config (system /etc/gitconfig can force
    # commit signing, and an orb-installed ~/.config/git/hooks dispatcher has
    # no scripts/<hook> to dispatch to in a temp fixture repo): a commit or
    # merge here must never fail on that config, and it is not under test.
    subprocess.run(['git', 'config', 'core.hooksPath', '/nonexistent-omi-test-hooks'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=repo, check=True)


def _commit(repo: Path, message: str) -> str:
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', message], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    return _git(repo, 'rev-parse', 'HEAD')


def test_changed_files_reports_delete_rename_and_file_type_change(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _init_hermetic_repo(repo)

    risky = repo / 'backend/desktop_backend.py'
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

    changed = set(
        subprocess.check_output(
            bash_command(CHANGED_FILES, base, head, cwd=ROOT),
            cwd=repo,
            text=True,
        ).splitlines()
    )

    assert changed == {
        'backend/routers/deleted.py',
        'backend/routers/changed_type.py',
        'backend/desktop_backend.py',
        'docs/risky.rs',
    }


def test_changed_files_helper_is_not_hidden_by_repository_ignore_rules():
    result = subprocess.run(
        ['git', 'check-ignore', '--no-index', '--quiet', 'scripts/changed-files'],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 1


def test_changed_files_three_dot_agrees_on_both_merge_parent_orders(tmp_path):
    """GitHub's merge ref has BASE as first parent; a local merge has the branch.

    First-parent two-dot therefore disagrees. Three-dot against the live base
    must return the same PR files on the branch head and on both merges.
    """
    repo = tmp_path / 'repo'
    repo.mkdir()
    _init_hermetic_repo(repo)

    (repo / 'base.txt').write_text('base\n')
    _commit(repo, 'base')
    subprocess.run(['git', 'branch', '-M', 'main'], cwd=repo, check=True)

    subprocess.run(['git', 'switch', '-q', '-c', 'feature'], cwd=repo, check=True)
    (repo / 'feature.txt').write_text('feature\n')
    _commit(repo, 'feature')
    feature = _git(repo, 'rev-parse', 'HEAD')

    subprocess.run(['git', 'switch', '-q', 'main'], cwd=repo, check=True)
    (repo / 'main.txt').write_text('main\n')
    _commit(repo, 'main')
    main = _git(repo, 'rev-parse', 'HEAD')

    def helper_at(sha: str) -> set[str]:
        subprocess.run(['git', 'switch', '-q', '--detach', sha], cwd=repo, check=True)
        return set(
            subprocess.check_output(
                bash_command(CHANGED_FILES, 'main...HEAD', cwd=ROOT),
                cwd=repo,
                text=True,
            ).splitlines()
        )

    branch_head = helper_at(feature)
    subprocess.run(['git', 'switch', '-q', '--detach', feature], cwd=repo, check=True)
    subprocess.run(['git', 'merge', '--no-ff', '-q', '--no-edit', main], cwd=repo, check=True)
    branch_first = helper_at(_git(repo, 'rev-parse', 'HEAD'))
    subprocess.run(['git', 'switch', '-q', '--detach', main], cwd=repo, check=True)
    subprocess.run(['git', 'merge', '--no-ff', '-q', '--no-edit', feature], cwd=repo, check=True)
    base_first = helper_at(_git(repo, 'rev-parse', 'HEAD'))

    assert branch_head == {'feature.txt'}
    assert branch_head == branch_first == base_first
